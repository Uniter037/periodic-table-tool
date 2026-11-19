"""Exercise real Qt commands and draft handling in isolated offscreen processes."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario", ["registry", "table", "inspector", "formula"])
def test_qt_commands_data(tmp_path, scenario):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8",
               PTT_USER_DIR=str(tmp_path / "user"))
    env.pop("PTT_SMOKE", None)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), scenario, str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=45,
    )
    assert result.returncode == 0, f"{scenario}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert f"QT_COMMANDS_DATA_OK:{scenario}" in result.stdout


def _registry():
    from PySide6.QtWidgets import QMainWindow, QToolButton

    from ui.qt.commands import Command, CommandRegistry, Ribbon

    window = QMainWindow()
    registry = CommandRegistry(window)
    invoked = []
    initial = Command("save", "Save project", "File", "Project", "Ctrl+S", "write")
    action = registry.register(initial, lambda: invoked.append("save"))
    ribbon = Ribbon(registry, window)
    window.setCentralWidget(ribbon)

    duplicate = Command("save", "Duplicate", "Extra", "Other")
    with pytest.raises(ValueError, match="Duplicate command: save"):
        registry.register(duplicate, lambda: invoked.append("duplicate"))
    assert registry.actions["save"] is action
    assert registry.search("") == [initial]
    assert window.actions() == [action]
    assert ribbon.count() == 1

    extra = Command("snapshot", "Capture image", "Tools", "Export", keywords="PNG preview")
    added = registry.register(extra, lambda: invoked.append("snapshot"))
    assert registry.search("  pNg   TOOLS  capture ") == [extra]
    assert registry.search("write project") == [initial]
    assert registry.search("save png") == []
    assert registry.search("") == [initial, extra]
    assert [ribbon.tabText(i) for i in range(ribbon.count())] == ["File", "Tools"]

    ribbon.setCurrentIndex(1)
    later = Command("open", "Open project", "File", "Project")
    opened = registry.register(later, lambda: invoked.append("open"))
    assert ribbon.tabText(ribbon.currentIndex()) == "Tools"
    assert {button.defaultAction() for button in ribbon.widget(0).findChildren(QToolButton)} == {action, opened}
    buttons = ribbon.currentWidget().widget().findChildren(QToolButton)
    assert len(buttons) == 1 and buttons[0].defaultAction() is added
    buttons[0].click()
    assert invoked == ["snapshot"]
    window.close()


def _value_index(model, symbol):
    from core.elements_data import ALL_SYMBOLS

    return model.index(ALL_SYMBOLS.index(symbol), 2)


def _table(window, _directory):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy

    model = window.table_model
    hydrogen = _value_index(model, "H")
    helium = _value_index(model, "He")
    assert model.setData(hydrogen, "0.25")
    baseline = window.session.document
    errors = QSignalSpy(model.error)
    commits = QSignalSpy(model.committed)

    assert model.setData(hydrogen, "invalid")
    assert model.setData(helium, "0.5")
    assert commits.count() == 0 and errors.count() == 2
    assert window.session.document == baseline
    model.set_snapshot(window.session.data)
    hydrogen = _value_index(model, "H")
    assert model.pending == {"H": "invalid", "He": "0.5"}
    assert model.data(hydrogen, Qt.ItemDataRole.DisplayRole) == "invalid"
    assert model.data(hydrogen, Qt.ItemDataRole.EditRole) == "invalid"
    assert model.data(hydrogen, Qt.ItemDataRole.ToolTipRole)

    assert model.setData(hydrogen, "0.75")
    assert commits.count() == 1 and errors.count() == 2
    assert not model.pending
    assert window.session.data == {"H": "0.75", "He": "0.5"}
    assert model.data(hydrogen) == "0.75"
    assert model.data(_value_index(model, "He")) == "0.5"
    assert model.data(hydrogen, Qt.ItemDataRole.ToolTipRole) is None


def _type(line_edit, text):
    from PySide6.QtTest import QTest

    line_edit.setFocus()
    line_edit.selectAll()
    QTest.keyClicks(line_edit, text)


def _inspector(window, _directory):
    assert window.table_model.setData(_value_index(window.table_model, "Fe"), "0.25")
    window.select_element("Fe", from_table=True)
    inspector = window.inspector
    offset = inspector.fields["value_dx"]
    baseline = window.session.document

    _type(inspector.value, "0.75")
    for invalid in ("invalid", "nan"):
        _type(offset, invalid)
        assert inspector.dirty and inspector.symbol == "Fe"
        assert not inspector.flush()
        assert window.session.document == baseline
        assert inspector.dirty
        assert offset.text() == invalid and inspector.value.text() == "0.75"
        assert window.status.text().startswith("未完成：")

    _type(offset, "0.125")
    assert inspector.flush()
    assert not inspector.dirty
    assert window.session.data["Fe"] == "0.75"
    assert window.session.plot["element_overrides"]["Fe"]["value_dx"] == 0.125


def _formula(window, directory):
    import json

    window.select_element("Fe", from_table=True)
    formula = window.formula_value
    baseline = window.session.document
    formula.setText("0.1")
    assert not window._formula_dirty
    _type(formula, "0.375")
    assert window._formula_dirty and window.session.document == baseline

    project = directory / "formula.ptproj"
    assert window.save_project(project), window.status.text()
    assert not window._formula_dirty and not window.session.dirty
    assert window.session.data["Fe"] == "0.375"
    assert window.table_model.data(_value_index(window.table_model, "Fe")) == "0.375"
    saved = project.read_bytes()
    assert json.loads(saved)["current"]["data"]["Fe"] == "0.375"
    baseline = window.session.document

    _type(formula, "invalid")
    assert window._formula_dirty
    assert not window.save_project(project)
    assert project.read_bytes() == saved
    rejected = directory / "invalid.ptproj"
    assert not window.save_project(rejected) and not rejected.exists()
    assert window.session.document == baseline and not window.session.dirty
    assert window._formula_dirty and formula.text() == "invalid"
    assert window.status.text().startswith("未完成：")


def main():
    from PySide6.QtWidgets import QApplication

    scenario, output = sys.argv[1:]
    sys.path.insert(0, str(ROOT))
    app = QApplication([])
    if scenario == "registry":
        _registry()
    else:
        from ui.qt.workbench import MainWindow

        directory = Path(output)
        window = MainWindow(user_dir=directory / "user", start_preview=False, recover=False)
        try:
            window.show()
            app.processEvents()
            {"table": _table, "inspector": _inspector, "formula": _formula}[scenario](window, directory)
        finally:
            window.shutdown()
            window.close()
    print(f"QT_COMMANDS_DATA_OK:{scenario}")


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
