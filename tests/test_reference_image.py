"""Reference decoding, resource isolation, and nonmodal snapshot contract."""
import hashlib
import sys
from io import BytesIO
from pathlib import Path
import socket
import base64
import tkinter as tk
from tkinter import ttk

import pytest
from PIL import Image

from core import reference_image as reference
from ui.reference_view import open_reference_window, _ImagePane


SVG11_DOCTYPE = ('<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n'
                 '  "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">')


@pytest.fixture
def matplotlib_svg(tmp_path):
    from matplotlib.figure import Figure
    figure = Figure(figsize=(3, 2))
    axes = figure.subplots()
    axes.plot([0, 1, 2], [2, 0, 1], label="NiTi")
    axes.set_title("Reference")
    axes.legend()
    buffer = BytesIO()
    figure.savefig(buffer, format="svg")
    path = tmp_path / "matplotlib.svg"
    path.write_bytes(buffer.getvalue())
    assert SVG11_DOCTYPE.encode() in path.read_bytes()
    return path


@pytest.mark.parametrize("doctype", [SVG11_DOCTYPE, SVG11_DOCTYPE.replace('"', "'")])
def test_standard_doctype_stripped_before_xml(doctype, monkeypatch):
    original = reference.ET.fromstring
    def parse_without_dtd(text):
        assert "<!DOCTYPE" not in text
        return original(text)
    monkeypatch.setattr(reference.ET, "fromstring", parse_without_dtd)
    cleaned, size = reference.sanitize_svg(
        ('<?xml version="1.0"?>\n<!-- export -->\n' + doctype).encode() + svg())
    assert "DOCTYPE" not in cleaned and size == (40, 30)


@pytest.mark.parametrize("doctype", [
    SVG11_DOCTYPE[:-1] + ' []>',
    SVG11_DOCTYPE[:-1] + ' [<!ENTITY x "secret">]>',
    SVG11_DOCTYPE.replace("http://www.w3.org", "https://evil.example"),
    SVG11_DOCTYPE.replace("SVG 1.1", "SVG 1.0"),
    '<!DOCTYPE svg SYSTEM "file:///C:/secret">',
    '<!DOCTYPE svg>',
    SVG11_DOCTYPE + SVG11_DOCTYPE,
    '<!ENTITY x SYSTEM "https://evil.example/x">' + SVG11_DOCTYPE,
])
def test_other_doctypes_rejected(doctype):
    with pytest.raises(reference.ReferenceImageError, match="DTD"):
        reference.sanitize_svg(doctype.encode() + svg())


def _verify_reference_load_and_window(path, monkeypatch, app):
    def no_network(*args, **kwargs):
        pytest.fail("Reference loading must never access the network")
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    data = path.read_bytes()
    before = hashlib.sha256(data).hexdigest()
    cleaned, expected = reference.sanitize_svg(data)
    assert "<!DOCTYPE" not in cleaned
    with reference.load_reference_image(path) as image:
        # resvg preserves aspect ratio and rounds fractional physical units.
        assert all(abs(actual - limit) <= 1 for actual, limit in zip(image.size, expected))
        expected = image.size
        assert image.getbbox() is not None
    window = None
    try:
        window = open_reference_window(app, path, None)
        app.update()
        assert window.reference_loaded, window.reference_error
        assert window.reference_error is None
        assert window.reference_path == str(path)
        assert app.grab_current() is None
        panes = next(w for w in window.winfo_children() if isinstance(w, ttk.Panedwindow))
        left = [w for w in panes.winfo_children() if isinstance(w, _ImagePane)][0]
        assert left.image.size == expected
        assert left.photo is not None
        assert left.canvas.itemcget(left.item, "image")
    finally:
        if window is not None:
            window.destroy()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    return expected, before


def test_matplotlib_svg_load_and_window(matplotlib_svg, monkeypatch, app):
    pytest.importorskip("resvg_py")
    _verify_reference_load_and_window(matplotlib_svg, monkeypatch, app)


def test_real_user_svg_load_and_window(monkeypatch, app):
    pytest.importorskip("resvg_py")
    path = Path("C:/Users/Uniter/Desktop/压缩包/26102002（NiTi)/Dis1.39.svg")
    if not path.is_file():
        pytest.skip("User reference file is only available on the user's Windows machine")
    size, digest = _verify_reference_load_and_window(path, monkeypatch, app)
    print(f"Real reference verified: size={size}, sha256={digest}")


def test_window_load_error_is_observable(tmp_path, app):
    path = tmp_path / "invalid.svg"
    path.write_bytes(b"invalid")
    window = None
    try:
        window = open_reference_window(app, path, None)
        app.update()
        assert window.reference_loaded is False
        assert window.reference_error
        assert window.reference_path is None
    finally:
        if window is not None:
            window.destroy()


def test_embedded_png_read_only_render(tmp_path):
    pytest.importorskip("resvg_py")
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    path = tmp_path / "embedded.svg"
    path.write_bytes(SVG11_DOCTYPE.encode() + svg(
        f'<image href="{uri}" width="40" height="30" preserveAspectRatio="none"/>'))
    before = path.read_bytes()
    with reference.load_reference_image(path) as image:
        assert image.getpixel((20, 15)) == (255, 0, 0, 255)
    assert path.read_bytes() == before


@pytest.mark.parametrize("uri", [
    "data:image/svg+xml;base64,PHN2Zy8+", "https://example.com/image.png",
    "file:///C:/secret.png", "data:image/png;base64,AAAA",
])
def test_embedded_image_restrictions(uri):
    with pytest.raises(reference.ReferenceImageError):
        reference.sanitize_svg(svg(f'<image href="{uri}"/>'))


def test_embedded_image_pixel_limit(monkeypatch):
    buffer = BytesIO()
    Image.new("RGB", (10, 10)).save(buffer, format="PNG")
    uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    monkeypatch.setattr(reference, "MAX_PIXELS", 50)
    with pytest.raises(reference.ReferenceImageError, match="尺寸"):
        reference.sanitize_svg(svg(f'<image href="{uri}"/>'))


def svg(body="", **attrs):
    attributes = {"width": "40", "height": "30", **attrs}
    return ('<svg xmlns="http://www.w3.org/2000/svg" ' +
            " ".join(f'{key}="{value}"' for key, value in attributes.items()) +
            f'>{body}</svg>').encode()


@pytest.mark.parametrize("extension,format", [("png", "PNG"), ("jpg", "JPEG")])
def test_raster_read_only(tmp_path, extension, format):
    path = tmp_path / f"sample.{extension}"
    Image.new("RGB", (40, 30), "red").save(path, format)
    before = hashlib.sha256(path.read_bytes()).digest()
    with reference.load_reference_image(path) as image:
        assert image.mode == "RGBA"
        assert image.size == (40, 30)
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_snapshot_independent():
    image = Image.new("RGB", (3, 4), "red")
    copy = reference.snapshot_image(image)
    image.putpixel((0, 0), (0, 0, 0))
    assert copy.getpixel((0, 0)) == (255, 0, 0, 255)
    assert reference.snapshot_image(None) is None


@pytest.mark.parametrize("body", [
    '<use href="https://example.com/a.svg#x"/>',
    '<use href="file:///C:/secret.svg#x"/>',
    '<use href="../secret.svg#x"/>',
    '<use xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="//example.com/a"/>',
    '<style>@import "https://example.com/x.css";</style>',
    '<style>rect{fill:URL(\'file:///x\')}</style>',
    '<rect style="fill:u/**/rl(https://example.com/a)"/>',
    '<rect style="fill:u\\72l(https://example.com/a)"/>',
    '<script>alert(1)</script>', '<rect onclick="alert(1)"/>',
    '<image href="data:image/png;base64,AAAA"/>',
    '<foreignObject/>', '<set attributeName="href" to="file:///secret"/>',
    '<g xml:base="file:///C:/"><use href="#x"/></g>',
])
def test_unsafe_svg_rejected(body):
    with pytest.raises(reference.ReferenceImageError):
        reference.sanitize_svg(svg(body))


@pytest.mark.parametrize("data", [b'<!DOCTYPE svg [<!ENTITY a "x">]><svg/>',
                                     b"<svg", b"<html/>", b"\xff"])
def test_bad_xml(data):
    with pytest.raises(reference.ReferenceImageError):
        reference.sanitize_svg(data)


@pytest.mark.parametrize("attrs", [{"width": "9000"}, {"width": "8000", "height": "8000"},
                                   {"width": "0"}, {"width": "1e999"}])
def test_svg_limits(attrs):
    with pytest.raises(reference.ReferenceImageError):
        reference.sanitize_svg(svg(**attrs))


def test_svg_render(tmp_path):
    pytest.importorskip("resvg_py")
    path = tmp_path / "gradient.svg"
    data = svg('<defs><linearGradient id="g"><stop stop-color="red"/></linearGradient></defs>'
               '<rect width="40" height="30" fill="url(#g)"/>')
    path.write_bytes(data)
    with reference.load_reference_image(path) as image:
        assert image.size == (40, 30)
        assert image.getpixel((20, 15)) == (255, 0, 0, 255)
    assert path.read_bytes() == data


def test_missing_svg_dependency(tmp_path, monkeypatch):
    path = tmp_path / "sample.svg"
    path.write_bytes(svg())
    monkeypatch.setitem(sys.modules, "resvg_py", None)
    with pytest.raises(reference.ReferenceImageError, match="resvg_py==0.5.0"):
        reference.load_reference_image(path)


def test_viewbox_and_physical_units():
    _, size = reference.sanitize_svg(b'<svg viewBox="0 0 40 30"/>')
    assert size == (40, 30)
    _, size = reference.sanitize_svg(svg(width="1in", height="72pt"))
    assert size == (96, 96)


def test_input_limits_and_errors(tmp_path, monkeypatch):
    path = tmp_path / "a.png"
    path.write_bytes(b"not an image")
    with pytest.raises(reference.ReferenceImageError, match="无法读取"):
        reference.load_reference_image(path)
    monkeypatch.setattr(reference, "MAX_FILE_BYTES", 2)
    with pytest.raises(reference.ReferenceImageError, match="文件过大"):
        reference.load_reference_image(path)
    Image.new("RGB", (10, 10)).save(path)
    monkeypatch.setattr(reference, "MAX_FILE_BYTES", 10000)
    monkeypatch.setattr(reference, "MAX_PIXELS", 50)
    with pytest.raises(reference.ReferenceImageError, match="尺寸"):
        reference.load_reference_image(path)


def test_window_snapshot_refresh_and_pan(app):
    original = Image.new("RGB", (40, 30), "red")
    fresh = Image.new("RGB", (40, 30), "blue")
    window = None
    try:
        window = open_reference_window(app, None, original, lambda: fresh)
        app.update()
        assert isinstance(window, tk.Toplevel)
        assert app.grab_current() is None
        panes = next(w for w in window.winfo_children() if isinstance(w, ttk.Panedwindow))
        right = [w for w in panes.winfo_children() if isinstance(w, _ImagePane)][1]
        original.putpixel((0, 0), (0, 0, 0))
        assert right.image.getpixel((0, 0)) == (255, 0, 0, 255)
        toolbar = window.winfo_children()[0]
        next(w for w in toolbar.winfo_children() if isinstance(w, ttk.Button)
             and w.cget("text") == "手动刷新当前快照").invoke()
        assert right.image.getpixel((0, 0)) == (0, 0, 255, 255)
        right.scale(2)
        assert right.zoom == 2
        class Event:
            x, y = 10, 20
        right.start_pan(Event())
        event = Event()
        event.x = 30
        right.move_pan(event)
        assert right.pan == [20, 0]
        right.fit()
        assert right.zoom == 1 and right.pan == [0, 0]
    finally:
        if window is not None:
            window.destroy()
    with pytest.raises(ValueError):
        fresh.getpixel((0, 0))
    with pytest.raises(ValueError):
        original.getpixel((0, 0))
