"""Native PlotSpec editor. The owner alone mutates sessions and renders plots."""
from copy import deepcopy
import json
import tkinter as tk
from tkinter import ttk, colorchooser

from domain.plot_spec import PlotSpec


# Chinese display names map to native values; no legacy preset IDs enter the model.
_CHOICES = {
    'kind': {'热力图': 'heatmap', '文本图': 'labels'},
    'layout': {'展开（118 元素）': 'expanded', '紧凑': 'compact'},
    'fmt': {'原始值': 'raw', '有效数字': 'g', '百分数（2位）': 'percent2',
            '小数（2位）': '2f', '小数（3位）': '3f', '小数（4位）': '4f', '科学计数': 'scientific'},
    'rounding': {'四舍五入': 'half_up', 'Python 舍入': 'python'},
    'num_ha': {'左对齐': 'left', '居中': 'center', '右对齐': 'right'},
    'cbar_orientation': {'垂直': 'vertical', '水平': 'horizontal'},
    'cbar_location': {'自动': 'auto', '左侧': 'left', '右侧': 'right', '上方': 'top', '下方': 'bottom'},
}
_GROUPS = [
    ('图形与画幅', [('kind', '图形类型'), ('layout', '元素布局'), ('title', '标题'),
     ('figsize', '画幅：宽、高（英寸 / 毫米）'), ('dpi', '分辨率 DPI'), ('bbox_tight', '紧凑裁剪'), ('transparent', '透明背景')]),
    ('字体与文本', [('font', '字体名称'), ('fmt', '数值格式'), ('rounding', '舍入方式'), ('unit', '单位'),
     ('show_symbol', '显示元素符号'), ('symbol_fs', '符号字号'), ('show_number', '显示原子序数'),
     ('number_fs', '序数字号'), ('num_x', '序数横向位置'), ('num_ha', '序数对齐'),
     ('show_value', '显示数值'), ('value_fs', '数值字号'), ('value_dx', '数值横向偏移'),
     ('value_dy', '数值纵向偏移'), ('label_wrap', '文本换行字符数（0关闭）'),
     ('label_fs', '文本字号'), ('label_dy', '文本纵向偏移'), ('label_color', '文本颜色（auto 自动）')]),
    ('背景与边框', [('empty', '空值颜色'), ('bg', '背景颜色'), ('highlight_bg', '高亮背景（空为自动）'),
     ('highlight_fg', '高亮文字（空为自动）'), ('plain_bg', '普通背景（空为自动）'),
     ('plain_fg', '普通文字（空为自动）'), ('edge', '边框：线宽、颜色（可关闭）')]),
    ('色条布局', [('show_cbar', '显示色条'), ('show_cbar_labels', '全局显示色条标签'),
     ('preserve_cbar_space', '保留色条空间'), ('check_label_overlap', '检查标签重叠'),
     ('cbar_orientation', '色条方向'), ('cbar_location', '色条位置'), ('cbar_label', '色条标题'),
     ('cbar_fraction', '色条宽度比例'), ('cbar_pad', '色条间距'), ('cbar_shrink', '色条长度比例')]),
    ('精确几何', [('margins', '绘图区：左、下、右、上（0–1）'),
     ('cbar_box', '色条框：左、下、宽、高（0–1）')]),
]
_COLORS = {'empty', 'bg', 'label_color', 'highlight_bg', 'highlight_fg', 'plain_bg', 'plain_fg'}
_NULLABLE = {'highlight_bg', 'highlight_fg', 'plain_bg', 'plain_fg'}
_TEXT = {'font', 'title', 'unit', 'cbar_label'}


def _color_text(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, tuple)) else (value or '')


def _parse_color(text):
    return json.loads(text) if text.strip().startswith('[') else text.strip()


class PlotSettingsPanel(ttk.Frame):
    """Scrollable, searchable forms with transactional, debounced top-level patches."""

    debounce_ms = 300

    def __init__(self, master, on_change, on_error=None):
        super().__init__(master)
        self.on_change, self.on_error = on_change, on_error
        self._loading = True
        self._job = None
        self._baseline = PlotSpec().to_dict()
        self._vars, self._enabled, self._sections = {}, {}, []
        self._bar_rows, self._nodes = [], []
        self.figsize_unit = tk.StringVar(self, value='英寸')
        self._figsize_unit_name = '英寸'
        self._figsize_inches = None
        self._figsize_display = None
        self.search_var = tk.StringVar(self)
        ttk.Label(self, text='搜索设置（中文或字段名）').pack(anchor='w')
        ttk.Entry(self, textvariable=self.search_var).pack(fill='x')
        self.search_var.trace_add('write', self._search)
        area = ttk.Frame(self)
        area.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(area, highlightthickness=0, width=370)
        scrollbar = ttk.Scrollbar(area, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        for title, fields in _GROUPS:
            section = self._section(title, ' '.join(k + ' ' + label for k, label in fields))
            for key, label in fields:
                self._field(section, key, label)
        self._build_range()
        self._build_colors()
        self._build_bar()
        advanced = self._section('高级自由配置', 'element_overrides 元素覆盖 JSON 全部字段')
        ttk.Button(advanced, text='元素覆盖 JSON…', command=lambda: self._json_dialog('element_overrides')).pack(fill='x')
        ttk.Button(advanced, text='完整 PlotSpec JSON…', command=self._json_dialog).pack(fill='x')
        self.error_var = tk.StringVar(self)
        ttk.Label(self, textvariable=self.error_var, foreground='#b00020', wraplength=360).pack(fill='x')
        self.bind('<Destroy>', self._destroyed, add='+')
        self.set_plot(self._baseline)
        self.figsize_unit.trace_add('write', self._change_figsize_unit)
        self._bind_wheel(self)

    def _section(self, title, keywords):
        frame = ttk.LabelFrame(self.body, text=title, padding=6)
        frame.pack(fill='x', padx=4, pady=4)
        self._sections.append((frame, (title + ' ' + keywords).casefold()))
        return frame

    def _var(self, key, boolean=False):
        var = tk.BooleanVar(self) if boolean else tk.StringVar(self)
        self._vars[key] = var
        var.trace_add('write', self._edited)
        return var

    def _entry(self, parent, var, width=12):
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.pack(side='left', fill='x', expand=True)
        return entry

    def _field(self, section, key, label):
        row = ttk.Frame(section)
        row.pack(fill='x', pady=2)
        default = self._baseline[key]
        var = self._var(key, isinstance(default, bool))
        if isinstance(default, bool):
            ttk.Checkbutton(row, text=label, variable=var).pack(anchor='w')
            return
        ttk.Label(row, text=label).pack(anchor='w')
        controls = ttk.Frame(row)
        controls.pack(fill='x')
        if key in _CHOICES:
            ttk.Combobox(controls, textvariable=var, values=list(_CHOICES[key]), state='readonly').pack(fill='x', expand=True)
        elif key in ('figsize', 'margins', 'cbar_box', 'edge'):
            if key != 'figsize':
                enabled = self._var(key + '_enabled', True)
                self._enabled[key] = enabled
                ttk.Checkbutton(controls, text='启用', variable=enabled).pack(side='left')
            parts = []
            for i in range(2 if key in ('figsize', 'edge') else 4):
                part = self._var(f'{key}.{i}')
                self._entry(controls, part, 7)
                parts.append(part)
            self._vars[key] = parts
            if key == 'figsize':
                ttk.Combobox(controls, textvariable=self.figsize_unit, values=['英寸', '毫米'],
                             state='readonly', width=5).pack(side='left', padx=(4, 0))
        else:
            self._entry(controls, var)
            if key in _COLORS:
                ttk.Button(controls, text='选色', command=lambda: self._choose(var)).pack(side='left')

    def _choose(self, var):
        chosen = colorchooser.askcolor(parent=self, title='选择颜色')[1]
        if chosen:
            var.set(chosen)

    def _read_figsize(self):
        display = tuple(var.get() for var in self._vars['figsize'])
        if display == self._figsize_display:
            return deepcopy(self._figsize_inches)
        scale = 25.4 if self._figsize_unit_name == '毫米' else 1
        return [float(text) / scale for text in display]

    def _display_figsize(self, inches):
        # Cache the exact native values so toggling units never introduces drift.
        scale = 25.4 if self._figsize_unit_name == '毫米' else 1
        for var, value in zip(self._vars['figsize'], inches):
            var.set(str(value * scale))
        self._figsize_inches = deepcopy(inches)
        self._figsize_display = tuple(var.get() for var in self._vars['figsize'])

    def _change_figsize_unit(self, *_):
        if self._loading:
            return
        chosen = self.figsize_unit.get()
        old_unit = self._figsize_unit_name
        try:
            if chosen not in ('英寸', '毫米'):
                raise ValueError('画幅单位必须为英寸或毫米')
            inches = PlotSpec.from_dict({'figsize': self._read_figsize()}).to_dict()['figsize']
        except (ValueError, TypeError) as error:
            self._loading = True
            try:
                self.figsize_unit.set(old_unit)
            finally:
                self._loading = False
            self._report(error)
            return
        self._loading = True
        try:
            self._figsize_unit_name = chosen
            self._display_figsize(inches)
        finally:
            self._loading = False
        # Keep any real edit's pending debounce; unit changes are display-only.

    def _build_range(self):
        frame = self._section('数值范围', 'norm 线性 中心 最小值 最大值')
        self.norm_mode = self._var('norm_mode')
        ttk.Combobox(frame, textvariable=self.norm_mode, values=['线性', '中心分段'], state='readonly').pack(fill='x')
        for key, label in [('norm_min', '最小值'), ('norm_center', '中心值（仅中心分段）'), ('norm_max', '最大值')]:
            row = ttk.Frame(frame)
            row.pack(fill='x')
            ttk.Label(row, text=label).pack(side='left')
            self._entry(row, self._var(key))

    def _build_colors(self):
        frame = self._section('配色与颜色节点', 'cmap 自定义 位置 颜色')
        self.custom_cmap = self._var('custom_cmap', True)
        ttk.Checkbutton(frame, text='使用自定义颜色节点', variable=self.custom_cmap).pack(anchor='w')
        self.cmap_name = self._var('cmap_name')
        ttk.Label(frame, text='内置配色名称（支持输入完整名称）').pack(anchor='w')
        ttk.Combobox(frame, textvariable=self.cmap_name, values=['coolwarm', 'viridis', 'plasma', 'RdBu', 'Blues', 'Greys']).pack(fill='x')
        ttk.Label(frame, text='节点：位置 0–1、颜色；必须包含 0 和 1').pack(anchor='w')
        self.nodes_frame = ttk.Frame(frame)
        self.nodes_frame.pack(fill='x')
        ttk.Button(frame, text='增加颜色节点', command=self._add_node).pack(fill='x')

    def _add_node(self, position='.5', color='#ffffff'):
        self._table_row(self.nodes_frame, self._nodes, [str(position), _color_text(color)], False)

    def _build_bar(self):
        frame = self._section('色条标签表格', 'cbar ticks labels visible fontsize 增加 删除 隐藏 字号')
        self.bar_enabled = self._var('bar_enabled', True)
        ttk.Checkbutton(frame, text='自定义色条标签（关闭使用自动刻度）', variable=self.bar_enabled).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x')
        ttk.Label(row, text='标签字号（整张色条）').pack(side='left')
        self._entry(row, self._var('bar_fontsize'))
        ttk.Label(frame, text='刻度值　　标签文字　　　逐行显示').pack(anchor='w')
        self.bar_frame = ttk.Frame(frame)
        self.bar_frame.pack(fill='x')
        ttk.Button(frame, text='增加色条标签行', command=self._add_bar_row).pack(fill='x')

    def _add_bar_row(self, tick='0', label='', visible=True):
        self._table_row(self.bar_frame, self._bar_rows, [str(tick), label, visible], True)

    def _table_row(self, parent, rows, values, bar):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2)
        variables = []
        for i, value in enumerate(values):
            var = tk.BooleanVar(self, value=value) if bar and i == 2 else tk.StringVar(self, value=value)
            var.trace_add('write', self._edited)
            variables.append(var)
            if bar and i == 2:
                ttk.Checkbutton(frame, variable=var, text='显示').pack(side='left')
            else:
                self._entry(frame, var, 9)
        record = (frame, variables)
        rows.append(record)
        if not bar:
            ttk.Button(frame, text='选色', command=lambda: self._choose(variables[1])).pack(side='left')
        ttk.Button(frame, text='删除', command=lambda: self._remove_row(rows, record)).pack(side='left')
        self._bind_wheel(frame)
        self._edited()

    def _remove_row(self, rows, record):
        rows.remove(record)
        record[0].destroy()
        self._edited()

    def _bind_wheel(self, widget):
        # Widget-local bindings avoid leaking bind_all handlers into sibling panels.
        widget.bind('<MouseWheel>', self._wheel, add='+')
        widget.bind('<Button-4>', lambda e: self._scroll(-1), add='+')
        widget.bind('<Button-5>', lambda e: self._scroll(1), add='+')
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _scroll(self, units):
        self.canvas.yview_scroll(units, 'units')
        return 'break'

    def _wheel(self, event):
        return self._scroll(-1 if event.delta > 0 else 1)

    def _search(self, *_):
        query = self.search_var.get().strip().casefold()
        for frame, keywords in self._sections:
            frame.pack_forget()
            if not query or query in keywords:
                frame.pack(fill='x', padx=4, pady=4)
        self.canvas.yview_moveto(0)

    def _edited(self, *_):
        if self._loading:
            return
        self._cancel_job()
        self._job = self.after(self.debounce_ms, self._commit)

    def _cancel_job(self):
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _destroyed(self, event):
        if event.widget is self:
            self._cancel_job()

    def _report(self, error):
        message = str(error)
        self.error_var.set(message)
        if self.on_error:
            self.on_error(message)

    def _commit(self):
        self._job = None
        try:
            plot = self.get_plot()
            baseline_before = self._baseline
            patch = {key: deepcopy(value) for key, value in plot.items() if value != self._baseline[key]}
            if patch:
                self.on_change(deepcopy(patch))
                # The callback may synchronously call set_plot with a new session snapshot.
                if self._baseline is baseline_before:
                    for key, value in patch.items():
                        self._baseline[key] = deepcopy(value)
            self.error_var.set('')
        except Exception as error:
            self._report(error)

    def get_plot(self):
        """Validate the entire current draft; never silently recover invalid input."""
        draft = deepcopy(self._baseline)
        draft['element_overrides'] = deepcopy(self._draft_overrides)
        key = 'plot'
        try:
            for _, fields in _GROUPS:
                for key, _ in fields:
                    var = self._vars[key]
                    if key == 'figsize':
                        draft[key] = self._read_figsize()
                    elif key in ('margins', 'cbar_box', 'edge'):
                        if key in self._enabled and not self._enabled[key].get():
                            draft[key] = None
                        else:
                            draft[key] = [float(v.get()) if key != 'edge' or i == 0 else _parse_color(v.get())
                                          for i, v in enumerate(var)]
                    elif key in _CHOICES:
                        draft[key] = _CHOICES[key][var.get()]
                    elif isinstance(self._baseline[key], bool):
                        draft[key] = var.get()
                    elif key in _TEXT:
                        draft[key] = var.get()
                    elif key in _COLORS:
                        draft[key] = None if key in _NULLABLE and not var.get().strip() else _parse_color(var.get())
                    else:
                        draft[key] = float(var.get())
            key = 'norm'
            bounds = [float(self._vars[k].get()) for k in ('norm_min', 'norm_max')]
            if self.norm_mode.get() == '中心分段':
                bounds.insert(1, float(self._vars['norm_center'].get()))
                draft['norm'] = ['twoslope', *bounds]
            elif self.norm_mode.get() == '线性':
                draft['norm'] = ['normalize', *bounds]
            else:
                raise ValueError('norm: 请选择线性或中心分段')
            key = 'cmap'
            draft['cmap'] = (['custom', [[float(v[0].get()), _parse_color(v[1].get())] for _, v in self._nodes]]
                             if self.custom_cmap.get() else self.cmap_name.get())
            if (self.custom_cmap.get() and isinstance(self._loaded_cmap, list)
                    and self._loaded_nodes == [(v[0].get(), v[1].get()) for _, v in self._nodes]):
                draft['cmap'] = deepcopy(self._loaded_cmap)
            key = 'cbar'
            if self.bar_enabled.get():
                rows = [variables for _, variables in self._bar_rows]
                draft['cbar'] = dict(ticks=[float(v[0].get()) for v in rows], labels=[v[1].get() for v in rows],
                                     visible=[v[2].get() for v in rows], fontsize=float(self._vars['bar_fontsize'].get()))
            else:
                draft['cbar'] = None
            return PlotSpec.from_dict(draft).to_dict()
        except (ValueError, KeyError, TypeError, tk.TclError) as error:
            raise ValueError(f'配置无效（{key}）：{error}') from error

    def set_plot(self, plot):
        canonical = PlotSpec.from_dict(plot).to_dict()
        self._cancel_job()
        self._loading = True
        try:
            self._baseline = deepcopy(canonical)
            self._draft_overrides = deepcopy(canonical['element_overrides'])
            for _, fields in _GROUPS:
                for key, _ in fields:
                    value = canonical[key]
                    var = self._vars[key]
                    if key == 'figsize':
                        self._display_figsize(value)
                    elif isinstance(var, list):
                        if key in self._enabled:
                            self._enabled[key].set(value is not None)
                        values = value if value is not None else ({'edge': [1, '#000000'], 'margins': [.05, .05, .95, .95], 'cbar_box': [.88, .15, .03, .7]}[key])
                        for item, part in zip(var, values):
                            item.set(_color_text(part) if key == 'edge' else str(part))
                    elif key in _CHOICES:
                        var.set(next(label for label, native in _CHOICES[key].items() if native == value))
                    elif key in _COLORS:
                        var.set(_color_text(value))
                    else:
                        var.set(value)
            norm = canonical['norm']
            self.norm_mode.set('中心分段' if norm[0] == 'twoslope' else '线性')
            self._vars['norm_min'].set(str(norm[1]))
            self._vars['norm_max'].set(str(norm[-1]))
            self._vars['norm_center'].set(str(norm[2] if norm[0] == 'twoslope' else (norm[1] + norm[2]) / 2))
            cmap = canonical['cmap']
            self.custom_cmap.set(not isinstance(cmap, str))
            self.cmap_name.set(cmap if isinstance(cmap, str) else 'coolwarm')
            self._clear_rows(self._nodes)
            if isinstance(cmap, str):
                colors = [[0, '#0000ff'], [1, '#ff0000']]
            else:
                colors = cmap[1]
                if not (isinstance(colors[0], list) and len(colors[0]) == 2):
                    # Preserve implicit evenly spaced palettes exactly until edited.
                    colors = [[i / (len(colors) - 1), color] for i, color in enumerate(colors)]
            self._loaded_cmap = deepcopy(cmap)
            for position, color in colors:
                self._add_node(position, color)
            self._loaded_nodes = [(v[0].get(), v[1].get()) for _, v in self._nodes]
            self._clear_rows(self._bar_rows)
            bar = canonical['cbar']
            self.bar_enabled.set(bar is not None)
            self._vars['bar_fontsize'].set(str(bar['fontsize'] if bar else 8))
            if bar:
                for tick, label, visible in zip(bar['ticks'], bar['labels'], bar['visible']):
                    self._add_bar_row(tick, label, visible)
            self.error_var.set('')
        finally:
            self._loading = False

    @staticmethod
    def _clear_rows(rows):
        for frame, _ in rows:
            frame.destroy()
        rows.clear()

    def _apply_advanced(self, value, key=None):
        # Validate before touching forms or canceling a pending edit.
        current = self.get_plot()
        if key:
            current[key] = value
        else:
            current = value
        validated = PlotSpec.from_dict(current).to_dict()
        baseline = deepcopy(self._baseline)
        self.set_plot(validated)
        self._baseline = baseline
        self._edited()

    def _json_dialog(self, key=None):
        try:
            current = self.get_plot()
        except ValueError as error:
            self._report(error)
            return
        dialog = tk.Toplevel(self)
        dialog.title('元素覆盖配置' if key else '完整 PlotSpec 高级配置')
        dialog.transient(self.winfo_toplevel())
        dialog.geometry('720x560')
        ttk.Label(dialog, text='应用前完整验证；元素覆盖支持 show_value / show_color / include_in_range / value_dx / value_dy。', wraplength=680).pack(fill='x')
        text = tk.Text(dialog, wrap='none', undo=True)
        text.pack(fill='both', expand=True)
        text.insert('1.0', json.dumps(current[key] if key else current, ensure_ascii=False, indent=2))
        error_var = tk.StringVar(dialog)
        ttk.Label(dialog, textvariable=error_var, foreground='#b00020', wraplength=680).pack(fill='x')
        def apply():
            try:
                self._apply_advanced(json.loads(text.get('1.0', 'end')), key)
            except (ValueError, TypeError) as error:
                error_var.set(str(error))
                self._report(error)
                return
            dialog.destroy()
        buttons = ttk.Frame(dialog)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='应用', command=apply).pack(side='right')
        ttk.Button(buttons, text='取消', command=dialog.destroy).pack(side='right')
