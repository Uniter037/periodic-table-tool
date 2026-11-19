"""Qt import workflow, asynchronous invalidation and native reader integration."""
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QDialog
import pytest

from ui.qt import excel_dialog


def ready(**changes):
    return {'status': 'ready', 'datasets': [{'id': 'dataset'}], 'diagnostics': [],
            'stats': {'record_count': 2, 'number_count': 1, 'missing_count': 1}, **changes}


@pytest.fixture(scope='module')
def qt_app():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    yield app


def wait(qt_app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    pytest.fail('Qt condition timed out')


@pytest.fixture
def dialogs(qt_app):
    instances = []

    def create(*args, **kwargs):
        dialog = excel_dialog.ExcelImportDialog(*args, **kwargs)
        instances.append(dialog)
        dialog.show()
        return dialog

    yield create
    # Every test releases its explicit gates in finally before this cleanup.
    for dialog in instances:
        dialog.reject()
        dialog.deleteLater()
    assert QThreadPool.globalInstance().waitForDone(10000), 'Preview task failed to finish'
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qt_app.processEvents()


@pytest.fixture
def fake_service(monkeypatch):
    class Service:
        instances = []
        output = ready()
        failure = None

        def __init__(self, path):
            self.path = path
            self.init_thread = threading.get_ident()
            self.calls = []
            self.threads = []
            self.instances.append(self)

        @property
        def sheets(self):
            return ['测量', '其他']

        def preview(self, *parameters):
            self.calls.append(parameters)
            self.threads.append(threading.get_ident())
            if self.failure:
                raise self.failure
            return deepcopy(self.output)

    monkeypatch.setattr(excel_dialog, 'ExcelImportService', Service)
    return Service


def loaded(qt_app, dialog):
    wait(qt_app, lambda: not dialog._loading)


def previewed(qt_app, dialog):
    dialog.preview_button.click()
    wait(qt_app, lambda: not dialog._busy)


def test_property_sheets_chinese_form_background_read_and_commit(qt_app, dialogs, fake_service):
    committed = []
    gui_thread = threading.get_ident()
    dialog = dialogs('sample.xlsx', on_commit=lambda value: committed.append((value, threading.get_ident())))
    assert not dialog.commit_button.isEnabled()
    dialog.accept()
    assert not committed
    loaded(qt_app, dialog)
    assert dialog.sheet.count() == 2 and dialog.sheet.currentText() == '测量'
    assert 'Excel 导入' in dialog.windowTitle()
    assert 'B1:C1' in dialog.range_hint.text()
    previewed(qt_app, dialog)
    service = fake_service.instances[0]
    assert service.init_thread != gui_thread and service.threads[0] != gui_thread
    assert service.calls == [('测量', 'B1:AG1', 'A2:A6', 'B2:AG6', 'matrix_rows')]
    assert dialog.commit_button.isEnabled()
    assert '数据组：1' in dialog.summary.toPlainText() and '空值：1' in dialog.summary.toPlainText()
    snapshot = dialog.preview_result
    snapshot['datasets'].clear()
    assert dialog.preview_result['datasets']
    dialog.commit_button.click()
    assert committed == [(fake_service.output, gui_thread)]
    assert dialog.result() == QDialog.DialogCode.Accepted and not dialog.isVisible()


@pytest.mark.parametrize('field', ['sheet', 'elements_range', 'conditions_range', 'values_range', 'direction'])
def test_every_parameter_invalidates_current_preview(qt_app, dialogs, fake_service, field):
    committed = []
    dialog = dialogs('sample.xlsx', on_commit=committed.append)
    loaded(qt_app, dialog)
    previewed(qt_app, dialog)
    assert dialog.commit_button.isEnabled()
    widget = getattr(dialog, field)
    if field in ('sheet', 'direction'):
        widget.setCurrentIndex(1)
    else:
        old = widget.text()
        widget.setText('D1:D3')
        widget.setText(old)  # Changing back still requires a new preview.
    assert not dialog.commit_button.isEnabled() and dialog.preview_result is None
    dialog.accept()
    assert not committed and dialog.isVisible()
    previewed(qt_app, dialog)
    assert dialog.commit_button.isEnabled()
    if field == 'direction':
        assert fake_service.instances[0].calls[-1][-1] == 'matrix_columns'
        assert 'A2:A3' in dialog.range_hint.text()


def test_slow_initial_inspection_and_preview_keep_event_loop_responsive(qt_app, dialogs, monkeypatch):
    init_started, init_release = threading.Event(), threading.Event()
    preview_started, preview_release = threading.Event(), threading.Event()

    class SlowService:
        def __init__(self, path):
            init_started.set()
            assert init_release.wait(5)

        @property
        def sheets(self):
            return ['Sheet']

        def preview(self, *args):
            preview_started.set()
            assert preview_release.wait(5)
            return ready()

    monkeypatch.setattr(excel_dialog, 'ExcelImportService', SlowService)
    ticks = []
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    try:
        dialog = dialogs('slow.xlsx')
        wait(qt_app, lambda: init_started.is_set() and len(ticks) >= 3)
        assert dialog._loading and not dialog.preview_button.isEnabled()
        init_release.set()
        loaded(qt_app, dialog)
        dialog.preview_button.click()
        before = len(ticks)
        wait(qt_app, lambda: preview_started.is_set() and len(ticks) >= before + 3)
        assert dialog._busy and not dialog.commit_button.isEnabled()
        dialog.values_range.setText('B2:C2')
        preview_release.set()
        wait(qt_app, lambda: not dialog._busy)
        assert dialog.preview_result is None and not dialog.commit_button.isEnabled()
        assert '作废' in dialog.status.text()
        previewed(qt_app, dialog)
        assert dialog.commit_button.isEnabled()
    finally:
        init_release.set()
        preview_release.set()
        timer.stop()


@pytest.mark.parametrize('payload', [
    ready(status='invalid'), ready(datasets=[]),
    ready(diagnostics=[{'severity': 'error', 'code': 'BAD', 'message': '选区有错误'}]),
    {'status': 'ready', 'datasets': 'invalid', 'diagnostics': []}, None,
])
def test_invalid_or_malformed_preview_cannot_commit(qt_app, dialogs, fake_service, payload):
    fake_service.output = payload
    committed = []
    dialog = dialogs('sample.xlsx', on_commit=committed.append)
    loaded(qt_app, dialog)
    previewed(qt_app, dialog)
    assert not dialog.commit_button.isEnabled() and dialog.preview_result is None
    dialog.accept()
    assert not committed and dialog.isVisible()
    assert dialog.status.text()


def test_warning_preview_can_commit_and_callback_failure_keeps_dialog_open(qt_app, dialogs, fake_service):
    fake_service.output = ready(diagnostics=[{'severity': 'warning', 'code': 'CACHE', 'message': '使用公式缓存'}])
    calls = []

    def commit(value):
        calls.append(deepcopy(value))
        if len(calls) == 1:
            value['datasets'].clear()
            raise ValueError('保存失败，请重试')

    dialog = dialogs('sample.xlsx', on_commit=commit)
    loaded(qt_app, dialog)
    previewed(qt_app, dialog)
    assert '警告 CACHE' in dialog.summary.toPlainText()
    dialog.commit_button.click()
    assert dialog.isVisible() and dialog.commit_button.isEnabled()
    assert '保存失败，请重试' in dialog.status.text()
    assert dialog.preview_result['datasets']
    dialog.commit_button.click()
    assert len(calls) == 2 and calls[0] == calls[1]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_preview_exception_clears_previous_result_and_allows_retry(qt_app, dialogs, fake_service):
    dialog = dialogs('sample.xlsx')
    loaded(qt_app, dialog)
    previewed(qt_app, dialog)
    fake_service.failure = OSError('文件暂不可读')
    previewed(qt_app, dialog)
    assert '文件暂不可读' in dialog.status.text() and not dialog.commit_button.isEnabled()
    assert dialog.preview_result is None and dialog.preview_button.isEnabled()
    fake_service.failure = None
    previewed(qt_app, dialog)
    assert dialog.commit_button.isEnabled()


def test_reject_while_reading_does_not_apply_late_preview(qt_app, dialogs, monkeypatch):
    started, release = threading.Event(), threading.Event()

    class Service:
        def __init__(self, path):
            pass

        @property
        def sheets(self):
            return ['Sheet']

        def preview(self, *args):
            started.set()
            assert release.wait(5)
            return ready()

    monkeypatch.setattr(excel_dialog, 'ExcelImportService', Service)
    commits = []
    dialog = dialogs('sample.xlsx', on_commit=commits.append)
    try:
        loaded(qt_app, dialog)
        dialog.preview_button.click()
        wait(qt_app, started.is_set)
        dialog.cancel_button.click()
        assert not dialog.isVisible() and dialog.result() == QDialog.DialogCode.Rejected
    finally:
        release.set()
    wait(qt_app, lambda: QThreadPool.globalInstance().activeThreadCount() == 0)
    qt_app.processEvents()
    assert dialog.preview_result is None and not dialog.commit_button.isEnabled()
    dialog.accept()
    assert not commits and dialog.result() == QDialog.DialogCode.Rejected


@pytest.mark.parametrize('error', [None, OSError('无法读取文件')])
def test_no_sheets_or_initial_read_failure_is_visible(qt_app, dialogs, monkeypatch, error):
    class EmptyService:
        def __init__(self, path):
            if error:
                raise error

        @property
        def sheets(self):
            return []

    monkeypatch.setattr(excel_dialog, 'ExcelImportService', EmptyService)
    dialog = dialogs('bad.xlsx')
    loaded(qt_app, dialog)
    assert not dialog.preview_button.isEnabled() and not dialog.commit_button.isEnabled()
    assert ('无法读取' if error else '没有可用') in dialog.status.text()


@pytest.mark.parametrize('direction', ['matrix_rows', 'matrix_columns'])
def test_real_synthetic_xlsx_preview_and_commit(qt_app, dialogs, tmp_path, direction):
    from application.excel_import import legacy_data
    from test_excel_import_service import _row, _sheet, _text, _workbook

    if direction == 'matrix_rows':
        contents = _sheet(
            _row(1, _text('B1', 'H'), _text('C1', 'He')),
            _row(2, _text('A2', '样品甲'), '<c r="B2"><v>0</v></c>', '<c r="C2"><v>-2.5</v></c>'),
            _row(3, _text('A3', '样品乙'), '<c r="B3"><v>3</v></c>'))
        ranges = ('B1:C1', 'A2:A3', 'B2:C3')
    else:
        contents = _sheet(
            _row(1, _text('B1', '样品甲'), _text('C1', '样品乙')),
            _row(2, _text('A2', 'H'), '<c r="B2"><v>0</v></c>', '<c r="C2"><v>3</v></c>'),
            _row(3, _text('A3', 'He'), '<c r="B3"><v>-2.5</v></c>'))
        ranges = ('A2:A3', 'B1:C1', 'B2:C3')
    path = _workbook(tmp_path, contents)
    original = path.read_bytes()
    committed = []
    dialog = dialogs(path, on_commit=committed.append)
    loaded(qt_app, dialog)
    assert dialog.sheet.currentText() == 'Values'
    for widget, text in zip((dialog.elements_range, dialog.conditions_range, dialog.values_range), ranges):
        widget.setText(text)
    dialog.direction.setCurrentIndex(dialog.direction.findData(direction))
    previewed(qt_app, dialog)
    assert dialog.commit_button.isEnabled(), dialog.status.text() + dialog.summary.toPlainText()
    dialog.commit_button.click()
    assert len(committed) == 1 and committed[0]['status'] == 'ready'
    assert [legacy_data(dataset) for dataset in committed[0]['datasets']] == [{'H': 0, 'He': -2.5}, {'H': 3}]
    assert committed[0]['stats']['missing_count'] == 1
    assert committed[0]['mapping']['layout'] == direction
    assert path.read_bytes() == original


@pytest.mark.parametrize('phase', ['initial', 'preview'])
def test_parent_destruction_during_task_is_safe_in_subprocess(tmp_path, phase):
    # A Qt lifetime crash must fail this test without taking down the test runner.
    script = tmp_path / 'qt_parent_lifetime.py'
    script.write_text(r'''
import sys, threading, time
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid
from ui.qt import excel_dialog
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
gate, started = threading.Event(), threading.Event()
phase = sys.argv[1]
class Service:
    def __init__(self, path):
        if phase == 'initial':
            started.set()
            assert gate.wait(10)
    @property
    def sheets(self):
        return ['Sheet']
    def preview(self, *args):
        started.set()
        assert gate.wait(10)
        return {'status': 'ready', 'datasets': [{'id': 'data'}], 'diagnostics': []}
excel_dialog.ExcelImportService = Service
parent = QWidget()
commits = []
dialog = excel_dialog.ExcelImportDialog('fake.xlsx', parent, commits.append)
dialog.show()
try:
    deadline = time.monotonic() + 5
    if phase == 'preview':
        while dialog._loading and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        assert not dialog._loading
        dialog.preview_button.click()
    assert started.wait(3)
    parent.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not isValid(parent) and not isValid(dialog)
finally:
    gate.set()
assert QThreadPool.globalInstance().waitForDone(10000)
app.processEvents()
assert not commits
print('LIFETIME_OK')
''', encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONIOENCODING='utf-8')
    env['PYTHONPATH'] = str(root) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run([sys.executable, str(script), phase], cwd=root, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'LIFETIME_OK' in result.stdout
    assert 'QThread: Destroyed' not in result.stderr
