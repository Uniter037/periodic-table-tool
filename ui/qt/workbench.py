"""Qt desktop composition: commands and widgets adapt the application session."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import sys

from PySide6.QtCore import Qt, QTimer, QSize, QByteArray
from PySide6.QtGui import QAction, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QToolBar, QDockWidget, QTreeWidget, QTreeWidgetItem,
    QSplitter, QTabBar, QDialog, QDialogButtonBox, QPlainTextEdit, QComboBox,
    QFormLayout, QCheckBox, QFileDialog, QMessageBox, QInputDialog, QListWidget,
    QAbstractItemView, QStyle, QSizePolicy, QScrollArea,
)

from application.workbench_session import WorkbenchSession, MigrationRequired
from application.plot_presets import PRESETS, preset
from application.plot_service import prepare_plot
from core.document import user_directory, write_document
from core.dataio import parse_data
from core.elements_data import ALL_SYMBOLS
from core.jobs import RenderJob
from core.saver import auto_name
from infrastructure.diagnostics import DiagnosticService, DiagnosticSettings
from .commands import Command, CommandRegistry, Ribbon
from .data_table import ElementTableModel, ElementTable
from .inspector import ElementInspector
from .preview import PreviewCanvas
from .theme import apply_theme
from .icons import command_icon


class MainWindow(QMainWindow):
    def __init__(self, user_dir=None, *, start_preview=True, recover=True):
        super().__init__()
        self.setObjectName('PeriodicTableWorkbench')
        self.setWindowIcon(command_icon('heatmap'))
        self.resize(1440, 930)
        self.setMinimumSize(940, 650)
        self.user_dir = Path(user_dir or user_directory())
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.session = WorkbenchSession(self.user_dir)
        self.preferences_path = self.user_dir / 'workbench-qt.json'
        try:
            self.preferences = json.loads(self.preferences_path.read_text(encoding='utf-8'))
            if not isinstance(self.preferences, dict):
                self.preferences = {}
        except (ValueError, OSError):
            self.preferences = {}
        self.output_dir = str(self.preferences.get('output_dir', Path.cwd() / 'output'))
        self.output_base = str(self.preferences.get('output_base', 'periodic_table'))
        self.output_format = self.preferences.get('format', 'svg')
        self.preview_job, self.export_job = RenderJob(), RenderJob()
        self.last_output = None
        self.export_context = None
        self.selected_symbol = ''
        self._formula_symbol = 'H'
        self._formula_dirty = False
        self._bar_box = None
        self._preview_warnings = []
        self._preview_budget = 0
        self._closed = self._syncing = self._flushing = False
        self._compact = None
        self._settings_panel = None
        self.log_enabled = self.preferences.get('log_enabled', True) is True
        self.log_level = self.preferences.get('log_level', 'INFO')
        if self.log_level not in ('DEBUG', 'INFO', 'WARNING'):
            self.log_level = 'INFO'
        self.diagnostics = DiagnosticService(self.user_dir / 'logs-v2',
            DiagnosticSettings(enabled=self.log_enabled, level=self.log_level))
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(220)
        self.preview_timer.timeout.connect(self._start_preview)
        self.quality_timer = QTimer(self)
        self.quality_timer.setSingleShot(True)
        self.quality_timer.setInterval(400)
        self.quality_timer.timeout.connect(self._refresh_quality)
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(900)
        self.draft_timer.timeout.connect(self._save_draft)
        self.registry = CommandRegistry(self)
        self._register_commands()
        self._build()
        self._restore_preferences()
        self._sync(discard_pending=True)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(60)
        self.diagnostics.record('INFO', 'app.started', 'Qt 绘图工作台已启动')
        if start_preview:
            self.schedule_preview()
        if recover and self.session.draft_path.exists():
            QTimer.singleShot(0, self.recover_draft)

    def _register_commands(self):
        definitions = [
            ('new', '新建项目', '文件', '项目', self.new_project, 'Ctrl+N', '新建', 'SP_FileIcon'),
            ('open', '打开项目', '文件', '项目', self.open_project, 'Ctrl+O', '加载', 'SP_DirOpenIcon'),
            ('save', '保存项目', '文件', '保存', self.save_project, 'Ctrl+S', '存储', 'SP_DialogSaveButton'),
            ('save_as', '另存为', '文件', '保存', lambda: self.save_project(save_as=True), 'Ctrl+Shift+S', '', 'SP_DialogSaveButton'),
            ('output', '输出设置', '文件', '导出', self.output_settings, '', '格式目录DPI', 'SP_FileDialogDetailedView'),
            ('export', '导出图片', '文件', '导出', self.export, 'Ctrl+E', 'SVG PNG PDF', 'SP_ArrowUp'),
            ('undo', '撤销', '开始', '编辑', lambda: self.history(-1), 'Ctrl+Z', '', 'SP_ArrowBack'),
            ('redo', '重做', '开始', '编辑', lambda: self.history(1), 'Ctrl+Y', '', 'SP_ArrowForward'),
            ('demo', '载入示例', '开始', '入门', self.demo, '', '演示', 'SP_ComputerIcon'),
            ('preset', '外观预设', '开始', '样式', self.choose_preset, '', '配色样式', 'SP_FileDialogListView'),
            ('save_preset', '保存预设', '开始', '样式', self.save_preset, '', '', 'SP_DialogSaveButton'),
            ('import', '导入数据', '数据', '输入', self.import_file, 'Ctrl+I', 'Excel xlsx csv txt json', 'SP_DialogOpenButton'),
            ('paste', '粘贴数据', '数据', '输入', self.paste_data, '', '剪贴板', 'SP_FileDialogContentsView'),
            ('batch', '批量导出', '数据', '数据组', self.batch_export, '', '工作表', 'SP_DirIcon'),
            ('heatmap', '热力图', '图形', '图形类型', lambda: self.change_plot({'kind': 'heatmap'}), '', '数值', 'SP_FileDialogDetailedView'),
            ('labels', '文本图', '图形', '图形类型', lambda: self.change_plot({'kind': 'labels'}), '', '标签', 'SP_FileIcon'),
            ('settings', '绘图设置', '图形', '精确设置', self.plot_settings, 'Ctrl+Shift+P', '颜色字体画幅范围刻度布局DPI', 'SP_FileDialogDetailedView'),
            ('colors', '自定义配色', '图形', '配色', lambda: self.plot_settings('配色'), '', '颜色节点RGB', 'SP_FileDialogDetailedView'),
            ('range', '自动范围', '图形', '数据范围', self.auto_range, '', '最小最大中心', 'SP_BrowserReload'),
            ('colorbar', '显示颜色条', '图形', '颜色条', self.toggle_colorbar, '', '色标显示隐藏', 'SP_FileDialogInfoView'),
            ('ticks', '编辑刻度', '图形', '颜色条', lambda: self.plot_settings('色条'), '', '颜色条标注', 'SP_FileDialogListView'),
            ('edit', '标注编辑', '标注', '交互', self.toggle_edit, '', '拖动标注', 'SP_FileIcon'),
            ('reset_element', '恢复元素', '标注', '元素', lambda: self.inspector.reset_overrides(), '', '位置显示', 'SP_BrowserReload'),
            ('inspect', '元素属性', '标注', '元素', lambda: self.inspector_dock.show(), '', '单元素着色范围', 'SP_FileDialogInfoView'),
            ('fit', '适应画布', '视图', '预览', lambda: self.preview.fit(), 'Ctrl+0', '缩放', 'SP_TitleBarMaxButton'),
            ('actual', '实际像素', '视图', '预览', lambda: self.preview.actual_size(), 'Ctrl+1', '清晰1:1', 'SP_TitleBarNormalButton'),
            ('reference', '样图对照', '视图', '预览', self.reference, '', '比较图片', 'SP_FileDialogContentsView'),
            ('resources', '项目资源', '视图', '面板', lambda: self.resources_dock.setVisible(not self.resources_dock.isVisible()), '', '', 'SP_DirIcon'),
            ('layout', '布局与缩放', '视图', '面板', self.view_settings, '', '字号字体大小', 'SP_DesktopIcon'),
            ('reset_layout', '恢复布局', '视图', '面板', self.reset_layout, '', '', 'SP_BrowserReload'),
            ('agent', 'Agent 接口', '自动化', '脚本调用', self.agent_help, '', 'API AI JSON', 'SP_FileDialogInfoView'),
            ('request', '复制绘图请求', '自动化', '脚本调用', self.copy_request, '', 'AI render', 'SP_FileDialogContentsView'),
            ('help', '使用帮助', '帮助', '说明', self.help, 'F1', '', 'SP_DialogHelpButton'),
            ('logs', '日志与排错', '帮助', '诊断', self.show_logs, '', '开关DEBUG', 'SP_FileDialogInfoView'),
            ('diagnostics', '导出诊断包', '帮助', '诊断', self.export_logs, '', '', 'SP_DialogSaveButton'),
        ]
        for key, label, tab, group, callback, shortcut, words, icon_name in definitions:
            icon = command_icon(key) or self.style().standardIcon(getattr(QStyle.StandardPixmap, icon_name))
            self.registry.register(Command(key, label, tab, group, shortcut, words,
                                           key in ('colorbar', 'edit')),
                                   lambda checked=False, fn=callback: fn(), icon)
        self.registry.actions['edit'].setChecked(True)
        self.registry.register(Command('search', '搜索功能', '帮助', '导航', 'Ctrl+K', '命令查找'),
                               lambda: self.registry.palette())

    def _build(self):
        quick = QToolBar('快捷操作', self)
        quick.setObjectName('QuickAccess')
        quick.setMovable(False)
        self.addToolBar(quick)
        brand = QLabel('元素绘图工作台  ')
        brand.setObjectName('Brand')
        quick.addWidget(brand)
        for key in ('save', 'undo', 'redo'):
            quick.addAction(self.registry.actions[key])
        self.document_label = QLabel('未命名项目')
        self.document_label.setObjectName('Muted')
        quick.addWidget(self.document_label)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        quick.addWidget(spacer)
        search = QLineEdit()
        search.setPlaceholderText('搜索功能、参数…   Ctrl+K')
        search.setMaximumWidth(320)
        search.returnPressed.connect(lambda: self.registry.palette(search.text()))
        quick.addWidget(search)
        export = QPushButton('导出图片  ↗')
        export.setObjectName('Primary')
        export.clicked.connect(self.export)
        quick.addWidget(export)
        self.addToolBarBreak()
        ribbon_bar = QToolBar('功能区', self)
        ribbon_bar.setObjectName('RibbonBar')
        ribbon_bar.setMovable(False)
        self.ribbon = Ribbon(self.registry)
        self.ribbon.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ribbon_bar.addWidget(self.ribbon)
        self.addToolBar(ribbon_bar)
        self.ribbon.setCurrentIndex(3)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(8, 6, 8, 0)
        heading = QHBoxLayout()
        title = QLabel('图形预览')
        title.setObjectName('Heading')
        heading.addWidget(title)
        self.edit_label = QLabel('● 标注编辑已开启')
        self.edit_label.setObjectName('Muted')
        heading.addWidget(self.edit_label)
        heading.addStretch()
        for text, method in [('适应', 'fit'), ('−', 'zoom_out'), ('+', 'zoom_in')]:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, name=method: getattr(self.preview, name)())
            heading.addWidget(button)
        preview_layout.addLayout(heading)
        self.preview = PreviewCanvas()
        self.preview.viewportChanged.connect(self.quality_timer.start)
        self.preview.elementSelected.connect(self.select_element)
        self.preview.labelMoved.connect(self.move_label)
        self.preview.colorbarMoved.connect(self.move_colorbar)
        preview_layout.addWidget(self.preview, 1)
        self.splitter.addWidget(preview_panel)
        data_panel = QWidget()
        data_layout = QVBoxLayout(data_panel)
        data_layout.setContentsMargins(8, 2, 8, 8)
        formula = QHBoxLayout()
        formula.addWidget(QLabel('数据表'))
        self.element_name = QComboBox()
        self.element_name.addItems(ALL_SYMBOLS)
        self.element_name.setMinimumWidth(80)
        self.element_name.activated.connect(lambda _: self.select_element(self.element_name.currentText(), from_table=True))
        formula.addWidget(self.element_name)
        formula.addWidget(QLabel('fx'))
        self.formula_value = QLineEdit()
        self.formula_value.setPlaceholderText('输入当前元素数值或标注，Enter 提交')
        self.formula_value.textEdited.connect(self._formula_edited)
        self.formula_value.returnPressed.connect(self.apply_formula)
        formula.addWidget(self.formula_value, 1)
        apply = QPushButton('应用')
        apply.clicked.connect(self.apply_formula)
        formula.addWidget(apply)
        data_layout.addLayout(formula)
        self.table_model = ElementTableModel(self._apply_table, self)
        self.table_model.error.connect(self.error)
        self.table_model.committed.connect(self._table_committed)
        self.table = ElementTable(self.table_model)
        self.table.pasteRequested.connect(self.paste_data)
        self.table.clicked.connect(lambda index: self.select_element(ALL_SYMBOLS[index.row()], from_table=True))
        data_layout.addWidget(self.table, 1)
        self.sheets = QTabBar()
        self.sheets.setExpanding(False)
        self.sheets.setDrawBase(False)
        self.sheets.currentChanged.connect(self._select_sheet)
        data_layout.addWidget(self.sheets)
        self.splitter.addWidget(data_panel)
        self.splitter.setSizes([520, 220])
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        self.setCentralWidget(self.splitter)

        self.resources = QTreeWidget()
        self.resources.setHeaderHidden(True)
        self.resources.itemDoubleClicked.connect(self._resource_activate)
        self.resources_dock = self._dock('项目资源', 'ResourcesDock', self.resources, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.inspector = ElementInspector(self._apply_inspector, self.error)
        self.inspector.issueSelected.connect(self.select_element)
        self.inspector_dock = self._dock('属性', 'InspectorDock', self.inspector, Qt.DockWidgetArea.RightDockWidgetArea)
        self.resizeDocks([self.resources_dock, self.inspector_dock], [190, 300], Qt.Orientation.Horizontal)
        self.status = QLabel('导入数据或载入示例开始绘图')
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.statusBar().addWidget(self.status, 1)
        cancel = QPushButton('取消任务')
        cancel.clicked.connect(self.cancel_jobs)
        self.statusBar().addPermanentWidget(cancel)
        self.zoom_label = QLabel('100%')
        self.statusBar().addPermanentWidget(self.zoom_label)
        self.preview.zoomChanged.connect(self.zoom_label.setText)

    def _dock(self, title, name, widget, area):
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setMinimumWidth(170 if area == Qt.DockWidgetArea.LeftDockWidgetArea else 270)
        self.addDockWidget(area, dock)
        return dock

    def message(self, text):
        self.status.setText(str(text))
        self.status.setToolTip(str(text))

    def error(self, message):
        self.message('未完成：' + str(message))
        self.preview_timer.stop()
        self.preview_job.invalidate()
        self.preview.set_stale(True)
        self.diagnostics.record('ERROR', 'operation.failed', '用户操作未完成')

    def perform(self, operation, *, flush=True):
        if flush and not self.commit_drafts():
            return False
        try:
            operation()
            self._sync()
            self.schedule_preview()
            return True
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.error(exc)
            return False

    def commit_drafts(self):
        if self._flushing:
            return True
        self._flushing = True
        try:
            focused = QApplication.focusWidget()
            if focused and self.table.isAncestorOf(focused):
                focused.clearFocus()
            if not self.table_model.flush() or not self.inspector.flush():
                return False
            if self._formula_dirty:
                symbol, value = self._formula_symbol, self.formula_value.text()
                self.session.patch(data={symbol: value if value.strip() else None})
                self._formula_dirty = False
                self._sync()
                self.schedule_preview()
            if self._settings_panel is not None:
                plot = self._settings_panel.get_plot()
                if plot != self.session.plot:
                    self.session.patch(plot=plot)
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False
        finally:
            self._flushing = False

    def _apply_table(self, patch):
        self.session.patch(data=patch)

    def _table_committed(self):
        self._sync(skip_table=True)
        self.schedule_preview()

    def _apply_inspector(self, plot, data):
        self.session.patch(plot=plot, data=data)
        self._sync()
        self.schedule_preview()

    def _sync(self, *, discard_pending=False, skip_table=False):
        self._syncing = True
        try:
            if discard_pending:
                self._formula_dirty = False
            name = self.session.path.name if self.session.path else '未命名项目'
            dirty = ' ● 未保存' if self.session.dirty else ' ✓ 已保存'
            self.setWindowTitle(name + ' · 元素绘图工作台 Qt · 2.0 Alpha 1')
            self.document_label.setText(name + dirty)
            if not skip_table:
                editing = self.table.state() == QAbstractItemView.State.EditingState
                index = self.table.currentIndex()
                protected = ALL_SYMBOLS[index.row()] if editing and index.isValid() else None
                self.table_model.set_snapshot(self.session.data, discard_pending=discard_pending, protected_symbol=protected)
            self.inspector.set_element(self.selected_symbol, self.session.data, self.session.plot, discard=discard_pending)
            if not self._formula_dirty:
                symbol = self.selected_symbol or self.element_name.currentText()
                self._formula_symbol = symbol
                self.formula_value.setText(str(self.session.data.get(symbol, '')))
            self.registry.actions['colorbar'].setChecked(self.session.plot['show_cbar'])
            self.resources.clear()
            source_root = QTreeWidgetItem(self.resources, ['数据源'])
            snapshot = self.session.collection.snapshot()
            for source in snapshot['sources']:
                QTreeWidgetItem(source_root, [source['display_name']])
            if not snapshot['sources']:
                QTreeWidgetItem(source_root, ['手动输入 / 粘贴数据'])
            group_root = QTreeWidgetItem(self.resources, ['数据组'])
            while self.sheets.count():
                self.sheets.removeTab(0)
            conditions = {row['id']: row['label'] for row in snapshot['conditions']}
            active = snapshot['active_dataset_id']
            for row in snapshot['datasets']:
                label = conditions.get(row['condition_id'], row['id'])
                item = QTreeWidgetItem(group_root, [label])
                item.setData(0, Qt.ItemDataRole.UserRole, ('dataset', row['id']))
                index = self.sheets.addTab(label)
                self.sheets.setTabData(index, row['id'])
                if row['id'] == active:
                    self.sheets.setCurrentIndex(index)
                    self.table_model.caption = label
            if not snapshot['datasets']:
                self.sheets.addTab('当前数据')
            preset_root = QTreeWidgetItem(self.resources, ['外观预设'])
            for key, (label, _) in PRESETS.items():
                item = QTreeWidgetItem(preset_root, [label])
                item.setData(0, Qt.ItemDataRole.UserRole, ('builtin', key))
            user_root = QTreeWidgetItem(self.resources, ['我的预设'])
            for name in self.session.list_presets():
                item = QTreeWidgetItem(user_root, [name])
                item.setData(0, Qt.ItemDataRole.UserRole, ('preset', name))
            self.resources.expandAll()
        finally:
            self._syncing = False

    def schedule_preview(self):
        self.preview.set_stale(True)
        self.preview_job.invalidate()
        self.inspector.set_issues([])
        if not self.export_job.active:
            self.message('修改已提交，正在更新预览…')
        self.preview_timer.start()
        self.draft_timer.start()

    def _start_preview(self):
        # Background rendering must never steal focus or commit a half-typed edit.
        # Explicit commands flush drafts; preview only observes committed state.
        if self.table.state() == QAbstractItemView.State.EditingState:
            self.preview_timer.start(250)
            return
        if self.table_model.pending or self.inspector.dirty or self._formula_dirty:
            return
        try:
            spec, data, warnings = prepare_plot(self.session.plot, self.session.data)
            self._preview_warnings = warnings
            # A display budget, independent from export DPI. Qt supplies physical pixels.
            pixel_width = max(1000, min(2400, round(self.preview.width() * self.preview.devicePixelRatioF())))
            self._preview_budget = pixel_width
            self.preview_job.start({'engine': 'v2', 'mode': 'preview', 'plot': spec.to_dict(),
                                    'data': data, 'preview_max_pixels': pixel_width})
            self.message('正在更新预览…')
        except (ValueError, OSError) as exc:
            self.error(exc)

    def _refresh_quality(self):
        desired = max(1000, min(2400, round(self.preview.width() * self.preview.devicePixelRatioF())))
        if (not self._closed and self.preview.source_image is not None
                and not self.preview.is_stale and desired > self._preview_budget * 1.15):
            self.schedule_preview()

    def _poll(self):
        for job, export in ((self.preview_job, False), (self.export_job, True)):
            event = job.poll()
            if not event:
                continue
            if event[0] == 'error':
                self.error('绘图失败：' + str(event[1]))
            elif event[0] == 'progress' and export:
                self.message(f'正在导出 {event[1]}/{event[2]}…')
            elif event[0] == 'done':
                packet = event[1]
                if export:
                    self._publish(packet)
                else:
                    try:
                        self.preview.show_packet(packet['png'], packet['hits'])
                    except (ValueError, TypeError, OSError) as exc:
                        self.error('预览显示失败：' + str(exc))
                        continue
                    self.preview.set_stale(False)
                    self.preview.set_selected(self.selected_symbol)
                    self._bar_box = packet.get('cbar_box')
                    self.preview.set_colorbar_box(None if self.session.plot['bbox_tight'] else self._bar_box)
                    self.inspector.set_issues(packet.get('layout_issues', []))
                    warnings = self._preview_warnings + packet.get('layout_warnings', [])
                    if not self.export_job.active:
                        self.message('；'.join(warnings) or f'预览已更新 · {len(self.session.data)} 个有效数据 · 点击元素编辑')

    def _save_draft(self):
        if self.session.dirty:
            try:
                self.session.save_draft()
            except (ValueError, OSError) as exc:
                self.error(exc)

    def cancel_jobs(self):
        self.preview_timer.stop()
        self.preview_job.cancel()
        self.export_job.cancel()
        self.message('绘图任务已取消')

    def change_plot(self, patch):
        self.perform(lambda: self.session.patch(plot=patch))

    def toggle_colorbar(self):
        self.change_plot({'show_cbar': self.registry.actions['colorbar'].isChecked()})

    def toggle_edit(self):
        enabled = self.registry.actions['edit'].isChecked()
        self.preview.set_edit_enabled(enabled)
        self.edit_label.setText('● 标注编辑已开启' if enabled else '标注编辑已关闭')

    def select_element(self, symbol, from_table=False):
        if symbol not in ALL_SYMBOLS or (not from_table and self.preview.is_stale):
            return
        if not self.commit_drafts():
            return
        self.selected_symbol = symbol
        self.preview.set_selected(symbol)
        self.inspector.set_element(symbol, self.session.data, self.session.plot)
        self.inspector_dock.show()
        self.element_name.setCurrentText(symbol)
        self._formula_symbol = symbol
        self.formula_value.setText(str(self.session.data.get(symbol, '')))
        if not from_table:
            index = self.table_model.index(ALL_SYMBOLS.index(symbol), 2)
            self.table.setCurrentIndex(index)
            self.table.scrollTo(index)

    def _formula_edited(self, _text):
        self._formula_dirty = True

    def apply_formula(self):
        symbol, value = self.element_name.currentText(), self.formula_value.text()
        if symbol not in ALL_SYMBOLS:
            self.error('请选择有效的元素符号')
            return
        self._formula_symbol = symbol
        self._formula_dirty = True
        if self.commit_drafts():
            self._sync()
            self.schedule_preview()

    def move_label(self, symbol, dx, dy):
        if self.preview.is_stale or not self.registry.actions['edit'].isChecked():
            return
        rows = self.session.plot['element_overrides']
        row = rows.setdefault(symbol, {})
        row.update(value_dx=row.get('value_dx', 0) + dx, value_dy=row.get('value_dy', 0) + dy)
        self.change_plot({'element_overrides': rows})

    def move_colorbar(self, x, y):
        if not self.preview.is_stale and self._bar_box and self.registry.actions['edit'].isChecked():
            self.change_plot({'cbar_box': [x, y, *self._bar_box[2:]]})

    def history(self, direction):
        if self.table_model.pending or self.inspector.dirty or self._formula_dirty:
            self.inspector.timer.stop()
            self._sync(discard_pending=True)
            self.schedule_preview()
            return
        self.perform(self.session.undo if direction < 0 else self.session.redo)

    def demo(self):
        self.perform(lambda: self.session.patch(data={'Ti': '-0.640', 'Ni': '0.820', 'Fe': '0.350', 'O': '0.160'}, replace_data=True))

    def auto_range(self):
        self.perform(self.session.auto_range)

    def _select_sheet(self, index):
        if self._syncing or index < 0:
            return
        key = self.sheets.tabData(index)
        if key and not self.perform(lambda: self.session.select_dataset(key)):
            self._sync()

    def _resource_activate(self, item, _column):
        action = item.data(0, Qt.ItemDataRole.UserRole)
        if not action:
            return
        kind, key = action
        if kind == 'dataset':
            self.perform(lambda: self.session.select_dataset(key))
        elif kind == 'builtin':
            self.perform(lambda: self.session.apply_preset({'plot': preset(key)}))
        else:
            self.perform(lambda: self.session.load_preset(key))

    def paste_data(self, text=None):
        dialog = QDialog(self)
        dialog.setWindowTitle('粘贴元素数据')
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('每行例如 Ni,0.820；支持从 Excel 复制元素、数值两列。\n应用后替换当前数据组，保留原始数字书写形式。'))
        editor = QPlainTextEdit(text if isinstance(text, str) else QApplication.clipboard().text())
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        def commit():
            if self.perform(lambda: self.session.patch(data=parse_data(editor.toPlainText(), preserve_text=True), replace_data=True)):
                dialog.accept()
        buttons.accepted.connect(commit)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def import_file(self, path=None):
        path = path or QFileDialog.getOpenFileName(self, '导入数据', '', '数据文件 (*.xlsx *.csv *.tsv *.txt *.json);;所有文件 (*)')[0]
        if not path or not self.commit_drafts():
            return False
        try:
            if Path(path).suffix.lower() == '.xlsx':
                from .excel_dialog import ExcelImportDialog
                def commit(preview):
                    if not self.commit_drafts():
                        raise ValueError('请先修正未提交的输入')
                    self.session.import_excel(preview)
                    self._sync(discard_pending=True)
                    self.schedule_preview()
                ExcelImportDialog(path, self, on_commit=commit).exec()
                return True
            return self.perform(lambda: self.session.patch(data=parse_data(Path(path).read_text(encoding='utf-8-sig'), preserve_text=True), replace_data=True))
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def plot_settings(self, section=None):
        if not self.commit_drafts():
            return
        from .settings import PlotSettingsPanel
        dialog = QDialog(self)
        dialog.setWindowTitle('绘图设置 · 修改后自动预览')
        dialog.resize(650, 740)
        layout = QVBoxLayout(dialog)
        def change(patch):
            self.session.patch(plot=patch)
            self._sync()
            self.schedule_preview()
        panel = PlotSettingsPanel(dialog, on_change=change, on_error=self.error)
        panel.set_plot(self.session.plot)
        if section:
            panel.select_section(section)
        self._settings_panel = panel
        layout.addWidget(panel)
        close = QPushButton('完成')
        close.clicked.connect(lambda: dialog.accept() if self.commit_drafts() else None)
        layout.addWidget(close)
        try:
            dialog.exec()
        finally:
            self._settings_panel = None
            # Closing the window cancels invalid/unsubmitted widget text only.
            self._sync()
            self.schedule_preview()
            dialog.deleteLater()

    def choose_preset(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('外观预设')
        layout = QVBoxLayout(dialog)
        choices = QComboBox()
        for key, (label, _) in PRESETS.items():
            choices.addItem(label, ('builtin', key))
        for name in self.session.list_presets():
            choices.addItem('我的预设 · ' + name, ('user', name))
        layout.addWidget(choices)
        include = QCheckBox('载入用户预设时包含数据（替换当前数据）')
        layout.addWidget(include)
        apply = QPushButton('应用预设')
        def commit():
            kind, name = choices.currentData()
            operation = (lambda: self.session.apply_preset({'plot': preset(name)})) if kind == 'builtin' else (lambda: self.session.load_preset(name, include.isChecked()))
            if self.perform(operation):
                dialog.accept()
        apply.clicked.connect(commit)
        layout.addWidget(apply)
        delete = QPushButton('删除所选用户预设')
        def remove():
            kind, name = choices.currentData()
            if kind != 'user':
                self.message('内置预设不能删除')
                return
            if QMessageBox.question(dialog, '删除预设', f'删除“{name}”？') == QMessageBox.StandardButton.Yes:
                self.session.delete_preset(name)
                choices.removeItem(choices.currentIndex())
                self._sync()
        delete.clicked.connect(remove)
        layout.addWidget(delete)
        dialog.exec()

    def save_preset(self):
        if not self.commit_drafts():
            return
        name, ok = QInputDialog.getText(self, '保存预设', '预设名称：')
        if not ok or not name.strip():
            return
        if name in self.session.list_presets() and QMessageBox.question(self, '覆盖预设', f'更新“{name}”？') != QMessageBox.StandardButton.Yes:
            return
        answer = QMessageBox.question(self, '预设内容', '是否同时保存当前数据？选择“否”仅保存外观。',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Cancel:
            self.perform(lambda: self.session.save_preset(name, answer == QMessageBox.StandardButton.Yes))

    def confirm_discard(self):
        valid = self.commit_drafts()
        if valid and not self.session.dirty:
            return True
        answer = QMessageBox.question(self, '未保存的修改', '保存当前项目后继续？' if valid else '当前输入无效。选择“否”放弃未保存修改，或取消返回修正。',
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            return self.save_project() if valid else False
        if answer == QMessageBox.StandardButton.No:
            return True
        return False

    def new_project(self):
        if self.confirm_discard():
            self.session.clear_draft()
            self.session = WorkbenchSession(self.user_dir)
            self.selected_symbol = ''
            self._sync(discard_pending=True)
            self.schedule_preview()

    def open_project(self, path=None):
        path = path or QFileDialog.getOpenFileName(self, '打开项目', '', '绘图项目 (*.ptproj *.json)')[0]
        if not path or not self.confirm_discard():
            return False
        try:
            try:
                self.session.load(path)
            except MigrationRequired as exc:
                box = QMessageBox(self)
                box.setWindowTitle('旧项目迁移')
                box.setText('转换为新工作区，并在保存时另存副本。原文件不变。')
                box.setDetailedText(json.dumps(exc.report, ensure_ascii=False, indent=2))
                box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                if box.exec() != QMessageBox.StandardButton.Ok:
                    return False
                self.session.load(path, migrate=True)
            self.session.clear_draft()
            self.selected_symbol = ''
            self._sync(discard_pending=True)
            self.schedule_preview()
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def save_project(self, path=None, *, save_as=False):
        if not self.commit_drafts():
            return False
        target = path or (None if save_as else self.session.path)
        if not target:
            initial = self.session.source_path.stem + '-migrated.ptproj' if self.session.source_path else 'untitled.ptproj'
            target = QFileDialog.getSaveFileName(self, '保存项目', initial, '绘图项目 (*.ptproj)')[0]
        if not target:
            return False
        try:
            self.session.save(target)
            self.session.clear_draft()
            self._sync()
            self.message('项目已保存：' + str(target))
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def recover_draft(self):
        if QMessageBox.question(self, '恢复工作', '发现未保存的工作区，是否恢复？') == QMessageBox.StandardButton.Yes:
            self.perform(self.session.recover_draft)

    def output_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('输出设置')
        form = QFormLayout(dialog)
        directory, base = QLineEdit(self.output_dir), QLineEdit(self.output_base)
        format_box = QComboBox()
        format_box.addItems(['svg', 'png', 'pdf'])
        format_box.setCurrentText(self.output_format)
        form.addRow('保存目录', directory)
        browse = QPushButton('选择目录…')
        browse.clicked.connect(lambda: directory.setText(QFileDialog.getExistingDirectory(dialog, '保存目录') or directory.text()))
        form.addRow(browse)
        form.addRow('基础文件名', base)
        form.addRow('格式', format_box)
        form.addRow(QLabel('自动附加时间戳和冲突序号，不覆盖已有图片。'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        def commit():
            if not directory.text().strip() or not re.fullmatch(r'[\w-]{1,80}', base.text()):
                QMessageBox.warning(dialog, '输入无效', '目录不能为空；文件名仅允许字母、数字、中文、下划线和连字符。')
                return
            self.output_dir, self.output_base, self.output_format = directory.text(), base.text(), format_box.currentText()
            self.save_preferences()
            dialog.accept()
        buttons.accepted.connect(commit)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        dialog.exec()

    def export(self):
        if self.commit_drafts():
            self.begin_export([({}, self.session.data)])

    def batch_export(self):
        if not self.commit_drafts():
            return
        snapshot = self.session.collection.snapshot()
        if not snapshot['datasets']:
            self.message('请先导入 Excel 数据组')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('批量导出 · 共用当前色标')
        layout = QVBoxLayout(dialog)
        choices = QListWidget()
        choices.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        conditions = {row['id']: row['label'] for row in snapshot['conditions']}
        for row in snapshot['datasets']:
            choices.addItem(conditions.get(row['condition_id'], row['id']))
            choices.item(choices.count() - 1).setData(Qt.ItemDataRole.UserRole, row['id'])
        choices.selectAll()
        layout.addWidget(choices)
        button = QPushButton('导出所选数据组')
        def commit():
            try:
                items = self.session.batch_items([item.data(Qt.ItemDataRole.UserRole) for item in choices.selectedItems()])
                if self.begin_export(items):
                    dialog.accept()
            except (ValueError, OSError) as exc:
                self.error(exc)
        button.clicked.connect(commit)
        layout.addWidget(button)
        dialog.exec()

    def begin_export(self, items):
        if self.export_job.active:
            self.message('已有导出任务运行，请等待或取消')
            return False
        try:
            if not re.fullmatch(r'[\w-]{1,80}', self.output_base):
                raise ValueError('文件基础名须为1～80个字母、数字、中文、下划线或连字符')
            if self.output_format not in ('svg', 'png', 'pdf'):
                raise ValueError('输出格式无效')
            plot = self.session.plot
            if plot['figsize'][0] * plot['figsize'][1] * plot['dpi'] ** 2 > 64_000_000:
                raise ValueError('画幅超过6400万像素，请降低尺寸或DPI')
            prepared, warnings = [], []
            for index, (metadata, data) in enumerate(items, 1):
                _, converted, messages = prepare_plot(plot, data)
                if not converted:
                    raise ValueError('所选数据组为空')
                warnings.extend(messages)
                suffix = re.sub(r'[^\w-]', '_', str(metadata.get('name', index)))[:35]
                name = self.output_base if len(items) == 1 else f'{self.output_base}_{index:03d}_{suffix}'
                prepared.append((name, converted))
            if warnings and QMessageBox.question(self, '确认绘图范围', '\n'.join(dict.fromkeys(warnings)) + '\n继续导出？') != QMessageBox.StandardButton.Yes:
                return False
            self.export_context = (str(Path(self.output_dir).resolve()), self.output_format)
            self.export_job.start({'engine': 'v2', 'mode': 'batch' if len(items) > 1 else 'export',
                                  'plot': plot, 'items': prepared, 'format': self.output_format})
            self.message('正在导出…')
            return True
        except (ValueError, OSError) as exc:
            self.error(exc)
            return False

    def _publish(self, packet):
        created = []
        try:
            directory, fmt = self.export_context
            for source, name in packet['files']:
                destination = auto_name(directory, name, fmt)
                created.append(destination)
                shutil.copyfile(source, destination)
            self.last_output = created[-1] if created else None
            self.message(f'已导出 {len(created)} 张图片：{self.last_output}')
            self.diagnostics.record('INFO', 'export.completed', '图片导出完成', details={'count': len(created)})
        except OSError as exc:
            for destination in created:
                Path(destination).unlink(missing_ok=True)
            self.error('导出未完成：' + str(exc))

    def reference(self):
        path = QFileDialog.getOpenFileName(self, '打开样图', '', '图片 (*.png *.jpg *.jpeg *.svg)')[0]
        if not path:
            return
        try:
            from io import BytesIO
            from core.reference_image import load_reference_image
            image = load_reference_image(path)
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            image.close()
            dialog = QDialog(self)
            dialog.setWindowTitle('样图对照 · 左：参考图 / 右：当前预览')
            dialog.resize(1100, 650)
            layout = QVBoxLayout(dialog)
            split = QSplitter()
            original, current = PreviewCanvas(), PreviewCanvas()
            original.show_packet(buffer.getvalue(), {})
            original.set_edit_enabled(False)
            current.set_edit_enabled(False)
            def refresh():
                if self.preview.source_image is not None:
                    from PySide6.QtCore import QBuffer, QIODevice
                    storage = QBuffer()
                    storage.open(QIODevice.OpenModeFlag.WriteOnly)
                    self.preview.source_image.save(storage, 'PNG')
                    current.show_packet(bytes(storage.data()), {})
            refresh()
            split.addWidget(original)
            split.addWidget(current)
            layout.addWidget(split)
            button = QPushButton('刷新当前预览快照')
            button.clicked.connect(refresh)
            layout.addWidget(button)
            dialog.exec()
        except (ValueError, OSError) as exc:
            self.error(exc)

    def view_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('布局与界面缩放')
        form = QFormLayout(dialog)
        scale = QComboBox()
        for label, value in [('跟随系统', 1.0), ('紧凑 85%', .85), ('放大 125%', 1.25), ('放大 150%', 1.5)]:
            scale.addItem(label, value)
        scale.setCurrentIndex(max(0, scale.findData(self.preferences.get('scale', 1.0))))
        automatic = QCheckBox('窄窗口自动收起项目资源面板')
        automatic.setChecked(self.preferences.get('responsive', True) is True)
        form.addRow('界面字号与控件', scale)
        form.addRow(automatic)
        form.addRow(QLabel('面板支持拖动、停靠和关闭；中间分隔条可调整预览占比。\n界面缩放不改变导出图片尺寸。'))
        button = QPushButton('应用')
        def apply():
            self.preferences.update(scale=scale.currentData(), responsive=automatic.isChecked())
            apply_theme(QApplication.instance(), scale.currentData())
            self._compact = None
            self._responsive()
            self.save_preferences()
            dialog.accept()
        button.clicked.connect(apply)
        form.addRow(button)
        dialog.exec()

    def _responsive(self):
        if not hasattr(self, 'resources_dock') or not self.preferences.get('responsive', True):
            return
        compact = self.width() < 1100
        if compact != self._compact:
            self._compact = compact
            self.resources_dock.setVisible(not compact)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._responsive()

    def reset_layout(self):
        for dock, area in [(self.resources_dock, Qt.DockWidgetArea.LeftDockWidgetArea), (self.inspector_dock, Qt.DockWidgetArea.RightDockWidgetArea)]:
            dock.setFloating(False)
            self.addDockWidget(area, dock)
            dock.show()
        self.resizeDocks([self.resources_dock, self.inspector_dock], [190, 300], Qt.Orientation.Horizontal)
        self.splitter.setSizes([520, 220])
        self._compact = None

    def _restore_preferences(self):
        scale = self.preferences.get('scale', 1.0)
        apply_theme(QApplication.instance(), scale if scale in (.85, 1.0, 1.25, 1.5) else 1.0)
        for key, restore in [('geometry', self.restoreGeometry), ('layout_state', self.restoreState)]:
            try:
                value = self.preferences.get(key, '')
                if isinstance(value, str) and value:
                    restore(QByteArray(base64.b64decode(value, validate=True)))
            except (ValueError, TypeError):
                pass

    def save_preferences(self):
        self.preferences.update(output_dir=self.output_dir, output_base=self.output_base, format=self.output_format,
            log_enabled=self.log_enabled, log_level=self.log_level,
            geometry=base64.b64encode(bytes(self.saveGeometry())).decode(),
            layout_state=base64.b64encode(bytes(self.saveState())).decode())
        write_document(self.preferences_path, self.preferences)

    def show_logs(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('日志与排错')
        dialog.resize(740, 520)
        layout = QVBoxLayout(dialog)
        row = QHBoxLayout()
        enabled = QCheckBox('启用日志')
        enabled.setChecked(self.log_enabled)
        level = QComboBox()
        level.addItems(['DEBUG', 'INFO', 'WARNING'])
        level.setCurrentText(self.log_level)
        row.addWidget(enabled)
        row.addWidget(level)
        temporary = QPushButton('详细排错 30 分钟')
        temporary.clicked.connect(lambda: self.diagnostics.start_session(30))
        row.addWidget(temporary)
        stop = QPushButton('结束详细排错')
        stop.clicked.connect(self.diagnostics.stop_session)
        row.addWidget(stop)
        layout.addLayout(row)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        def refresh():
            text.setPlainText('\n'.join(json.dumps(row, ensure_ascii=False) for row in self.diagnostics.query(limit=300).entries))
        def configure():
            self.log_enabled, self.log_level = enabled.isChecked(), level.currentText()
            self.diagnostics.configure(DiagnosticSettings(enabled=self.log_enabled, level=self.log_level))
            self.save_preferences()
        enabled.toggled.connect(configure)
        level.currentTextChanged.connect(configure)
        layout.addWidget(text)
        button = QPushButton('刷新本次日志')
        button.clicked.connect(refresh)
        layout.addWidget(button)
        refresh()
        dialog.exec()

    def export_logs(self):
        directory = QFileDialog.getExistingDirectory(self, '诊断包保存目录')
        if directory:
            try:
                path = self.diagnostics.export_bundle(None, directory)
                self.message('诊断包已导出：' + str(path))
            except (ValueError, OSError) as exc:
                self.error(exc)

    def _text_dialog(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(700, 520)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(text)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dialog.reject)
        layout.addWidget(close)
        dialog.exec()

    def copy_request(self):
        if self.commit_drafts():
            request = {'api_version': 2, 'action': 'render', 'plot': self.session.plot, 'data': self.session.data,
                       'output_dir': self.output_dir, 'formats': [self.output_format], 'base': self.output_base}
            QApplication.clipboard().setText(json.dumps(request, ensure_ascii=False, indent=2))
            self.message('已复制当前配置与数据的 Agent v2 绘图请求')

    def agent_help(self):
        self._text_dialog('Agent 接口', '界面和 Agent 共用 PlotSpec 与 schema 2 项目。\n\n'
            '1. 点击「复制绘图请求」，保存为 request.json。\n'
            '2. 源码调用：\npython main.py --agent-request request.json --agent-response result.json\n\n'
            '3. EXE 调用：\nPeriodicTableTool.exe --agent-request request.json --agent-response result.json\n\n'
            '查询能力：{"api_version":2,"action":"describe"}\n'
            '详细契约参见 docs/AGENT-V2.md。图形设置不绑定界面，Agent 可以修改并保存项目后由桌面继续编辑。')

    def help(self):
        self._text_dialog('使用帮助', '完成第一张图\n\n'
            '1. 开始 → 载入示例，或 数据 → 导入数据 / 粘贴数据。\n'
            '2. 双击表格的数值列编辑，Enter 提交。Ctrl+C 复制选择；Ctrl+V 粘贴。\n'
            '3. 图形 → 绘图设置，调整配色、色标、字体、毫米画幅和DPI。\n'
            '4. 点击预览中的元素，在右侧修改标注；左拖移动标注，右拖平移画布。\n'
            '5. 文件 → 输出设置，然后点击「导出图片」。已有文件不会被覆盖。\n\n'
            'Excel 数据组保留各组编辑，底部标签切换；批量导出共用当前色标。\n'
            'Ctrl+K 搜索所有功能；Ctrl+S 保存；Ctrl+Z/Y 撤销/重做。\n'
            '视图 → 布局与缩放调整界面，恢复布局可找回关闭或浮动的面板。\n\n'
            '这是 2.0 Alpha 1 Qt 预览版；稳定版为 v1.9.0。')

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        for timer in (self.poll_timer, self.preview_timer, self.quality_timer, self.draft_timer, self.inspector.timer):
            timer.stop()
        self.preview_job.cancel()
        self.export_job.cancel()
        try:
            self.save_preferences()
        except OSError:
            pass
        self.diagnostics.close()

    def closeEvent(self, event):
        if self._closed or self.confirm_discard():
            if not self._closed:
                self.session.clear_draft()
            self.shutdown()
            event.accept()
        else:
            event.ignore()


def main():
    from .smoke import run_smoke
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('PeriodicTableTool')
    app.setOrganizationName('PeriodicTableTool')
    if os.environ.get('PTT_SMOKE') == '1':
        return run_smoke(app, MainWindow)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
