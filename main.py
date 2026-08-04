# -*- coding: utf-8 -*-
"""元素周期表绘图工具 - 图形化入口（v1.1 迭代版）。

运行: python main.py

功能：
- 14 种绘图模式（13 种与原脚本输出一致 + 1 种自定义扩展）
- 实时预览画布：参数 / 数据 / 颜色 / 颜色条开关变化即时反映，所见即所得
- 两种数据输入方式（可切换）：
  1. 表格编辑（118 行，双击编辑）
  2. 图形化实时标注（开启"图形化标注模式"后在预览图中点击元素格赋值）
- 颜色条显示开关
- 自定义颜色（任意颜色序列，可视化编辑）
- 命名预设：保存 / 加载 / 删除整套设置与数据
- 输出自动改名，绝不覆盖已有文件
"""
from __future__ import annotations

import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 注意：不强制 matplotlib 后端。FigureCanvasTkAgg 在任意后端下均可工作
# （内部使用 agg 渲染），无头/测试环境（Agg）也能创建预览画布（需有显示）。

from core import (STYLES, parse_data, validate_data, demo_data,
                  known_symbols, render_table, render_cmap_preview,
                  save_figure, auto_name, PresetStore)
from core.ptable import build_elements, xy_bounds_for, CELL_STEP
from core.elements_data import ALL_SYMBOLS

SYMBOLS = set(ALL_SYMBOLS)
FORMATS = ["svg", "png", "pdf"]
DEFAULT_COLORS = [(0.1726, 0.2941, 0.4588), (1, 1, 1), (0.5686, 0.1333, 0.1098)]


def _rgb_to_hex(rgb) -> str:
    r, g, b = (int(round(c * 255)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _hex_to_rgb(hex_str) -> tuple:
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i + 2], 16) / 255 for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# 预览画布
# ---------------------------------------------------------------------------
class PreviewCanvas(tk.Frame):
    """嵌入的 matplotlib 预览画布，支持点击命中元素。"""

    def __init__(self, master, on_click=None, **kw):
        super().__init__(master, **kw)
        self.on_click = on_click
        self.fig = None
        self.canvas = None
        self.hit_map = {}
        self._placeholder = None
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            self._CanvasCls = FigureCanvasTkAgg
        except Exception:
            self._CanvasCls = None

    def show(self, fig, hit_map: dict):
        """显示新渲染的 figure，并更新点击命中表。"""
        if self.canvas is not None:
            try:
                self.canvas.get_tk_widget().destroy()
            except Exception:
                pass
            self.canvas = None
        self.fig = fig
        self.hit_map = hit_map or {}
        if self._CanvasCls is None:
            if self._placeholder is None:
                self._placeholder = tk.Label(
                    self, text="实时预览不可用（缺少 TkAgg 后端，不影响出图）",
                    fg="#888888")
                self._placeholder.pack(fill="both", expand=True)
            return
        if self._placeholder is not None:
            self._placeholder.destroy()
            self._placeholder = None
        self.canvas = self._CanvasCls(fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.canvas.draw()

    def _on_click(self, event):
        if event.inaxes is None:
            return
        sym = self.hit_test(event.xdata, event.ydata)
        if sym and self.on_click:
            self.on_click(sym)

    def hit_test(self, x, y):
        if x is None or y is None:
            return None
        for (x0, y0, x1, y1), sym in self.hit_map.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return sym
        return None


# ---------------------------------------------------------------------------
# 数据表格
# ---------------------------------------------------------------------------
class DataTable(tk.Frame):
    """元素数据表格：118 行，双击编辑值列。"""

    def __init__(self, master, on_change=None, **kw):
        super().__init__(master, **kw)
        self._edit_entry = None
        self._edit_item = None
        self.on_change = on_change

        self.tree = ttk.Treeview(self, columns=("num", "symbol", "value"),
                                 show="headings", height=16)
        self.tree.heading("num", text="原子序数")
        self.tree.heading("symbol", text="符号")
        self.tree.heading("value", text="数值 / 标注")
        self.tree.column("num", width=70, anchor="center", stretch=False)
        self.tree.column("symbol", width=60, anchor="center", stretch=False)
        self.tree.column("value", width=140, anchor="center")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._start_edit)
        self._fill_rows()

    def _fill_rows(self):
        self.tree.delete(*self.tree.get_children())
        for i in range(1, 119):
            self.tree.insert("", "end",
                             values=(i, ALL_SYMBOLS[i - 1], ""))

    def _start_edit(self, event):
        if self._edit_entry is not None:
            # 双击其他行时，先提交当前正在编辑的内容
            self._commit_edit(self._edit_item, self._edit_entry)
        col = self.tree.identify_column(event.x)
        if col != "#3":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        x, y, w, h = self.tree.bbox(item, "#3")
        entry = tk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, self.tree.set(item, "value"))
        entry.focus_set()
        entry.bind("<Return>", lambda e: self._commit_edit(item, entry))
        entry.bind("<Escape>", lambda e: self._cancel_edit(entry))
        entry.bind("<FocusOut>", lambda e: self._commit_edit(item, entry))
        self._edit_entry = entry
        self._edit_item = item

    def _cancel_edit(self, entry):
        """取消编辑：销毁输入框并重置状态，不写回任何值。"""
        entry.destroy()
        if self._edit_entry is entry:
            self._edit_entry = None
            self._edit_item = None

    def _commit_edit(self, item, entry):
        if self._edit_entry is not entry:
            # 输入框已被取消/销毁，忽略
            return
        value = entry.get().strip()
        entry.destroy()
        self._edit_entry = None
        self._edit_item = None
        self.tree.set(item, "value", value)
        if self.on_change:
            self.on_change()

    def set_data(self, data: dict):
        """用字典数据填充表格（不触发 on_change）。"""
        self._fill_rows()
        for child in self.tree.get_children():
            sym = self.tree.set(child, "symbol")
            if sym in data:
                self.tree.set(child, "value", str(data[sym]))

    def get_data(self) -> dict:
        """读取表格数据为 {符号: 值}。"""
        data = {}
        for child in self.tree.get_children():
            val = self.tree.set(child, "value").strip()
            if val:
                data[self.tree.set(child, "symbol")] = val
        return data

    def clear(self):
        self._fill_rows()
        if self.on_change:
            self.on_change()


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("元素周期表绘图工具 v1.1")
        self.geometry("1280x800")
        self.minsize(1080, 640)

        self.out_dir = os.path.join(PROJECT_ROOT, "output")
        self.last_output = None
        self.data = {}                       # 统一数据源 {符号: 值}
        self.custom_colors = list(DEFAULT_COLORS)
        self.presets = PresetStore(os.path.join(PROJECT_ROOT, "presets"))

        self._build_ui()
        self._on_style_change()

    # ------------------------------------------------------------------
    def _build_ui(self):
        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        # ================= 左侧控制面板 =================
        left = ttk.LabelFrame(main, text="绘图设置", padding=8)
        left.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 8))

        ttk.Label(left, text="绘图模式").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar()
        self.mode_combo = ttk.Combobox(left, textvariable=self.mode_var,
                                       state="readonly", width=30)
        self.mode_combo["values"] = [s["name"] for s in STYLES.values()]
        self.mode_combo.grid(row=0, column=1, columnspan=3, sticky="we", pady=(2, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_style_change())
        self.mode_combo.current(0)

        self.file_label = ttk.Label(left, text="", foreground="#666666", wraplength=280)
        self.file_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 6))

        # 参数
        params = [
            ("cmap", "颜色映射"),
            ("vmin", "最小值 vmin"),
            ("vcenter", "中心值 vcenter"),
            ("vmax", "最大值 vmax"),
            ("fmt", "数值格式"),
            ("title", "图标题"),
        ]
        self.param_vars = {}
        self.param_entries = {}
        for r, (key, label) in enumerate(params, start=2):
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w")
            var = tk.StringVar()
            entry = ttk.Entry(left, textvariable=var, width=24)
            entry.grid(row=r, column=1, columnspan=3, sticky="we", pady=2)
            entry.bind("<KeyRelease>", lambda e: self._refresh_preview())
            self.param_vars[key] = var
            self.param_entries[key] = entry

        # 颜色条开关
        r = 8
        self.show_cbar_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="显示颜色条", variable=self.show_cbar_var,
                        command=self._refresh_preview).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(8, 2))

        # ---- 自定义颜色 ----
        color_lf = ttk.LabelFrame(left, text="自定义颜色（仅自定义模式）", padding=4)
        color_lf.grid(row=r + 1, column=0, columnspan=4, sticky="we", pady=(4, 2))
        self.color_buttons = []
        self._build_color_row(color_lf)
        cbtns = ttk.Frame(color_lf)
        cbtns.pack(fill="x", pady=(4, 0))
        ttk.Button(cbtns, text="添加颜色", width=9,
                   command=self._add_color).pack(side="left", padx=(0, 4))
        ttk.Button(cbtns, text="移除最后", width=9,
                   command=self._remove_color).pack(side="left", padx=(0, 4))
        ttk.Button(cbtns, text="默认蓝白红", width=10,
                   command=self._reset_colors).pack(side="left")
        self.color_frame = color_lf

        # ---- 预设 ----
        preset_lf = ttk.LabelFrame(left, text="预设（保存整套设置）", padding=4)
        preset_lf.grid(row=r + 2, column=0, columnspan=4, sticky="we", pady=(6, 2))
        self.preset_name_var = tk.StringVar()
        ttk.Entry(preset_lf, textvariable=self.preset_name_var, width=22).pack(
            fill="x", pady=(0, 4))
        self.preset_combo = ttk.Combobox(preset_lf, state="readonly", width=22)
        self.preset_combo.pack(fill="x", pady=(0, 4))
        pbtns = ttk.Frame(preset_lf)
        pbtns.pack(fill="x")
        ttk.Button(pbtns, text="保存预设", width=8, command=self._preset_save).pack(
            side="left", padx=(0, 3))
        ttk.Button(pbtns, text="加载", width=6, command=self._preset_load).pack(
            side="left", padx=(0, 3))
        ttk.Button(pbtns, text="删除", width=6, command=self._preset_delete).pack(
            side="left", padx=(0, 3))
        ttk.Button(pbtns, text="刷新", width=6, command=self._preset_refresh).pack(
            side="left")

        # ---- 输出 ----
        out_row = r + 3
        ttk.Label(left, text="输出格式").grid(row=out_row, column=0, sticky="w", pady=(10, 0))
        self.fmt_var = tk.StringVar(value="svg")
        fmt_combo = ttk.Combobox(left, textvariable=self.fmt_var, state="readonly",
                                 values=FORMATS, width=6)
        fmt_combo.grid(row=out_row, column=1, sticky="w", pady=(10, 0))

        ttk.Label(left, text="输出目录").grid(row=out_row + 1, column=0, sticky="w", pady=(6, 0))
        self.out_var = tk.StringVar(value=self.out_dir)
        out_entry = ttk.Entry(left, textvariable=self.out_var, width=16)
        out_entry.grid(row=out_row + 1, column=1, columnspan=2, sticky="we", pady=(6, 0))
        ttk.Button(left, text="浏览", width=5,
                   command=self._choose_out_dir).grid(row=out_row + 1, column=3, pady=(6, 0))

        ttk.Button(left, text="生成图片", command=self.generate).grid(
            row=out_row + 2, column=0, columnspan=4, sticky="we", pady=(12, 4))
        ttk.Button(left, text="打开输出目录", command=self._open_out_dir).grid(
            row=out_row + 3, column=0, columnspan=4, sticky="we", pady=4)

        self.hint_label = ttk.Label(left, text="", foreground="#888888",
                                    wraplength=280, justify="left")
        self.hint_label.grid(row=out_row + 4, column=0, columnspan=4, sticky="w", pady=(10, 0))

        # ================= 右侧：预览 + 数据 =================
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        # 预览区
        prev_lf = ttk.LabelFrame(right, text="实时预览（输出图片的预览）", padding=4)
        prev_lf.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        prev_lf.rowconfigure(0, weight=1)
        prev_lf.columnconfigure(0, weight=1)
        self.preview = PreviewCanvas(prev_lf, on_click=self._on_preview_click)
        self.preview.grid(row=0, column=0, sticky="nsew")

        ptool = ttk.Frame(prev_lf)
        ptool.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.mark_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ptool, text="图形化标注模式（点击预览中的元素格进行标注）",
                        variable=self.mark_mode_var).pack(side="left")
        ttk.Label(ptool, text="  切换按钮：开启后点击预览图即可标注数据，与表格输入实时同步",
                  foreground="#666666").pack(side="left")

        # 数据区（两种输入方式切换）
        data_nb = ttk.Notebook(right)
        data_nb.grid(row=1, column=0, sticky="nsew")
        data_nb.rowconfigure(0, weight=1)
        data_nb.columnconfigure(0, weight=1)

        # Tab1：表格
        tab_table = ttk.Frame(data_nb, padding=6)
        data_nb.add(tab_table, text="① 表格编辑")
        tab_table.rowconfigure(0, weight=1)
        tab_table.columnconfigure(0, weight=1)
        self.table = DataTable(tab_table, on_change=self._table_changed)
        self.table.grid(row=0, column=0, sticky="nsew")
        tbtns = ttk.Frame(tab_table)
        tbtns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(tbtns, text="载入示例数据", command=self._load_demo).pack(side="left", padx=(0, 6))
        ttk.Button(tbtns, text="导入数据文件", command=self._import_file).pack(side="left", padx=(0, 6))
        ttk.Button(tbtns, text="清空数据", command=self._clear_data).pack(side="left")

        # Tab2：图形化标注
        tab_mark = ttk.Frame(data_nb, padding=8)
        data_nb.add(tab_mark, text="② 图形化标注")
        tab_mark.columnconfigure(1, weight=1)
        ttk.Label(tab_mark, text="使用方法：\n1. 勾选上方「图形化标注模式」；\n"
                                 "2. 在预览图中点击某个元素格子；\n"
                                 "3. 在下方输入数值（热力图模式）或文本标注（标注模式），点「应用」。\n"
                                 "4. 再次点击同一元素可修改；输入框留空点「应用」则清除该元素。",
                  justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.mark_symbol_var = tk.StringVar(value="（点击预览中的元素格）")
        ttk.Label(tab_mark, text="当前元素：", font=("", 10, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(tab_mark, textvariable=self.mark_symbol_var, foreground="#0b6bcb",
                  font=("", 11, "bold")).grid(row=1, column=1, sticky="w")
        ttk.Label(tab_mark, text="数值 / 标注：").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.mark_value_var = tk.StringVar()
        mark_entry = ttk.Entry(tab_mark, textvariable=self.mark_value_var, width=24)
        mark_entry.grid(row=2, column=1, sticky="we", pady=(8, 0))
        mark_entry.bind("<Return>", lambda e: self._apply_mark())
        mbtns = ttk.Frame(tab_mark)
        mbtns.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Button(mbtns, text="应用标注", command=self._apply_mark).pack(side="left", padx=(0, 6))
        ttk.Button(mbtns, text="清除该元素", command=self._clear_mark).pack(side="left")

        # ================= 状态栏 =================
        status = ttk.Frame(main)
        status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var, foreground="#333333").pack(side="left")

    # ------------------------------------------------------------------
    def _build_color_row(self, parent):
        """重建自定义颜色色块按钮行。"""
        for b in self.color_buttons:
            b.destroy()
        self.color_buttons = []
        row = ttk.Frame(parent)
        row.pack(fill="x")
        for i, rgb in enumerate(self.custom_colors):
            btn = tk.Button(row, width=4, bg=_rgb_to_hex(rgb),
                            command=lambda idx=i: self._edit_color(idx))
            btn.pack(side="left", padx=1)
            self.color_buttons.append(btn)

    # ------------------------------------------------------------------
    def _current_style_id(self) -> str:
        return list(STYLES.keys())[self.mode_combo.current()]

    def _current_work_style(self):
        """当前生效的样式：自定义模式应用面板参数与自定义颜色。"""
        style = STYLES[self._current_style_id()]
        if style.get("customizable"):
            return self._apply_custom_params(style)
        return style

    def _on_style_change(self):
        style_id = self._current_style_id()
        style = STYLES[style_id]
        self.file_label.config(text=f"对应原脚本：{style['file']}")

        norm = style.get("norm")
        self.param_vars["cmap"].set(_cmap_name(style))
        self.param_vars["vmin"].set(str(norm[1]) if norm else "")
        self.param_vars["vcenter"].set(str(norm[2]) if norm and norm[0] == "twoslope" else "")
        self.param_vars["vmax"].set(str(norm[-1]) if norm else "")
        self.param_vars["fmt"].set(style.get("fmt", ""))
        self.param_vars["title"].set("")

        editable = style.get("customizable", False)
        for key in ("cmap", "vmin", "vcenter", "vmax", "fmt"):
            self.param_entries[key].config(state="normal" if editable else "readonly")
        # 自定义颜色仅自定义模式可用
        for b in self.color_buttons:
            b.config(state="normal" if editable else "disabled")

        if style_id == "cmap_preview":
            self.hint_label.config(text="本模式生成所有 matplotlib 颜色映射的预览图，无需数据。")
        elif style.get("kind") == "labels":
            self.hint_label.config(text="标注模式：数值/标注列填文本（如 3c1、1b）。")
        else:
            self.hint_label.config(text="热力图模式：数值列填数字，缺失元素显示为空/灰格。")

        self._preset_refresh()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    def _table_changed(self):
        """表格编辑后：同步统一数据源并刷新预览。"""
        self.data = self.table.get_data()
        self._refresh_preview()

    def _clear_data(self):
        self.data = {}
        self.table.clear()
        self._refresh_preview()

    def _load_demo(self):
        style_id = self._current_style_id()
        data = demo_data(style_id)
        if not data:
            messagebox.showinfo("提示", "该模式没有内置示例数据，请手动输入或导入文件。")
            return
        self.data = data
        self.table.set_data(data)
        self.status_var.set(f"已载入示例数据（{len(data)} 个元素）")
        self._refresh_preview()

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="选择数据文件",
            filetypes=[("数据文件", "*.txt *.csv *.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            data = parse_data(text)
            if not data:
                raise ValueError("文件中没有可解析的数据")
            self.data = data
            self.table.set_data(data)
            self.status_var.set(f"已从 {os.path.basename(path)} 导入 {len(data)} 条数据")
            self._refresh_preview()
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    # ------------------------------------------------------------------
    # 图形化标注
    # ------------------------------------------------------------------
    def _on_preview_click(self, sym):
        if not self.mark_mode_var.get():
            self.status_var.set("提示：请先勾选「图形化标注模式」再点击预览标注。")
            return
        self.mark_symbol_var.set(sym)
        self.mark_value_var.set(str(self.data.get(sym, "")))
        self.status_var.set(f"已选中元素 {sym}，输入数值后点「应用标注」")
        # 跳到标注 Tab
        self._mark_tab_select()

    def _mark_tab_select(self):
        for child in self.winfo_children():
            pass  # 简化：不强制切换 Tab，提示已足够

    def _apply_mark(self):
        sym = self.mark_symbol_var.get()
        if not sym or not all(c.isalnum() for c in sym) or sym not in SYMBOLS:
            messagebox.showwarning("提示", "请先在预览图中点击一个元素格子。")
            return
        val = self.mark_value_var.get().strip()
        if val:
            self.data[sym] = val
        else:
            self.data.pop(sym, None)
        self.table.set_data(self.data)
        self.status_var.set(f"已标注 {sym} = {val if val else '(清除)'}")
        self._refresh_preview()

    def _clear_mark(self):
        sym = self.mark_symbol_var.get()
        if sym in SYMBOLS:
            self.data.pop(sym, None)
            self.table.set_data(self.data)
            self.status_var.set(f"已清除 {sym}")
            self._refresh_preview()

    # ------------------------------------------------------------------
    # 自定义颜色
    # ------------------------------------------------------------------
    def _edit_color(self, idx):
        _, rgb = colorchooser.askcolor(color=_rgb_to_hex(self.custom_colors[idx]),
                                       title=f"选择第 {idx + 1} 个颜色")
        if rgb:
            self.custom_colors[idx] = tuple(c / 255 for c in rgb)
            self._build_color_row(self.color_frame)
            self._refresh_preview()

    def _add_color(self):
        _, rgb = colorchooser.askcolor(color="#888888", title="添加一个颜色")
        if rgb:
            self.custom_colors.append(tuple(c / 255 for c in rgb))
            self._build_color_row(self.color_frame)
            self._refresh_preview()

    def _remove_color(self):
        if len(self.custom_colors) > 2:
            self.custom_colors.pop()
            self._build_color_row(self.color_frame)
            self._refresh_preview()
        else:
            messagebox.showinfo("提示", "至少保留 2 个颜色。")

    def _reset_colors(self):
        self.custom_colors = list(DEFAULT_COLORS)
        self._build_color_row(self.color_frame)
        self._refresh_preview()

    # ------------------------------------------------------------------
    # 预设
    # ------------------------------------------------------------------
    def _preset_refresh(self):
        self.preset_combo["values"] = self.presets.list()

    def _current_preset_payload(self) -> dict:
        return {
            "mode_id": self._current_style_id(),
            "params": {k: self.param_vars[k].get() for k in
                       ("cmap", "vmin", "vcenter", "vmax", "fmt", "title")},
            "show_cbar": self.show_cbar_var.get(),
            "custom_colors": self.custom_colors,
            "data": self.data,
        }

    def _preset_save(self):
        name = self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先输入预设名。")
            return
        try:
            path = self.presets.save(name, self._current_preset_payload())
        except ValueError as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.status_var.set(f"已保存预设 {name} → {path}")
        self._preset_refresh()

    def _preset_load(self):
        name = self.preset_combo.get() or self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请选择或输入要加载的预设名。")
            return
        try:
            payload = self.presets.load(name)
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))
            return
        # 应用预设
        mode_id = payload.get("mode_id", "custom")
        names = [s["name"] for s in STYLES.values()]
        ids = list(STYLES.keys())
        if mode_id in ids:
            self.mode_combo.current(ids.index(mode_id))
            self._on_style_change()
        for k, v in payload.get("params", {}).items():
            if k in self.param_vars:
                self.param_vars[k].set(str(v))
        self.show_cbar_var.set(bool(payload.get("show_cbar", True)))
        self.custom_colors = list(payload.get("custom_colors", DEFAULT_COLORS))
        self._build_color_row(self.color_frame)
        self.data = dict(payload.get("data", {}))
        self.table.set_data(self.data)
        self.status_var.set(f"已加载预设 {name}")
        self._refresh_preview()

    def _preset_delete(self):
        name = self.preset_combo.get() or self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请选择要删除的预设名。")
            return
        if messagebox.askyesno("删除预设", f"确定删除预设「{name}」吗？"):
            self.presets.delete(name)
            self.status_var.set(f"已删除预设 {name}")
            self._preset_refresh()

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    def _build_hit_map(self) -> dict:
        """构建元素格子坐标 → 符号 的命中表（与渲染布局一致）。"""
        style = STYLES[self._current_style_id()]
        layout = style["layout"]
        elements = build_elements(layout, {})
        bounds = xy_bounds_for(layout)
        hit = {}
        for num, symbol, group, period, _ in elements:
            if group is None or num is None:
                continue
            x = CELL_STEP * (group - 1)
            y = bounds[1] - CELL_STEP * period
            if period >= 8:
                y -= 0.5
            hit[(x, y, x + 1, y + 1)] = symbol
        return hit

    def _refresh_preview(self):
        style_id = self._current_style_id()
        if style_id == "cmap_preview":
            # 本模式无周期表预览，仅提示
            return
        try:
            style = self._current_work_style()
            title = (self.param_vars["title"].get().strip()
                     if style.get("customizable") else "")
            fig = render_table(style, self.data, title=title or None,
                               show_cbar=self.show_cbar_var.get())
            self.preview.show(fig, self._build_hit_map())
        except Exception as exc:
            self.status_var.set(f"预览失败：{exc}")

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def generate(self):
        style_id = self._current_style_id()
        style = STYLES[style_id]
        out_dir = self.out_var.get().strip() or self.out_dir

        try:
            if style_id == "cmap_preview":
                self._generate_cmap_preview(out_dir)
                return

            if not self.data:
                messagebox.showwarning("提示", "请先输入数据：表格编辑、图形化标注、导入文件或载入示例。")
                return

            if style.get("kind") == "labels":
                data = {s: v for s, v in self.data.items() if s in known_symbols()}
                unknown = [s for s in self.data if s not in known_symbols()]
                if unknown:
                    messagebox.showwarning("未知元素", f"以下符号不在周期表中，将被忽略：{', '.join(unknown)}")
            else:
                data, unknown, bad = validate_data(self.data)
                if unknown:
                    messagebox.showwarning("未知元素", f"以下符号不在周期表中，将被忽略：{', '.join(unknown)}")
                bad = bad + [(s, v) for s, v in data.items() if isinstance(v, str)]
                data = {s: v for s, v in data.items() if not isinstance(v, str)}
                if bad:
                    messagebox.showwarning("非法值", f"以下数据不是有效数字，将被忽略：{bad}")

            work_style = self._current_work_style()
            fmt = self.fmt_var.get()
            title = (self.param_vars["title"].get().strip()
                     if style.get("customizable") else "")
            fig = render_table(work_style, data, title=title or None,
                               show_cbar=self.show_cbar_var.get())
            path = save_figure(fig, out_dir, "periodic_table", fmt,
                               bbox_inches="tight" if work_style.get("bbox_tight", True) else None)
            import matplotlib.pyplot as plt
            plt.close(fig)

            self.last_output = path
            self.status_var.set(f"已生成：{path}")
            if messagebox.askyesno("完成", f"图片已保存到：\n{path}\n\n是否打开查看？"):
                webbrowser.open(path)
        except Exception as exc:
            messagebox.showerror("生成失败", str(exc))

    def _generate_cmap_preview(self, out_dir):
        paths = render_cmap_preview(out_dir)
        self.last_output = out_dir
        self.status_var.set(f"已生成 {len(paths)} 张颜色映射预览图 → {out_dir}")
        messagebox.showinfo("完成", f"已生成 {len(paths)} 张预览图：\n{out_dir}")

    def _apply_custom_params(self, style):
        import copy
        work = copy.deepcopy(style)
        cmap_name = self.param_vars["cmap"].get().strip()
        try:
            vmin = float(self.param_vars["vmin"].get())
            vmax = float(self.param_vars["vmax"].get())
        except ValueError as exc:
            raise ValueError("vmin / vmax 必须是数字") from exc
        center_text = self.param_vars["vcenter"].get().strip()
        work["norm"] = ("twoslope", vmin, float(center_text), vmax) if center_text else ("normalize", vmin, vmax)
        work["fmt"] = self.param_vars["fmt"].get().strip() or "3f"
        # 自定义颜色优先；否则按输入的名称取预置色图
        if cmap_name.strip().startswith("自定义"):
            work["cmap"] = ("custom", [tuple(c) for c in self.custom_colors])
        elif cmap_name.strip():
            work["cmap"] = cmap_name.strip()
        else:
            work["cmap"] = ("custom", [tuple(c) for c in self.custom_colors])
        return work

    # ------------------------------------------------------------------
    def _choose_out_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_var.set(path)

    def _open_out_dir(self):
        path = self.out_var.get().strip() or self.out_dir
        try:
            os.makedirs(path, exist_ok=True)
            webbrowser.open(path)
        except OSError as exc:
            messagebox.showerror("打开失败", f"无法打开输出目录：{exc}")


def _cmap_name(style):
    spec = style.get("cmap")
    if isinstance(spec, tuple) and spec[0] == "custom":
        return "自定义(蓝-白-红)"
    return spec or ""


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
