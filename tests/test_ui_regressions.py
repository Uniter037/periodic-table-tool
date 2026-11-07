from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pytest

import main
from core import PresetStore
from ui.preview import PreviewCanvas


@pytest.fixture
def custom(app):
    app.mode_combo.current(list(main.STYLES).index('custom'))
    app._on_style_change()
    return app


def test_color_selection_and_cancel(custom, monkeypatch):
    monkeypatch.setattr(main.colorchooser, 'askcolor', lambda **kw: ((0, 128, 255), '#0080ff'))
    custom._edit_color(0)
    assert custom.custom_colors[0] == (0, 128 / 255, 1)
    custom._add_color()
    assert custom.custom_colors[-1] == (0, 128 / 255, 1)
    before = list(custom.custom_colors)
    monkeypatch.setattr(main.colorchooser, 'askcolor', lambda **kw: (None, None))
    custom._edit_color(0)
    custom._add_color()
    assert custom.custom_colors == before


def test_combobox_stays_readonly(custom):
    assert custom.param_entries['layout'].instate(['readonly', '!disabled'])
    assert custom.param_entries['vmin'].instate(['!readonly', '!disabled'])


def test_preset_output_roundtrip_and_legacy(custom, monkeypatch, tmp_path):
    store = PresetStore(str(tmp_path / 'presets'))
    monkeypatch.setattr(custom, 'presets', store)
    custom.fmt_var.set('pdf')
    custom.out_var.set(str(tmp_path / 'exports'))
    payload = custom._current_preset_payload()
    store.save('roundtrip', payload)
    custom.preset_combo.set('roundtrip')
    custom.fmt_var.set('png')
    custom.out_var.set('other')
    custom.preset_include_data.set(True)
    custom._preset_load()
    assert custom.fmt_var.get() == 'pdf'
    assert custom.out_var.get() == str(tmp_path / 'exports')
    del payload['output_format'], payload['output_dir']
    store.save('legacy', payload)
    custom.preset_combo.set('legacy')
    custom._preset_load()
    assert custom.fmt_var.get() == 'pdf'
    assert custom.out_var.get() == str(tmp_path / 'exports')


@pytest.mark.parametrize('size', [(600, 200), (200, 600)])
def test_preview_resize_preserves_composition_and_hit(app, monkeypatch, size):
    clicked = []
    preview = PreviewCanvas(app, on_click=clicked.append)
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.set_xlim(0, 2)
    ax.set_ylim(0, 2)
    preview.show(fig, {(0, 0, 1, 1): 'H'})
    original_size = fig.get_size_inches().copy()
    original_position = ax.get_position().bounds
    monkeypatch.setattr(preview._surface, 'winfo_width', lambda: size[0])
    monkeypatch.setattr(preview._surface, 'winfo_height', lambda: size[1])
    try:
        preview.resize()
        np.testing.assert_array_equal(fig.get_size_inches(), original_size)
        assert ax.get_position().bounds == original_position
        left, top, width, height = preview._display_box
        assert abs(width / height - 8 / 3) < .04
        px, py = ax.transData.transform((.5, .5))
        sw, sh = preview._source.size
        preview._on_surface_click(SimpleNamespace(x=left + px * width / sw,
                                                  y=top + (sh - py) * height / sh))
        assert clicked == ['H']
        preview._on_surface_click(SimpleNamespace(x=-1, y=-1))
        assert clicked == ['H']
    finally:
        preview.destroy()
    assert not plt.fignum_exists(fig.number)


def test_preview_render_failure_keeps_old_figure(app, monkeypatch):
    preview = PreviewCanvas(app)
    old = plt.figure()
    preview.show(old, {})
    new = plt.figure()
    monkeypatch.setattr('ui.preview.FigureCanvasAgg.draw', lambda self: (_ for _ in ()).throw(RuntimeError('draw failed')))
    try:
        with pytest.raises(RuntimeError):
            preview.show(new, {})
        assert preview.fig is old
        assert not plt.fignum_exists(new.number)
    finally:
        preview.destroy()


def test_generate_save_failure_closes_figure(custom, monkeypatch, tmp_path):
    custom.data = {'H': .1}
    custom.out_var.set(str(tmp_path))
    figure = plt.figure()
    monkeypatch.setattr(main, 'render_table', lambda *a, **kw: figure)
    def fail(*a, **kw):
        raise OSError('disk full')
    monkeypatch.setattr(main, 'save_figure', fail)
    errors = []
    monkeypatch.setattr(main.messagebox, 'showerror', lambda *a: errors.append(a))
    custom.generate()
    assert errors
    assert not plt.fignum_exists(figure.number)
