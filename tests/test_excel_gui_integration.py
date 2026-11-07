import tkinter as tk
import copy
import pytest

from test_excel_import_service import _workbook, _sheet, _row, _text


def test_real_excel_dialog_loads_selected_group(app, tmp_path):
    from ui.import_wizard import ExcelImportDialog
    path = _workbook(tmp_path, _sheet(
        _row(1, _text("B1", "Fe"), _text("C1", "Cu")),
        _row(2, _text("A2", "sample"), '<c r="B2"><v>0</v></c>',
             '<c r="C2"><v>-2.5</v></c>'),
    ))
    before = set(app.winfo_children())
    try:
        app._import_excel(str(path))
        dialog = next(w for w in app.winfo_children() if isinstance(w, ExcelImportDialog))
        dialog.elements_range.set("B1:C1")
        dialog.conditions_range.set("A2:A2")
        dialog.values_range.set("B2:C2")
        dialog.preview_button.invoke()
        assert dialog.commit_button.instate(["!disabled"]), dialog.status.get()
        dialog.commit_button.invoke()
        chooser = next(w for w in app.winfo_children()
                       if isinstance(w, tk.Toplevel) and w.title() == "选择绘图数据组")
        button = next(w for w in chooser.winfo_children() if w.winfo_class() == "TButton")
        button.invoke()
        assert app.data == {"Fe": 0, "Cu": -2.5}
    finally:
        for window in set(app.winfo_children()) - before:
            if isinstance(window, tk.Toplevel) and window.winfo_exists():
                window.destroy()


def test_group_edits_roundtrip_undo_and_failed_restore(app, tmp_path):
    from application.excel_import import ExcelImportService
    from core.document import read_document, write_document
    path = _workbook(tmp_path, _sheet(
        _row(1, _text("B1", "Fe")),
        _row(2, _text("A2", "one"), '<c r="B2"><v>1</v></c>'),
        _row(3, _text("A3", "two"), '<c r="B3"><v>2</v></c>'),
    ))
    result = ExcelImportService(path).preview("Values", "B1", "A2:A3", "B2:B3", "matrix_rows")
    first, second = app.excel_collection.append(result)
    app._select_excel_group(first)
    app.data = {"Fe": "1.2500"}
    app.table.set_data(app.data)
    app._refresh_preview()
    app._on_preview_click("Fe")
    assert app.mark_value_var.get() == "1.2500"
    app._select_excel_group(second)
    assert app.data == {"Fe": 2}
    assert app.mark_value_var.get() == "2"
    app._undo()
    assert app.excel_collection.active_dataset_id == first
    assert app.data == {"Fe": "1.2500"}
    app._redo()
    assert app.excel_collection.active_dataset_id == second
    saved = app._document_snapshot()
    project = tmp_path / "groups.ptproj"
    write_document(project, saved)
    app._load_demo()
    app._restore_document(read_document(project))
    app._select_excel_group(first)
    assert app.data == {"Fe": "1.2500"}
    before = app._document_snapshot()
    broken = copy.deepcopy(before)
    broken["excel_collection"]["active_dataset_id"] = "missing"
    with pytest.raises(ValueError):
        app._restore_document(broken)
    assert app._document_snapshot() == before
