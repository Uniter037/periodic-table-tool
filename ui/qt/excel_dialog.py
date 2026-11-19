"""Asynchronous, read-only Excel selection preview for the Qt desktop."""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from application.excel_import import ExcelImportService


class _ResultSignals(QObject):
    completed = Signal(int, object, str)


class _ReadTask(QRunnable):
    """Pool owns the task; neither it nor its signals own any GUI object.

    A deleted dialog is automatically disconnected from completed. The global
    pool outlives dialogs (including when their parent is deleted) and waits for
    running tasks on application shutdown, without a child QThread to destroy.
    """

    def __init__(self, token, *, factory=None, path=None, service=None, parameters=None):
        super().__init__()
        self.signals = _ResultSignals()
        self.token = token
        self.factory, self.path = factory, path
        self.service, self.parameters = service, parameters

    def run(self):
        try:
            if self.service is None:
                service = self.factory(self.path)
                result = (service, list(service.sheets))  # sheets is a property.
            else:
                result = self.service.preview(*self.parameters)
        except Exception as exc:
            self.signals.completed.emit(self.token, None, str(exc) or type(exc).__name__)
        else:
            self.signals.completed.emit(self.token, result, '')


class ExcelImportDialog(QDialog):
    def __init__(self, path, parent=None, on_commit=None):
        super().__init__(parent)
        self.setWindowTitle('Excel 导入向导')
        self.resize(600, 510)
        self._on_commit = on_commit
        self._service = None
        self._task = None
        self._loading = True
        self._busy = False
        self._committing = False
        self._closed = False
        self._revision = 0
        self._preview_revision = None
        self._preview_parameters = None
        self._result = None

        layout = QVBoxLayout(self)
        source = QLabel(f'文件：{path}')
        source.setWordWrap(True)
        layout.addWidget(source)
        form = QFormLayout()
        self.sheet = QComboBox()
        self.sheet.setObjectName('sheet')
        self.elements_range = QLineEdit('B1:AG1')
        self.conditions_range = QLineEdit('A2:A6')
        self.values_range = QLineEdit('B2:AG6')
        self.direction = QComboBox()
        self.direction.addItem('按行：每行一组条件，元素在首行', 'matrix_rows')
        self.direction.addItem('按列：每列一组条件，元素在首列', 'matrix_columns')
        for key, label, widget in (
            ('sheet', '工作表', self.sheet),
            ('elements_range', '元素区域', self.elements_range),
            ('conditions_range', '条件区域', self.conditions_range),
            ('values_range', '数值区域', self.values_range),
            ('direction', '矩阵方向', self.direction),
        ):
            widget.setObjectName(key)
            form.addRow(label, widget)
        self.elements_range.setPlaceholderText('例如 B1:C1，内容为 H、He 等元素符号')
        self.conditions_range.setPlaceholderText('例如 A2:A3，内容为样品或条件名称')
        self.values_range.setPlaceholderText('例如 B2:C3，数值或文本标注矩阵')
        layout.addLayout(form)
        self.range_hint = QLabel()
        self.range_hint.setWordWrap(True)
        layout.addWidget(self.range_hint)
        self.status = QLabel('正在读取工作表…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlaceholderText('预览后显示数据组数量、记录数量及选区诊断。')
        layout.addWidget(self.summary, 1)
        actions = QHBoxLayout()
        self.preview_button = QPushButton('预览')
        self.commit_button = QPushButton('确认导入')
        self.cancel_button = QPushButton('取消')
        # Enter must not silently accept an unreviewed mapping.
        for button in (self.preview_button, self.commit_button, self.cancel_button):
            button.setAutoDefault(False)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.preview_button.clicked.connect(self._preview)
        self.commit_button.clicked.connect(self._commit)
        self.cancel_button.clicked.connect(self.reject)
        for edit in (self.elements_range, self.conditions_range, self.values_range):
            edit.textChanged.connect(self._invalidate)
        self.sheet.currentIndexChanged.connect(self._invalidate)
        self.direction.currentIndexChanged.connect(self._invalidate)
        self._update_hint()
        self._sync_actions()
        self._start_task(_ReadTask(0, factory=ExcelImportService, path=path))

    @property
    def preview_result(self):
        """Return a detached copy; only a current, validated preview is exposed."""
        return deepcopy(self._result) if self._is_current() else None

    def _parameters(self):
        return (self.sheet.currentText(), self.elements_range.text().strip(),
                self.conditions_range.text().strip(), self.values_range.text().strip(),
                self.direction.currentData())

    def _is_current(self):
        return (not self._closed and not self._loading and not self._busy
                and self._result is not None and self._preview_revision == self._revision
                and self._preview_parameters == self._parameters())

    def _sync_actions(self):
        self.preview_button.setEnabled(
            not self._closed and not self._loading and not self._busy and not self._committing
            and self._service is not None and all(self._parameters()))
        self.commit_button.setEnabled(self._is_current() and not self._committing)

    def _update_hint(self):
        if self.direction.currentData() == 'matrix_rows':
            self.range_hint.setText('按行示例：元素 B1:C1（H、He）；条件 A2:A3；数值 B2:C3。'
                                    '每行生成一个数据组，三个区域须尺寸对应。')
        else:
            self.range_hint.setText('按列示例：元素 A2:A3（H、He）；条件 B1:C1；数值 B2:C3。'
                                    '每列生成一个数据组，三个区域须尺寸对应。')

    @Slot()
    def _invalidate(self):
        self._revision += 1
        self._result = None
        self._preview_revision = self._preview_parameters = None
        self.summary.clear()
        self._update_hint()
        if not self._loading:
            self.status.setText('参数已更改，当前读取结果将作废；完成后请重新预览。' if self._busy
                                else '请预览当前设置。')
        self._sync_actions()

    def _start_task(self, task):
        self._task = task
        task.signals.completed.connect(self._task_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(task)

    @Slot()
    def _preview(self):
        if not self.preview_button.isEnabled():
            return
        self._invalidate()
        self._busy = True
        self.status.setText('正在读取选区并生成预览…')
        self._sync_actions()
        self._start_task(_ReadTask(self._revision, service=self._service,
                                   parameters=self._parameters()))

    @Slot(int, object, str)
    def _task_finished(self, token, result, error):
        self._task = None
        if self._closed:
            return
        if self._loading:
            self._loading = False
            if error:
                self.status.setText('无法读取工作簿：' + error)
            else:
                self._service, sheets = result
                self.sheet.addItems(sheets)
                self.status.setText('请填写选区并预览。' if sheets else '工作簿没有可用的工作表。')
            self._sync_actions()
            return
        self._busy = False
        if token != self._revision:
            self.status.setText('参数已更改，旧预览已作废，请重新预览。')
        elif error:
            self.status.setText('预览失败：' + error)
        else:
            try:
                self._show_preview(result)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                self._result = None
                self.status.setText('预览结果无效：' + str(exc))
        self._sync_actions()

    def _show_preview(self, result):
        if not isinstance(result, dict):
            raise ValueError('应返回预览字典。')
        datasets, diagnostics = result.get('datasets'), result.get('diagnostics')
        if not isinstance(datasets, list) or not isinstance(diagnostics, list):
            raise ValueError('datasets 和 diagnostics 须为列表。')
        lines = [f'数据组：{len(datasets)}；诊断：{len(diagnostics)}']
        stats = result.get('stats') or {}
        if stats:
            lines.append(f'记录：{stats.get("record_count", 0)}；数值：{stats.get("number_count", 0)}；'
                         f'文本：{stats.get("text_count", 0)}；空值：{stats.get("missing_count", 0)}')
        has_error = False
        for item in diagnostics:
            severity = str(item.get('severity', '')).lower()
            has_error |= severity == 'error'
            label = {'error': '错误', 'warning': '警告', 'info': '提示'}.get(severity, severity)
            lines.append(f'{label} {item.get("code", "")}：{item.get("message", "")}')
        self.summary.setPlainText('\n'.join(lines))
        if result.get('status') == 'ready' and datasets and not has_error:
            self._result = deepcopy(result)
            self._preview_revision = self._revision
            self._preview_parameters = self._parameters()
            self.status.setText('预览有效，请检查摘要后确认导入。')
        else:
            self.status.setText('预览含错误或没有可导入的数据组，请修改选区后重新预览。')

    @Slot()
    def _commit(self):
        if not self._is_current() or self._committing:
            self._sync_actions()
            return
        self._committing = True
        self._sync_actions()
        try:
            if self._on_commit is not None:
                self._on_commit(deepcopy(self._result))
        except Exception as exc:
            self.status.setText('导入失败：' + (str(exc) or type(exc).__name__))
        else:
            self._closed = True
            super().accept()
        finally:
            self._committing = False
            if not self._closed:
                self._sync_actions()

    def accept(self):
        # The QDialog API follows the same validation as the confirm button.
        self._commit()

    def done(self, result):
        # Tasks have application lifetime, not dialog/parent lifetime. Results
        # are ignored if a still-alive rejected dialog receives its queued signal.
        self._closed = True
        self._result = None
        self._sync_actions()
        super().done(result)
