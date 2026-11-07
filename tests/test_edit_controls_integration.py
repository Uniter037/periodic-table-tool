import copy
import pytest

from ui.edit_controls import parse_figure_size


def test_physical_size_preserves_inches_and_rejects_bad_values():
    assert parse_figure_size('254x127 mm') == pytest.approx((10, 5))
    assert parse_figure_size('10×5') == (10, 5)
    for value in ('nanx5', '0x5', '4xinf', '10', '10x5x2'):
        with pytest.raises(ValueError):
            parse_figure_size(value)


def test_hidden_element_keeps_value_and_range_choice_is_independent(app):
    app._import_text('Fe,100\nCu,1\nZn,3')
    before = dict(app.data)
    app._set_element_options('Fe', {'show_value': False, 'show_color': False, 'include_in_range': False})
    assert app.data == before
    assert app._auto_range()
    assert float(app.param_vars['vmin'].get()) == 1
    assert float(app.param_vars['vmax'].get()) == 3
    saved = app._document_snapshot()
    app.element_overrides = {}
    app._restore_document(saved)
    assert app.element_overrides['Fe']['show_value'] is False
    assert app.data == before


def test_label_drag_is_document_edit_and_undoable(app):
    app._import_text('Fe,0.73925')
    app._on_preview_click('Fe')
    app._move_element_label('Fe', .15, -.1)
    assert app.element_overrides['Fe']['value_dx'] == pytest.approx(.15)
    app._undo()
    assert app.element_overrides == {}
    app._redo()
    assert app.element_overrides['Fe']['value_dy'] == pytest.approx(-.1)
    assert app.data == {'Fe': '0.73925'}


def test_geometry_validation_is_atomic_and_colorbar_drag_undoable(app):
    app._import_text('Fe,0.7')
    before = app._document_snapshot()
    with pytest.raises(ValueError):
        app._apply_edit_params({'figsize': '254x127 mm', 'margins': '0.8,0.1,0.2,0.9'})
    assert app._document_snapshot() == before
    app._apply_edit_params({'figsize': '254x127 mm', 'cbar_box': '.9,.1,.02,.8'})
    app._displayed_colorbar_box = [.9,.1,.02,.8]
    app._move_colorbar(.85,.12)
    assert app._current_work_style()['cbar_box'] == pytest.approx([.85,.12,.02,.8])
    app._undo()
    assert app._current_work_style()['cbar_box'] == pytest.approx([.9,.1,.02,.8])


def test_style_only_preset_keeps_excel_group_and_output(app, tmp_path):
    from application.excel_import import ExcelImportService
    from test_excel_import_service import _workbook, _sheet, _row, _text
    path = _workbook(tmp_path, _sheet(
        _row(1, _text('B1','Fe')), _row(2, _text('A2','one'), '<c r="B2"><v>2</v></c>')))
    result = ExcelImportService(path).preview('Values','B1','A2','B2','matrix_rows')
    ids = app.excel_collection.append(result)
    app._select_excel_group(ids[0])
    original = app._document_snapshot()
    payload = copy.deepcopy(original['current'])
    payload['data'] = {'Fe': 999}
    payload['params']['fmt'] = '四位小数'
    payload['output_dir'] = 'unwanted'
    app.presets.save('style', payload)
    app.preset_combo.set('style')
    app._preset_load()
    assert app.data == {'Fe': 2}
    assert app._excel_attached
    assert app.excel_collection.active_dataset_id == ids[0]
    assert app.out_var.get() == original['current']['output_dir']
    assert app.param_vars['fmt'].get() == '四位小数'
    app._preset_load(include_data=True)
    assert app.data == {'Fe': 999}
    assert not app._excel_attached


def test_style_only_preset_save_omits_measurements(app):
    app._import_text('Fe,123')
    app.preset_name_var.set('styleonly')
    app._preset_save()
    assert 'data' not in app.presets.load('styleonly')


def test_invalid_element_options_leave_document_unchanged(app):
    before = app._document_snapshot()
    for row in ({'show_value': 'false'}, {'value_dx': float('nan')}, {'unexpected': True}):
        with pytest.raises(ValueError):
            app._set_element_options('Fe', row)
        assert app._document_snapshot() == before
