from types import SimpleNamespace

from PIL import Image
import pytest

from ui.preview import PreviewCanvas


class Surface:
    def __init__(self):
        self.rectangles = []
        self.options = []

    def delete(self, tag):
        self.rectangles.clear()
        self.options.clear()

    def create_rectangle(self, *coords, **kwargs):
        self.rectangles.append(coords)
        self.options.append(kwargs)

    def coords(self, *args):
        pass

    def itemconfigure(self, *args, **kwargs):
        pass


@pytest.fixture
def preview():
    p = PreviewCanvas.__new__(PreviewCanvas)
    p._source = Image.new('RGBA', (1000, 500), 'white')
    p._display_box = (73, -41, 2000, 1000)
    p._pixel_hits = {(100, 100, 150, 125): 'H'}
    p.hit_map = {(0, 0, 1, 1): 'H'}
    p._surface = Surface()
    p._selected = p._colorbar_box = p._drag = None
    p._edit_enabled, p._is_stale = True, False
    p.on_click = p.on_move = p.on_colorbar_move = None
    yield p
    if p._source is not None:
        p._source.close()


def event(p, x, y):
    left, top, w, h = p._display_box
    sw, sh = p._source.size
    return SimpleNamespace(x=left + x * w / sw, y=top + y * h / sh)


@pytest.mark.parametrize('box', [(73, -41, 2000, 1000), (-50, 112, 500, 250)])
def test_element_zoom_pan_single_commit(preview, box):
    p = preview
    p._display_box = box
    clicks, moves = [], []
    p.on_click = clicks.append
    p.on_move = lambda *args: moves.append(args)
    before, hits = p._source.tobytes(), p._pixel_hits.copy()
    p._on_surface_click(event(p, 125, 112))
    p._on_surface_drag(event(p, 150, 90))
    assert moves == []
    p._on_surface_release(event(p, 175, 87))
    p._on_surface_release(event(p, 175, 87))
    assert clicks == ['H']
    assert moves == [('H', 1., 1.)]
    assert p._selected == 'H'
    assert p._surface.rectangles
    assert p._source.tobytes() == before
    assert p._pixel_hits == hits


@pytest.mark.parametrize('distance,commits', [(0, 0), (4, 0), (4.1, 1)])
def test_screen_pixel_threshold(preview, distance, commits):
    p = preview
    moves = []
    p.on_move = lambda *args: moves.append(args)
    start = event(p, 125, 112)
    p._on_surface_click(start)
    p._on_surface_release(SimpleNamespace(x=start.x + distance, y=start.y))
    assert len(moves) == commits


def test_disabled_and_stale_cancel(preview):
    p = preview
    moves, clicks = [], []
    p.on_click = clicks.append
    p.on_move = lambda *args: moves.append(args)
    p.set_edit_enabled(False)
    p._on_surface_click(event(p, 125, 112))
    p._on_surface_release(event(p, 175, 87))
    assert p._selected is None
    assert clicks == ['H']
    p.set_edit_enabled(True)
    p._on_surface_click(event(p, 125, 112))
    p._stale = SimpleNamespace(place=lambda **kw: None, place_forget=lambda: None)
    p.set_stale(True)
    p._on_surface_release(event(p, 175, 87))
    p._on_surface_click(event(p, 125, 112))
    p._on_surface_release(event(p, 175, 87))
    assert moves == []


@pytest.mark.parametrize('target,expected', [((850, 300), (.8, .3)), ((2000, -500), (.9, .8)), ((-500, 900), (0., 0.))])
def test_colorbar_coordinates_and_clamping(preview, target, expected):
    p = preview
    moves = []
    p.on_colorbar_move = lambda *args: moves.append(args)
    p.set_colorbar_box((.7, .2, .1, .2))
    assert p._surface.rectangles[-1] == pytest.approx((1473, 559, 1673, 759))
    p._on_surface_click(event(p, 750, 350))
    p._on_surface_release(event(p, *target))
    p._on_surface_release(event(p, *target))
    assert len(moves) == 1
    assert moves[0] == pytest.approx(expected)
    p.set_colorbar_box(None)
    assert p._surface.rectangles == []


def test_snapshot_is_independent(preview):
    snapshot = preview.current_image()
    snapshot.putpixel((0, 0), (0, 0, 0, 0))
    assert snapshot.getpixel((0, 0)) != preview._source.getpixel((0, 0))
    snapshot.close()
    preview._source.close()
    preview._source = None
    assert preview.current_image() is None


def test_replace_failure_restores_source_hits_and_overlay(preview):
    p = preview
    p.fig = p.canvas = None
    p._photo = 'old'
    p._paper, p._item = 'paper', 'image'
    p.set_selected('H')
    old = p._source, p._pixel_hits, p._display_box
    overlay = p._surface.rectangles.copy()
    def fail():
        raise RuntimeError('display failure')
    p.resize = fail
    new = Image.new('RGBA', (10, 10))
    with pytest.raises(RuntimeError):
        p._replace_source(new, {}, None, None, {})
    assert (p._source, p._pixel_hits, p._display_box) == old
    assert p._surface.rectangles == overlay


@pytest.mark.parametrize('box', [(73, -41, 2000, 1000), (-50, 112, 500, 250)])
def test_live_target_and_selection_callback(preview, box):
    p = preview
    p._display_box = box
    p.on_click = p.set_selected  # Same synchronous selection update as main.
    moves = []
    p.on_move = lambda *args: moves.append(args)
    pixels, hits = p._source.tobytes(), p._pixel_hits.copy()
    p._on_surface_click(event(p, 125, 112))
    p._on_surface_drag(event(p, 175, 87))
    assert p._drag is not None
    assert p._drag_target == pytest.approx((150, 75, 200, 100))
    left, top, w, h = box
    assert p._surface.rectangles[-1] == pytest.approx(
        (left + .15 * w, top + .15 * h, left + .2 * w, top + .2 * h))
    assert p._surface.options[-1]['dash'] == (5, 3)
    p.set_selected('H')
    assert p._surface.options[-1]['dash'] == (5, 3)
    assert moves == []
    assert p._source.tobytes() == pixels and p._pixel_hits == hits
    p._on_surface_release(event(p, 175, 87))
    p._on_surface_release(event(p, 175, 87))
    assert moves == [('H', 1., 1.)]
    assert p._drag_target is None
    assert all('dash' not in options for options in p._surface.options)


def test_colorbar_target_matches_clamped_release(preview):
    p = preview
    moves = []
    p.on_colorbar_move = lambda *args: moves.append(args)
    p.set_colorbar_box((.7, .2, .1, .2))
    p._on_surface_click(event(p, 750, 350))
    p._on_surface_drag(event(p, 2000, -500))
    assert p._drag_target == pytest.approx((900, 0, 1000, 100))
    assert p._surface.options[-1]['dash'] == (5, 3)
    assert moves == []
    p._on_surface_release(event(p, 2000, -500))
    assert moves[0] == pytest.approx((.9, .8))
    assert all('dash' not in options for options in p._surface.options)


@pytest.mark.parametrize('action', ['escape', 'disabled', 'stale', 'wheel', 'pan', 'fit', 'resize', 'new_click'])
def test_cancel_feedback_without_commit(preview, monkeypatch, action):
    p = preview
    p.zoom, p.pan = 1., [0, 0]
    p._paper, p._item = 'paper', 'image'
    p._surface.winfo_width = lambda: 600
    p._surface.winfo_height = lambda: 400
    p._stale = SimpleNamespace(place=lambda **kw: None, place_forget=lambda: None)
    monkeypatch.setattr('ui.preview.ImageTk.PhotoImage', lambda image, **kw: object())
    moves = []
    p.on_move = lambda *args: moves.append(args)
    p._on_surface_click(event(p, 125, 112))
    target = event(p, 175, 87)
    p._on_surface_drag(target)
    assert p._drag_target is not None
    if action == 'escape':
        p._cancel_drag(SimpleNamespace())
    elif action == 'disabled':
        p.set_edit_enabled(False)
    elif action == 'stale':
        p.set_stale(True)
    elif action == 'wheel':
        p._wheel(SimpleNamespace(delta=120))
    elif action == 'pan':
        p._pan_start(target)
    elif action == 'fit':
        p.fit()
    elif action == 'resize':
        p.resize()
    else:
        p._on_surface_click(event(p, 900, 450))
    assert p._drag is None and p._drag_target is None
    assert all('dash' not in options for options in p._surface.options)
    p._on_surface_release(target)
    assert moves == []


def test_feedback_disappears_inside_threshold(preview):
    p = preview
    start = event(p, 125, 112)
    p._on_surface_click(start)
    p._on_surface_drag(event(p, 175, 87))
    p._on_surface_drag(SimpleNamespace(x=start.x + 4, y=start.y))
    assert p._drag_target is None
    assert all('dash' not in options for options in p._surface.options)
