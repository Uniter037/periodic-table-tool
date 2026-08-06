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

import json
import math
import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import tkinter.font as tkfont

# 打包为 exe 时（PyInstaller --onefile），__file__ 位于临时解压目录，
# 输出/预设必须落在可写的 exe 同目录；源码运行用项目目录。
if getattr(sys, "frozen", False):
    PROJECT_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# exe 冒烟标记（模块级，定位 windowed 版 import 卡点）
def _smoke_log(msg):
    if os.environ.get("PTT_SMOKE") == "1":
        try:
            marker = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                                  "smoke_progress.txt")
            with open(marker, "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except OSError:
            pass


_smoke_log("import:before_matplotlib")
# exe 内显式使用 TkAgg 后端（保证预览画布与 PyInstaller hook 收集）；
# 源码/测试环境保持默认（不污染测试进程）。
if getattr(sys, "frozen", False):
    import matplotlib
    matplotlib.use("TkAgg")
_smoke_log("import:after_matplotlib")

from core import (STYLES, parse_data, validate_data, demo_data,
                  known_symbols, render_table, render_cmap_preview,
                  save_figure, auto_name, PresetStore)
from core.ptable import build_elements, xy_bounds_for, CELL_STEP
from core.elements_data import ALL_SYMBOLS
_smoke_log("import:after_core")

SYMBOLS = set(ALL_SYMBOLS)
FORMATS = ["svg", "png", "pdf"]
DEFAULT_COLORS = [(0.1726, 0.2941, 0.4588), (1, 1, 1), (0.5686, 0.1333, 0.1098)]
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".periodic-table-tool.json")
# 自动布局：窗口宽度低于该值时切换为上下分栏
AUTO_SPLIT_THRESHOLD = 1150
LAYOUT_MODES = (
    ("auto", "自动调整（随窗口宽度）"),
    ("split-h", "左右分栏"),
    ("split-v", "上下分栏"),
)
# 界面缩放选项：auto 随窗口宽度，或手动固定比例
SCALE_OPTIONS = (
    ("auto", "自动（随窗口）"),
    ("0.8", "80%"),
    ("1.0", "100%"),
    ("1.25", "125%"),
    ("1.5", "150%"),
)
# 预览区域占右侧上部的高度比例（可手动调节）
PREVIEW_RATIO_OPTIONS = (0.4, 0.5, 0.6)
BASE_FONT_SIZE = 10          # 100% 缩放时的基准字号
BASE_WINDOW_WIDTH = 1280     # auto 缩放的基准窗口宽度
SCALE_RANGE = (0.8, 1.5)     # auto 缩放的上下限

# 自定义模式高级参数：GUI 中文标签 → 样式值（反向映射用于回填）
LAYOUT_CHOICES = {"镧锕三行块（重构）": "reconstructed",
                  "展开 8-9 行（经典）": "classic"}
KIND_CHOICES = {"热力图": "heatmap", "标注图（文本）": "labels"}
FONT_CHOICES = {"Arial": "Arial", "Helvetica": "Helvetica",
                "DejaVu Sans": "DejaVu Sans"}
EDGE_CHOICES = {"无边框": "none", "黑色细线": "black"}
EMPTY_CHOICES = {"浅灰": "#f0f0f0", "白色": "white", "白色(w)": "w", "透明": "none"}
FMT_CHOICES = {"百分比 2 位": "percent2", "两位小数": "2f", "三位小数": "3f",
               "四位小数": "4f", "原始": "raw"}
DPI_CHOICES = {"72": 72, "100": 100, "150": 150, "300": 300}
_REV = {name: {v: k for k, v in m.items()} for name, m in
        (("layout", LAYOUT_CHOICES), ("kind", KIND_CHOICES),
         ("font", FONT_CHOICES), ("edge", EDGE_CHOICES),
         ("empty", EMPTY_CHOICES), ("fmt", FMT_CHOICES), ("dpi", DPI_CHOICES))}


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
        # 关闭旧 figure，避免 matplotlib 状态机持有导致内存累积
        old_fig = self.fig
        self.fig = fig
        if old_fig is not None and old_fig is not fig:
            import matplotlib.pyplot as plt
            plt.close(old_fig)
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
        if event.inaxes is None or event.button != 1:
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
        self.title("元素周期表绘图工具 v1.2")
        self.geometry("1280x920")
        self.minsize(1080, 720)

        self.out_dir = os.path.join(PROJECT_ROOT, "output")
        self.last_output = None
        self.data = {}                       # 统一数据源 {符号: 值}
        self.custom_colors = list(DEFAULT_COLORS)
        self.presets = PresetStore(os.path.join(PROJECT_ROOT, "presets"))
        self._main = None
        self._left = None
        self._right = None
        self._current_layout = None          # 当前实际生效的布局
        self.layout_mode = "auto"            # 用户选择：auto / split-h / split-v
        self.scale_mode = "auto"             # 界面缩放：auto 或 "0.8"/"1.0"/"1.25"/"1.5"
        self.preview_ratio = 0.5             # 预览区域高度占比（右侧上部）
        self._current_scale = None           # 已应用的缩放值（防抖）
        self._last_preview_size = (0, 0)     # 预览画布上次尺寸（防抖）
        self._app_font = None
        self.cbar_override = None            # 颜色条标注自定义（None=用样式默认）
        self._load_config()
        if isinstance(self._config.get("geometry"), str):
            try:
                self.geometry(self._config["geometry"])
            except tk.TclError:
                pass

        self._build_ui()
        self._on_style_change()
        # 随窗口大小自动调整布局
        self.bind("<Configure>", self._on_window_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    def _load_config(self):
        """读取用户配置（布局模式、窗口尺寸、界面缩放、预览比例）。"""
        cfg = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception:
            cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        self._config = cfg
        mode = cfg.get("layout", "auto")
        self.layout_mode = (mode if isinstance(mode, str)
                            and mode in dict(LAYOUT_MODES) else "auto")
        scale = cfg.get("scale", "auto")
        self.scale_mode = (scale if isinstance(scale, str)
                           and scale in dict(SCALE_OPTIONS) else "auto")
        try:
            ratio = float(cfg.get("preview_ratio", 0.5))
            self.preview_ratio = ratio if ratio in PREVIEW_RATIO_OPTIONS else 0.5
        except (TypeError, ValueError):
            self.preview_ratio = 0.5

    def _save_config(self):
        """保存用户配置（布局模式、窗口尺寸、界面缩放、预览比例）。"""
        cfg = {
            "layout": self.layout_mode,
            "geometry": self.geometry(),
            "scale": self.scale_mode,
            "preview_ratio": self.preview_ratio,
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _on_close(self):
        self._save_config()
        self.destroy()

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def _effective_layout(self) -> str:
        """auto 模式下按当前窗口宽度决定实际布局。"""
        if self.layout_mode == "auto":
            try:
                width = self.winfo_width()
            except tk.TclError:
                width = 0
            if width <= 1:
                # 窗口尚未映射：用默认宽布局，避免启动闪变
                return "split-h"
            return "split-v" if width < AUTO_SPLIT_THRESHOLD else "split-h"
        return self.layout_mode

    def _apply_layout(self):
        """根据布局模式重新摆放控制面板与主区（左右/上下）。"""
        if self._main is None:
            return
        layout = self._effective_layout()
        if layout == self._current_layout:
            return
        self._current_layout = layout
        main = self._main
        if layout == "split-h":
            main.columnconfigure(0, weight=0)
            main.columnconfigure(1, weight=1)
            main.rowconfigure(0, weight=0)
            main.rowconfigure(1, weight=1)
            self._left.grid(row=0, column=0, rowspan=2,
                            sticky="ns", padx=(0, 8), pady=0)
            self._right.grid(row=0, column=1, rowspan=1,
                             sticky="nsew", padx=0, pady=0)
        else:   # split-v：上下分栏（注意 rowspan 必须显式重置，grid 配置是增量更新的）
            main.columnconfigure(0, weight=1)
            main.columnconfigure(1, weight=0)
            main.rowconfigure(0, weight=0)
            main.rowconfigure(1, weight=1)
            self._left.grid(row=0, column=0, rowspan=1,
                            sticky="ew", padx=0, pady=(0, 6))
            self._right.grid(row=1, column=0, rowspan=1,
                             sticky="nsew", padx=0, pady=0)
        # 状态栏始终占满底部
        for child in main.winfo_children():
            if child is self._status:
                child.grid(row=2, column=0, columnspan=2, sticky="ew",
                           pady=(6, 0))

    def _on_window_resize(self, event):
        if event.widget is not self:
            return
        self._apply_layout()
        self._apply_scale()
        self._resize_preview()

    # ------------------------------------------------------------------
    # 界面缩放与预览自适应
    # ------------------------------------------------------------------
    def _effective_scale(self) -> float:
        """当前缩放值：auto 模式随窗口宽度 clamp 到 SCALE_RANGE，手动用固定值。"""
        if self.scale_mode == "auto":
            try:
                width = self.winfo_width()
            except tk.TclError:
                width = BASE_WINDOW_WIDTH
            if width <= 1:
                return 1.0
            return max(SCALE_RANGE[0],
                       min(SCALE_RANGE[1], width / BASE_WINDOW_WIDTH))
        return float(self.scale_mode)

    def _apply_scale(self):
        """将缩放值应用到界面字号与控件大小（字号未变则跳过，防抖）。"""
        scale = self._effective_scale()
        font_size = round(BASE_FONT_SIZE * scale)
        if self._current_scale == font_size:
            return
        self._current_scale = font_size
        if self._app_font is None:
            family = tkfont.nametofont("TkDefaultFont").cget("family")
            self._app_font = tkfont.Font(family=family, size=font_size)
        else:
            self._app_font.configure(size=font_size)
        style = ttk.Style(self)
        for s in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton",
                  "TCombobox", "TEntry", "TNotebook", "TNotebook.Tab",
                  "TLabelframe", "TLabelframe.Label"):
            try:
                style.configure(s, font=self._app_font)
            except tk.TclError:
                pass
        try:
            style.configure("Treeview", font=self._app_font,
                            rowheight=max(20, round(24 * scale)))
            style.configure("Treeview.Heading", font=self._app_font)
        except tk.TclError:
            pass
        self._resize_preview()

    def _apply_preview_ratio(self):
        """按预览区域比例调整右侧上（预览）/下（数据）区域的权重。"""
        if self._right is None:
            return
        self._right.rowconfigure(0, weight=int(self.preview_ratio * 10))
        self._right.rowconfigure(1, weight=int((1 - self.preview_ratio) * 10))

    def _resize_preview(self):
        """预览画布随窗口尺寸自适应（figure 重设尺寸，防抖）。"""
        pv = self.preview
        if pv.canvas is None or pv.fig is None:
            return
        try:
            w = pv.winfo_width()
            h = pv.winfo_height()
        except tk.TclError:
            return
        if w <= 10 or h <= 10 or (w, h) == self._last_preview_size:
            return
        self._last_preview_size = (w, h)
        try:
            dpi = self.winfo_fpixels("1i")
            pv.fig.set_size_inches(max(w / dpi, 4.0), max(h / dpi, 2.0))
            pv.fig.tight_layout()
            pv.canvas.draw()
        except Exception:
            pass

    def _on_scale_change(self, *args):
        self.scale_mode = self.scale_var.get()
        self._current_scale = None          # 强制重新应用
        self._apply_scale()
        self._save_config()

    def _on_ratio_change(self, *args):
        self.preview_ratio = float(self.ratio_var.get())
        self._apply_preview_ratio()
        self._save_config()
        self._resize_preview()

    def _on_layout_mode_change(self, *args):
        self.layout_mode = self.layout_var.get()
        self._apply_layout()
        self._save_config()
        self.status_var.set(f"布局：{dict(LAYOUT_MODES)[self.layout_mode]}")

    # ------------------------------------------------------------------
    def _build_ui(self):
        # 视图菜单（布局设置、界面缩放、预览比例）
        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        self.layout_var = tk.StringVar(value=self.layout_mode)
        for mode, label in LAYOUT_MODES:
            view_menu.add_radiobutton(
                label=label, variable=self.layout_var, value=mode,
                command=self._on_layout_mode_change)
        view_menu.add_separator()
        # 界面缩放
        self.scale_var = tk.StringVar(value=self.scale_mode)
        scale_menu = tk.Menu(view_menu, tearoff=0)
        for val, label in SCALE_OPTIONS:
            scale_menu.add_radiobutton(
                label=label, variable=self.scale_var, value=val,
                command=self._on_scale_change)
        view_menu.add_cascade(label="界面缩放（字号/控件）", menu=scale_menu)
        # 预览区域比例
        self.ratio_var = tk.DoubleVar(value=self.preview_ratio)
        ratio_menu = tk.Menu(view_menu, tearoff=0)
        for r in PREVIEW_RATIO_OPTIONS:
            ratio_menu.add_radiobutton(
                label=f"预览区 {int(r * 100)}% / 数据区 {int((1 - r) * 100)}%",
                variable=self.ratio_var, value=r,
                command=self._on_ratio_change)
        view_menu.add_cascade(label="预览区域大小", menu=ratio_menu)
        menubar.add_cascade(label="视图", menu=view_menu)
        self.config(menu=menubar)

        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
        self._main = main

        # ================= 左侧控制面板 =================
        left = ttk.LabelFrame(main, text="绘图设置", padding=8)
        self._left = left

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

        # 参数（自定义模式全部可调；其他模式只读显示）
        params = [
            ("cmap", "颜色映射", "entry"),
            ("vmin", "最小值 vmin", "entry"),
            ("vcenter", "中心值 vcenter", "entry"),
            ("vmax", "最大值 vmax", "entry"),
            ("fmt", "数值格式", "combo", list(FMT_CHOICES)),
            ("layout", "元素布局", "combo", list(LAYOUT_CHOICES)),
            ("kind", "图表类型", "combo", list(KIND_CHOICES)),
            ("font", "字体", "combo", list(FONT_CHOICES)),
            ("edge", "格子边框", "combo", list(EDGE_CHOICES)),
            ("empty", "空值格颜色", "combo", list(EMPTY_CHOICES)),
            ("dpi", "输出分辨率 dpi", "combo", list(DPI_CHOICES)),
            ("figsize", "图尺寸(宽x高 英寸)", "entry"),
            ("title", "图标题", "entry"),
        ]
        self.param_vars = {}
        self.param_entries = {}
        for r, spec in enumerate(params, start=2):
            key, label = spec[0], spec[1]
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w")
            var = tk.StringVar()
            if spec[2] == "combo":
                widget = ttk.Combobox(left, textvariable=var, state="readonly",
                                      values=spec[3], width=20)
                widget.bind("<<ComboboxSelected>>",
                            lambda e: self._refresh_preview())
            else:
                widget = ttk.Entry(left, textvariable=var, width=24)
                widget.bind("<KeyRelease>", lambda e: self._refresh_preview())
            widget.grid(row=r, column=1, columnspan=3, sticky="we", pady=1)
            self.param_vars[key] = var
            self.param_entries[key] = widget

        # 颜色条开关
        r = 15
        self.show_cbar_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(left, text="显示颜色条", variable=self.show_cbar_var,
                        command=self._refresh_preview).grid(
            row=r, column=0, columnspan=4, sticky="w", pady=(8, 2))

        # ---- 颜色条标注（刻度自定义）----
        cbar_lf = ttk.LabelFrame(
            left, text="颜色条标注（刻度与标签可增删改）", padding=4)
        cbar_lf.grid(row=r + 1, column=0, columnspan=4, sticky="we", pady=(4, 2))
        self.cbar_tree = ttk.Treeview(cbar_lf, columns=("v", "l"),
                                      show="headings", height=3)
        self.cbar_tree.heading("v", text="刻度值")
        self.cbar_tree.heading("l", text="标签")
        self.cbar_tree.column("v", width=80, anchor="center")
        self.cbar_tree.column("l", width=130, anchor="center")
        self.cbar_tree.pack(fill="x")
        cbar_edit = ttk.Frame(cbar_lf)
        cbar_edit.pack(fill="x", pady=(4, 0))
        self.cbar_value_var = tk.StringVar()
        self.cbar_label_var = tk.StringVar()
        ttk.Entry(cbar_edit, textvariable=self.cbar_value_var, width=9).pack(
            side="left", padx=(0, 3))
        ttk.Entry(cbar_edit, textvariable=self.cbar_label_var, width=16).pack(
            side="left")
        cbar_btns = ttk.Frame(cbar_lf)
        cbar_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(cbar_btns, text="添加", width=5,
                   command=self._cbar_add).pack(side="left", padx=(0, 3))
        ttk.Button(cbar_btns, text="更新选中", width=7,
                   command=self._cbar_update).pack(side="left", padx=(0, 3))
        ttk.Button(cbar_btns, text="删除选中", width=7,
                   command=self._cbar_delete).pack(side="left", padx=(0, 3))
        ttk.Button(cbar_btns, text="恢复默认", width=8,
                   command=self._cbar_reset).pack(side="left")
        self.cbar_controls = (cbar_lf,)

        # ---- 自定义颜色 ----
        color_lf = ttk.LabelFrame(left, text="自定义颜色（仅自定义模式）", padding=4)
        color_lf.grid(row=r + 2, column=0, columnspan=4, sticky="we", pady=(4, 2))
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
        preset_lf.grid(row=r + 3, column=0, columnspan=4, sticky="we", pady=(6, 2))
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
        out_row = r + 4
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
        self._right = right
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
        self._status = status
        status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var, foreground="#333333").pack(side="left")

        # 应用初始布局（读自用户配置）
        self._apply_layout()
        self._apply_preview_ratio()
        self._apply_scale()

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
        """当前生效的样式：自定义模式应用面板参数；任意模式注入颜色条标注覆盖。"""
        style = STYLES[self._current_style_id()]
        work = (self._apply_custom_params(style)
                if style.get("customizable") else style)
        if self.cbar_override is not None:
            # 非自定义模式返回的是 STYLES 原对象，浅拷贝避免污染全局
            if not style.get("customizable"):
                work = dict(work)
            work["cbar"] = self.cbar_override
        return work

    def _on_style_change(self):
        style_id = self._current_style_id()
        style = STYLES[style_id]
        self.file_label.config(text=f"对应原脚本：{style['file']}")

        norm = style.get("norm")
        self.param_vars["cmap"].set(_cmap_name(style))
        self.param_vars["vmin"].set(str(norm[1]) if norm else "")
        self.param_vars["vcenter"].set(str(norm[2]) if norm and norm[0] == "twoslope" else "")
        self.param_vars["vmax"].set(str(norm[-1]) if norm else "")
        # 组合类参数：样式值 → 中文标签回填（不在映射中则显示原始值/默认）
        self.param_vars["fmt"].set(_REV["fmt"].get(style.get("fmt", ""),
                                                   style.get("fmt", "")))
        self.param_vars["layout"].set(_REV["layout"].get(style.get("layout", "classic")))
        self.param_vars["kind"].set(_REV["kind"].get(style.get("kind", "heatmap")))
        self.param_vars["font"].set(_REV["font"].get(style.get("font", "Arial"),
                                                     style.get("font", "Arial")))
        edge = style.get("edge")
        self.param_vars["edge"].set(_REV["edge"].get(
            "none" if edge is None else "black"))
        self.param_vars["empty"].set(_REV["empty"].get(style.get("empty", "#f0f0f0"),
                                                       style.get("empty", "#f0f0f0")))
        self.param_vars["dpi"].set("100")
        self.param_vars["figsize"].set("10x5")
        self.param_vars["title"].set("")

        editable = style.get("customizable", False)
        for key in self.param_entries:
            w = self.param_entries[key]
            if editable:
                w.config(state="normal" if isinstance(w, ttk.Entry) else "readonly")
            else:
                w.config(state="disabled")
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
        self._cbar_refresh_tree()
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
        else:
            self.status_var.set("提示：请先在预览图中点击一个元素格子。")

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
    # 颜色条标注（刻度与标签自定义）
    # ------------------------------------------------------------------
    def _cbar_current_entries(self):
        """当前生效的标注列表（覆盖值优先，否则样式自带，否则空）。"""
        if self.cbar_override is not None:
            return self.cbar_override["ticks"], self.cbar_override["labels"]
        style = self._current_work_style()
        cfg = style.get("cbar") if not style.get("customizable") else \
            STYLES["custom"].get("cbar")
        if cfg:
            return list(cfg["ticks"]), list(cfg["labels"])
        return [], []

    def _cbar_refresh_tree(self):
        """把当前标注刷新到 Treeview 显示。"""
        ticks, labels = self._cbar_current_entries()
        self.cbar_tree.delete(*self.cbar_tree.get_children())
        for t, l in zip(ticks, labels):
            self.cbar_tree.insert("", "end", values=(str(t), str(l)))

    def _cbar_apply(self, ticks, labels):
        """写入覆盖并刷新预览。"""
        cfg = STYLES[self._current_style_id()].get("cbar")
        fontsize = cfg["fontsize"] if cfg else 8
        self.cbar_override = {"ticks": ticks, "labels": labels,
                              "fontsize": fontsize}
        self._cbar_refresh_tree()
        self._refresh_preview()
        self.status_var.set(f"颜色条标注：{len(ticks)} 个刻度")

    def _cbar_add(self):
        try:
            val = float(self.cbar_value_var.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "刻度值必须是数字。")
            return
        label = self.cbar_label_var.get().strip()
        ticks, labels = self._cbar_current_entries()
        ticks.append(val)
        labels.append(label)
        self._cbar_apply(ticks, labels)

    def _cbar_update(self):
        sel = self.cbar_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选择一行。")
            return
        try:
            val = float(self.cbar_value_var.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "刻度值必须是数字。")
            return
        label = self.cbar_label_var.get().strip()
        idx = self.cbar_tree.index(sel[0])
        ticks, labels = self._cbar_current_entries()
        ticks[idx] = val
        labels[idx] = label
        self._cbar_apply(ticks, labels)

    def _cbar_delete(self):
        sel = self.cbar_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选择一行。")
            return
        idx = self.cbar_tree.index(sel[0])
        ticks, labels = self._cbar_current_entries()
        ticks.pop(idx)
        labels.pop(idx)
        self._cbar_apply(ticks, labels)

    def _cbar_reset(self):
        """恢复默认：不覆盖样式自带的颜色条标注。"""
        self.cbar_override = None
        self.cbar_value_var.set("")
        self.cbar_label_var.set("")
        self._cbar_refresh_tree()
        self._refresh_preview()
        self.status_var.set("颜色条标注已恢复默认")

    # ------------------------------------------------------------------
    # 预设
    # ------------------------------------------------------------------
    def _preset_refresh(self):
        self.preset_combo["values"] = self.presets.list()

    def _current_preset_payload(self) -> dict:
        return {
            "mode_id": self._current_style_id(),
            "params": {k: self.param_vars[k].get() for k in
                       ("cmap", "vmin", "vcenter", "vmax", "fmt",
                        "layout", "kind", "font", "edge", "empty",
                        "dpi", "figsize", "title")},
            "show_cbar": self.show_cbar_var.get(),
            "cbar_override": self.cbar_override,
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

    def _sanitize_colors(self, value) -> list:
        """校验预设中的自定义颜色：须为列表且每项为 3 个 0~1 数值，否则回退默认。"""
        if not isinstance(value, (list, tuple)):
            return list(DEFAULT_COLORS)
        colors = []
        for item in value:
            if (isinstance(item, (list, tuple)) and len(item) == 3 and
                    all(isinstance(c, (int, float)) and 0 <= c <= 1 for c in item)):
                colors.append(tuple(float(c) for c in item))
            else:
                return list(DEFAULT_COLORS)
        return colors if len(colors) >= 2 else list(DEFAULT_COLORS)

    def _preset_load(self):
        name = self.preset_combo.get() or self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请选择或输入要加载的预设名。")
            return
        try:
            payload = self.presets.load(name)
            # 应用预设（对损坏/篡改的 JSON 整体兜底，避免 tkinter 回调 traceback）
            mode_id = payload.get("mode_id", "custom")
            names = [s["name"] for s in STYLES.values()]
            ids = list(STYLES.keys())
            if mode_id in ids:
                self.mode_combo.current(ids.index(mode_id))
                self._on_style_change()
            params = payload.get("params", {})
            if isinstance(params, dict):
                for k, v in params.items():
                    if k in self.param_vars:
                        self.param_vars[k].set(str(v))
            self.show_cbar_var.set(bool(payload.get("show_cbar", True)))
            raw_cbar = payload.get("cbar_override")
            if (isinstance(raw_cbar, dict)
                    and isinstance(raw_cbar.get("ticks"), list)
                    and isinstance(raw_cbar.get("labels"), list)
                    and len(raw_cbar["ticks"]) == len(raw_cbar["labels"])
                    and all(isinstance(t, (int, float)) and math.isfinite(t)
                            for t in raw_cbar["ticks"])):
                fontsize = raw_cbar.get("fontsize", 8)
                if not (isinstance(fontsize, (int, float))
                        and math.isfinite(fontsize)):
                    fontsize = 8
                self.cbar_override = {
                    "ticks": list(raw_cbar["ticks"]),
                    "labels": list(raw_cbar["labels"]),
                    "fontsize": fontsize,
                }
            else:
                self.cbar_override = None
            self._cbar_refresh_tree()
            self.custom_colors = self._sanitize_colors(payload.get("custom_colors"))
            self._build_color_row(self.color_frame)
            raw_data = payload.get("data", {})
            self.data = raw_data if isinstance(raw_data, dict) else {}
            self.table.set_data(self.data)
            self.status_var.set(f"已加载预设 {name}")
            self._refresh_preview()
        except Exception as exc:
            messagebox.showerror("加载失败", str(exc))

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
        style = self._current_work_style()
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

    def _preview_data(self) -> dict:
        """与 generate() 使用相同的数据校验逻辑（保证预览与输出一致）。"""
        work = self._current_work_style()
        if work.get("kind") == "labels":
            return {s: v for s, v in self.data.items() if s in known_symbols()}
        data, _, _ = validate_data(self.data)
        return {s: v for s, v in data.items() if not isinstance(v, str)}

    def _refresh_preview(self):
        style_id = self._current_style_id()
        if style_id == "cmap_preview":
            # 本模式无周期表预览：显示占位说明，避免残留旧预览误导
            import matplotlib.pyplot as plt
            empty_fig = plt.figure(figsize=(8, 3))
            ax = empty_fig.add_subplot(111)
            ax.text(0.5, 0.5, "颜色映射预览模式：点击「生成图片」输出全部色图预览",
                    ha="center", va="center", fontsize=12)
            ax.axis("off")
            self.preview.show(empty_fig, {})
            return
        try:
            style = self._current_work_style()
            title = (self.param_vars["title"].get().strip()
                     if style.get("customizable") else "")
            fig = render_table(style, self._preview_data(), title=title or None,
                               show_cbar=self.show_cbar_var.get(),
                               figsize=style.get("figsize", (10, 5)))
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

            work_style = self._current_work_style()
            if work_style.get("kind") == "labels":
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

            fmt = self.fmt_var.get()
            title = (self.param_vars["title"].get().strip()
                     if style.get("customizable") else "")
            fig = render_table(work_style, data, title=title or None,
                               show_cbar=self.show_cbar_var.get(),
                               figsize=work_style.get("figsize", (10, 5)))
            path = save_figure(
                fig, out_dir, "periodic_table", fmt,
                bbox_inches="tight" if work_style.get("bbox_tight", True) else None,
                dpi=work_style.get("dpi", 100))
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
        import math
        work = copy.deepcopy(style)
        cmap_name = self.param_vars["cmap"].get().strip()
        try:
            vmin = float(self.param_vars["vmin"].get())
            vmax = float(self.param_vars["vmax"].get())
            center_text = self.param_vars["vcenter"].get().strip()
            vcenter = float(center_text) if center_text else None
        except (ValueError, TypeError) as exc:
            raise ValueError("vmin / vcenter / vmax 必须是数字") from exc
        # 拒绝 NaN / Infinity，避免污染 norm 与渲染
        if (not math.isfinite(vmin) or not math.isfinite(vmax) or
                (vcenter is not None and not math.isfinite(vcenter))):
            raise ValueError("vmin / vcenter / vmax 必须是有限数值")
        work["norm"] = (("twoslope", vmin, vcenter, vmax) if vcenter is not None
                        else ("normalize", vmin, vmax))
        # 范围顺序校验：vmin < vcenter < vmax（normalize 时 vmin < vmax）
        if vcenter is not None:
            if not (vmin < vcenter < vmax):
                raise ValueError("范围顺序应为 vmin < vcenter < vmax")
        elif vmin >= vmax:
            raise ValueError("vmin 必须小于 vmax")
        work["fmt"] = FMT_CHOICES.get(self.param_vars["fmt"].get(), "3f")
        # 自定义颜色优先；否则按输入的名称取预置色图
        if cmap_name.strip().startswith("自定义"):
            work["cmap"] = ("custom", [tuple(c) for c in self.custom_colors])
        elif cmap_name.strip():
            work["cmap"] = cmap_name.strip()
        else:
            work["cmap"] = ("custom", [tuple(c) for c in self.custom_colors])

        # ---- 高级参数（渲染自由度）----
        work["layout"] = LAYOUT_CHOICES.get(self.param_vars["layout"].get(),
                                            "classic")
        work["kind"] = KIND_CHOICES.get(self.param_vars["kind"].get(),
                                        "heatmap")
        work["font"] = FONT_CHOICES.get(self.param_vars["font"].get(), "Arial")
        edge = EDGE_CHOICES.get(self.param_vars["edge"].get(), "none")
        work["edge"] = None if edge == "none" else (0.5, "black")
        work["empty"] = EMPTY_CHOICES.get(self.param_vars["empty"].get(),
                                          "#f0f0f0")
        work["dpi"] = DPI_CHOICES.get(self.param_vars["dpi"].get(), 100)
        # 图尺寸 "宽x高"（英寸），解析失败/非有限值保持默认；上限 40 英寸防资源滥用
        fs = self.param_vars["figsize"].get().strip().lower()
        try:
            if "x" in fs:
                w, h = fs.split("x", 1)
                fw, fh = float(w), float(h)
                if math.isfinite(fw) and math.isfinite(fh):
                    work["figsize"] = (min(max(fw, 2.0), 40.0),
                                       min(max(fh, 1.0), 40.0))
        except (ValueError, TypeError):
            pass
        # 标注图类型：注入 labels 专属默认键（浅灰底 + 深灰标注）
        if work["kind"] == "labels":
            work.setdefault("bg", "#f0f0f0")
            work.setdefault("label_color", "#666666")
            work.setdefault("label_fs", 8)
            work.setdefault("label_dy", 0.12)
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
    _smoke_log("start")
    app = App()
    _smoke_log("app_created")
    # PTT_SMOKE=1：构造成功即自动退出（隐藏窗口避免无交互桌面阻塞）
    if os.environ.get("PTT_SMOKE") == "1":
        app.withdraw()
        app.after(1500, app.destroy)
    _smoke_log("before_mainloop")
    app.mainloop()
    _smoke_log("after_mainloop")


if __name__ == "__main__":
    main()
