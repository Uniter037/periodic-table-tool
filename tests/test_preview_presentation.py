from types import SimpleNamespace

import pytest
from PIL import Image

from ui.preview import PreviewCanvas


class Surface:
    width, height = 400, 300

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def coords(self, *args):
        pass

    def itemconfigure(self, *args, **kwargs):
        pass


@pytest.fixture
def preview(monkeypatch):
    monkeypatch.setattr('ui.preview.ImageTk.PhotoImage', lambda image, **kw: image)
    p = PreviewCanvas.__new__(PreviewCanvas)
    p._source = Image.new('RGBA', (1000, 500), '#123456')
    p._surface = Surface()
    p._display_box = None
    p._paper, p._item = 1, 2
    p.zoom, p.pan = 1., [0, 0]
    p._pixel_hits = {(100, 100, 200, 200): 'H'}
    p._selected = p._colorbar_box = None
    p.on_click = None
    yield p
    p._source.close()


def test_actual_size_stays_one_to_one_after_viewport_resize(preview):
    p = preview
    before = p._source.tobytes()
    notices = []
    p.on_zoom = notices.append
    p.fit()
    assert p._display_box == (0, 50, 400, 200)
    assert p.zoom_label == '40%'
    p.actual_size()
    assert p._display_box == (-300, -100, 1000, 500)
    assert p.zoom_label == '100%'
    p._surface.width = 700
    p.resize()
    assert p._display_box == (-150, -100, 1000, 500)
    assert p._source.tobytes() == before
    assert notices == ['40%', '100%', '100%']
    p.fit()
    assert p._display_box[2:] == (600, 300)
    assert p.pan == [0, 0]


def test_zoom_keeps_source_hits_and_click_transform(preview):
    p = preview
    hits = p._pixel_hits.copy()
    clicks = []
    p.on_click = clicks.append
    p.actual_size()
    p.zoom_in()
    assert p._display_box[2:] == (1150, 575)
    left, top, width, height = p._display_box
    p._on_surface_click(SimpleNamespace(x=left + 150 * width / 1000,
                                       y=top + 150 * height / 500))
    assert clicks == ['H']
    p.zoom_out()
    assert p._display_box[2:] == (1000, 500)
    assert p._pixel_hits == hits


def test_theme_scale_and_styles(_application):
    from tkinter import font as tkfont, ttk
    from ui.theme import apply_scale, apply_theme

    app = _application
    style = ttk.Style(app)
    original_theme = style.theme_use()
    original_background = app.cget('background')
    original_scale = app._theme_scale
    original_fonts = app._theme_fonts.copy()
    font_settings = {key: font.actual() for key, font in original_fonts.items()}
    names = (
        '.', 'Card.TFrame', 'Toolbar.TFrame', 'Card.TLabel', 'Toolbar.TLabel',
        'Muted.TLabel', 'Status.TLabel', 'Header.TLabel', 'TButton',
        'Accent.TButton', 'Export.TButton', 'Section.TButton', 'TEntry',
        'TCombobox', 'TSpinbox', 'Treeview', 'Treeview.Heading', 'TNotebook',
        'TNotebook.Tab', 'TLabelframe', 'TLabelframe.Label', 'TProgressbar',
    )
    original_styles = {name: (style.configure(name) or {}, style.map(name))
                       for name in names}
    supplied = tkfont.Font(root=app, size=10)
    try:
        apply_theme(app)
        font = apply_scale(app, supplied, 1.5)
        assert font is supplied
        assert font.cget('size') == 15
        assert style.lookup('Header.TLabel', 'font') != style.lookup('.', 'font')
        assert style.lookup('Accent.TButton', 'background') == '#2563eb'
        assert style.lookup('Card.TFrame', 'background') == '#ffffff'
        assert int(style.lookup('Treeview', 'rowheight')) >= 42
        assert int(style.lookup('Treeview', 'rowheight')) >= font.metrics('linespace') + 8
        assert apply_scale(app, supplied, 1.0) is font
        assert font.cget('size') == 10
        with pytest.raises(ValueError):
            apply_scale(app, supplied, float('nan'))
    finally:
        app._theme_fonts = original_fonts
        apply_scale(app, original_fonts['body'], original_scale)
        for key, settings in font_settings.items():
            original_fonts[key].configure(**settings)
        style.theme_use(original_theme)
        for name, (configuration, mapping) in original_styles.items():
            # Clear options introduced by the test before restoring prior values.
            for option in set(style.configure(name) or {}) - configuration.keys():
                style.configure(name, **{option: ''})
            for option in set(style.map(name)) - mapping.keys():
                style.map(name, **{option: []})
            style.configure(name, **configuration)
            style.map(name, **mapping)
        app.configure(background=original_background)
