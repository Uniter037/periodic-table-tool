"""Headless acceptance: real spawn workers, saved pixels, and canvas hit geometry.

No Tk root is constructed; only the image display adapter is replaced for canvas
tests. Process/IPC/rendering/filesystem paths run without mocks.
"""
from io import BytesIO
import multiprocessing as mp
from pathlib import Path
import pickle
import time
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
from PIL import Image
import pytest

from core.imaging import rasterize, save_options
from core.jobs import RenderJob
from core.ptable import xy_bounds_for, CELL_STEP
from core.styles import STYLES
from ui.preview import PreviewCanvas


@pytest.fixture(scope="module")
def worker():
    job = RenderJob()
    yield job
    job.cancel()


def request(mode="preview", **overrides):
    style = dict(STYLES["custom"], kind="labels", font="DejaVu Sans",
                 figsize=(4, 2.5), dpi=100, bbox_tight=True,
                 highlight_bg="#e63f37", plain_bg="#eff1f3",
                 show_symbol=False, show_number=False, show_value=False)
    y = xy_bounds_for(style["layout"])[1] - CELL_STEP
    result = {"mode": mode, "style": style, "data": {"H": "sample"},
              "show_cbar": False, "format": "png", "title": "Crop test",
              "hit_map": {(0, y, 1, y + 1): "H"}}
    result.update(overrides)
    return result


def wait_terminal(job, timeout=30):
    messages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = job.poll()
        if message is not None:
            messages.append(message)
            if message[0] in ("done", "error") or (message[0] == "obsolete" and not job.active):
                return message, messages
        time.sleep(.01)
    pytest.fail(f"Worker timed out; active={job.active}; messages={messages}")


def run(job, task):
    job.start(task)
    terminal, messages = wait_terminal(job)
    assert terminal[0] == "done", messages
    assert not job.active
    return terminal[1]


def decode(png):
    with Image.open(BytesIO(png)) as image:
        return image.convert("RGBA")


def assert_red_cell(image, hits, symbol="H"):
    box = next(box for box, value in hits.items() if value == symbol)
    x0, y0, x1, y1 = box
    assert 0 <= x0 < x1 <= image.width
    assert 0 <= y0 < y1 <= image.height
    assert image.getpixel((int((x0 + x1) / 2), int((y0 + y1) / 2))) == (230, 63, 55, 255)


@pytest.mark.parametrize("tight,transparent,dpi", [
    (False, False, 100), (True, False, 100),
    (False, True, 100), (True, True, 100), (True, False, 72),
])
def test_spawn_export_preview_same_pixels_and_reuse(worker, tight, transparent, dpi):
    task = request("export")
    task["style"].update(bbox_tight=tight, transparent=transparent, dpi=dpi)
    exported = run(worker, task)
    process = worker.process
    assert process.pid != mp.current_process().pid
    assert process._start_method == "spawn"
    path, name = exported["files"][0]
    assert name == "periodic_table"
    export_png = Path(path).read_bytes()
    task["mode"] = "preview"
    preview = run(worker, task)
    assert worker.process is process and process.is_alive()
    assert not Path(path).exists()  # Finished export lifetime is documented.
    assert list(Path(worker.directory.name).iterdir()) == []
    with decode(export_png) as saved, decode(preview["png"]) as shown:
        np.testing.assert_array_equal(np.asarray(saved), np.asarray(shown))
        assert_red_cell(shown, preview["hits"])
        if transparent:
            assert shown.getpixel((0, 0))[3] == 0


@pytest.mark.parametrize("fmt,signature", [("svg", b"<?xml"), ("pdf", b"%PDF")])
def test_spawn_vector_exports(worker, fmt, signature):
    result = run(worker, request("export", format=fmt))
    path, _ = result["files"][0]
    assert Path(path).read_bytes().startswith(signature)


@pytest.mark.parametrize("orientation", ["vertical", "horizontal"])
def test_spawn_colorbar_crop_matches_preview(worker, orientation):
    task = request("export", data={"H": 0}, show_cbar=True)
    task["style"].update(kind="heatmap", figsize=(5, 3),
                         norm=("normalize", -1, 1), cbar_orientation=orientation)
    exported = run(worker, task)
    png = Path(exported["files"][0][0]).read_bytes()
    task["mode"] = "preview"
    packet = run(worker, task)
    with decode(png) as saved, decode(packet["png"]) as preview:
        np.testing.assert_array_equal(np.asarray(saved), np.asarray(preview))
        assert set(packet["hits"].values()) == {"H"}


def test_high_dpi_export_preserves_crop_and_preview_cap(worker):
    task = request("export")
    task["style"]["dpi"] = 300
    exported = run(worker, task)
    png = Path(exported["files"][0][0]).read_bytes()
    task["mode"] = "preview"
    packet = run(worker, task)
    with decode(png) as saved, decode(packet["png"]) as preview:
        assert abs(saved.width / 3 - preview.width) <= 1
        assert abs(saved.height / 3 - preview.height) <= 1
        # Compare the actual cell's position in both crops (font rasterization
        # can change a tight crop by a subpixel amount at a different DPI).
        pixels = np.asarray(saved)
        red_y, red_x = np.nonzero(np.all(pixels == [230, 63, 55, 255], axis=2))
        left, top, right, bottom = next(iter(packet["hits"]))
        assert abs((red_x.min() + red_x.max()) / 6 - (left + right) / 2) <= 1
        assert abs((red_y.min() + red_y.max()) / 6 - (top + bottom) / 2) <= 1
        assert_red_cell(preview, packet["hits"])


def test_latest_request_wins_and_is_snapshotted(worker):
    old = request("export")
    worker.start(old)
    process = worker.process
    root = Path(worker.directory.name)
    # Both superseded export and intermediate error must be invisible.
    worker.start({"mode": "invalid intermediate request"})
    latest = request()
    latest["hit_map"] = {box: "latest" for box in latest["hit_map"]}
    worker.start(latest)
    latest["hit_map"].clear()
    latest["data"].clear()
    latest["style"]["highlight_bg"] = "blue"
    terminal, messages = wait_terminal(worker)
    assert terminal[0] == "done", messages
    assert [message[0] for message in messages] == ["obsolete", "progress", "done"]
    with decode(terminal[1]["png"]) as image:
        assert_red_cell(image, terminal[1]["hits"], "latest")
    assert worker.process is process
    assert list(root.iterdir()) == []
    assert worker.poll() is None


def test_invalidate_drops_queued_request_during_debounce(worker):
    worker.start(request("export"))
    process = worker.process
    worker.start(request())
    worker.invalidate()
    terminal, messages = wait_terminal(worker)
    assert terminal == ("obsolete",)
    assert messages == [("obsolete",)]
    assert not worker.active and worker.pending is None
    assert list(Path(worker.directory.name).iterdir()) == []
    assert worker.poll() is None
    run(worker, request())
    assert worker.process is process


def test_obsolete_error_does_not_replace_latest_preview(worker):
    worker.start({"mode": "bad old request"})
    worker.invalidate()
    worker.start(request())
    terminal, messages = wait_terminal(worker)
    assert terminal[0] == "done", messages
    assert messages[0] == ("obsolete",)
    assert not any(message[0] == "error" for message in messages)


def test_partial_batch_error_cleanup_and_worker_recovery(worker):
    task = request("batch", items=[("first", {"H": "ok"}), ("bad", {"H": float("nan")})])
    worker.start(task)
    process = worker.process
    terminal, messages = wait_terminal(worker)
    assert terminal[0] == "error", messages
    assert ("progress", 1, 2) in messages  # First real output existed before failure.
    assert list(Path(worker.directory.name).iterdir()) == []
    assert not worker.active and worker.poll() is None
    run(worker, request())
    assert worker.process is process


def test_batch_without_unused_data_key_preserves_order_and_names(worker):
    task = request("batch", items=[("sample A", {"H": "one"}), ("sample B", {"He": "two"})])
    del task["data"]
    result = run(worker, task)
    assert [name for _, name in result["files"]] == ["sample A", "sample B"]
    paths = [Path(path) for path, _ in result["files"]]
    assert all(path.is_file() and path.stat().st_size > 0 for path in paths)
    run(worker, request())
    assert all(not path.exists() for path in paths)


def test_cancel_clears_running_pending_and_completed_exports():
    job = RenderJob()
    try:
        # Wait for a real first file, then cancel before accepting any result.
        task = request("batch", items=[(str(i), {"H": str(i)}) for i in range(20)])
        job.start(task)
        process = job.process
        root = Path(job.directory.name)
        deadline = time.monotonic() + 30
        while not list(root.rglob("*.png")) and time.monotonic() < deadline:
            time.sleep(.01)
        assert list(root.rglob("*.png")), "Expected at least one partial export"
        job.start(request())
        job.cancel()
        assert process._closed
        assert not root.exists()
        assert job.process is job.connection is job.directory is None
        assert not job.active and job.pending is None and job.poll() is None
        job.cancel()  # Idempotent, then restart via a fresh real spawn.
        result = run(job, request("export"))
        assert job.process is not process
        path = Path(result["files"][0][0])
        assert path.is_file()
        root = Path(job.directory.name)
        job.cancel()
        assert not path.exists() and not root.exists()
    finally:
        job.cancel()


@pytest.mark.parametrize("superseded", [False, True])
def test_crash_cleanup_once_and_latest_recovery(superseded):
    job = RenderJob()
    try:
        job.start(request("export"))
        root = Path(job.directory.name)
        process = job.process
        if superseded:
            job.start(request())
        process.terminate()
        process.join(timeout=5)
        terminal, messages = wait_terminal(job)
        assert not root.exists()
        if superseded:
            assert terminal[0] == "done", messages
            assert messages[0] == ("obsolete",)
            assert job.process is not process
        else:
            assert terminal[0] == "error"
            assert job.process is None and job.connection is None
            assert not job.active
            assert job.poll() is None
            run(job, request())
    finally:
        job.cancel()


def test_unpicklable_update_does_not_invalidate_valid_request(worker):
    worker.start(request())
    with pytest.raises((AttributeError, TypeError, pickle.PicklingError)):
        worker.start({"bad": lambda: None})
    terminal, messages = wait_terminal(worker)
    assert terminal[0] == "done", messages


def test_corrupt_result_cleans_staging_without_restarting(worker):
    worker.start(request("export"))
    process = worker.process
    result_file = worker._staging / "result.pkl"
    deadline = time.monotonic() + 30
    while not result_file.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    assert result_file.exists()
    # The worker publishes via atomic rename and closes before sending done.
    result_file.write_bytes(b"corrupt result")
    terminal, messages = wait_terminal(worker)
    assert terminal[0] == "error", messages
    assert "无法读取" in terminal[1]
    assert not worker.active and worker.poll() is None
    assert list(Path(worker.directory.name).iterdir()) == []
    run(worker, request())
    assert worker.process is process


def test_spawn_start_failure_cleans_handles_and_directory(monkeypatch):
    job = RenderJob()
    roots = []
    from core import jobs
    temporary_directory = jobs.tempfile.TemporaryDirectory

    def track_directory(**kwargs):
        directory = temporary_directory(**kwargs)
        roots.append(Path(directory.name))
        return directory

    def fail_start(self):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(jobs.tempfile, "TemporaryDirectory", track_directory)
    monkeypatch.setattr(mp.context.SpawnProcess, "start", fail_start)
    with pytest.raises(RuntimeError, match="spawn failed"):
        job.start(request())
    assert roots and not roots[0].exists()
    assert job.process is job.connection is job.directory is None
    assert not job.active and job.poll() is None
    job.cancel()


def test_queued_dispatch_failure_is_a_terminal_error(worker, monkeypatch):
    worker.start(request())
    worker.start(request())
    dispatch = worker._dispatch

    def fail(snapshot):
        worker.cancel()
        raise RuntimeError("queued dispatch failed")

    monkeypatch.setattr(worker, "_dispatch", fail)
    terminal, messages = wait_terminal(worker)
    assert terminal[0] == "error", messages
    assert "queued dispatch failed" in terminal[1]
    assert not worker.active and worker.poll() is None
    monkeypatch.setattr(worker, "_dispatch", dispatch)
    run(worker, request())


class Surface:
    """Only the Tk image sink is fake; rendering and canvas methods are real."""
    def __init__(self, size):
        self.size = size
        self.items = {}

    def winfo_width(self):
        return self.size[0]

    def winfo_height(self):
        return self.size[1]

    def coords(self, item, *coords):
        self.items[item] = coords

    def itemconfigure(self, item, **kw):
        self.items[(item, "image")] = kw["image"]


def canvas(monkeypatch, size=(603, 227)):
    # Bypass Frame.__init__; no Tcl interpreter or GUI is created.
    preview = PreviewCanvas.__new__(PreviewCanvas)
    preview.fig = preview.canvas = None
    preview.hit_map, preview._pixel_hits = {}, {}
    preview._source = preview._photo = preview._display_box = None
    preview.zoom, preview.pan = 1., [0, 0]
    preview._surface = Surface(size)
    preview._paper, preview._item = "paper", "image"
    monkeypatch.setattr("ui.preview.ImageTk.PhotoImage", lambda image, **kw: image.copy())
    return preview


@pytest.mark.parametrize("tight", [False, True])
@pytest.mark.parametrize("zoom,pan,size", [
    (1., [0, 0], (603, 227)), (2.35, [170, 60], (227, 603)),
    (.37, [-43, 67], (603, 227)),
])
def test_packet_hit_after_zoom_pan_and_resize(worker, monkeypatch, tight, zoom, pan, size):
    task = request()
    task["style"]["bbox_tight"] = tight
    packet = run(worker, task)
    preview = canvas(monkeypatch, size)
    clicked = []
    preview.on_click = clicked.append
    preview.show_packet(packet["png"], packet["hits"])
    preview.zoom, preview.pan = zoom, pan
    preview.resize()
    x0, y0, x1, y1 = next(iter(packet["hits"]))
    for new_size in (size, size[::-1]):
        preview._surface.size = new_size
        preview.resize()
        left, top, width, height = preview._display_box
        sw, sh = preview._source.size
        event = SimpleNamespace(
            x=left + (x0 + x1) / 2 * width / sw,
            y=top + (y0 + y1) / 2 * height / sh)
        assert 0 <= event.x < new_size[0] and 0 <= event.y < new_size[1]
        preview._on_surface_click(event)
        preview._on_surface_click(SimpleNamespace(x=left - 1, y=top - 1))
        # Blank lower right paper cannot become a hit after changing view.
        preview._on_surface_click(SimpleNamespace(x=left + width - .01, y=top + height - .01))
    assert clicked == ["H", "H"]
    preview._source.close()


@pytest.mark.parametrize("tight", [False, True])
def test_saved_crop_transform_hits_actual_pixels_and_clips_axes(tight):
    fig, ax = plt.subplots(figsize=(4, 2), dpi=91)
    try:
        ax.set(xlim=(0, 2), ylim=(0, 1))
        ax.add_patch(Rectangle((.3, .2), .6, .5, facecolor="#e63f37", linewidth=0))
        fig.suptitle("Title extending outside the axes crop")
        hit_map = {(.3, .2, .9, .7): "H", (2.1, 0, 4, 1): "outside"}
        source, hits = rasterize(fig, hit_map, tight)
        assert list(hits.values()) == ["H"]
        assert_red_cell(source, hits)
        pixels = np.asarray(source)
        red_y, red_x = np.nonzero(np.all(pixels == [230, 63, 55, 255], axis=2))
        left, top, right, bottom = next(iter(hits))
        assert abs(left - red_x.min()) <= 1
        assert abs(right - (red_x.max() + 1)) <= 1
        assert abs(top - red_y.min()) <= 1
        assert abs(bottom - (red_y.max() + 1)) <= 1
        with BytesIO() as stream:
            fig.savefig(stream, format="png", **save_options({"dpi": fig.dpi, "bbox_tight": tight}))
            with decode(stream.getvalue()) as exported:
                np.testing.assert_array_equal(np.asarray(source), np.asarray(exported))
        source.close()
    finally:
        plt.close(fig)


@pytest.mark.parametrize("packet", [False, True])
def test_display_failure_keeps_pixels_hits_and_owned_figure(monkeypatch, packet):
    preview = canvas(monkeypatch)
    old, new = plt.figure(), plt.figure()
    try:
        preview.show(old, {(0, 0, 1, 1): "old"})
        # An empty figure has no pixel hits; give the snapshot a unique sentinel.
        preview._pixel_hits = {(1, 2, 3, 4): "old"}
        attributes = ("fig", "canvas", "hit_map", "_source", "_pixel_hits", "_photo", "_display_box")
        before = tuple(getattr(preview, name) for name in attributes)

        def fail(*args, **kwargs):
            raise RuntimeError("display failure")

        monkeypatch.setattr(preview, "resize", fail)
        with pytest.raises(RuntimeError, match="display failure"):
            if packet:
                with BytesIO() as buffer:
                    Image.new("RGBA", (20, 10)).save(buffer, format="PNG")
                    preview.show_packet(buffer.getvalue(), {(0, 0, 1, 1): "new"})
            else:
                preview.show(new, {(0, 0, 1, 1): "new"})
        assert tuple(getattr(preview, name) for name in attributes) == before
        assert plt.fignum_exists(old.number)
        if not packet:
            assert not plt.fignum_exists(new.number)
        with pytest.raises(Exception):
            preview.show_packet(b"not an image", {})
        assert tuple(getattr(preview, name) for name in attributes) == before
    finally:
        plt.close(old)
        plt.close(new)
        if preview._source:
            preview._source.close()


def test_packet_releases_old_figure_and_legacy_hit_map(worker, monkeypatch):
    preview = canvas(monkeypatch)
    fig = plt.figure()
    try:
        preview.show(fig, {(0, 0, 1, 1): "old"})
        packet = run(worker, request())
        preview.show_packet(packet["png"], packet["hits"])
        assert not plt.fignum_exists(fig.number)
        assert preview.fig is preview.canvas is None
        assert preview.hit_map == {} and preview.hit_test(.5, .5) is None
        assert preview._pixel_hits == packet["hits"]
    finally:
        plt.close(fig)
        if preview._source:
            preview._source.close()
