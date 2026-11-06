from tkinter import Toplevel, messagebox, ttk
from unittest.mock import Mock

import pytest

from ui.import_wizard import ExcelImportDialog


@pytest.fixture
def wizard(_application, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail(f"Unexpected global message box: {args}")

    monkeypatch.setattr(messagebox, "_show", unexpected)
    dialogs = []

    def open_dialog(result=None, sheets=("Sheet 1", "Sheet 2")):
        preview = Mock(return_value=result)
        commit = Mock()
        dialog = ExcelImportDialog(_application, list(sheets), preview, commit)
        dialogs.append(dialog)
        return dialog, preview, commit

    yield open_dialog
    for dialog in dialogs:
        if dialog.winfo_exists():
            dialog.destroy()


def test_preview_uses_selected_mapping_and_commit_receives_same_result(wizard):
    result = {
        "datasets": [{"id": "example"}],
        "diagnostics": [{"severity": "warning", "message": "示例警告"}],
    }
    dialog, preview, commit = wizard(result)
    assert dialog.commit_button.instate(["disabled"])
    dialog.preview_button.invoke()
    preview.assert_called_once_with("Sheet 1", "B1:AG1", "A2:A6", "B2:AG6", "matrix_rows")
    assert "数据集：1" in dialog.status.get()
    assert "示例警告" in dialog.status.get()
    assert dialog.commit_button.instate(["!disabled"])

    controls = [child for child in dialog.scroll.content.winfo_children()
                if isinstance(child, ttk.Combobox)]
    controls[0].current(1)
    controls[1].current(1)
    assert dialog.commit_button.instate(["disabled"])
    dialog.preview_button.invoke()
    assert preview.call_args.args == ("Sheet 2", "B1:AG1", "A2:A6", "B2:AG6", "matrix_columns")
    dialog.commit_button.invoke()
    assert commit.call_count == 1
    assert commit.call_args.args[0] is result
    assert not dialog.winfo_exists()


@pytest.mark.parametrize("field,new_value", [
    ("sheet", "Sheet 2"),
    ("elements_range", "B1:Z1"),
    ("conditions_range", "A2:A4"),
    ("values_range", "B2:Z4"),
    ("direction", "matrix_columns"),
])
def test_edit_invalidates_preview(wizard, field, new_value):
    dialog, _, commit = wizard({"datasets": [{}], "diagnostics": []})
    dialog.preview_button.invoke()
    assert dialog.commit_button.instate(["!disabled"])
    getattr(dialog, field).set(new_value)
    assert "请预览" in dialog.status.get()
    assert dialog.commit_button.instate(["disabled"])
    dialog.commit_button.invoke()
    commit.assert_not_called()


@pytest.mark.parametrize("datasets,diagnostics,message", [
    ([{}], [{"severity": "error", "message": "范围无效"}], "范围无效"),
    ([], [], "没有可导入的数据集"),
])
def test_unimportable_preview_disables_confirmation(wizard, datasets, diagnostics, message):
    dialog, _, commit = wizard({"datasets": datasets, "diagnostics": diagnostics})
    dialog.preview_button.invoke()
    assert message in dialog.status.get()
    assert dialog.commit_button.instate(["disabled"])
    dialog.commit_button.invoke()
    commit.assert_not_called()


def test_callback_failures_are_reported_inside_dialog(wizard):
    dialog, preview, commit = wizard({"datasets": [{}], "diagnostics": []})
    dialog.preview_button.invoke()
    preview.side_effect = ValueError("预览回调失败")
    dialog.preview_button.invoke()
    assert "预览回调失败" in dialog.status.get()
    assert dialog.commit_button.instate(["disabled"])

    preview.side_effect = None
    dialog.preview_button.invoke()
    commit.side_effect = RuntimeError("提交回调失败")
    dialog.commit_button.invoke()
    assert dialog.winfo_exists()
    assert "提交回调失败" in dialog.status.get()
    assert dialog.commit_button.instate(["disabled"])
    assert dialog.preview_button.instate(["!disabled"])


@pytest.mark.parametrize("via_window_manager", [False, True])
def test_cancel_calls_neither_callback(wizard, via_window_manager):
    dialog, preview, commit = wizard()
    if via_window_manager:
        dialog.tk.call(dialog.protocol("WM_DELETE_WINDOW"))
    else:
        dialog.cancel_button.invoke()
    assert not dialog.winfo_exists()
    preview.assert_not_called()
    commit.assert_not_called()


def test_no_sheets_disables_preview(wizard):
    dialog, preview, _ = wizard(sheets=())
    assert "没有可用的工作表" in dialog.status.get()
    assert dialog.preview_button.instate(["disabled"])
    dialog.preview_button.invoke()
    preview.assert_not_called()


def test_small_window_scrolls_and_keeps_actions_visible(wizard, monkeypatch):
    dialog, _, _ = wizard({
        "datasets": [{}],
        "diagnostics": [{"severity": "warning", "message": "需要检查此单元格。"}] * 20,
    })
    dialog.geometry("250x160")
    dialog.update()
    dialog.preview_button.invoke()
    dialog.update()
    assert (dialog.winfo_width(), dialog.winfo_height()) == (250, 160)
    canvas = dialog.scroll.canvas
    start, end = canvas.yview()
    assert 0 < start < end < 1
    other_window = Toplevel(dialog.master)
    try:
        other_window.update()
        assert other_window.winfo_viewable()
        # Simulate a conflicting screen hit without depending on desktop focus
        # or stacking. Tk still dispatches both wheel events to real widgets.
        monkeypatch.setattr(dialog.scroll, "winfo_containing", lambda *_: other_window)
        other_window.event_generate("<MouseWheel>", x=2, y=2, delta=-120)
        assert canvas.yview()[0] == start
        canvas.event_generate("<MouseWheel>", x=2, y=2, delta=-120)
        assert canvas.yview()[0] > start
    finally:
        other_window.destroy()
    canvas.yview_moveto(1)
    assert canvas.yview()[1] == 1
    for button in (dialog.preview_button, dialog.commit_button, dialog.cancel_button):
        assert button.winfo_viewable()
        x = button.winfo_rootx() - dialog.winfo_rootx()
        y = button.winfo_rooty() - dialog.winfo_rooty()
        assert 0 <= x <= dialog.winfo_width() - button.winfo_width()
        assert 0 <= y <= dialog.winfo_height() - button.winfo_height()
