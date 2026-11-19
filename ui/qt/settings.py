"""Qt-only native PlotSpec forms; the owner handles sessions and rendering."""
from copy import deepcopy
import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QCheckBox, QComboBox, QPushButton, QTabWidget, QScrollArea, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QColorDialog, QDialog, QDialogButtonBox, QPlainTextEdit,
)

from domain.plot_spec import PlotSpec


_CHOICES = {
    'kind': [('热力图', 'heatmap'), ('文本图', 'labels')],
    'layout': [('展开（118 元素）', 'expanded'), ('紧凑', 'compact')],
    'fmt': [('原始值', 'raw'), ('有效数字', 'g'), ('百分数（2位）', 'percent2'),
            ('小数（2位）', '2f'), ('小数（3位）', '3f'), ('小数（4位）', '4f'), ('科学计数', 'scientific')],
    'rounding': [('四舍五入', 'half_up'), ('Python 舍入', 'python')],
    'num_ha': [('左对齐', 'left'), ('居中', 'center'), ('右对齐', 'right')],
    'cbar_orientation': [('垂直', 'vertical'), ('水平', 'horizontal')],
    'cbar_location': [('自动', 'auto'), ('左侧', 'left'), ('右侧', 'right'), ('上方', 'top'), ('下方', 'bottom')],
}
_GROUPS = [
    ('基本', '图形与画幅', [('kind', '图形类型'), ('layout', '元素布局'), ('title', '图形标题'),
     ('figsize', '画幅宽 × 高'), ('dpi', '分辨率 DPI'), ('bbox_tight', '紧凑裁剪'), ('transparent', '透明背景')]),
    ('文本', '字体与数值', [('font', '字体名称'), ('fmt', '数值格式'), ('rounding', '舍入方式'), ('unit', '数值单位'),
     ('show_symbol', '显示元素符号'), ('symbol_fs', '符号字号'), ('show_number', '显示原子序数'),
     ('number_fs', '序数字号'), ('num_x', '序数横向位置'), ('num_ha', '序数对齐'),
     ('show_value', '显示数值'), ('value_fs', '数值字号'), ('value_dx', '数值横向偏移'),
     ('value_dy', '数值纵向偏移'), ('label_wrap', '换行字符数（0关闭）'), ('label_fs', '文本字号'),
     ('label_dy', '文本纵向偏移'), ('label_color', '文本颜色（auto 自动）')]),
    ('配色', '背景与边框', [('empty', '空值颜色'), ('bg', '背景颜色'), ('highlight_bg', '高亮背景'),
     ('highlight_fg', '高亮文字'), ('plain_bg', '普通背景'), ('plain_fg', '普通文字'), ('edge', '边框宽度与颜色')]),
    ('色条', '色条布局', [('show_cbar', '显示色条'), ('show_cbar_labels', '全局显示色条标签'),
     ('preserve_cbar_space', '保留色条空间'), ('check_label_overlap', '检查标签重叠'),
     ('cbar_orientation', '色条方向'), ('cbar_location', '色条位置'), ('cbar_label', '色条标题'),
     ('cbar_fraction', '色条宽度比例'), ('cbar_pad', '色条间距'), ('cbar_shrink', '色条长度比例')]),
    ('几何', '精确几何（Figure 比例 0–1）', [('margins', '绘图区：左、下、右、上'),
     ('cbar_box', '色条框：左、下、宽、高')]),
]
_COLORS = {'empty', 'bg', 'label_color', 'highlight_bg', 'highlight_fg', 'plain_bg', 'plain_fg'}
_NULLABLE = {'highlight_bg', 'highlight_fg', 'plain_bg', 'plain_fg'}
_TEXT = {'font', 'title', 'unit', 'cbar_label'}


def _color_text(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, tuple)) else ('' if value is None else str(value))


def _parse_color(text):
    return json.loads(text) if text.strip().startswith('[') else text.strip()


class PlotSettingsPanel(QWidget):
    """Independent editor with validated, transactional top-level patch callbacks.

    ``flush`` returns True for successful submission (including no changes), False
    for invalid drafts or rejected callbacks. Failed drafts remain fully editable.
    """

    def __init__(self, parent=None, on_change=None, on_error=None):
        super().__init__(parent)
        self.on_change, self.on_error = on_change, on_error
        self._loading = True
        self._revision = 0
        self._baseline = PlotSpec().to_dict()
        self._draft = deepcopy(self._baseline)
        self.fields = {}
        self._fields = self.fields
        self._enabled = {}
        self._rows, self._groups, self._pages = [], [], {}
        self._unit_name = '英寸'
        self._figsize_inches, self._figsize_display = None, None
        self._dialogs = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.flush)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.search = QLineEdit(self)
        self.search.setObjectName('settings_search')
        self.search.setPlaceholderText('搜索设置：中文名称或字段名…')
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)
        for page, title, fields in _GROUPS:
            form = self._group(page, title)
            for key, label in fields:
                self._field(form, key, label)
        self._build_range()
        self._build_cmap()
        self._build_cbar()
        form = self._group('高级', '复杂配置')
        hint = QLabel('所有字段均使用原生 PlotSpec。元素覆盖等复杂配置可通过 JSON 编辑。')
        hint.setWordWrap(True)
        self._add_row(form, '说明', hint, 'element_overrides 元素 覆盖 JSON 全部字段')
        for label, key in [('编辑元素覆盖 JSON…', 'element_overrides'), ('编辑完整 PlotSpec JSON…', None)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, field=key: self.open_advanced(field))
            self._add_row(form, '', button, 'element_overrides 元素 覆盖 JSON 全部字段')
        self.no_results = QLabel('没有匹配的设置')
        self.no_results.hide()
        layout.addWidget(self.no_results)
        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #b42318;')
        layout.addWidget(self.error_label)
        self.search.textChanged.connect(self._search)
        self.set_plot(self._baseline)

    def _group(self, page, title):
        if page not in self._pages:
            scroll = QScrollArea(self.tabs)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            content = QWidget()
            box = QVBoxLayout(content)
            box.setContentsMargins(4, 6, 4, 6)
            box.addStretch(1)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, page)
            self._pages[page] = (scroll, box)
        scroll, box = self._pages[page]
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        box.insertWidget(box.count() - 1, group)
        self._groups.append((page, group, form))
        return form

    def _add_row(self, form, label, widget, keywords):
        index = form.rowCount()
        form.addRow(label, widget)
        widget.setToolTip(keywords)
        self._rows.append((form, index, keywords.casefold()))

    def _line(self, name, text=''):
        widget = QLineEdit(str(text))
        widget.setObjectName(name)
        widget.setMinimumWidth(45)
        widget.textChanged.connect(self._changed)
        return widget

    def _combo(self, name, choices):
        widget = QComboBox()
        widget.setObjectName(name)
        for label, value in choices:
            widget.addItem(label, value)
        widget.currentIndexChanged.connect(self._changed)
        return widget

    def _check(self, name, label=''):
        widget = QCheckBox(label)
        widget.setObjectName(name)
        widget.toggled.connect(self._changed)
        return widget

    @staticmethod
    def _horizontal():
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        return widget, layout

    def _field(self, form, key, label):
        default = self._baseline[key]
        if isinstance(default, bool):
            editor = self._check(key)
        elif key in _CHOICES:
            editor = self._combo(key, _CHOICES[key])
        elif key in ('figsize', 'margins', 'cbar_box', 'edge'):
            editor, row = self._horizontal()
            if key != 'figsize':
                self._enabled[key] = self._check(key + '_enabled', '启用')
                row.addWidget(self._enabled[key])
            parts = [self._line(f'{key}.{i}') for i in range(2 if key in ('figsize', 'edge') else 4)]
            for part in parts:
                row.addWidget(part, 1)
            self.fields[key] = parts
            if key == 'figsize':
                self.figsize_unit = QComboBox()
                self.figsize_unit.setObjectName('figsize_unit')
                self.figsize_unit.addItems(['英寸', '毫米'])
                self.figsize_unit.currentTextChanged.connect(self._unit_changed)
                row.addWidget(self.figsize_unit)
            self._add_row(form, label, editor, key + ' ' + label + (' 英寸 毫米' if key == 'figsize' else ''))
            return
        else:
            editor = self._line(key)
        self.fields[key] = editor
        shown = editor
        if key in _COLORS:
            if key in _NULLABLE:
                editor.setPlaceholderText('留空使用自动颜色')
            shown, row = self._horizontal()
            row.addWidget(editor, 1)
            choose = QPushButton('选色')
            choose.setMaximumWidth(52)
            choose.clicked.connect(lambda checked=False, target=editor: self._choose_color(target))
            row.addWidget(choose)
        self._add_row(form, label, shown, key + ' ' + label)

    def _choose_color(self, target):
        color = QColorDialog.getColor(parent=self, title='选择颜色', options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            rgba = [color.redF(), color.greenF(), color.blueF(), color.alphaF()]
            target.setText(color.name() if color.alpha() == 255 else json.dumps(rgba))

    def _build_range(self):
        form = self._group('配色', '数值范围')
        self.norm_mode = self._combo('norm_mode', [('线性', 'normalize'), ('中心分段', 'twoslope')])
        self._add_row(form, '范围类型', self.norm_mode, 'norm 范围 线性 中心')
        self.norm_fields = [self._line('norm_min'), self._line('norm_center'), self._line('norm_max')]
        for label, field in zip(['最小值', '中心值（仅中心分段）', '最大值'], self.norm_fields):
            self._add_row(form, label, field, 'norm 范围 ' + label)

    def _table(self, columns, name):
        table = QTableWidget(0, len(columns))
        table.setObjectName(name)
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setMinimumHeight(155)
        table.setMaximumHeight(245)
        table.itemChanged.connect(self._changed)
        return table

    def _buttons(self, add, table):
        widget, layout = self._horizontal()
        add_button, delete_button = QPushButton('增加一行'), QPushButton('删除选中行')
        add_button.clicked.connect(lambda checked=False: add())
        delete_button.clicked.connect(lambda checked=False: self._delete_rows(table))
        layout.addWidget(add_button)
        layout.addWidget(delete_button)
        return widget

    def _build_cmap(self):
        form = self._group('配色', '配色与自定义颜色节点')
        self.custom_cmap = self._check('custom_cmap', '使用自定义颜色节点')
        self.cmap_name = QComboBox()
        self.cmap_name.setEditable(True)
        self.cmap_name.setObjectName('cmap_name')
        self.cmap_name.addItems(['coolwarm', 'viridis', 'plasma', 'RdBu', 'Blues', 'Greys'])
        self.cmap_name.currentTextChanged.connect(self._changed)
        self.nodes = self._table(['位置（0–1）', '颜色 / RGB(A)'], 'cmap_nodes')
        for label, widget in [('模式', self.custom_cmap), ('内置配色名称', self.cmap_name),
                              ('节点（须含0和1）', self.nodes), ('', self._buttons(self.add_color_node, self.nodes))]:
            self._add_row(form, label, widget, 'cmap 配色 自定义 颜色 节点 ' + label)

    def _build_cbar(self):
        form = self._group('色条', '逐行刻度与标签')
        self.bar_enabled = self._check('cbar_enabled', '自定义色条标签（关闭使用自动刻度）')
        self.bar_fontsize = self._line('cbar.fontsize')
        self.cbar_table = self._table(['刻度值', '标签文字', '显示'], 'cbar_rows')
        for label, widget in [('模式', self.bar_enabled), ('色条标签字号', self.bar_fontsize),
                              ('逐行编辑', self.cbar_table), ('', self._buttons(self.add_cbar_row, self.cbar_table))]:
            self._add_row(form, label, widget, 'cbar ticks labels visible fontsize 色条 标签 隐藏 字号 ' + label)

    def _append_row(self, table, values, check_last=False):
        loading = self._loading
        self._loading = True
        try:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(values):
                item = QTableWidgetItem('' if check_last and col == len(values) - 1 else str(value))
                if check_last and col == len(values) - 1:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
                table.setItem(row, col, item)
        finally:
            self._loading = loading
        self._changed()

    def add_cbar_row(self, tick=None, label='', visible=True):
        if tick is None:
            try:
                ticks = [float(self.cbar_table.item(r, 0).text()) for r in range(self.cbar_table.rowCount())]
                tick = max(ticks) + 1 if ticks else 0
            except (ValueError, AttributeError):
                tick = 0
        self._append_row(self.cbar_table, [tick, label, visible], True)

    def add_color_node(self, position=None, color='#ffffff'):
        if position is None:
            try:
                points = sorted(float(self.nodes.item(r, 0).text()) for r in range(self.nodes.rowCount()))
                start, end = max(zip(points, points[1:]), key=lambda pair: pair[1] - pair[0])
                position = (start + end) / 2
            except (ValueError, AttributeError):
                position = .5
        self._append_row(self.nodes, [position, _color_text(color)])

    def _delete_rows(self, table):
        selected = {index.row() for index in table.selectionModel().selectedRows()}
        for row in sorted(selected, reverse=True):
            table.removeRow(row)
        if selected:
            self._changed()

    def _changed(self, *_):
        if not self._loading:
            self.timer.start()

    def _report(self, error):
        message = str(error)
        self.error_label.setText(message)
        if self.on_error is not None:
            self.on_error(message)

    def _read_figsize(self):
        display = tuple(field.text() for field in self.fields['figsize'])
        if display == self._figsize_display:
            return deepcopy(self._figsize_inches)
        scale = 25.4 if self._unit_name == '毫米' else 1
        return [float(text) / scale for text in display]

    def _show_figsize(self, inches):
        scale = 25.4 if self._unit_name == '毫米' else 1
        for field, value in zip(self.fields['figsize'], inches):
            field.setText(str(value * scale))
        self._figsize_inches = deepcopy(inches)
        self._figsize_display = tuple(field.text() for field in self.fields['figsize'])

    def _unit_changed(self, unit):
        if self._loading:
            return
        old = self._unit_name
        try:
            inches = PlotSpec.from_dict({'figsize': self._read_figsize()}).to_dict()['figsize']
        except (ValueError, TypeError) as error:
            self._loading = True
            try:
                self.figsize_unit.setCurrentText(old)
            finally:
                self._loading = False
            self._report(error)
            return
        self._loading = True
        try:
            self._unit_name = unit
            self._show_figsize(inches)
        finally:
            self._loading = False

    @staticmethod
    def _table_values(table):
        return [[table.item(r, c).text() if table.item(r, c) is not None else ''
                 for c in range(table.columnCount())] for r in range(table.rowCount())]

    def get_plot(self):
        """Return a detached, fully validated snapshot including unsubmitted edits."""
        draft = deepcopy(self._draft)
        key = 'plot'
        try:
            for _, _, fields in _GROUPS:
                for key, _ in fields:
                    editor = self.fields[key]
                    if key == 'figsize':
                        draft[key] = self._read_figsize()
                    elif key in ('margins', 'cbar_box', 'edge'):
                        draft[key] = ([float(field.text()) if key != 'edge' or i == 0 else _parse_color(field.text())
                                       for i, field in enumerate(editor)] if self._enabled[key].isChecked() else None)
                    elif key in _CHOICES:
                        draft[key] = editor.currentData()
                    elif isinstance(editor, QCheckBox):
                        draft[key] = editor.isChecked()
                    elif key in _TEXT:
                        draft[key] = editor.text()
                    elif key in _COLORS:
                        draft[key] = None if key in _NULLABLE and not editor.text().strip() else _parse_color(editor.text())
                    else:
                        draft[key] = float(editor.text())
            key = 'norm'
            low, center, high = [field.text() for field in self.norm_fields]
            draft['norm'] = (['twoslope', float(low), float(center), float(high)]
                             if self.norm_mode.currentData() == 'twoslope' else ['normalize', float(low), float(high)])
            key = 'cmap'
            node_values = self._table_values(self.nodes)
            if self.custom_cmap.isChecked():
                draft['cmap'] = (deepcopy(self._loaded_cmap) if isinstance(self._loaded_cmap, list) and node_values == self._loaded_nodes
                                 else ['custom', [[float(position), _parse_color(color)] for position, color in node_values]])
            else:
                draft['cmap'] = self.cmap_name.currentText()
            key = 'cbar'
            if self.bar_enabled.isChecked():
                rows = self._table_values(self.cbar_table)
                draft['cbar'] = dict(ticks=[float(row[0]) for row in rows], labels=[row[1] for row in rows],
                    visible=[self.cbar_table.item(r, 2).checkState() == Qt.CheckState.Checked for r in range(len(rows))],
                    fontsize=float(self.bar_fontsize.text()))
            else:
                draft['cbar'] = None
            return PlotSpec.from_dict(draft).to_dict()
        except (ValueError, TypeError, AttributeError, OverflowError) as error:
            raise ValueError(f'配置无效（{key}）：{error}') from error

    def _load(self, plot):
        self._loading = True
        try:
            self._draft = deepcopy(plot)
            for _, _, fields in _GROUPS:
                for key, _ in fields:
                    value, editor = plot[key], self.fields[key]
                    if key == 'figsize':
                        self._show_figsize(value)
                    elif isinstance(editor, list):
                        self._enabled[key].setChecked(value is not None)
                        fallback = {'edge': [1, '#000000'], 'margins': [.05, .05, .95, .95], 'cbar_box': [.88, .15, .03, .7]}[key]
                        for field, part in zip(editor, value if value is not None else fallback):
                            field.setText(_color_text(part) if key == 'edge' else str(part))
                    elif key in _CHOICES:
                        editor.setCurrentIndex(editor.findData(value))
                    elif isinstance(editor, QCheckBox):
                        editor.setChecked(value)
                    else:
                        editor.setText(_color_text(value) if key in _COLORS else str(value))
            norm = plot['norm']
            self.norm_mode.setCurrentIndex(self.norm_mode.findData(norm[0]))
            values = [norm[1], norm[2] if norm[0] == 'twoslope' else (norm[1] + norm[2]) / 2, norm[-1]]
            for field, value in zip(self.norm_fields, values):
                field.setText(str(value))
            cmap = plot['cmap']
            self.custom_cmap.setChecked(not isinstance(cmap, str))
            self.cmap_name.setCurrentText(cmap if isinstance(cmap, str) else 'coolwarm')
            colors = [[0, '#0000ff'], [1, '#ff0000']] if isinstance(cmap, str) else cmap[1]
            if not (isinstance(colors[0], list) and len(colors[0]) == 2):
                colors = [[i / (len(colors) - 1), color] for i, color in enumerate(colors)]
            self.nodes.setRowCount(0)
            for position, color in colors:
                self.add_color_node(position, color)
            self._loaded_cmap = deepcopy(cmap)
            self._loaded_nodes = self._table_values(self.nodes)
            bar = plot['cbar']
            self.bar_enabled.setChecked(bar is not None)
            self.bar_fontsize.setText(str(bar['fontsize'] if bar else 8))
            self.cbar_table.setRowCount(0)
            if bar:
                for tick, label, visible in zip(bar['ticks'], bar['labels'], bar['visible']):
                    self.add_cbar_row(tick, label, visible)
            self.error_label.clear()
        finally:
            self._loading = False

    def set_plot(self, plot):
        canonical = PlotSpec.from_dict(plot).to_dict()
        self.timer.stop()
        self._revision += 1
        self._baseline = deepcopy(canonical)
        self._load(canonical)

    def flush(self):
        """Submit valid changed top-level fields, retaining baseline on rejection."""
        self.timer.stop()
        try:
            plot = self.get_plot()
            patch = {key: deepcopy(value) for key, value in plot.items() if value != self._baseline[key]}
            revision = self._revision
            if patch and self.on_change is not None:
                self.on_change(deepcopy(patch))
            if revision == self._revision:
                self._baseline = deepcopy(plot)
            self.error_label.clear()
            return True
        except Exception as error:
            self._report(error)
            return False

    def select_section(self, name: str) -> bool:
        """Reveal a section for menu commands, clearing any search filter.

        Canonical tab titles and common menu aliases are accepted. Unknown
        names return False without changing the current page or search.
        """
        aliases = {'图形': '基本', '画幅': '基本', '字体': '文本', '范围': '配色'}
        title = aliases.get(name, name)
        if title not in self._pages:
            return False
        self.search.clear()
        self.tabs.setCurrentWidget(self._pages[title][0])
        return True

    def _search(self, query):
        query = query.strip().casefold()
        matches = {}
        for form, row, keywords in self._rows:
            visible = not query or query in keywords
            form.setRowVisible(row, visible)
            matches[id(form)] = matches.get(id(form), False) or visible
        any_page = False
        for page, (scroll, _) in self._pages.items():
            page_matches = False
            for group_page, group, form in self._groups:
                if page == group_page:
                    visible = matches.get(id(form), False)
                    group.setVisible(visible)
                    page_matches |= visible
            self.tabs.setTabVisible(self.tabs.indexOf(scroll), page_matches)
            any_page |= page_matches
        self.no_results.setVisible(not any_page)

    def apply_advanced(self, value, key=None):
        """Validate advanced edits atomically, then debounce the resulting patch."""
        if key is None:
            candidate = value
        else:
            candidate = self.get_plot()
            if key not in candidate:
                raise ValueError(f'未知 PlotSpec 字段：{key}')
            candidate[key] = value
        canonical = PlotSpec.from_dict(candidate).to_dict()
        self._load(canonical)
        self._changed()

    def open_advanced(self, key=None):
        try:
            plot = self.get_plot()
        except ValueError as error:
            self._report(error)
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle('元素覆盖 JSON' if key else '完整 PlotSpec JSON')
        dialog.resize(560, 560)
        box = QVBoxLayout(dialog)
        hint = QLabel('应用前完整校验。元素覆盖支持 show_value、show_color、include_in_range、value_dx、value_dy。')
        hint.setWordWrap(True)
        box.addWidget(hint)
        editor = QPlainTextEdit()
        editor.setObjectName('advanced_json')
        editor.setPlainText(json.dumps(plot[key] if key else plot, ensure_ascii=False, indent=2))
        box.addWidget(editor, 1)
        error_label = QLabel()
        error_label.setWordWrap(True)
        error_label.setStyleSheet('color: #b42318;')
        box.addWidget(error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('应用')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        box.addWidget(buttons)
        def apply():
            try:
                self.apply_advanced(json.loads(editor.toPlainText()), key)
            except (ValueError, TypeError) as error:
                error_label.setText(str(error))
                self._report(error)
                return
            dialog.accept()
        buttons.accepted.connect(apply)
        buttons.rejected.connect(dialog.reject)
        self._dialogs.append(dialog)
        dialog.finished.connect(lambda result: self._dialogs.remove(dialog) if dialog in self._dialogs else None)
        dialog.open()
        return dialog
