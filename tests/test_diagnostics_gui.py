import json
import zipfile


def test_log_switch_applies_immediately_and_persists(app, monkeypatch, tmp_path):
    import main
    from infrastructure.diagnostics import DiagnosticService
    monkeypatch.setattr(main, "CONFIG_PATH", str(tmp_path / "settings.json"))
    service = DiagnosticService(tmp_path / "logs")
    monkeypatch.setattr(app, "diagnostics", service)
    original = app.log_enabled.get(), app.log_level.get()
    try:
        app.log_enabled.set(False)
        app._configure_diagnostics()
        assert not service.record("ERROR", "test.error", "Test error")
        assert not service.directory.exists()
        saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert saved["diagnostics"]["enabled"] is False
        app.log_enabled.set(True)
        app.log_level.set("WARNING")
        app._configure_diagnostics()
        assert not service.record("INFO", "test.info", "Info")
        assert service.record("ERROR", "test.error", "Error")
        assert len(service.query().entries) == 1
        app.log_enabled.set(False)
        app._configure_diagnostics()
        assert not service.record("ERROR", "test.error", "Second error")
        assert len(service.query().entries) == 1
    finally:
        service.close()
        app.log_enabled.set(original[0])
        app.log_level.set(original[1])


def test_temporary_debug_and_bundle_actions(app, monkeypatch, tmp_path):
    import main
    from infrastructure.diagnostics import DiagnosticService, DiagnosticSettings
    service = DiagnosticService(tmp_path / "logs", DiagnosticSettings(enabled=False))
    monkeypatch.setattr(app, "diagnostics", service)
    monkeypatch.setattr(main.filedialog, "askdirectory", lambda **kw: str(tmp_path / "bundles"))
    try:
        app._start_diagnostic_session()
        assert service.record("DEBUG", "test.session", "Temporary diagnostics")
        app._stop_diagnostic_session()
        assert not service.record("ERROR", "test.stopped", "Disabled")
        app._export_diagnostics()
        bundles = list((tmp_path / "bundles").glob("*.zip"))
        assert len(bundles) == 1
        with zipfile.ZipFile(bundles[0]) as archive:
            assert set(archive.namelist()) == {"events.jsonl", "metadata.json"}
            events = archive.read("events.jsonl").decode("utf-8")
            assert "test.session" in events and "test.stopped" not in events
    finally:
        service.close()
