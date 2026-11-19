"""Contextual element editing; retains invalid drafts until corrected/discarded."""
from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QCheckBox, QPushButton, QGroupBox, QListWidget


class ElementInspector(QWidget):
    issueSelected = Signal(str)

    def __init__(self, apply, on_error, parent=None):
        super().__init__(parent)
        self.apply, self.on_error = apply, on_error
        self.symbol, self.dirty, self._loading = '', False, False
        self._plot = {}
        self._dirty_fields = set()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.flush)
        layout = QVBoxLayout(self)
        self.heading = QLabel('点击图中的元素开始编辑')
        self.heading.setObjectName('Heading')
        layout.addWidget(self.heading)
        self.form_group = QGroupBox('标注与位置')
        form = QFormLayout(self.form_group)
        self.value = QLineEdit()
        self.value.setPlaceholderText('数值或文本，留空清除')
        form.addRow('数值 / 标注', self.value)
        self.fields = {}
        for key, label in [('show_value', '显示标注'), ('show_color', '显示着色'), ('include_in_range', '参与自动范围')]:
            control = QCheckBox(label)
            self.fields[key] = control
            form.addRow(control)
            control.toggled.connect(lambda checked, field=key: self.changed(field))
        for key, label in [('value_dx', '水平偏移（格宽）'), ('value_dy', '垂直偏移（格高）')]:
            control = QLineEdit('0')
            self.fields[key] = control
            form.addRow(label, control)
            control.textEdited.connect(lambda text, field=key: self.changed(field))
        self.value.textEdited.connect(lambda text: self.changed('value'))
        self.value.returnPressed.connect(self.flush)
        button = QPushButton('应用标注')
        button.setObjectName('Primary')
        button.clicked.connect(self.flush)
        form.addRow(button)
        reset = QPushButton('恢复元素默认位置与显示')
        reset.clicked.connect(self.reset_overrides)
        form.addRow(reset)
        layout.addWidget(self.form_group)
        note = QLabel('字号、字体和颜色在「图形 → 绘图设置」中调整。\n也可直接拖动图中的标注位置。')
        note.setObjectName('Muted')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.issue_heading = QLabel('排版检查')
        self.issue_heading.setObjectName('Heading')
        layout.addWidget(self.issue_heading)
        self.issues = QListWidget()
        self.issues.itemClicked.connect(lambda item: self.issueSelected.emit(item.data(256)))
        layout.addWidget(self.issues, 1)
        self.form_group.setEnabled(False)

    def changed(self, field):
        if not self._loading:
            self._dirty_fields.add(field)
            self.dirty = True
            self.timer.start()

    def set_element(self, symbol, data, plot, *, discard=False):
        if self.dirty and symbol == self.symbol and not discard:
            self._plot = plot
            if 'value' not in self._dirty_fields:
                self.value.setText(str(data.get(symbol, '')))
            return
        self.timer.stop()
        self._loading = True
        try:
            self.symbol, self._plot = symbol, plot
            self.heading.setText(f'元素属性 · {symbol}' if symbol else '点击图中的元素开始编辑')
            self.form_group.setEnabled(bool(symbol))
            self.value.setText(str(data.get(symbol, '')))
            override = plot.get('element_overrides', {}).get(symbol, {})
            for key, control in self.fields.items():
                if isinstance(control, QCheckBox):
                    control.setChecked(override.get(key, True))
                else:
                    control.setText(str(override.get(key, 0)))
            self.dirty = False
            self._dirty_fields.clear()
        finally:
            self._loading = False

    def flush(self):
        self.timer.stop()
        if not self.dirty or not self.symbol:
            return True
        try:
            overrides = dict(self._plot.get('element_overrides', {}))
            row = dict(overrides.get(self.symbol, {}))
            for key, control in self.fields.items():
                if key in self._dirty_fields:
                    row[key] = control.isChecked() if isinstance(control, QCheckBox) else float(control.text())
            plot = None
            if self._dirty_fields - {'value'}:
                overrides[self.symbol] = row
                plot = {'element_overrides': overrides}
            value = self.value.text()
            data = {self.symbol: value if value.strip() else None} if 'value' in self._dirty_fields else None
            self.apply(plot, data)
        except (ValueError, OSError) as exc:
            self.on_error(str(exc))
            return False
        self.dirty = False
        self._dirty_fields.clear()
        return True

    def reset_overrides(self):
        if self.symbol and self.flush():
            rows = dict(self._plot.get('element_overrides', {}))
            rows.pop(self.symbol, None)
            try:
                self.apply({'element_overrides': rows}, None)
            except (ValueError, OSError) as exc:
                self.on_error(str(exc))

    def set_issues(self, issues):
        self.issues.clear()
        self.issue_heading.setText(f'排版检查 · {len(issues)} 条提示' if issues else '排版检查 · 未发现重叠')
        for issue in issues:
            symbol = issue.get('text', {}).get('element', '')
            self.issues.addItem(symbol + ' · ' + str(issue.get('suggestion', issue.get('code', ''))))
            self.issues.item(self.issues.count() - 1).setData(256, symbol)
