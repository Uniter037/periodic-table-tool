"""User workflows across document state, rendering and project persistence."""
import copy
import json
from pathlib import Path
import time

import main


def test_annotation_import_keeps_lexical_values(app):
    app._import_text("Fe,001\nCu,1.00\nAu,1e3")
    assert app.data == {"Fe": "001", "Cu": "1.00", "Au": "1e3"}
    app.param_vars["kind"].set("标注图（文本）")
    app.param_vars["vmin"].set("not a number")
    assert app._refresh_preview_now(), app._preview_error
    texts = [text.get_text() for text in app.preview.fig.axes[0].texts]
    assert {"001", "1.00", "1e3"} <= set(texts)


def test_style_roundtrip_preserves_settings_and_current_data(app):
    app.param_vars["title"].set("我的设置")
    app.cbar_override = {"ticks": [-1, 0, 1], "labels": ["低", "零", "高"],
                         "visible": [True, False, True], "fontsize": 8}
    app._import_text("H,001")
    app.mode_combo.current(list(main.STYLES).index("classic_blues"))
    app._on_style_change()
    assert app.cbar_override is None
    app._import_text("Fe,2")
    app.mode_combo.current(list(main.STYLES).index("custom"))
    app._on_style_change()
    assert app.param_vars["title"].get() == "我的设置"
    assert app.cbar_override["visible"] == [True, False, True]
    assert app.data == {"Fe": "2"}


def test_clear_undo_redo_preserves_raw_data(app):
    app._import_text("H,001\nFe,1.00")
    app._clear_data()
    app._undo()
    assert app.data == {"H": "001", "Fe": "1.00"}
    app._redo()
    assert app.data == {}


def test_project_roundtrip_and_invalid_load_are_atomic(app, tmp_path, monkeypatch):
    app._import_text("H,001\nFe,1.00")
    app.param_vars["title"].set("项目往返")
    app.cbar_override = {"ticks": [0, 1], "labels": ["零", "一"],
                         "visible": [False, True], "fontsize": 8}
    project = tmp_path / "我的项目.ptproj"
    assert app._save_project(path=project)
    saved = app._document_snapshot()
    app._clear_data()
    assert app._open_project(path=project)
    assert app._document_snapshot() == saved
    broken = copy.deepcopy(saved)
    broken["current"]["cbar_override"]["ticks"] = [0, 0]
    project.write_text(json.dumps(broken), encoding="utf-8")
    errors = []
    monkeypatch.setattr(main.messagebox, "showerror", lambda *a, **kw: errors.append(a))
    assert not app._open_project(path=project)
    assert errors
    assert app._document_snapshot() == saved


def test_draft_only_writes_changed_work_and_respects_pending_recovery(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "user_dir", tmp_path)
    draft = tmp_path / "draft.ptproj"
    app._save_draft()
    assert not draft.exists()
    app._import_text("Fe,001")
    app._save_draft()
    original = draft.read_bytes()
    monkeypatch.setattr(app, "_recovery_pending", True)
    app._import_text("H,2")
    app._save_draft()
    assert draft.read_bytes() == original


def test_colorbar_row_visibility_survives_sorting(app):
    app._cbar_apply([1, -1, 0], ["高", "低", "零"])
    app.cbar_tree.selection_set(app.cbar_tree.get_children()[2])
    app._cbar_toggle()
    assert app._current_work_style()["cbar"]["ticks"] == [-1, 1]
    app._cbar_sort()
    assert app.cbar_override["ticks"] == [-1, 0, 1]
    assert app.cbar_override["labels"] == ["低", "零", "高"]
    assert app.cbar_override["visible"] == [True, False, True]
    app.cbar_tree.selection_set(app.cbar_tree.get_children()[1])
    app._cbar_toggle()
    assert app._current_work_style()["cbar"]["labels"] == ["低", "零", "高"]


def test_real_background_export_and_preview(app, tmp_path):
    app._import_text("H,0\nC,-1\nFe,1")
    app.out_var.set(str(tmp_path))
    app.fmt_var.set("png")
    app.last_output = None
    app.generate_async()
    deadline = time.monotonic() + 90
    while app._job_mode is not None and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    assert app._job_mode is None, "background export did not finish"
    assert app.last_output and Path(app.last_output).is_file(), app.status_var.get()
    app._refresh_preview_async()
    while app._job_mode is not None and time.monotonic() < deadline:
        app.update()
        time.sleep(.02)
    assert app._job_mode is None, "background preview did not finish"
    assert app.preview._source is not None, app.status_var.get()
    assert not app._preview_error


def test_fast_export_and_cancel_keep_latest_preview_request(app, tmp_path, monkeypatch):
    class Worker:
        active = False
        def start(self, request):
            self.active = True
        def cancel(self):
            self.active = False
        def invalidate(self):
            pass
        def poll(self):
            self.active = False
            return ("done", {"files": [(str(tmp_path / "staged.png"), "chart")]})
    worker = Worker()
    monkeypatch.setattr(app, "_worker", worker)
    (tmp_path / "staged.png").write_bytes(b"staged output")
    app._import_text("H,0")
    assert app._refresh_job is not None
    app.generate_async()
    assert app._pending_preview
    app._poll_render_job()
    assert app._refresh_job is not None
    assert not app._pending_preview
    app.generate_async()
    app._import_text("H,1")
    assert app._pending_preview
    app._cancel_job()
    assert app._refresh_job is not None
    assert not app._pending_preview


def test_clean_state_and_project_switch_clear_old_draft(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "user_dir", tmp_path)
    project = tmp_path / "saved.ptproj"
    app._import_text("H,0")
    assert app._save_project(path=project)
    app._import_text("H,1")
    app._save_draft()
    draft = tmp_path / "draft.ptproj"
    assert draft.exists()
    app._undo()
    assert app.data == {"H": "0"}
    app._save_draft()
    assert not draft.exists()
    app._import_text("H,2")
    app._save_draft()
    assert draft.exists()
    assert app._open_project(path=project)
    assert not draft.exists()
