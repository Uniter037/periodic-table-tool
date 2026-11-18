"""Native PlotSpec desktop: widgets adapt data, application services own state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from application.workbench_session import WorkbenchSession, MigrationRequired
from application.plot_presets import PRESETS, preset
from application.plot_service import prepare_plot
from core.document import user_directory, write_document
from core.dataio import parse_data
from core.elements_data import ALL_SYMBOLS
from core.jobs import RenderJob
from core.saver import auto_name
from infrastructure.diagnostics import DiagnosticService, DiagnosticSettings
from .dpi import enable_high_dpi
from .theme import apply_theme, apply_scale
from .preview import PreviewCanvas
from .plot_settings_v2 import PlotSettingsPanel
from .layout_issues import LayoutIssuesPanel


class App(tk.Tk):
    def __init__(self, user_dir=None, *, start_preview=True, recover=True):
        self.dpi_status = enable_high_dpi()
        super().__init__()
        self.title('元素周期表绘图工作台 · 2.0 开发版')
        self.geometry('1440x860')
        self.minsize(800, 600)
        self.user_dir = Path(user_dir or user_directory())
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.session = WorkbenchSession(self.user_dir)
        self.preferences_path = self.user_dir / 'workbench-v2.json'
        self.preferences = self._load_preferences()
        self.preview_job, self.export_job = RenderJob(), RenderJob()
        self._preview_after = self._draft_after = self._poll_after = None
        self._layout = None
        self._drawer = False
        self._table_entry = None
        self._colorbar_box = None
        self._preview_warnings = []
        self._closed = False
        self.last_output = None
        self.export_context = None
        self.output_dir = self.preferences.get('output_dir', str(Path.cwd() / 'output'))
        self.output_base = self.preferences.get('output_base', 'periodic_table')
        self.format_var = tk.StringVar(self, self.preferences.get('format', 'svg'))
        self.status = tk.StringVar(self, '导入文件、粘贴数据或载入示例开始绘图')
        self.log_enabled = tk.BooleanVar(self, self.preferences.get('log_enabled', True) is True)
        self.log_level = tk.StringVar(self, self.preferences.get('log_level', 'INFO'))
        if self.log_level.get() not in ('DEBUG', 'INFO', 'WARNING'):
            self.log_level.set('INFO')
        self.diagnostics = DiagnosticService(self.user_dir / 'logs-v2',
            DiagnosticSettings(enabled=self.log_enabled.get(), level=self.log_level.get()))
        apply_theme(self)
        self._build()
        self._sync()
        self.bind('<Configure>', self._resize, add='+')
        self.bind('<Control-s>', lambda e: self.save())
        self.bind('<Control-o>', lambda e: self.open_project())
        self.bind('<Control-z>', lambda e: self._history(-1))
        self.bind('<Control-y>', lambda e: self._history(1))
        self.protocol('WM_DELETE_WINDOW', self._close)
        self._poll_after = self.after(80, self._poll)
        if start_preview:
            self.schedule_preview()
        if recover and self.session.draft_path.exists():
            self.after_idle(self._recover)
        self.diagnostics.record('INFO', 'app.started', '独立绘图工作台已启动')

    def _load_preferences(self):
        try:
            value = json.loads(self.preferences_path.read_text(encoding='utf-8'))
            if not isinstance(value, dict):
                return {}
            if value.get('layout') not in ('auto', 'wide', 'compact'):
                value['layout'] = 'auto'
            if str(value.get('scale')) not in ('auto', '.8', '1.0', '1.25', '1.5'):
                value['scale'] = 'auto'
            return value
        except (ValueError, OSError):
            return {}

    def _build(self):
        menu = tk.Menu(self)
        project = tk.Menu(menu, tearoff=False)
        for label, command in [('新建', self.new), ('打开项目…', self.open_project),
                               ('保存', self.save), ('另存为…', lambda: self.save(True)),
                               ('导入数据…', self.import_file), ('选择 Excel 数据组…', self.dataset_dialog),
                               ('批量导出数据组…', self.batch_dialog), ('输出设置…', self.output_settings)]:
            project.add_command(label=label, command=command)
        menu.add_cascade(label='项目', menu=project)
        view = tk.Menu(menu, tearoff=False)
        view.add_command(label='布局与缩放…', command=self.view_settings)
        view.add_command(label='预览适合窗口', command=lambda: self.preview.fit())
        view.add_command(label='样图对照…', command=self.reference)
        menu.add_cascade(label='视图', menu=view)
        logs = tk.Menu(menu, tearoff=False)
        logs.add_checkbutton(label='启用日志', variable=self.log_enabled, command=self.configure_logs)
        for level in ('DEBUG', 'INFO', 'WARNING'):
            logs.add_radiobutton(label=level, variable=self.log_level, value=level, command=self.configure_logs)
        logs.add_command(label='临时详细排错（30分钟）', command=lambda: self.diagnostics.start_session(30))
        logs.add_command(label='结束临时排错', command=self.diagnostics.stop_session)
        logs.add_command(label='查看本次日志', command=self.show_logs)
        logs.add_command(label='导出诊断包…', command=self.export_logs)
        menu.add_cascade(label='日志与排错', menu=logs)
        self.config(menu=menu)
        self.toolbar = ttk.Frame(self, padding=8, style='Toolbar.TFrame')
        self.toolbar.pack(fill='x')
        self.buttons = []
        for label, command in [('导入文件', self.import_file), ('粘贴数据', self.paste),
                               ('打开项目', self.open_project), ('保存项目', self.save),
                               ('撤销', lambda: self._history(-1)), ('载入示例', self.demo),
                               ('绘图设置', self.toggle_settings), ('导出图片', self.export),
                               ('输出目录', self.open_output)]:
            button = ttk.Button(self.toolbar, text=label, command=command,
                                style='Accent.TButton' if label == '导出图片' else 'TButton')
            self.buttons.append(button)
        self.footer = ttk.Frame(self, padding=(8, 4))
        self.footer.pack(side='bottom', fill='x')
        ttk.Button(self.footer, text='取消任务', command=self.cancel).pack(side='right')
        ttk.Label(self.footer, textvariable=self.status, wraplength=650).pack(side='left', fill='x', expand=True)
        self.main_area = ttk.Frame(self, padding=8)
        self.main_area.pack(fill='both', expand=True)
        self.panes = tk.PanedWindow(self.main_area, sashwidth=8, borderwidth=0, background='#e5e7eb')
        self.settings_area = ttk.Frame(self.main_area, width=360)
        self.settings_area.pack_propagate(False)
        presetbar = ttk.Frame(self.settings_area, padding=(4, 0, 4, 6))
        presetbar.pack(fill='x')
        ttk.Label(presetbar, text='外观预设', style='Header.TLabel').pack(anchor='w')
        self.preset_combo = ttk.Combobox(presetbar, state='readonly')
        self.preset_combo.pack(fill='x', pady=4)
        self.preset_combo.bind('<<ComboboxSelected>>', self.apply_selected_preset)
        row = ttk.Frame(presetbar)
        row.pack(fill='x')
        ttk.Button(row, text='保存预设', command=self.save_preset).pack(side='left')
        ttk.Button(row, text='删除预设', command=self.delete_preset).pack(side='left')
        self.include_data = tk.BooleanVar(self, False)
        ttk.Checkbutton(presetbar, text='预设包含数据', variable=self.include_data).pack(anchor='w')
        self.settings = PlotSettingsPanel(self.settings_area, self._settings_changed, self._invalid)
        self.settings.pack(fill='both', expand=True)
        self.tabs = ttk.Notebook(self.panes)
        data_tab = ttk.Frame(self.tabs)
        self.tabs.add(data_tab, text='数据')
        controls = ttk.Frame(data_tab)
        controls.pack(fill='x', side='bottom')
        ttk.Button(controls, text='自动范围', command=lambda: self.perform(self.session.auto_range)).pack(fill='x')
        ttk.Button(controls, text='Excel 数据组', command=self.dataset_dialog).pack(fill='x')
        self.table = ttk.Treeview(data_tab, columns=('number', 'symbol', 'value'), show='headings', selectmode='browse')
        for name, label, width in [('number', '序数', 50), ('symbol', '元素', 55), ('value', '数值 / 标注', 120)]:
            self.table.heading(name, text=label)
            self.table.column(name, width=width, minwidth=40, stretch=name == 'value')
        bar = ttk.Scrollbar(data_tab, orient='vertical', command=self.table.yview)
        bar.pack(side='right', fill='y')
        self.table.configure(yscrollcommand=bar.set)
        self.table.pack(fill='both', expand=True)
        for index, symbol in enumerate(ALL_SYMBOLS, 1):
            self.table.insert('', 'end', iid=symbol, values=(index, symbol, ''))
        self.table.bind('<Double-1>', self._edit_table)
        self.mark_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.mark_tab, text='标注')
        self.selected_symbol = tk.StringVar(self, '')
        self.mark_value = tk.StringVar(self, '')
        ttk.Label(self.mark_tab, text='点击预览中的元素，或在数据表中双击编辑', wraplength=220).pack(anchor='w')
        ttk.Label(self.mark_tab, textvariable=self.selected_symbol, style='Header.TLabel').pack(anchor='w')
        entry = self.mark_entry = ttk.Entry(self.mark_tab, textvariable=self.mark_value)
        entry.pack(fill='x', pady=4)
        entry.bind('<Return>', lambda e: self.apply_mark())
        entry.bind('<Escape>', lambda e: self.select_element(self.selected_symbol.get()))
        row = ttk.Frame(self.mark_tab)
        row.pack(fill='x')
        for label, command in [('应用', self.apply_mark), ('清除', self.clear_mark), ('显示 / 位置…', self.element_options)]:
            ttk.Button(row, text=label, command=command).pack(fill='x')
        self.issues = LayoutIssuesPanel(self.tabs, self.select_element)
        self.tabs.add(self.issues, text='排版检查')
        self.preview_frame = ttk.Frame(self.panes, padding=4)
        tools = ttk.Frame(self.preview_frame)
        tools.pack(side='bottom', fill='x')
        self.edit_enabled = tk.BooleanVar(self, True)
        ttk.Checkbutton(tools, text='标注编辑', variable=self.edit_enabled,
                        command=lambda: self.preview.set_edit_enabled(self.edit_enabled.get())).pack(side='left')
        self.preview = PreviewCanvas(self.preview_frame, on_click=self.select_element,
                                     on_move=self.move_label, on_colorbar_move=self.move_colorbar)
        self.preview.pack(fill='both', expand=True)
        for label, command in [('−', self.preview.zoom_out), ('+', self.preview.zoom_in),
                               ('适应', self.preview.fit), ('1:1', self.preview.actual_size), ('样图对照', self.reference)]:
            ttk.Button(tools, text=label, width=5, command=command).pack(side='left')
        self.refresh_presets()

    def _resize(self, event=None):
        if event is not None and event.widget is not self:
            return
        width = max(800, self.winfo_width())
        value = self.preferences.get('scale', 'auto')
        scale = max(.8, min(1.3, width / 1280)) if value == 'auto' else float(value)
        effective_scale = round(scale, 1 if value == 'auto' else 2)
        if getattr(self, '_font_scale', None) != effective_scale:
            self._font_scale = effective_scale
            apply_scale(self, None, self._font_scale)
        col = row = used = 0
        for button in self.buttons:
            requested = button.winfo_reqwidth() + 6
            if used and used + requested > width - 24:
                row, col, used = row + 1, 0, 0
            button.grid(row=row, column=col, padx=3, pady=2, sticky='w')
            used, col = used + requested, col + 1
        mode = self.preferences.get('layout', 'auto')
        layout = ('wide' if width >= 1200 else 'compact') if mode == 'auto' else mode
        key = (layout, self._drawer)
        if key == self._layout:
            return
        self._layout = key
        self.settings_area.grid_forget()
        self.settings_area.place_forget()
        for child in self.panes.panes():
            self.panes.forget(child)
        self.main_area.rowconfigure(0, weight=1)
        self.main_area.columnconfigure(0, weight=1)
        self.panes.grid(row=0, column=0, sticky='nsew')
        if layout == 'wide':
            self.panes.configure(orient='horizontal')
            self.panes.add(self.tabs, minsize=250, width=270, stretch='never')
            self.panes.add(self.preview_frame, minsize=280, stretch='always')
            self.settings_area.configure(width=max(340, round(350 * scale)))
            self.settings_area.grid(row=0, column=1, sticky='nsew', padx=(8, 0))
        else:
            self.panes.configure(orient='vertical')
            self.panes.add(self.preview_frame, minsize=180, stretch='always')
            self.panes.add(self.tabs, minsize=170, height=195, stretch='never')
            if self._drawer:
                self.settings_area.place(relx=1, y=0, anchor='ne', width=min(width - 20, 420), relheight=1)
                self.settings_area.lift()

    def toggle_settings(self):
        self._drawer = not self._drawer
        self._layout = None
        self._resize()

    def _invalid(self, message):
        self.status.set(str(message))
        self.preview.set_stale(True)
        self.preview_job.invalidate()
        if self._preview_after:
            self.after_cancel(self._preview_after)
            self._preview_after = None

    def perform(self, operation, *, sync=True):
        try:
            result = operation()
            if sync:
                self._sync()
                self.schedule_preview()
            return result if result is not None else True
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self._invalid(exc)
            self.diagnostics.record('ERROR', 'operation.failed', '操作未完成', details={'error_type': type(exc).__name__})
            return False

    def _settings_changed(self, patch):
        # Let the panel retain its prior baseline and show errors if the service
        # rejects e.g. a named Matplotlib color which passes structural checks.
        self.session.patch(plot=patch)
        self._sync(update_settings=False, update_mark=False)
        self.schedule_preview()

    def _sync(self, *, update_settings=True, update_mark=True):
        if update_settings:
            self.settings.set_plot(self.session.plot)
        data = self.session.data
        for index, symbol in enumerate(ALL_SYMBOLS, 1):
            self.table.item(symbol, values=(index, symbol, data.get(symbol, '')))
        symbol = self.selected_symbol.get()
        if update_mark:
            self.mark_value.set(str(data.get(symbol, '')))
        self.title(f"{'* ' if self.session.dirty else ''}{self.session.path.name if self.session.path else '未命名项目'} · 周期表工作台 2.0 开发版")

    def _valid_controls(self):
        if not self._flush_table():
            return False
        try:
            plot = self.settings.get_plot()
            if plot != self.session.plot:
                self.session.patch(plot=plot)
            return True
        except ValueError as exc:
            self._invalid(exc)
            return False

    def schedule_preview(self):
        self.preview.set_stale(True)
        self.preview_job.invalidate()
        self.issues.set_issues([])
        if self._preview_after:
            self.after_cancel(self._preview_after)
        self._preview_after = self.after(220, self._start_preview)
        if self._draft_after:
            self.after_cancel(self._draft_after)
        self._draft_after = self.after(800, self._save_draft)

    def _save_draft(self):
        self._draft_after = None
        if self.session.dirty:
            self.perform(self.session.save_draft, sync=False)

    def _start_preview(self):
        self._preview_after = None
        if not self._valid_controls():
            return
        try:
            spec, data, warnings = prepare_plot(self.session.plot, self.session.data)
            self._preview_warnings = warnings
            self.preview_job.start({'engine': 'v2', 'mode': 'preview', 'plot': spec.to_dict(), 'data': data})
            self.status.set('; '.join(warnings) or '正在更新预览…')
        except (ValueError, OSError) as exc:
            self._invalid(exc)

    def _poll(self):
        self._poll_after = None
        for worker, is_export in ((self.preview_job, False), (self.export_job, True)):
            event = worker.poll()
            if not event:
                continue
            if event[0] == 'error':
                self.status.set('绘图失败：' + event[1])
                self.diagnostics.record('ERROR', 'render.failed', '绘图任务失败')
            elif event[0] == 'progress' and is_export:
                self.status.set(f'正在导出 {event[1]}/{event[2]}…')
            elif event[0] == 'done':
                packet = event[1]
                if is_export:
                    self._publish(packet)
                else:
                    self.preview.show_packet(packet['png'], packet['hits'])
                    self.preview.set_stale(False)
                    self.preview.set_selected(self.selected_symbol.get())
                    self._colorbar_box = packet.get('cbar_box')
                    self.preview.set_colorbar_box(None if self.session.plot['bbox_tight'] else self._colorbar_box)
                    self.issues.set_issues(packet.get('layout_issues', []))
                    if not self.export_job.active:
                        self.status.set('; '.join(self._preview_warnings + packet.get('layout_warnings', [])) or '预览已更新；点击元素编辑，左拖标注，右拖平移')
        if not self._closed:
            self._poll_after = self.after(80, self._poll)

    def _edit_table(self, event):
        symbol = self.table.identify_row(event.y)
        if not symbol or self.table.identify_column(event.x) != '#3' or not self._flush_table():
            return
        box = self.table.bbox(symbol, 'value')
        if not box:
            return
        entry = ttk.Entry(self.table)
        entry.insert(0, str(self.session.data.get(symbol, '')))
        entry.place(x=box[0], y=box[1], width=box[2], height=box[3])
        self._table_entry = (symbol, entry)
        entry.focus_set()
        entry.selection_range(0, 'end')
        entry.bind('<Return>', lambda e: self._flush_table())
        entry.bind('<Escape>', lambda e: self._cancel_table())

    def _cancel_table(self):
        if self._table_entry:
            self._table_entry[1].destroy()
            self._table_entry = None

    def _flush_table(self):
        if not self._table_entry:
            return True
        symbol, entry = self._table_entry
        value = entry.get()
        try:
            # Validate and commit both drafts before resetting either widget.
            self.session.patch(plot=self.settings.get_plot(),
                               data={symbol: value if value.strip() else None})
            self._cancel_table()
            self._sync()
            self.schedule_preview()
            return True
        except ValueError as exc:
            self._invalid(exc)
            entry.focus_set()
            return False

    def select_element(self, symbol):
        if symbol not in ALL_SYMBOLS or self.preview._is_stale or not self._flush_table():
            return
        self.selected_symbol.set(symbol)
        self.mark_value.set(str(self.session.data.get(symbol, '')))
        self.preview.set_selected(symbol)
        self.table.selection_set(symbol)
        self.table.see(symbol)
        self.tabs.select(self.mark_tab)
        self.mark_entry.focus_set()
        self.mark_entry.selection_range(0, 'end')

    def apply_mark(self):
        symbol = self.selected_symbol.get()
        if symbol in ALL_SYMBOLS:
            value = self.mark_value.get()
            if self._valid_controls():
                self.perform(lambda: self.session.patch(data={symbol: value if value.strip() else None}))

    def clear_mark(self):
        symbol = self.selected_symbol.get()
        if symbol in ALL_SYMBOLS and self._valid_controls():
            self.perform(lambda: self.session.patch(data={symbol: None}))

    def move_label(self, symbol, dx, dy):
        if not self.edit_enabled.get() or self.preview._is_stale:
            return
        rows = self.session.plot['element_overrides']
        row = rows.setdefault(symbol, {})
        row.update(value_dx=row.get('value_dx', 0) + dx, value_dy=row.get('value_dy', 0) + dy)
        self.perform(lambda: self.session.patch(plot={'element_overrides': rows}))

    def move_colorbar(self, x, y):
        if self._colorbar_box and self.edit_enabled.get() and not self.preview._is_stale:
            self.perform(lambda: self.session.patch(plot={'cbar_box': [x, y, *self._colorbar_box[2:]]}))

    def element_options(self):
        symbol = self.selected_symbol.get()
        if symbol not in ALL_SYMBOLS:
            self.status.set('请先点击预览中的元素')
            return
        window = tk.Toplevel(self)
        window.title(symbol + ' 显示与位置')
        row = self.session.plot['element_overrides'].get(symbol, {})
        variables = {}
        for key, label in [('show_value', '显示标注'), ('show_color', '显示数据着色'), ('include_in_range', '参与自动范围')]:
            var = variables[key] = tk.BooleanVar(window, row.get(key, True))
            ttk.Checkbutton(window, text=label, variable=var).pack(anchor='w', padx=12, pady=4)
        for key, label in [('value_dx', '水平偏移（格宽）'), ('value_dy', '垂直偏移（格高）')]:
            ttk.Label(window, text=label).pack(anchor='w', padx=12)
            var = variables[key] = tk.StringVar(window, str(row.get(key, 0)))
            ttk.Entry(window, textvariable=var).pack(fill='x', padx=12, pady=4)
        def commit(reset=False):
            rows = self.session.plot['element_overrides']
            try:
                if reset:
                    rows.pop(symbol, None)
                else:
                    rows[symbol] = {key: (float(var.get()) if key.startswith('value_') else var.get()) for key, var in variables.items()}
                self.session.patch(plot={'element_overrides': rows})
                self._sync()
                self.schedule_preview()
                window.destroy()
            except ValueError as exc:
                messagebox.showerror('修改失败', str(exc), parent=window)
        ttk.Button(window, text='应用', command=commit).pack(side='left', padx=12, pady=8)
        ttk.Button(window, text='恢复默认', command=lambda: commit(True)).pack(side='right', padx=12)

    def _history(self, direction):
        self._cancel_table()
        self.perform(self.session.undo if direction < 0 else self.session.redo)

    def demo(self):
        if self._valid_controls():
            self.perform(lambda: self.session.patch(data={'H': 0, 'C': -.5, 'O': .5, 'Ti': -.8, 'Ni': .8}, replace_data=True))

    def paste(self):
        window = tk.Toplevel(self)
        window.title('粘贴元素数据')
        text = tk.Text(window, width=50, height=18)
        text.pack(fill='both', expand=True, padx=8, pady=8)
        try:
            text.insert('1.0', self.clipboard_get())
        except tk.TclError:
            pass
        ttk.Label(window, text='每行例如 Ni,0.5；应用后替换当前数据组').pack()
        def apply():
            if not self._valid_controls():
                return
            if self.perform(lambda: self.session.patch(data=parse_data(text.get('1.0', 'end'), preserve_text=True), replace_data=True)) is not False:
                window.destroy()
        ttk.Button(window, text='应用数据', command=apply).pack(pady=8)

    def import_file(self, path=None):
        path = path or filedialog.askopenfilename(filetypes=[('数据文件', '*.xlsx *.csv *.tsv *.txt *.json'), ('所有文件', '*.*')])
        if not path or not self._valid_controls():
            return
        if Path(path).suffix.lower() == '.xlsx':
            from application.excel_import import ExcelImportService
            from .import_wizard import ExcelImportDialog
            try:
                service = ExcelImportService(path)
                def commit(preview):
                    if not self._valid_controls():
                        raise ValueError('请先修正当前未提交的输入')
                    self.session.import_excel(preview)
                    self._sync()
                    self.schedule_preview()
                ExcelImportDialog(self, service.sheets(), service.preview, commit)
            except (ValueError, OSError) as exc:
                self._invalid(exc)
        else:
            self.perform(lambda: self.session.patch(data=parse_data(Path(path).read_text(encoding='utf-8-sig'), preserve_text=True), replace_data=True))

    def dataset_dialog(self, batch=False):
        snapshot = self.session.collection.snapshot()
        datasets = snapshot['datasets']
        if not datasets:
            self.status.set('请先导入 Excel 数据组')
            return
        window = tk.Toplevel(self)
        window.title('选择批量导出数据组' if batch else '切换 Excel 数据组')
        choices = tk.Listbox(window, selectmode='extended' if batch else 'browse', width=55, exportselection=False)
        choices.pack(fill='both', expand=True, padx=8, pady=8)
        conditions = {c['id']: c for c in snapshot['conditions']}
        metrics = {m['id']: m for m in snapshot['metrics']}
        for item in datasets:
            label = conditions.get(item['condition_id'], {}).get('label', item['condition_id'])
            metric = metrics.get(item['metric_id'], {}).get('name', item['metric_id'])
            choices.insert('end', f'{metric} · {label}')
        choices.selection_set(0, 'end' if batch else 0)
        def commit():
            if not self._valid_controls():
                return
            selected = [datasets[i]['id'] for i in choices.curselection()]
            if not selected:
                return
            if batch:
                result = self.perform(lambda: self.session.batch_items(selected), sync=False)
                if result is not False:
                    self._begin_export(result)
                    window.destroy()
            elif self.perform(lambda: self.session.select_dataset(selected[0])) is not False:
                window.destroy()
        ttk.Button(window, text='导出' if batch else '切换', command=commit).pack(pady=8)

    def batch_dialog(self):
        if self._valid_controls():
            self.dataset_dialog(True)

    def refresh_presets(self):
        self._preset_items = [('builtin', key, label) for key, (label, _) in PRESETS.items()]
        self._preset_items += [('user', name, '我的预设 · ' + name) for name in self.session.list_presets()]
        self.preset_combo.configure(values=[item[2] for item in self._preset_items])

    def apply_selected_preset(self, event=None):
        index = self.preset_combo.current()
        if index < 0 or not self._flush_table():
            return
        kind, name, _ = self._preset_items[index]
        if kind == 'builtin':
            self.perform(lambda: self.session.apply_preset({'plot': preset(name)}))
        else:
            self.perform(lambda: self.session.load_preset(name, self.include_data.get()))

    def save_preset(self):
        if not self._valid_controls():
            return
        name = simpledialog.askstring('保存预设', '输入预设名称：', parent=self)
        if name:
            if name in self.session.list_presets() and not messagebox.askyesno('覆盖预设', f'更新已有预设“{name}”？', parent=self):
                return
            self.perform(lambda: self.session.save_preset(name, self.include_data.get()), sync=False)
            self.refresh_presets()

    def delete_preset(self):
        index = self.preset_combo.current()
        if index < 0 or self._preset_items[index][0] != 'user':
            return
        name = self._preset_items[index][1]
        if messagebox.askyesno('删除预设', f'删除“{name}”？', parent=self):
            self.perform(lambda: self.session.delete_preset(name), sync=False)
            self.preset_combo.set('')
            self.refresh_presets()

    def _confirm_discard(self):
        if not self._valid_controls():
            if not messagebox.askyesno('尚有无效输入', '放弃当前未保存的修改并继续？', parent=self):
                return False
            self._cancel_table()
            self.session.clear_draft()
            return True
        if not self.session.dirty:
            return True
        answer = messagebox.askyesnocancel('未保存的修改', '保存当前项目后继续？', parent=self)
        if answer is None:
            return False
        if answer:
            return bool(self.save())
        self.session.clear_draft()
        return True

    def new(self):
        if self._confirm_discard():
            self.session = WorkbenchSession(self.user_dir)
            self.selected_symbol.set('')
            self._sync()
            self.schedule_preview()

    def open_project(self, path=None):
        path = path or filedialog.askopenfilename(filetypes=[('绘图项目', '*.ptproj'), ('JSON', '*.json')])
        if not path or not self._confirm_discard():
            return False
        try:
            report = self.session.load(path)
        except MigrationRequired as exc:
            details = json.dumps(exc.report, ensure_ascii=False, indent=2)
            window = tk.Toplevel(self)
            window.title('旧项目迁移预览')
            ttk.Label(window, text='转换为新工作区；保存时另存副本，原项目保留。').pack(padx=10, pady=6)
            text = tk.Text(window, width=85, height=22)
            text.insert('1.0', details)
            text.configure(state='disabled')
            text.pack(fill='both', expand=True, padx=8)
            def migrate():
                if self.perform(lambda: self.session.load(path, migrate=True)) is not False:
                    window.destroy()
            ttk.Button(window, text='迁移并打开', command=migrate).pack(pady=8)
            return False
        except (ValueError, OSError) as exc:
            self._invalid(exc)
            return False
        self._sync()
        self.schedule_preview()
        return True

    def save(self, save_as=False, path=None):
        if not self._valid_controls():
            return False
        target = path or (None if save_as else self.session.path)
        if target is None:
            source = self.session.source_path
            target = filedialog.asksaveasfilename(defaultextension='.ptproj',
                initialfile=(source.stem + '-migrated.ptproj') if source else 'untitled.ptproj',
                filetypes=[('绘图项目', '*.ptproj')])
        if not target:
            return False
        result = self.perform(lambda: self.session.save(target), sync=False)
        if result is not False:
            self.session.clear_draft()
            self._sync(update_settings=False)
            self.status.set(f'项目已保存：{target}')
            return True
        return False

    def _recover(self):
        if messagebox.askyesno('恢复工作', '发现未保存的 2.0 工作区，是否恢复？', parent=self):
            self.perform(self.session.recover_draft)

    def export(self):
        if self._valid_controls():
            self._begin_export([({}, self.session.data)])

    def _begin_export(self, items):
        if self.export_job.active:
            self.status.set('已有导出任务运行，请等待或取消')
            return
        try:
            if not re.fullmatch(r'[\w-]{1,80}', self.output_base):
                raise ValueError('文件基础名仅可包含1～80个字母、数字、中文、下划线或连字符')
            config = self.session.plot
            if config['figsize'][0] * config['figsize'][1] * config['dpi'] ** 2 > 64_000_000:
                raise ValueError('画幅超过6400万像素，请降低尺寸或DPI')
            warnings, prepared = [], []
            for index, (metadata, data) in enumerate(items, 1):
                _, values, rows = prepare_plot(config, data)
                if not values:
                    raise ValueError('当前数据组为空')
                warnings.extend(rows)
                name = self.output_base if len(items) == 1 else f'{self.output_base}_{index:03d}'
                prepared.append((name, values))
            if warnings and not messagebox.askyesno('确认绘图范围', '\n'.join(dict.fromkeys(warnings)) + '\n继续导出？', parent=self):
                return
            fmt = self.format_var.get()
            if fmt not in ('svg', 'png', 'pdf'):
                raise ValueError('输出格式须为 svg/png/pdf')
            self.export_context = (str(Path(self.output_dir).resolve()), fmt)
            self.export_job.start({'engine': 'v2', 'mode': 'batch' if len(items) > 1 else 'export',
                                   'plot': config, 'items': prepared, 'format': fmt})
            self.status.set('正在导出…')
        except (ValueError, OSError) as exc:
            self._invalid(exc)

    def _publish(self, packet):
        created = []
        try:
            directory, fmt = self.export_context
            for source, name in packet['files']:
                destination = auto_name(directory, name, fmt)
                created.append(destination)
                shutil.copyfile(source, destination)
            self.last_output = created[-1] if created else None
            self.status.set(f'已导出 {len(created)} 张图片：{self.last_output}')
            self.diagnostics.record('INFO', 'export.completed', '图片导出完成', details={'count': len(created)})
        except OSError as exc:
            for path in created:
                Path(path).unlink(missing_ok=True)
            self.status.set('导出未完成：' + str(exc))

    def cancel(self):
        for worker in (self.preview_job, self.export_job):
            worker.cancel()
        if self._preview_after:
            self.after_cancel(self._preview_after)
            self._preview_after = None
        self.status.set('绘图任务已取消')

    def reference(self):
        from .reference_view import open_reference_window
        path = filedialog.askopenfilename(filetypes=[('样图', '*.png *.jpg *.jpeg *.svg')])
        if path:
            snapshot = lambda: self.preview._source.copy() if self.preview._source else None
            open_reference_window(self, path, snapshot(), snapshot)

    def output_settings(self):
        window = tk.Toplevel(self)
        window.title('输出设置')
        directory = tk.StringVar(window, self.output_dir)
        base = tk.StringVar(window, self.output_base)
        for label, variable in [('保存目录', directory), ('文件基础名（自动附加时间戳）', base)]:
            ttk.Label(window, text=label).pack(anchor='w', padx=10, pady=4)
            ttk.Entry(window, textvariable=variable, width=55).pack(fill='x', padx=10)
        def choose():
            path = filedialog.askdirectory(parent=window)
            if path:
                directory.set(path)
        ttk.Button(window, text='选择目录', command=choose).pack(anchor='w', padx=10, pady=4)
        ttk.Combobox(window, textvariable=self.format_var, state='readonly', values=('svg', 'png', 'pdf')).pack(padx=10)
        def commit():
            if not directory.get().strip() or not re.fullmatch(r'[\w-]{1,80}', base.get()):
                messagebox.showerror('输出设置无效', '目录不能为空；基础名仅允许字母、中文、数字、下划线和连字符。', parent=window)
                return
            self.output_dir, self.output_base = directory.get(), base.get()
            self._save_preferences()
            window.destroy()
        ttk.Button(window, text='应用', command=commit).pack(pady=8)

    def open_output(self):
        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            os.startfile(self.output_dir)
        except OSError as exc:
            self._invalid(exc)

    def view_settings(self):
        window = tk.Toplevel(self)
        window.title('布局与界面缩放')
        layout = tk.StringVar(window, self.preferences.get('layout', 'auto'))
        scale = tk.StringVar(window, self.preferences.get('scale', 'auto'))
        ttk.Label(window, text='布局：auto 自动 / wide 三栏 / compact 上下').pack(padx=12, pady=8)
        ttk.Combobox(window, textvariable=layout, values=('auto', 'wide', 'compact'), state='readonly').pack()
        ttk.Label(window, text='界面字号及控件倍率（不改变导出图片）').pack(padx=12, pady=8)
        ttk.Combobox(window, textvariable=scale, values=('auto', '.8', '1.0', '1.25', '1.5'), state='readonly').pack()
        def apply():
            self.preferences.update(layout=layout.get(), scale=scale.get())
            self._layout = None
            self._resize()
            self._save_preferences()
            window.destroy()
        ttk.Button(window, text='应用', command=apply).pack(pady=10)

    def configure_logs(self):
        self.diagnostics.configure(DiagnosticSettings(enabled=self.log_enabled.get(), level=self.log_level.get()))
        self._save_preferences()

    def show_logs(self):
        window = tk.Toplevel(self)
        window.title('本次运行日志')
        text = tk.Text(window, width=90, height=24)
        text.pack(fill='both', expand=True)
        text.insert('end', '\n'.join(json.dumps(row, ensure_ascii=False) for row in self.diagnostics.query(limit=300).entries))
        text.configure(state='disabled')

    def export_logs(self):
        directory = filedialog.askdirectory(title='诊断包保存目录')
        if directory:
            self.perform(lambda: self.diagnostics.export_bundle(None, directory), sync=False)

    def _save_preferences(self):
        self.preferences.update(output_dir=self.output_dir, output_base=self.output_base,
                                format=self.format_var.get(), log_enabled=self.log_enabled.get(), log_level=self.log_level.get())
        write_document(self.preferences_path, self.preferences)

    def _close(self):
        if self._confirm_discard():
            self.destroy()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        for name in ('_preview_after', '_draft_after', '_poll_after'):
            task = getattr(self, name, None)
            if task:
                self.after_cancel(task)
        self.preview_job.cancel()
        self.export_job.cancel()
        try:
            self._save_preferences()
        except OSError:
            pass
        self.diagnostics.close()
        super().destroy()


def main():
    import sys
    import tempfile
    import time
    smoke = os.environ.get('PTT_SMOKE') == '1'
    temporary = tempfile.TemporaryDirectory(prefix='ptt-desktop-smoke-') if smoke else None
    marker = Path(sys.executable).parent / 'smoke_progress.txt'
    def record(message):
        if smoke:
            with marker.open('a', encoding='utf-8') as stream:
                stream.write(message + '\n')
    record('start')
    app = App(user_dir=temporary.name if temporary else None, recover=not smoke)
    record('app_created')
    if smoke:
        app.withdraw()
        destination = os.environ.get('PTT_SMOKE_EXPORT_DIR')
        app.output_dir = destination or str(Path(temporary.name) / 'output')
        app.demo()
        steps = iter(('svg', 'png', 'pdf'))
        started = time.monotonic()
        phase = ['preview']
        def finish(error=None):
            record('smoke:failed:' + str(error) if error else 'smoke:passed')
            app.destroy()
        def check():
            try:
                if time.monotonic() - started > 120:
                    raise RuntimeError('桌面绘图验收超时：' + app.status.get())
                if app.status.get().startswith(('绘图失败', '导出未完成')):
                    raise RuntimeError(app.status.get())
                if phase[0] == 'preview':
                    ready = app.preview._source is not None and not app.preview._is_stale
                else:
                    ready = app.last_output and Path(app.last_output).is_file()
                if not ready:
                    app.after(100, check)
                    return
                if phase[0] == 'preview':
                    record('preview:passed')
                    from core.reference_image import load_reference_image
                    reference = Path(temporary.name) / 'reference.svg'
                    reference.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="red"/></svg>', encoding='utf-8')
                    image = load_reference_image(reference)
                    assert image.size == (40, 20)
                    image.close()
                    record('reference:passed')
                else:
                    record('export:' + phase[0])
                step = next(steps, None)
                if step is None:
                    finish()
                    return
                phase[0] = step
                app.last_output = None
                app.format_var.set(step)
                app.export()
                app.after(100, check)
            except Exception as exc:
                finish(exc)
        app.after(100, check)
    record('before_mainloop')
    app.mainloop()
    record('after_mainloop')
    if temporary:
        temporary.cleanup()
