"""Usability contracts for the bounded settings / preview layout."""
import json

import pytest
import main


@pytest.mark.parametrize('size', ['1024x768', '800x600'])
def test_small_window_keeps_toolbar_preview_and_data(app, size):
    app.layout_mode = 'auto'
    app.scale_mode = 'auto'
    app._apply_layout()
    app.geometry(size)
    app.deiconify()
    app.update()
    try:
        assert app._effective_layout() == 'split-v'
        assert app.preview.winfo_width() >= 400
        assert app.preview.winfo_height() >= 160
        assert app.table.winfo_height() >= 60
        assert app.toolbar.winfo_ismapped()
        for button in app.toolbar_buttons.values():
            assert button.winfo_rootx() >= app.winfo_rootx()
            assert button.winfo_rootx() + button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
        assert app._right.winfo_rooty() + app._right.winfo_height() <= app._status.winfo_rooty()
    finally:
        app.withdraw()


def test_every_settings_page_scrolls_to_last_control(app):
    app.geometry('1024x768')
    app.layout_mode = 'auto'
    app._apply_layout()
    app.deiconify()
    app.update()
    try:
        assert len(app.settings_notebook.tabs()) == 3
        for page in app.settings_pages.values():
            app.settings_notebook.select(page)
            app.update()
            page.canvas.yview_moveto(1)
            app.update_idletasks()
            assert page.canvas.yview()[1] == pytest.approx(1)
            last = page.content.winfo_children()[-1]
            assert last.winfo_rooty() + last.winfo_height() <= page.canvas.winfo_rooty() + page.canvas.winfo_height()
            assert last.winfo_rootx() + last.winfo_width() <= page.canvas.winfo_rootx() + page.canvas.winfo_width()
            page.canvas.yview_moveto(0)
    finally:
        app.settings_notebook.select(0)
        app.withdraw()


def test_layout_switch_preserves_data_and_bounds(app):
    app.data = {'Fe': '0.75'}
    app.geometry('1024x768')
    app.deiconify()
    try:
        for layout in ('split-v', 'split-h', 'auto'):
            app.layout_mode = layout
            app._apply_layout()
            app.update()
            assert app.data == {'Fe': '0.75'}
            assert app.preview.winfo_height() >= 160
            assert app._left.winfo_height() < app.winfo_height()
            assert app._right.winfo_ismapped()
    finally:
        app.layout_mode = 'auto'
        app._apply_layout()
        app.withdraw()


def test_config_roundtrip(app, tmp_path, monkeypatch):
    cfg_file = tmp_path / 'cfg.json'
    monkeypatch.setattr(main, 'CONFIG_PATH', str(cfg_file))
    app.layout_mode = 'split-v'
    app.geometry('900x700+10+10')
    app._save_config()
    cfg = json.loads(cfg_file.read_text(encoding='utf-8'))
    assert cfg['layout'] == 'split-v'
    assert '+10+10' in cfg['geometry']
    app.layout_mode = 'auto'
    app._load_config()
    assert app.layout_mode == 'split-v'
    app.layout_mode = 'auto'
    app._apply_layout()
