import json
import os
import time

from infrastructure.diagnostics import DiagnosticService, DiagnosticSettings


def test_switch_level_and_close(tmp_path):
    service = DiagnosticService(tmp_path, DiagnosticSettings(enabled=False, level="DEBUG"))
    assert not service.record("ERROR", "disabled", "ignored")
    assert not service.directory.exists()
    service.configure(DiagnosticSettings())
    assert not service.record("DEBUG", "low_level", "ignored")
    assert service.record("INFO", "started", "启动")
    path, = service.directory.glob("*.jsonl")
    original = path.read_bytes()
    service.configure(DiagnosticSettings(enabled=False))
    assert not service.record("CRITICAL", "disabled", "ignored")
    assert path.read_bytes() == original
    service.configure(DiagnosticSettings(level="WARNING"))
    assert not service.record("INFO", "low_level", "ignored")
    assert service.record("WARNING", "warned", "warning")
    service.close()
    service.close()
    assert not service.record("ERROR", "closed", "ignored")
    assert [event["event_code"] for event in service.query().entries] == ["warned", "started"]


def test_rotation_retention_and_pagination(tmp_path):
    service = DiagnosticService(tmp_path, DiagnosticSettings(
        max_file_bytes=620, max_total_bytes=1900, retention_days=1))
    for index in range(12):
        assert service.record("INFO", "phase", "进度" * 25, job_id="j1",
                              project_revision=index)
    files = sorted(service.directory.glob("*.jsonl"))
    assert 2 <= len(files) < 12
    assert all(path.stat().st_size <= 620 for path in files)
    assert sum(path.stat().st_size for path in files) <= 1900
    old_time = time.time() - 2 * 86400
    os.utime(files[0], (old_time, old_time))
    assert service.record("INFO", "other", "different job", job_id="j2")
    assert not files[0].exists()

    filters = {"job_id": "j1", "level": "INFO", "keyword": "进度"}
    expected = service.query(filters).entries
    page = service.query(filters, limit=1)
    assert page.entries == expected[:1]
    assert page.next_cursor is not None
    # A new record must not shift the cursor. Increase the capacity to
    # isolate pagination from retention eviction.
    service.configure(DiagnosticSettings(max_file_bytes=620, max_total_bytes=9000))
    assert service.record("INFO", "phase", "进度" * 25, job_id="j1")
    assert service.query(filters, page.next_cursor).entries == expected[1:]
    service.close()


def test_redaction_on_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("USERNAME", "privateuser")
    service = DiagnosticService(tmp_path, DiagnosticSettings(level="DEBUG"))
    try:
        raise ValueError("unlabelled exception body")
    except ValueError as error:
        assert service.record(
            "DEBUG", "import.failed",
            "privateuser opened C:\\Users\\privateuser\\report.xlsx\ncell text: raw content",
            module="importer", error_id="err-1", job_id="report.xlsx",
            details={"row_count": 3, "nested": {"data": "nested secret"},
                     "row_count_text": "arbitrary user content"},
            exception=error,
        )
    service.close()
    path, = service.directory.glob("*.jsonl")
    raw = path.read_text(encoding="utf-8")
    for value in ("privateuser", "report.xlsx", "raw content", "nested secret",
                  "arbitrary user content", "unlabelled exception body"):
        assert value not in raw
    event = json.loads(raw)
    assert event["message"] == "<USER> opened <SOURCE>\n<REDACTED>"
    assert event["details"]["row_count"] == 3
    assert event["details"]["exception"]["type"] == "ValueError"
    assert event["details"]["exception"]["frames"][0]["file"] == "<SOURCE>"
    assert service.query({"error_id": "err-1"}).entries == (event,)


def test_disk_failure_and_session_scoped_clear(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("keep", encoding="utf-8")
    failed = DiagnosticService(blocked)
    assert not failed.record("ERROR", "failure", "cannot create log directory")
    assert failed.write_failed
    assert not failed.record("ERROR", "retry", "no retry")
    failed.close()

    first, second = DiagnosticService(tmp_path), DiagnosticService(tmp_path)
    assert first.record("INFO", "first", "first")
    assert second.record("INFO", "second", "second")
    unrelated = first.directory / "journal.jsonl"
    unrelated.write_text("keep", encoding="utf-8")
    assert first.clear_history().removed == 1
    assert first.query().entries == ()
    assert len(second.query().entries) == 1
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert first.record("INFO", "after_clear", "started again")
    first.close()
    second.close()

def test_temporary_debug_stop_and_configure_priority(tmp_path):
    service = DiagnosticService(tmp_path, DiagnosticSettings(level="WARNING"))
    try:
        service.start_session()
        assert service.record("DEBUG", "debug", "temporary")
        service.stop_session()
        assert not service.record("INFO", "info", "warning threshold restored")
        assert service.record("WARNING", "warning", "warning threshold restored")

        service.start_session()
        service.configure(DiagnosticSettings(enabled=False, level="INFO"))
        service.stop_session()
        assert not service.record("ERROR", "error", "manual switch wins")

        service.start_session()
        service.configure(DiagnosticSettings(level="ERROR"))
        service.stop_session()
        assert not service.record("WARNING", "warning", "manual level wins")
        assert service.record("ERROR", "error", "manual level wins")
    finally:
        service.close()


def test_temporary_debug_expires_while_idle(tmp_path, monkeypatch):
    from threading import Event

    service = DiagnosticService(tmp_path, DiagnosticSettings(enabled=False))
    finished = Event()
    finish_file = service._finish_file

    def observe_close():
        was_open = service._stream is not None
        finish_file()
        if was_open:
            finished.set()

    monkeypatch.setattr(service, "_finish_file", observe_close)
    try:
        service.start_session(duration_minutes=0.01)
        assert service.record("DEBUG", "debug", "temporarily enabled")
        assert finished.wait(timeout=5)
        assert not service.record("ERROR", "error", "disabled again")
    finally:
        service.close()


def test_export_selection_redaction_metadata_and_no_overwrite(tmp_path, monkeypatch):
    from zipfile import ZipFile

    monkeypatch.setenv("USERNAME", "privateuser")
    service = DiagnosticService(tmp_path / "logs")
    assert service.record("INFO", "selected", "selected", job_id="j1")
    assert service.record("INFO", "excluded", "excluded", job_id="j2")
    service.close()
    path, = service.directory.glob("*.jsonl")
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    events[0]["message"] = "privateuser opened C:\\Users\\privateuser\\secret.xlsx"
    events[0]["details"] = {"row_count": 4, "clipboard": "private payload",
                            "exception": {"type": "ValueError", "message": "private payload",
                                          "frames": [{"file": "C:/secret.py", "line": 3,
                                                      "function": "parse"}]}}
    path.write_text("\n".join(map(json.dumps, events)) + "\n{broken\n", encoding="utf-8")

    destination = tmp_path / "export"
    first = service.export_bundle({"job_id": "j1"}, destination)
    original = first.read_bytes()
    second = service.export_bundle({"job_id": "j2"}, destination)
    assert first != second
    assert first.read_bytes() == original
    with ZipFile(first) as archive:
        metadata = json.loads(archive.read("metadata.json"))
        assert set(archive.namelist()) == set(metadata["files"])
        assert metadata["event_count"] == 1
        assert metadata["settings"]["level"] == "INFO"
        assert metadata["python"]
        raw = archive.read("events.jsonl").decode("utf-8")
        event = json.loads(raw)
        assert event["event_code"] == "selected"
        assert event["message"] == "<USER> opened <SOURCE>"
        assert event["details"]["exception"]["frames"][0]["file"] == "<SOURCE>"
        for private in ("privateuser", "secret.xlsx", "private payload", "secret.py"):
            assert private not in raw


def test_export_failure_leaves_no_partial_bundle(tmp_path, monkeypatch):
    import pytest
    from infrastructure.diagnostics import _service

    service = DiagnosticService(tmp_path / "logs")
    try:
        assert service.record("INFO", "before", "before export")
        destination = tmp_path / "export"
        existing = service.export_bundle(None, destination)
        original = existing.read_bytes()

        def fail_publication(*args):
            raise PermissionError("simulated publication failure")

        monkeypatch.setattr(_service.os, "link", fail_publication)
        with pytest.raises(PermissionError):
            service.export_bundle(None, destination)
        assert list(destination.iterdir()) == [existing]
        assert existing.read_bytes() == original
        assert service.record("INFO", "after", "after export")
    finally:
        service.close()
