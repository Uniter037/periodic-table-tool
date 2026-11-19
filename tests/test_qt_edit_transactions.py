"""Exercise Qt edit transactions in isolated offscreen processes."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    'inspector_preserves_table_value',
    'formula_exports_selected_element',
    'preview_preserves_active_editor',
    'inspector_preserves_active_editor',
    'failed_open_preserves_recovery_draft',
)


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_qt_edit_transaction(tmp_path, scenario):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR='1',
               PYTHONIOENCODING='utf-8')
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), scenario, str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=30,
    )
    assert result.returncode == 0, f'{scenario}\n{result.stdout}\n{result.stderr}'
    assert f'QT_EDIT_OK:{scenario}' in result.stdout


def run_scenario(scenario, directory):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QSignalSpy, QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

    from application.workbench_session import WorkbenchSession
    from core.elements_data import ALL_SYMBOLS
    from ui.qt.workbench import MainWindow

    app = QApplication([])
    window = MainWindow(directory / 'user', start_preview=False, recover=False)
    initial = {'H': '0.10', 'He': '0.20'}
    window.session.patch(data=initial)
    window._sync()
    window.show()
    app.processEvents()

    preview_packets = []
    window.preview_job.start = preview_packets.append

    def type_value(editor, value):
        editor.selectAll()
        QTest.keyClicks(editor, value)

    def edit_cell(symbol, value):
        index = window.table_model.index(ALL_SYMBOLS.index(symbol), 2)
        window.table.setCurrentIndex(index)
        window.table.edit(index)
        editor = app.focusWidget()
        assert isinstance(editor, QLineEdit) and window.table.isAncestorOf(editor)
        type_value(editor, value)
        return editor

    def save_and_reload():
        path = directory / 'saved.ptproj'
        assert window.save_project(path), window.status.text()
        reader = WorkbenchSession(directory / 'reader')
        reader.load(path)
        return reader

    def wait_for_timer(timer):
        assert timer.isActive()
        timeout = QSignalSpy(timer.timeout)
        assert timeout.wait(3000), 'Qt timer did not fire'

    try:
        if scenario == 'inspector_preserves_table_value':
            window.select_element('H', from_table=True)
            window.inspector.fields['show_value'].click()
            assert window.inspector.dirty
            editor = edit_cell('H', '0.30')
            QTest.keyClick(editor, Qt.Key.Key_Return)
            app.processEvents()
            assert window.session.data['H'] == '0.30', window.session.data
            saved = save_and_reload()
            assert saved.data == dict(initial, H='0.30')
            assert saved.plot['element_overrides']['H']['show_value'] is False

        elif scenario == 'formula_exports_selected_element':
            window.select_element('H', from_table=True)
            window.preview.set_stale(True)
            combo = window.element_name
            combo.setFocus()
            QTest.keyClick(combo, Qt.Key.Key_Down)
            assert combo.currentText() == 'He'
            type_value(window.formula_value, '0.40')
            export_packets = []
            window.export_job.start = export_packets.append
            window.export()
            assert window.session.data == dict(initial, He='0.40')
            assert len(export_packets) == 1, window.status.text()
            assert export_packets[0]['items'][0][1] == {'H': 0.10, 'He': 0.40}

        elif scenario == 'preview_preserves_active_editor':
            window.schedule_preview()
            editor = edit_cell('H', '0')
            wait_for_timer(window.preview_timer)
            assert window.session.data == initial
            assert app.focusWidget() is editor and editor.text() == '0'
            assert all(packet['data'] == {'H': 0.10, 'He': 0.20} for packet in preview_packets)
            QTest.keyClicks(editor, '.60')
            QTest.keyClick(editor, Qt.Key.Key_Return)
            app.processEvents()
            assert window.session.data == dict(initial, H='0.60'), window.session.data

        elif scenario == 'inspector_preserves_active_editor':
            window.select_element('H', from_table=True)
            window.inspector.fields['show_color'].click()
            editor = edit_cell('He', '0.60')
            wait_for_timer(window.inspector.timer)
            assert window.session.plot['element_overrides']['H']['show_color'] is False
            assert window.session.data == initial
            assert app.focusWidget() is editor and editor.text() == '0.60'
            QTest.keyClick(editor, Qt.Key.Key_Return)
            app.processEvents()
            assert save_and_reload().data == dict(initial, He='0.60')

        elif scenario == 'failed_open_preserves_recovery_draft':
            window._save_draft()
            draft = window.session.draft_path
            contents = draft.read_bytes()
            invalid = directory / 'invalid.ptproj'
            invalid.write_text('invalid project', encoding='utf-8')
            QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.No
            assert not window.open_project(invalid)
            assert window.session.dirty and window.session.data == initial
            assert draft.is_file() and draft.read_bytes() == contents

            other = WorkbenchSession(directory / 'other')
            other.patch(data={'Li': '0.50'})
            valid = directory / 'valid.ptproj'
            other.save(valid)
            assert window.open_project(valid), window.status.text()
            assert window.session.data == {'Li': '0.50'}
            assert not draft.exists()

        else:
            raise AssertionError(f'Unknown scenario: {scenario}')
    finally:
        window.shutdown()
        window.close()
        app.processEvents()

    print(f'QT_EDIT_OK:{scenario}')


if __name__ == '__main__':
    run_scenario(sys.argv[1], Path(sys.argv[2]))
