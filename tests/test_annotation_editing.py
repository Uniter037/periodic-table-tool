def test_graphic_edit_is_default_and_cancel_keeps_data(app):
    assert app.mark_mode_var.get()
    app._import_text('Fe,1.2500')
    app._on_preview_click('Fe')
    assert app.mark_value_var.get() == '1.2500'
    assert app.data_notebook.select() == str(app.mark_tab)
    app.mark_value_var.set('pending')
    app._reset_mark()
    assert app.mark_value_var.get() == '1.2500'
    assert app.data == {'Fe': '1.2500'}


def test_heatmap_invalid_edit_is_atomic_and_zero_can_be_undone(app):
    import main
    app.mode_combo.current(list(main.STYLES).index('reconstruct_percent'))
    app._on_style_change()
    app._import_text('Fe,1')
    app._on_preview_click('Fe')
    before = app._document_snapshot()
    app.mark_value_var.set('not a number')
    app._apply_mark()
    assert app._document_snapshot() == before
    app.mark_value_var.set('0')
    app._apply_mark()
    assert app.data['Fe'] == '0'
    app._clear_mark()
    assert 'Fe' not in app.data and app.mark_value_var.get() == ''
    app._undo()
    assert app.data['Fe'] == '0'
    assert app.mark_value_var.get() == '0'
    app._redo()
    assert 'Fe' not in app.data
    assert app.mark_value_var.get() == ''


def test_disabled_graphic_edit_does_not_change_selection(app):
    app.mark_mode_var.set(False)
    before = app.mark_symbol_var.get()
    app._on_preview_click('Fe')
    assert app.mark_symbol_var.get() == before
