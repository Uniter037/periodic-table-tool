"""Real Qt/session/spawn-worker integration in clean, main-guarded processes."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import json
import multiprocessing
from pathlib import Path
import sys
import time
import traceback


def main():
    root, scenario, directory = sys.argv[1:]
    sys.path.insert(0, root)
    from PySide6.QtCore import QPoint, Qt, QTimer
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QListWidget, QMessageBox
    from core.elements_data import ALL_SYMBOLS
    from ui.qt.workbench import MainWindow

    def native_only():
        forbidden = {'core.styles', 'core.options', 'core.scientific', 'core.ptable',
                     'ui.legacy_workbench'}
        loaded = forbidden.intersection(sys.modules)
        loaded.update(name for name in sys.modules if name == 'tkinter' or name.startswith('tkinter.'))
        assert not loaded, sorted(loaded)

    native_only()
    directory = Path(directory)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    callbacks = []

    def exception_hook(*exc):
        callbacks.append(''.join(traceback.format_exception(*exc)))
        sys.__excepthook__(*exc)

    sys.excepthook = exception_hook

    def unexpected_dialog(*args, **kwargs):
        raise AssertionError('Unexpected QMessageBox: ' + repr(args))

    for name in ('question', 'warning', 'critical', 'information'):
        setattr(QMessageBox, name, unexpected_dialog)
    window = MainWindow(user_dir=directory / 'user', start_preview=False, recover=False)
    window.show()
    app.processEvents()

    def pump_until(predicate, description, timeout=60, allow_error=False):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            assert not callbacks, '\n'.join(callbacks)
            if not allow_error:
                assert not window.status.text().startswith('未完成：'), window.status.text()
            if predicate():
                return
            time.sleep(.005)
        raise AssertionError(description + ' timed out: ' + window.status.text())

    def preview():
        pump_until(lambda: not window.preview_timer.isActive() and not window.preview_job.active
                   and window.preview.source_image is not None and not window.preview.is_stale,
                   'native preview worker')
        assert window.preview_job.process is not None and window.preview_job.process.is_alive()
        assert window.preview_job.process.pid != __import__('os').getpid()
        image = window.preview.source_image
        assert not image.isNull() and image.width() > 100 and image.height() > 100
        assert len(window.preview.pixel_hits) == 118
        assert set(window.preview.pixel_hits.values()) == set(ALL_SYMBOLS)

    def demo():
        window.demo()
        assert window.session.data == {'Ti': '-0.640', 'Ni': '0.820', 'Fe': '0.350', 'O': '0.160'}
        assert window.preview.is_stale and window.preview_timer.isActive()
        preview()

    def table_index(symbol):
        return window.table_model.index(ALL_SYMBOLS.index(symbol), 2)

    try:
        assert not callbacks, callbacks
        assert window.session.data == {} and not window.session.dirty
        assert window.preview.source_image is None and not window.preview_timer.isActive()
        assert window.preview_job.process is None and window.export_job.process is None
        assert window.table_model.rowCount() == 118 and window.sheets.count() == 1
        assert window.session.user_dir == (directory / 'user').resolve()
        native_only()

        if scenario == 'startup':
            window.copy_request()
            request = json.loads(app.clipboard().text())
            assert request['api_version'] == 2 and request['action'] == 'render'
            assert request['plot'] == window.session.plot and request['data'] == {}
            assert window.preview_job.process is None and window.export_job.process is None
            assert not window.preview_timer.isActive()

        elif scenario == 'startup_commands':
            registry = window.registry
            assert 'export' in {c.id for c in registry.search('PNG')}
            assert 'settings' in {c.id for c in registry.search('字体')}
            assert 'demo' in {c.id for c in registry.search('演示')}
            assert not registry.search('nonexistent-command-82901')
            assert registry.actions['save'].shortcut().toString() == 'Ctrl+S'
            assert window.ribbon.count() >= 7
            invoked = []

            def execute_search():
                try:
                    palette = app.activeModalWidget()
                    assert palette is not None and palette.windowTitle() == '搜索功能'
                    search = palette.findChild(QLineEdit)
                    results = palette.findChild(QListWidget)
                    assert results.count() == 1
                    assert results.item(0).data(Qt.ItemDataRole.UserRole) == 'demo'
                    invoked.append(True)
                    QTest.keyClick(search, Qt.Key.Key_Return)
                except Exception:
                    callbacks.append(traceback.format_exc())
                    if app.activeModalWidget():
                        app.activeModalWidget().reject()

            QTimer.singleShot(0, execute_search)
            registry.palette('演示')
            assert invoked and not callbacks, callbacks
            assert window.session.data['Ti'] == '-0.640'
            preview()
            before = window.session.document
            window.resize(1000, 740)
            app.processEvents()
            assert not window.resources_dock.isVisible()
            window.resize(1440, 930)
            app.processEvents()
            assert window.resources_dock.isVisible()
            assert window.session.document == before

        elif scenario == 'graphical_edit_roundtrip':
            demo()
            canvas = window.preview
            box = next(box for box, symbol in canvas.pixel_hits.items() if symbol == 'Ti')
            image = canvas.source_image
            scale = min(canvas.width() / image.width(), canvas.height() / image.height())
            point = QPoint(round((canvas.width() - image.width() * scale) / 2 + (box[0] + box[2]) / 2 * scale),
                           round((canvas.height() - image.height() * scale) / 2 + (box[1] + box[3]) / 2 * scale))
            assert canvas.rect().contains(point)
            QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=point)
            assert window.selected_symbol == 'Ti' and window.inspector.symbol == 'Ti'
            assert window.formula_value.text() == '-0.640'
            assert window.table.currentIndex().row() == ALL_SYMBOLS.index('Ti')
            end = point + QPoint(9, -7)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=point)
            QTest.mouseMove(canvas, end)
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
            override = window.session.plot['element_overrides']['Ti']
            assert override['value_dx'] > 0 and override['value_dy'] > 0
            moved = dict(override)
            window.registry.actions['undo'].trigger()
            assert 'Ti' not in window.session.plot['element_overrides']
            window.registry.actions['redo'].trigger()
            assert window.session.plot['element_overrides']['Ti'] == moved
            preview()
            # Disabling graph editing prevents the same drag from changing data.
            window.registry.actions['edit'].trigger()
            assert not window.registry.actions['edit'].isChecked()
            before = window.session.document
            canvas.labelMoved.emit('Ti', .2, .1)
            assert window.session.document == before
            window.registry.actions['edit'].trigger()
            window.registry.actions['labels'].trigger()
            assert window.session.plot['kind'] == 'labels'
            window.select_element('Ti', from_table=True)
            window.inspector.value.setFocus()
            window.inspector.value.selectAll()
            QTest.keyClicks(window.inspector.value, 'site-A')
            assert window.inspector.dirty
            assert window.inspector.flush()
            assert window.session.data['Ti'] == 'site-A'
            assert window.table_model.data(table_index('Ti')) == 'site-A'
            window.history(-1)
            assert window.session.data['Ti'] == '-0.640'
            window.history(1)
            assert window.session.data['Ti'] == 'site-A'
            project = directory / 'qt-roundtrip.ptproj'
            assert window.save_project(project), window.status.text()
            saved = window.session.document
            assert not window.session.dirty and project.is_file()
            document = json.loads(project.read_text(encoding='utf-8'))
            assert document['schema'] == 2 and document['current']['data']['Ti'] == 'site-A'
            assert document['current']['plot']['element_overrides']['Ti']['value_dx'] > 0
            window.new_project()
            assert window.session.data == {} and not window.selected_symbol
            assert window.open_project(project), window.status.text()
            assert window.session.document == saved and not window.session.dirty
            assert window.table_model.data(table_index('Ti')) == 'site-A'
            preview()

        elif scenario == 'invalid_table':
            demo()
            index = table_index('Ti')
            before = window.session.document
            assert window.table_model.setData(index, 'not-a-number')
            assert window.table_model.pending == {'Ti': 'not-a-number'}
            assert window.table_model.data(index) == 'not-a-number'
            assert window.session.document == before and window.preview.is_stale
            assert window.status.text().startswith('未完成：')
            project = directory / 'must-not-save.ptproj'
            assert not window.save_project(project) and not project.exists()
            window.output_dir = str(directory / 'must-not-export')
            window.export()
            assert window.export_job.process is None and window.last_output is None
            assert not window.preview_timer.isActive()
            window.registry.actions['undo'].trigger()
            assert not window.table_model.pending and window.session.document == before
            assert window.table_model.data(index) == '-0.640'
            preview()
            assert window.table_model.setData(index, '0.1250')
            assert not window.table_model.pending and window.session.data['Ti'] == '0.1250'
            window.registry.actions['undo'].trigger()
            assert window.session.data['Ti'] == '-0.640'
            window.registry.actions['redo'].trigger()
            assert window.session.data['Ti'] == '0.1250'
            preview()

        elif scenario == 'excel_groups':
            from zipfile import ZipFile
            from ui.qt.excel_dialog import ExcelImportDialog
            namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            office = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
            package = 'http://schemas.openxmlformats.org/package/2006/relationships'
            workbook = directory / 'groups.xlsx'
            parts = {
                '_rels/.rels': f'<Relationships xmlns="{package}"><Relationship Id="r1" Type="{office}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
                'xl/workbook.xml': f'<workbook xmlns="{namespace}" xmlns:r="{office}"><sheets><sheet name="Values" sheetId="1" r:id="r1"/></sheets></workbook>',
                'xl/_rels/workbook.xml.rels': f'<Relationships xmlns="{package}"><Relationship Id="r1" Type="{office}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
                'xl/worksheets/sheet1.xml': f'<worksheet xmlns="{namespace}"><sheetData>'
                    '<row r="1"><c r="B1" t="inlineStr"><is><t>H</t></is></c><c r="C1" t="inlineStr"><is><t>He</t></is></c></row>'
                    '<row r="2"><c r="A2" t="inlineStr"><is><t>first</t></is></c><c r="B2"><v>0</v></c><c r="C2"><v>-0.5</v></c></row>'
                    '<row r="3"><c r="A3" t="inlineStr"><is><t>second</t></is></c><c r="B3"><v>0.2</v></c><c r="C3"><v>0.8</v></c></row>'
                    '</sheetData></worksheet>',
            }
            with ZipFile(workbook, 'w') as archive:
                for name, text in parts.items():
                    archive.writestr(name, text)
            phase = ['loading']
            driver = QTimer()
            driver.setInterval(10)
            deadline = time.monotonic() + 20

            def drive_import():
                dialog = app.activeModalWidget()
                try:
                    assert time.monotonic() < deadline, 'Excel modal timed out'
                    if not isinstance(dialog, ExcelImportDialog):
                        return
                    if phase[0] == 'loading' and not dialog._loading:
                        dialog.elements_range.setText('B1:C1')
                        dialog.conditions_range.setText('A2:A3')
                        dialog.values_range.setText('B2:C3')
                        dialog.preview_button.click()
                        phase[0] = 'reading'
                    elif phase[0] == 'reading' and not dialog._busy:
                        assert dialog.commit_button.isEnabled(), dialog.status.text() + dialog.summary.toPlainText()
                        dialog.commit_button.click()
                        phase[0] = 'committed'
                        driver.stop()
                except Exception:
                    callbacks.append(traceback.format_exc())
                    driver.stop()
                    if dialog:
                        dialog.reject()

            driver.timeout.connect(drive_import)
            driver.start()
            try:
                assert window.import_file(str(workbook))
            finally:
                driver.stop()
            assert not callbacks and phase[0] == 'committed', callbacks
            assert window.sheets.count() == 2 and window.session.data == {'H': 0, 'He': -.5}
            first_id = window.session.collection.active_dataset_id
            assert window.table_model.setData(table_index('H'), '0.1250')
            window.sheets.setCurrentIndex(1)
            second_id = window.session.collection.active_dataset_id
            assert first_id != second_id and window.session.data == {'H': .2, 'He': .8}
            window.sheets.setCurrentIndex(0)
            assert window.session.data == {'H': '0.1250', 'He': -.5}
            assert window.table_model.data(table_index('H')) == '0.1250'
            # Invalid pending data must prevent switching, then undo discards it.
            window.table_model.setData(table_index('H'), 'invalid')
            window.sheets.setCurrentIndex(1)
            assert window.session.collection.active_dataset_id == first_id
            assert window.sheets.currentIndex() == 0 and window.table_model.pending
            window.history(-1)
            assert not window.table_model.pending and window.session.data['H'] == '0.1250'
            window.sheets.setCurrentIndex(1)
            assert window.session.collection.active_dataset_id == second_id
            project = directory / 'groups.ptproj'
            assert window.save_project(project)
            saved = window.session.document
            window.new_project()
            assert window.open_project(project) and window.session.document == saved
            assert window.sheets.count() == 2 and window.sheets.currentIndex() == 1
            window.sheets.setCurrentIndex(0)
            assert window.session.data['H'] == '0.1250'
            preview()

        elif scenario.startswith('export_'):
            fmt = scenario.removeprefix('export_')
            # Export must work even if a user cancels a pending preview.
            # Other scenarios exercise the complete displayed-preview pipeline.
            window.demo()
            window.cancel_jobs()
            assert window.session.data['Ti'] == '-0.640'
            window.change_plot({'font': 'DejaVu Sans', 'dpi': 72, 'figsize': [8, 5], 'bbox_tight': False})
            window.cancel_jobs()
            window.output_dir = str(directory / 'exports')
            window.output_base = 'qt-native'
            window.output_format = fmt
            window.export()
            assert window.export_job.active
            pump_until(lambda: not window.export_job.active and window.last_output is not None,
                       'real ' + fmt + ' export')
            path = Path(window.last_output)
            assert path.parent == directory / 'exports' and path.suffix == '.' + fmt
            assert path.name.startswith('qt-native_') and path.stat().st_size > 1000
            raw = path.read_bytes()
            if fmt == 'png':
                image = QImage(str(path))
                assert not image.isNull() and (image.width(), image.height()) == (576, 360)
                assert raw.startswith(b'\x89PNG\r\n\x1a\n')
            elif fmt == 'pdf':
                assert raw.startswith(b'%PDF-') and b'%%EOF' in raw[-1024:]
            else:
                from xml.etree import ElementTree
                assert ElementTree.parse(path).getroot().tag == '{http://www.w3.org/2000/svg}svg'
            assert '已导出 1 张图片' in window.status.text()
            window.last_output = None
            window.export()
            pump_until(lambda: not window.export_job.active and window.last_output is not None,
                       'repeat export without overwriting')
            assert Path(window.last_output) != path and path.read_bytes() == raw
            assert len(list(path.parent.glob('*.' + fmt))) == 2

        else:
            raise AssertionError('Unknown scenario: ' + scenario)
        native_only()
        assert not callbacks, '\n'.join(callbacks)
    finally:
        pids = {job.process.pid for job in (window.preview_job, window.export_job) if job.process}
        window.shutdown()
        assert window._closed
        assert not window.preview_timer.isActive() and not window.poll_timer.isActive()
        assert window.preview_job.process is None and window.export_job.process is None
        assert not pids.intersection(child.pid for child in multiprocessing.active_children())
        assert window.close()  # shutdown bypasses dirty-project prompts.
        app.processEvents()
    print('QT_WORKBENCH_OK:' + scenario)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
'''


@pytest.mark.parametrize('scenario', [
    'startup', 'startup_commands', 'graphical_edit_roundtrip', 'invalid_table', 'excel_groups',
    'export_svg', 'export_png', 'export_pdf',
])
def test_qt_workbench_real_integration(tmp_path, scenario):
    script = tmp_path / 'qt_workbench_scenario.py'
    script.write_text(_SCRIPT, encoding='utf-8')
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_SCALE_FACTOR='1',
               PTT_USER_DIR=str(tmp_path / 'user'), PYTHONIOENCODING='utf-8')
    env.pop('PTT_SMOKE', None)
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, str(script), str(ROOT), scenario, str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=180,
    )
    assert result.returncode == 0, f'{scenario}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}'
    assert 'QT_WORKBENCH_OK:' + scenario in result.stdout
