"""Integration contracts for responsive UI without changing drawing state."""
import copy
import pytest


@pytest.mark.parametrize('size,scale', [('1440x860','auto'), ('1440x860','1.5'), ('800x600','auto')])
def test_layout_and_scaling_preserve_drawing(app, size, scale):
    before = copy.deepcopy(app._current_preset_payload())
    app.layout_mode, app.scale_mode = 'auto', scale
    app._current_scale = None
    app.geometry(size)
    app.deiconify()
    app.update()
    try:
        if size.startswith('1440'):
            assert app.data_notebook.winfo_rootx() < app.preview.winfo_rootx() < app._left.winfo_rootx()
            assert app.preview.winfo_width() >= 300
        else:
            app._compact_settings_open = False
            app._current_layout = None
            app._apply_layout()
            app.update()
            assert not app._left.winfo_ismapped()
            app.toolbar_buttons['绘图设置'].invoke()
            app.update()
            assert app._left.winfo_ismapped()
            app.toolbar_buttons['绘图设置'].invoke()
            app.update()
            assert not app._left.winfo_ismapped()
        for button in app.toolbar_buttons.values():
            assert button.winfo_rootx() + button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
        assert app._current_preset_payload() == before
    finally:
        app.scale_mode = 'auto'
        app._current_scale = None
        app.withdraw()


def test_search_reveals_folded_setting_without_editing_document(app):
    app.geometry('1440x860')
    app.deiconify()
    app.update()
    before = copy.deepcopy(app._current_preset_payload())
    try:
        section = app.parameter_sections['文字与标注']
        if section.expanded:
            section.toggle()
        assert app.settings_search.select('value_fs')
        app.update()
        widget = app.param_entries['value_fs']
        page = app.settings_pages['figure']
        assert section.expanded
        assert widget.winfo_ismapped()
        assert page.canvas.winfo_rooty() <= widget.winfo_rooty()
        assert widget.winfo_rooty() + widget.winfo_height() <= page.canvas.winfo_rooty() + page.canvas.winfo_height()
        assert app._current_preset_payload() == before
    finally:
        app.withdraw()


def test_issue_navigation_and_invalidation(app):
    app.data = {'Fe': .25}
    app._set_layout_issues([{'code':'TEXT_OVERLAP','text':{'element':'Fe','role':'value'}}])
    assert app.layout_issues_panel.tree.get_children()
    app.preview.set_stale(False)
    app._select_layout_issue('Fe')
    assert app.mark_symbol_var.get() == 'Fe'
    assert app.data_notebook.select() == str(app.mark_tab)
    assert app.data == {'Fe': .25}
    app._refresh_preview()
    assert not app.layout_issues_panel.tree.get_children()
    app._cancel_refresh()
