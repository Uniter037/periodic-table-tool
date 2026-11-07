# -*- coding: utf-8 -*-
"""pytest 共享配置：确保项目根目录可被所有测试导入；共享 GUI 实例。"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
import tempfile

# Test collection imports main; isolate all user state before those imports.
_user_files = tempfile.TemporaryDirectory(prefix="ptable-tests-")
os.environ["PTT_USER_DIR"] = _user_files.name


@pytest.fixture(scope="session")
def _application():
    """整个测试会话共享一个 GUI 实例（连续创建多个 Tk 根窗口在 Windows 会失败）。"""
    import main  # 业务导入失败必须使测试失败，不能伪装成环境跳过。
    instance = main.App()
    instance.withdraw()
    instance._test_initial = instance._document_snapshot()
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass


@pytest.fixture
def app(_application, monkeypatch, tmp_path):
    """Reuse Tk but isolate document state; unexpected modal errors must fail."""
    import copy
    import main
    from core.document import History
    instance = _application
    def unexpected(title, message, **kwargs):
        pytest.fail(f"Unexpected dialog {title}: {message}")
    monkeypatch.setattr(main.messagebox, "showerror", unexpected)
    monkeypatch.setattr(main.messagebox, "showwarning", unexpected)
    monkeypatch.setattr(main.messagebox, "askyesnocancel", lambda *a, **kw: False)
    instance._cancel_job(quiet=True)
    instance._cancel_refresh()
    if instance.table._edit_entry is not None:
        instance.table._cancel_edit(instance.table._edit_entry)
    snapshot = copy.deepcopy(instance._test_initial)
    snapshot["current"]["output_dir"] = str(tmp_path / "output")
    instance._restore_document(snapshot)
    instance.data_notebook.select(0)
    instance.mark_mode_var.set(True)
    instance.mark_symbol_var.set("（点击预览元素）")
    instance.mark_value_var.set("")
    instance.preset_include_data.set(False)
    instance.presets = main.PresetStore(str(tmp_path / "presets"))
    instance.project_path = None
    instance._history = History(instance._document_snapshot())
    instance._saved_snapshot = instance._document_snapshot()
    instance._cancel_refresh()
    yield instance
    instance._cancel_refresh()
    instance._cancel_job(quiet=True)
    if instance._draft_job is not None:
        instance.after_cancel(instance._draft_job)
        instance._draft_job = None
