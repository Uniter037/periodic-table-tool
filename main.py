# -*- coding: utf-8 -*-
"""元素周期表绘图工作台 - 项目编辑、科学绘图与兼容输出。

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
import copy
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


# Tk 仅承载应用界面；所有绘图均离屏渲染，打包版也不创建额外 Figure 窗口。
_smoke_log("import:before_matplotlib")
import matplotlib
matplotlib.use("Agg")
_smoke_log("import:after_matplotlib")

from core import (STYLES, parse_data, validate_data, demo_data,
                  known_symbols, render_table, render_cmap_preview,
                  save_figure, auto_name, PresetStore)
from core.ptable import build_elements, xy_bounds_for, CELL_STEP
from core.elements_data import ALL_SYMBOLS
from core.dataio import convert_data
from core.document import History, read_document, write_document, user_directory
from core.scientific import corrected_style, colorbar_config, range_warnings
from application.dataset_collection import DatasetCollection
from core.jobs import RenderJob
from infrastructure.diagnostics import DiagnosticService, DiagnosticSettings
from ui.preview import PreviewCanvas
from ui.scrolling import ScrollableFrame
_smoke_log("import:after_core")

SYMBOLS = set(ALL_SYMBOLS)
FORMATS = ["svg", "png", "pdf"]
DEFAULT_COLORS = [(0.1726, 0.2941, 0.4588), (1, 1, 1), (0.5686, 0.1333, 0.1098)]
CONFIG_PATH = str(user_directory() / "settings.json")
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
PREVIEW_RATIO_OPTIONS = (0.4, 0.5, 0.6, 0.72, 0.85)
BASE_FONT_SIZE = 10          # 100% 缩放时的基准字号
BASE_WINDOW_WIDTH = 1280     # auto 缩放的基准窗口宽度
SCALE_RANGE = (0.9, 1.5)     # auto 缩放的上下限

# 自定义模式高级参数：GUI 中文标签 → 样式值（反向映射用于回填）
LAYOUT_CHOICES = {"镧锕三行块（重构）": "reconstructed",
                  "展开 8-9 行（经典）": "classic"}
KIND_CHOICES = {"热力图": "heatmap", "标注图（文本）": "labels"}
FONT_CHOICES = {"Arial": "Arial", "Helvetica": "Helvetica",
                "DejaVu Sans": "DejaVu Sans"}
EDGE_CHOICES = {"无边框": "none", "黑色细线": "black"}
EMPTY_CHOICES = {"浅灰": "#f0f0f0", "白色": "white", "白色(w)": "w", "透明": "none"}
FMT_CHOICES = {"百分比 2 位": "percent2", "两位小数": "2f", "三位小数": "3f",
               "四位小数": "4f", "科学计数法": "scientific", "原始": "raw"}
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
        self.title("元素周期表绘图工作台 · v1.7.0")
        self.geometry("1180x760")
        self.minsize(800, 560)
        self._refresh_job = None
        self._ratio_job = None
        self._preview_error = None

        self.out_dir = os.path.join(PROJECT_ROOT, "output")
        self.last_output = None
        self.excel_collection = DatasetCollection()
        self._excel_attached = False
        self.data = {}                       # 统一数据源 {符号: 值}
        self.custom_colors = list(DEFAULT_COLORS)
        self.user_dir = user_directory()
        if not os.environ.get("PTT_USER_DIR"):
            self._migrate_user_files()
        self.presets = PresetStore(str(self.user_dir / "presets"))
        self._style_states = {}
        self._active_style = None
        self._restoring = True
        self._history = None
        self._draft_job = None
        self._recovery_pending = (self.user_dir / "draft.ptproj").is_file() and os.environ.get("PTT_SMOKE") != "1"
        self._worker = RenderJob()
        self._poll_job = None
        self._job_mode = None
        self._pending_preview = False
        self.project_path = None
        self._main = None
        self._left = None
        self._right = None
        self._current_layout = None          # 当前实际生效的布局
        self.layout_mode = "auto"            # 用户选择：auto / split-h / split-v
        self.scale_mode = "auto"             # 界面缩放：auto 或 "0.8"/"1.0"/"1.25"/"1.5"
        self.preview_ratio = 0.72             # 预览区域高度占比（右侧上部）
        self._current_scale = None           # 已应用的缩放值（防抖）
        self._app_font = None
        self.cbar_override = None            # 颜色条标注自定义（None=用样式默认）
        self._load_config()
        log_cfg = self._config.get("diagnostics", {})
        if not isinstance(log_cfg, dict):
            log_cfg = {}
        self.log_enabled = tk.BooleanVar(value=log_cfg.get("enabled", True) is True)
        level = log_cfg.get("level", "INFO")
        self.log_level = tk.StringVar(value=level if level in ("DEBUG", "INFO", "WARNING") else "INFO")
        self.diagnostics = DiagnosticService(settings=DiagnosticSettings(enabled=self.log_enabled.get(), level=self.log_level.get()))
        self.diagnostics.record("INFO", "app.started", "应用已启动")
        self._restore_geometry()

        self._build_ui()
        self._on_style_change()
        self._restoring = False
        self._history = History(self._document_snapshot())
        self._saved_snapshot = self._document_snapshot()
        self._refresh_preview()
        if self._recovery_pending:
            self.after_idle(self._offer_recovery)
        # 随窗口大小自动调整布局
        self.bind("<Configure>", self._on_window_resize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    def _configure_diagnostics(self):
        self.diagnostics.configure(DiagnosticSettings(enabled=self.log_enabled.get(), level=self.log_level.get()))
        self._save_config()

    def _start_diagnostic_session(self):
        self.diagnostics.start_session(30)
        self.status_var.set("临时详细日志已开启，30分钟后恢复原设置；手动修改日志设置将结束临时排错。")

    def _stop_diagnostic_session(self):
        self.diagnostics.stop_session()
        self.status_var.set("临时排错已结束，已恢复日志设置。")

    def _export_diagnostics(self):
        directory = filedialog.askdirectory(title="选择诊断包保存目录（仅含本次脱敏日志与环境信息，不含Excel数据）")
        if not directory:
            return
        try:
            path = self.diagnostics.export_bundle(None, directory)
        except Exception as exc:
            messagebox.showerror("诊断包导出失败", str(exc))
            return
        self.status_var.set(f"诊断包已保存：{path}")

    def _show_diagnostics(self):
        window = tk.Toplevel(self)
        window.title("本次运行日志")
        window.geometry("760x420")
        text = tk.Text(window, wrap="word")
        text.pack(fill="both", expand=True)
        def refresh():
            page = self.diagnostics.query(limit=300)
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("end", "\n".join(json.dumps(row, ensure_ascii=False) for row in page.entries) or "本次运行暂无日志。")
            text.configure(state="disabled")
        ttk.Button(window, text="刷新", command=refresh).pack()
        refresh()

    def _migrate_user_files(self):
        """Copy only absent legacy user files; never overwrite an edited preset."""
        import shutil
        from pathlib import Path
        try:
            self.user_dir.mkdir(parents=True, exist_ok=True)
            legacy = Path.home() / ".periodic-table-tool.json"
            target = self.user_dir / "settings.json"
            if legacy.is_file() and not target.exists():
                shutil.copy2(legacy, target)
            destination = self.user_dir / "presets"
            destination.mkdir(exist_ok=True)
            for source in (Path(PROJECT_ROOT) / "presets").glob("*.json"):
                if not (destination / source.name).exists():
                    shutil.copy2(source, destination / source.name)
        except OSError:
            pass

    def _restore_geometry(self):
        """以 Tk 的逻辑像素限幅并居中，丢弃旧屏幕坐标与超屏尺寸。"""
        import re
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        available_w, available_h = max(320, screen_w - 80), max(300, screen_h - 120)
        match = re.match(r"^(\d+)x(\d+)", str(self._config.get("geometry", "")))
        width, height = (map(int, match.groups()) if match else (1180, 760))
        min_w, min_h = min(800, available_w), min(560, available_h)
        width = max(min_w, min(width, available_w))
        height = max(min_h, min(height, available_h))
        self.minsize(min_w, min_h)
        self.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{(screen_h - height) // 2}")

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
            ratio = float(cfg.get("preview_ratio", 0.72))
            self.preview_ratio = ratio if 0.35 <= ratio <= 0.9 else 0.72
        except (TypeError, ValueError):
            self.preview_ratio = 0.72

    def _save_config(self):
        """保存用户配置（布局模式、窗口尺寸、界面缩放、预览比例）。"""
        cfg = {
            "layout": self.layout_mode,
            "geometry": self.geometry(),
            "scale": self.scale_mode,
            "preview_ratio": self.preview_ratio,
            "diagnostics": {"enabled": self.log_enabled.get(), "level": self.log_level.get()},
        }
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def destroy(self):
        if self._draft_job is not None:
            self.after_cancel(self._draft_job)
            self._draft_job = None
        if getattr(self, "_worker", None) is not None:
            self._worker.cancel()
        if getattr(self, "_poll_job", None) is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._cancel_refresh()
        if self._ratio_job is not None:
            self.after_cancel(self._ratio_job)
            self._ratio_job = None
        if getattr(self, "diagnostics", None) is not None:
            self.diagnostics.close()
        super().destroy()

    def _on_close(self):
        self._commit_table_edit()
        if not self._confirm_discard():
            return
        self._save_config()
        self._remove_draft()
        self.destroy()

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def _effective_layout(self) -> str:
        if self.layout_mode == "auto":
            return "split-v" if 1 < self.winfo_width() < AUTO_SPLIT_THRESHOLD else "split-h"
        return self.layout_mode

    def _apply_layout(self):
        if self._main is None:
            return
        layout = self._effective_layout()
        if layout == "split-v":
            self._left.configure(height=max(110, min(190, round(self.winfo_height() * .20))))
        if self._right is not None and self._right.panes():
            self._right.paneconfigure(self._right.panes()[0], minsize=210 if layout == "split-v" and self.winfo_height() < 700 else 252)
        if layout == self._current_layout:
            return
        self._current_layout = layout
        main = self._main
        for index in (0, 1):
            main.rowconfigure(index, weight=0, minsize=0)
            main.columnconfigure(index, weight=0, minsize=0)
        if layout == "split-h":
            main.rowconfigure(0, weight=1)
            main.columnconfigure(1, weight=1)
            self._left.configure(width=330, height=200)
            self._left.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
            self._right.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        else:
            main.columnconfigure(0, weight=1)
            main.rowconfigure(1, weight=1)
            self._left.configure(height=max(110, min(190, round(self.winfo_height() * .20))))
            self._left.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 6))
            self._right.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

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
        if self._current_layout == "split-h":
            self._left.configure(width=round(330 * max(1.0, scale / 1.1)))
        self._resize_preview()

    def _apply_preview_ratio(self):
        """调节真实可拖动的预览 / 数据分隔条。"""
        if self._right is None:
            return
        height = self._right.winfo_height()
        if height > 1:
            self._right.sash_place(0, 0, int(height * self.preview_ratio))

    def _remember_preview_ratio(self, event=None):
        height = self._right.winfo_height()
        if height > 1:
            self.preview_ratio = max(.35, min(.9, self._right.sash_coord(0)[1] / height))
            self.ratio_var.set(self.preview_ratio)

    def _resize_preview(self):
        """仅缩放预览图像，保留配置的 Figure 画幅和构图。"""
        self.preview.resize()

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
        menubar = tk.Menu(self)
        project_menu = tk.Menu(menubar, tearoff=0)
        project_menu.add_command(label="打开项目…", command=self._open_project)
        project_menu.add_command(label="保存项目", command=self._save_project)
        project_menu.add_command(label="项目另存为…", command=lambda: self._save_project(save_as=True))
        project_menu.add_command(label="批量导出（共用当前色标）…", command=self._batch_export)
        project_menu.add_separator()
        project_menu.add_command(label="撤销  Ctrl+Z", command=self._undo)
        project_menu.add_command(label="重做  Ctrl+Y", command=self._redo)
        project_menu.add_command(label="切换 Excel 数据组", command=self._show_excel_groups)
        menubar.add_cascade(label="项目", menu=project_menu)
        self.bind("<Control-z>", lambda e: self._undo())
        self.bind("<Control-y>", lambda e: self._redo())
        self.bind("<Control-s>", lambda e: self._save_project())
        view_menu = tk.Menu(menubar, tearoff=0)
        self.layout_var = tk.StringVar(value=self.layout_mode)
        for mode, label in LAYOUT_MODES:
            view_menu.add_radiobutton(label=label, variable=self.layout_var,
                                     value=mode, command=self._on_layout_mode_change)
        self.scale_var = tk.StringVar(value=self.scale_mode)
        scale_menu = tk.Menu(view_menu, tearoff=0)
        for value, label in SCALE_OPTIONS:
            scale_menu.add_radiobutton(label=label, variable=self.scale_var,
                                      value=value, command=self._on_scale_change)
        view_menu.add_cascade(label="界面缩放", menu=scale_menu)
        self.ratio_var = tk.DoubleVar(value=self.preview_ratio)
        ratio_menu = tk.Menu(view_menu, tearoff=0)
        for ratio in PREVIEW_RATIO_OPTIONS:
            ratio_menu.add_radiobutton(label=f"预览区 {ratio:.0%}", variable=self.ratio_var,
                                      value=ratio, command=self._on_ratio_change)
        view_menu.add_cascade(label="预览区域大小（也可拖动分隔条）", menu=ratio_menu)
        view_menu.add_command(label="预览适合窗口（滚轮缩放，右键拖动）", command=lambda: self.preview.fit())
        menubar.add_cascade(label="视图", menu=view_menu)
        logs_menu = tk.Menu(menubar, tearoff=0)
        logs_menu.add_checkbutton(label="记录日志", variable=self.log_enabled, command=self._configure_diagnostics)
        for label, value in (("精简", "WARNING"), ("标准", "INFO"), ("详细", "DEBUG")):
            logs_menu.add_radiobutton(label=label, variable=self.log_level, value=value, command=self._configure_diagnostics)
        logs_menu.add_separator()
        logs_menu.add_command(label="查看本次日志", command=self._show_diagnostics)
        logs_menu.add_command(label="临时详细排错（30分钟）", command=self._start_diagnostic_session)
        logs_menu.add_command(label="结束临时排错", command=self._stop_diagnostic_session)
        logs_menu.add_command(label="导出本次诊断包", command=self._export_diagnostics)
        menubar.add_cascade(label="日志与排错", menu=logs_menu)
        self.config(menu=menubar)

        # 工具栏与状态栏独立于可滚动内容，始终保持可见。
        self.toolbar = ttk.Frame(self, padding=(8, 6))
        self.toolbar.pack(side="top", fill="x")
        style = ttk.Style(self)
        style.configure("TButton", padding=(8, 5))
        style.configure("TNotebook.Tab", padding=(9, 6))
        style.configure("Export.TButton", font=("Microsoft YaHei", 10, "bold"), padding=(14, 6))
        self.toolbar_buttons = {}
        for label, command in (("导入文件", self._import_file), ("粘贴数据", self._paste_data),
                               ("载入示例", self._load_demo), ("导出图片", self.generate_async),
                               ("打开输出目录", self._open_out_dir)):
            button = ttk.Button(self.toolbar, text=label, command=command,
                                style="Export.TButton" if label == "导出图片" else "TButton")
            button.pack(side="left", padx=(0, 6))
            self.toolbar_buttons[label] = button
        self._status = ttk.Frame(self, padding=(8, 4))
        self._status.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="就绪 · 导入、粘贴或载入示例开始绘图")
        self._status.columnconfigure(0, weight=1)
        ttk.Label(self._status, textvariable=self.status_var, anchor="w").grid(row=0, column=0, sticky="ew")
        self.progress = ttk.Progressbar(self._status, mode="determinate", maximum=100, length=100)
        self.progress.grid(row=0, column=1, padx=6)
        ttk.Button(self._status, text="取消任务", command=self._cancel_job).grid(row=0, column=2)
        main = self._main = ttk.Frame(self, padding=(8, 0, 8, 0))
        main.pack(fill="both", expand=True)
        left = self._left = ttk.Frame(main, width=330, height=200)
        left.pack_propagate(False)
        self.settings_notebook = ttk.Notebook(left)
        self.settings_notebook.pack(fill="both", expand=True)
        self.settings_pages = {}
        for key, label in (("figure", "图形"), ("colors", "配色 / 颜色条"),
                           ("export", "预设 / 导出")):
            page = ScrollableFrame(self.settings_notebook)
            self.settings_notebook.add(page, text=label)
            self.settings_pages[key] = page
        graph = self.settings_pages["figure"].content
        colors = self.settings_pages["colors"].content
        export = self.settings_pages["export"].content

        ttk.Label(graph, text="绘图模式").pack(anchor="w")
        self.mode_var = tk.StringVar()
        self.mode_combo = ttk.Combobox(graph, textvariable=self.mode_var, state="readonly",
                                      values=[s["name"] for s in STYLES.values()], width=20)
        self.mode_combo.pack(fill="x", pady=(2, 6))
        self.mode_combo.current(list(STYLES).index("custom"))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_style_change())
        self.compat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(graph, text="原脚本兼容（保留历史零值与色标行为）",
                        variable=self.compat_var, command=self._compat_changed).pack(anchor="w")
        self.file_label = ttk.Label(graph, foreground="#666666", wraplength=280)
        self.file_label.pack(anchor="w")
        self.hint_label = ttk.Label(graph, foreground="#666666", wraplength=280)
        self.hint_label.pack(fill="x", pady=(2, 8))
        self.param_vars, self.param_entries = {}, {}
        self.custom_controls = []

        def field(parent, key, label, choices=None):
            ttk.Label(parent, text=label).pack(anchor="w", pady=(5, 1))
            var = tk.StringVar()
            widget = (ttk.Combobox(parent, textvariable=var, values=choices,
                                   state="readonly", width=16) if choices else
                      ttk.Entry(parent, textvariable=var, width=16))
            widget.pack(fill="x", pady=(0, 2))
            var.trace_add("write", lambda *args: self._refresh_preview())
            self.param_vars[key], self.param_entries[key] = var, widget

        for key, label, choices in (
            ("layout", "元素布局", list(LAYOUT_CHOICES)),
            ("kind", "图表类型", list(KIND_CHOICES)),
            ("title", "图标题", None), ("font", "字体（可输入本机字体名称）", sorted(set(tkfont.families(self)) | set(FONT_CHOICES) | {"Microsoft YaHei", "SimHei", "SimSun"})),
            ("fmt", "数值格式", list(FMT_CHOICES)),
            ("symbol_fs", "元素符号字号（pt）", None),
            ("number_fs", "原子序数字号（pt）", None),
            ("value_fs", "数值 / 标注字号（pt）", None),
            ("edge_width", "边框线宽（pt，0 为无边框）", None),
            ("edge_color", "边框颜色（名称或 #RRGGBB）", None),
            ("value_dx", "标注水平偏移（格宽）", None),
            ("value_dy", "标注垂直偏移（格高）", None),
            ("label_wrap", "标注每行字符数（0 不自动换行）", None),
            ("unit", "数值后缀 / 单位", None),
            ("edge", "边框快捷设置（可继续调整线宽和颜色）", list(EDGE_CHOICES)),
            ("empty", "空值格颜色", list(EMPTY_CHOICES))):
            field(graph, key, label, choices)
        self.param_vars["edge"].trace_add("write", self._edge_preset_changed)
        self.bool_vars = {}
        for key, label, parent, default in (
            ("show_symbol", "显示元素符号", graph, True),
            ("show_number", "显示原子序数", graph, True),
            ("show_value", "显示数值 / 标注", graph, True),
            ("transparent", "透明背景", export, False)):
            var = tk.BooleanVar(value=default)
            self.bool_vars[key] = var
            setattr(self, key + "_var", var)
            button = ttk.Checkbutton(parent, text=label, variable=var, command=self._refresh_preview)
            button.pack(anchor="w", pady=3)
            self.custom_controls.append(button)

        for key, label in (("cmap", "颜色映射名称 / 自定义"), ("vmin", "最小值 vmin"),
                           ("vcenter", "中心值 vcenter（留空为线性）"), ("vmax", "最大值 vmax")):
            field(colors, key, label)
        self.auto_range_button = ttk.Button(colors, text="自动范围（按当前数据）", command=self._auto_range)
        self.auto_range_button.pack(fill="x", pady=5)
        self.custom_controls.append(self.auto_range_button)
        color_lf = self.color_frame = ttk.LabelFrame(colors, text="自定义颜色", padding=4)
        color_lf.pack(fill="x", pady=6)
        self.color_buttons = []
        self._build_color_row(color_lf)
        field(colors, "color_nodes", "颜色节点：位置:颜色；例如 0:#0000ff;0.3:#ffffff;1:#ff0000")
        color_actions = ttk.Frame(color_lf)
        color_actions.pack(fill="x", pady=4)
        for label, command in (("添加", self._add_color), ("移除最后", self._remove_color),
                               ("默认", self._reset_colors)):
            button = ttk.Button(color_actions, text=label, width=7, command=command)
            button.pack(side="left", padx=2)
            self.custom_controls.append(button)
        self.show_cbar_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(colors, text="显示颜色条", variable=self.show_cbar_var,
                        command=self._refresh_preview).pack(anchor="w", pady=4)
        field(colors, "cbar_orientation", "颜色条方向", ["vertical", "horizontal"])
        field(colors, "cbar_label", "颜色条标题 / 单位")
        field(colors, "cbar_location", "颜色条位置（自动跟随方向或手动）", ["auto", "left", "right", "top", "bottom"])
        for key, label in (("cbar_fraction", "颜色条宽度比例"), ("cbar_pad", "颜色条间距比例"),
                           ("cbar_shrink", "颜色条长度比例")):
            field(colors, key, label)
        self.show_cbar_labels_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(colors, text="显示刻度标签（隐藏后可恢复）", variable=self.show_cbar_labels_var,
                        command=self._refresh_preview).pack(anchor="w", pady=4)
        cbar_lf = ttk.LabelFrame(colors, text="颜色条刻度与标签", padding=4)
        cbar_lf.pack(fill="x", pady=6)
        tree_row = ttk.Frame(cbar_lf)
        tree_row.pack(fill="x")
        self.cbar_tree = ttk.Treeview(tree_row, columns=("v", "l", "visible"), show="headings", height=4,
                                     selectmode="browse")
        self.cbar_tree.heading("v", text="刻度值")
        self.cbar_tree.heading("l", text="标签")
        self.cbar_tree.heading("visible", text="显示")
        self.cbar_tree.column("visible", width=42, stretch=False)
        self.cbar_tree.column("v", width=75, minwidth=40)
        self.cbar_tree.column("l", width=125, minwidth=60)
        self.cbar_tree.pack(side="left", fill="both", expand=True)
        ttk.Scrollbar(tree_row, orient="vertical", command=self.cbar_tree.yview).pack(side="right", fill="y")
        self.cbar_tree.configure(yscrollcommand=tree_row.winfo_children()[-1].set)
        self.cbar_tree.bind("<<TreeviewSelect>>", self._cbar_select)
        self.cbar_value_var, self.cbar_label_var = tk.StringVar(), tk.StringVar()
        for label, var in (("刻度值", self.cbar_value_var), ("标签文本", self.cbar_label_var)):
            ttk.Label(cbar_lf, text=label).pack(anchor="w")
            ttk.Entry(cbar_lf, textvariable=var).pack(fill="x", pady=2)
        cbar_btns = ttk.Frame(cbar_lf)
        cbar_btns.pack(fill="x", pady=4)
        for index, (label, command) in enumerate((("添加", self._cbar_add), ("更新选中", self._cbar_update),
                                                ("删除选中", self._cbar_delete), ("恢复默认", self._cbar_reset))):
            ttk.Button(cbar_btns, text=label, command=command).grid(row=index // 2, column=index % 2, sticky="ew")
        cbar_btns.columnconfigure((0, 1), weight=1)
        ttk.Button(cbar_lf, text="显示 / 隐藏选中刻度", command=self._cbar_toggle).pack(fill="x")
        ttk.Button(cbar_lf, text="按数值排序", command=self._cbar_sort).pack(fill="x")
        self.cbar_controls = (cbar_lf,)

        for key, label, choices in (("dpi", "输出分辨率 dpi", list(DPI_CHOICES)),
                                   ("figsize", "画幅尺寸（宽 x 高，英寸）", None)):
            field(export, key, label, choices)
        ttk.Label(export, text="输出格式").pack(anchor="w", pady=(8, 2))
        self.fmt_var = tk.StringVar(value="svg")
        ttk.Combobox(export, textvariable=self.fmt_var, values=FORMATS, state="readonly").pack(fill="x")
        ttk.Label(export, text="输出目录").pack(anchor="w", pady=(8, 2))
        self.out_var = tk.StringVar(value=self.out_dir)
        self.fmt_var.trace_add("write", self._record_document_change)
        self.out_var.trace_add("write", self._record_document_change)
        ttk.Entry(export, textvariable=self.out_var).pack(fill="x")
        ttk.Button(export, text="选择输出目录", command=self._choose_out_dir).pack(fill="x", pady=4)
        ttk.Label(export, text="导出会自动命名，不覆盖已有文件。", wraplength=280).pack(anchor="w", pady=4)
        preset_lf = ttk.LabelFrame(export, text="预设（设置与数据）", padding=6)
        preset_lf.pack(fill="x", pady=10)
        self.preset_name_var = tk.StringVar()
        ttk.Label(preset_lf, text="预设名称").pack(anchor="w")
        ttk.Entry(preset_lf, textvariable=self.preset_name_var).pack(fill="x", pady=4)
        self.preset_combo = ttk.Combobox(preset_lf, state="readonly")
        self.preset_combo.pack(fill="x", pady=4)
        for label, command in (("保存预设", self._preset_save), ("加载预设", self._preset_load),
                               ("删除预设", self._preset_delete), ("刷新列表", self._preset_refresh)):
            ttk.Button(preset_lf, text=label, command=command).pack(fill="x", pady=2)

        # 预览获得剩余空间，数据区高度可直接拖动调整。
        right = self._right = tk.PanedWindow(main, orient="vertical", sashwidth=8,
                                            sashrelief="raised", borderwidth=0, opaqueresize=True)
        prev_lf = ttk.LabelFrame(right, text="实时预览 · 拖动下方分隔条调整数据区", padding=4)
        self.preview = PreviewCanvas(prev_lf)
        self.preview.on_click = self._on_preview_click
        self.preview.pack(fill="both", expand=True)
        self.mark_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(prev_lf, text="图形化标注：点击元素格编辑", variable=self.mark_mode_var).pack(anchor="w")
        data_nb = self.data_notebook = ttk.Notebook(right)
        right.add(prev_lf, minsize=252, height=440, stretch="always")
        right.add(data_nb, minsize=150, height=180, stretch="never")
        right.bind("<ButtonRelease-1>", self._remember_preview_ratio)
        right.bind("<Map>", lambda e: self._schedule_ratio())
        tab_table = ttk.Frame(data_nb, padding=4)
        data_nb.add(tab_table, text="数据表 · 双击数值编辑")
        ttk.Button(tab_table, text="清空数据", command=self._clear_data).pack(side="bottom", anchor="e")
        self.table = DataTable(tab_table, on_change=self._table_changed)
        self.table.tree.configure(height=5)
        self.table.pack(fill="both", expand=True)
        self.mark_tab = ttk.Frame(data_nb, padding=6)
        data_nb.add(self.mark_tab, text="图形化标注")
        self.mark_tab.columnconfigure(1, weight=1)
        self.mark_symbol_var = tk.StringVar(value="（点击预览元素）")
        self.mark_value_var = tk.StringVar()
        ttk.Label(self.mark_tab, text="当前元素").grid(row=0, column=0, sticky="w")
        ttk.Label(self.mark_tab, textvariable=self.mark_symbol_var).grid(row=0, column=1, sticky="w")
        ttk.Label(self.mark_tab, text="数值 / 标注").grid(row=1, column=0, sticky="w", pady=4)
        entry = ttk.Entry(self.mark_tab, textvariable=self.mark_value_var)
        entry.grid(row=1, column=1, sticky="ew", pady=4)
        entry.bind("<Return>", lambda e: self._apply_mark())
        buttons = ttk.Frame(self.mark_tab)
        buttons.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Button(buttons, text="应用标注", command=self._apply_mark).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="清除该元素", command=self._clear_mark).pack(side="left")
        self._apply_layout()
        self._apply_scale()
        self._schedule_ratio()

    def _schedule_ratio(self):
        if self._ratio_job is not None:
            self.after_cancel(self._ratio_job)
        self._ratio_job = self.after_idle(self._initial_ratio)

    def _initial_ratio(self):
        self._ratio_job = None
        self._apply_preview_ratio()

    # ------------------------------------------------------------------
    def _build_color_row(self, parent):
        """重建自定义颜色色块按钮行。"""
        if hasattr(self, "_color_row"):
            self._color_row.destroy()
        self.color_buttons = []
        row = self._color_row = ttk.Frame(parent)
        siblings = parent.winfo_children()
        if len(siblings) > 1:
            row.pack(fill="x", before=siblings[0])
        else:
            row.pack(fill="x")
        for i, rgb in enumerate(self.custom_colors):
            btn = tk.Button(row, width=4, bg=_rgb_to_hex(rgb),
                            command=lambda idx=i: self._edit_color(idx))
            btn.grid(row=i // 5, column=i % 5, padx=2, pady=2)
            self.color_buttons.append(btn)

    # ------------------------------------------------------------------
    def _current_style_id(self) -> str:
        return list(STYLES.keys())[self.mode_combo.current()]

    def _current_work_style(self):
        """当前生效的样式：自定义模式应用面板参数；任意模式注入颜色条标注覆盖。"""
        style = STYLES[self._current_style_id()]
        if not self.compat_var.get() and style.get("kind") != "cmap":
            style = corrected_style(style)
        work = (self._apply_custom_params(style)
                if style.get("customizable") else style)
        if self.cbar_override is not None:
            # 非自定义模式返回的是 STYLES 原对象，浅拷贝避免污染全局
            if not style.get("customizable"):
                work = dict(work)
            work["cbar"] = {**self.cbar_override,
                            "ticks": list(self.cbar_override["ticks"]),
                            "labels": list(self.cbar_override["labels"])}
            work["cbar"] = colorbar_config(work["cbar"])
        # 隐藏标签只作用于本次渲染，不销毁用户输入和默认刻度。
        if not self.show_cbar_labels_var.get():
            work = dict(work)
            cfg = work.get("cbar")
            if cfg:
                work["cbar"] = {**cfg, "labels": [""] * len(cfg["ticks"])}
            else:
                work["cbar"] = {"ticks": [], "labels": [], "fontsize": 8}
        return work

    def _on_style_change(self):
        self._commit_table_edit()
        restoring = self._restoring
        self._restoring = True
        if self._active_style is not None:
            previous = self._current_preset_payload()
            previous["mode_id"] = self._active_style
            self._style_states[self._active_style] = copy.deepcopy(previous)
        style_id = self._current_style_id()
        style = STYLES[style_id]
        self._active_style = style_id
        self.cbar_override = None
        self.custom_colors = list(DEFAULT_COLORS)
        self.show_cbar_var.set(True)
        self.show_cbar_labels_var.set(True)
        saved = self._style_states.get(style_id)
        self.compat_var.set(saved.get("compatibility", False) if saved else False)
        if not self.compat_var.get() and style.get("kind") != "cmap":
            style = corrected_style(style)
        self.file_label.config(text=f"对应原脚本：{style['file']}")

        norm = style.get("norm")
        self.param_vars["cmap"].set(_cmap_name(style))
        self.param_vars["vmin"].set(str(norm[1]) if norm else "0")
        self.param_vars["vcenter"].set(str(norm[2]) if norm and norm[0] == "twoslope" else "")
        self.param_vars["vmax"].set(str(norm[-1]) if norm else "1")
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
        for key, default in (("symbol_fs", 9), ("number_fs", 6), ("value_fs", 6),
                             ("cbar_orientation", "vertical"), ("cbar_label", ""),
                             ("edge_width", style.get("edge", (0, "black"))[0] if style.get("edge") else 0),
                             ("edge_color", "black"), ("value_dx", 0), ("value_dy", 0),
                             ("label_wrap", 0), ("unit", ""), ("color_nodes", ""),
                             ("cbar_location", "auto"), ("cbar_fraction", .046),
                             ("cbar_pad", .04), ("cbar_shrink", 1)):
            self.param_vars[key].set(str(style.get(key, default)))
        for key, var in self.bool_vars.items():
            var.set(style.get(key, key != "transparent"))
        if style_id == "custom":
            self.param_vars["vmin"].set("-1")
            self.param_vars["vcenter"].set("0")
            self.param_vars["vmax"].set("1")

        if saved:
            self._apply_payload(saved, include_data=False)
        self._build_color_row(self.color_frame)
        editable = style.get("customizable", False)
        for key in self.param_entries:
            w = self.param_entries[key]
            if editable:
                w.config(state="readonly" if isinstance(w, ttk.Combobox) and key != "font" else "normal")
            else:
                w.config(state="disabled")
        for control in self.custom_controls:
            control.configure(state="normal" if editable else "disabled")
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
        self._restoring = restoring
        self._refresh_preview()

    def _compat_changed(self):
        sid = self._current_style_id()
        enabled = not self.compat_var.get() or sid == "custom"
        for key, widget in self.param_entries.items():
            widget.configure(state=("readonly" if isinstance(widget, ttk.Combobox) and key != "font" else "normal") if enabled else "disabled")
        for widget in self.custom_controls + self.color_buttons:
            widget.configure(state="normal" if enabled else "disabled")
        self._refresh_preview()

    def _apply_payload(self, payload, include_data=True):
        for key, value in payload.get("params", {}).items():
            if key in self.param_vars:
                self.param_vars[key].set(str(value))
        params = payload.get("params", {})
        if "edge" in params and "edge_width" not in params:
            self.param_vars["edge_width"].set("0.5" if params["edge"] == "黑色细线" else "0")
        for key, variable in self.bool_vars.items():
            variable.set(payload.get("display", {}).get(key, key != "transparent") is True)
        self.compat_var.set(payload.get("compatibility", False) is True)
        self.show_cbar_var.set(payload.get("show_cbar", True) is True)
        self.show_cbar_labels_var.set(payload.get("show_cbar_labels", True) is True)
        self.cbar_override = copy.deepcopy(payload.get("cbar_override"))
        if self.cbar_override is not None:
            colorbar_config(self.cbar_override)
        self.custom_colors = self._sanitize_colors(payload.get("custom_colors"))
        if include_data:
            self.data = copy.deepcopy(payload.get("data", {}))
            self.table.set_data(self.data)
            if "output_format" in payload:
                self.fmt_var.set(payload["output_format"])
            if "output_dir" in payload:
                self.out_var.set(payload["output_dir"])

    def _validate_payload(self, payload):
        if not isinstance(payload, dict) or payload.get("mode_id") not in STYLES:
            raise ValueError("未知项目 / 预设样式")
        if not isinstance(payload.get("params", {}), dict) or not isinstance(payload.get("display", {}), dict):
            raise ValueError("项目参数必须是字典")
        if not isinstance(payload.get("data", {}), dict):
            raise ValueError("项目数据必须是字典")
        # Validate structure without coercing annotation text or discarding unknown symbols.
        for key, value in payload.get("data", {}).items():
            if not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError("项目数据必须是元素对应文本或数字")
        if payload.get("output_format", "svg") not in FORMATS:
            raise ValueError("输出格式无效")
        if payload.get("cbar_override") is not None:
            colorbar_config(payload["cbar_override"])
        json.dumps(payload, allow_nan=False)

    def _document_snapshot(self):
        current = copy.deepcopy(self._current_preset_payload())
        states = copy.deepcopy(self._style_states)
        states[current["mode_id"]] = current
        self._stash_excel_group()
        return {"schema": 1, "current": current, "styles": states,
                "excel_collection": self.excel_collection.snapshot(), "excel_attached": self._excel_attached}

    def _restore_document(self, snapshot):
        collection = DatasetCollection.from_snapshot(snapshot["excel_collection"]) if "excel_collection" in snapshot else DatasetCollection()
        attached = snapshot.get("excel_attached", False)
        if type(attached) is not bool or (attached and collection.active_dataset_id is None):
            raise ValueError("Excel数据组关联无效")
        payload = snapshot["current"]
        for item in [payload, *snapshot["styles"].values()]:
            self._validate_payload(item)
        self._restoring = True
        try:
            self.excel_collection = collection
            self._excel_attached = attached
            self._style_states = copy.deepcopy(snapshot["styles"])
            self._style_states[payload["mode_id"]] = copy.deepcopy(payload)
            self._active_style = None
            self.mode_combo.current(list(STYLES).index(payload["mode_id"]))
            self._on_style_change()
            self._apply_payload(payload)
            self._cbar_refresh_tree()
        finally:
            self._restoring = False
        self._refresh_preview()

    def _undo(self):
        self._commit_table_edit()
        self._history.record(self._document_snapshot())
        self._restore_document(self._history.step(-1))
        self.status_var.set("已撤销（已导出的文件不受影响）")
        return "break"

    def _redo(self):
        self._commit_table_edit()
        self._history.record(self._document_snapshot())
        self._restore_document(self._history.step(1))
        self.status_var.set("已重做")
        return "break"

    def _save_draft(self):
        self._draft_job = None
        if os.environ.get("PTT_SMOKE") == "1" or self._recovery_pending:
            return
        if self._document_snapshot() == self._saved_snapshot:
            self._remove_draft()
            return
        try:
            write_document(self.user_dir / "draft.ptproj", self._document_snapshot())
        except (OSError, ValueError, TypeError) as exc:
            self.status_var.set(f"自动草稿保存失败：{exc}")

    def _remove_draft(self):
        try:
            (self.user_dir / "draft.ptproj").unlink(missing_ok=True)
        except OSError:
            pass

    def _offer_recovery(self):
        draft = self.user_dir / "draft.ptproj"
        try:
            if draft.exists():
                snapshot = read_document(draft)
                if messagebox.askyesno("恢复工作", "发现上次未完成的工作草稿，是否恢复？", parent=self):
                    self._restore_document(snapshot)
                else:
                    self._remove_draft()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.status_var.set(f"草稿无法恢复：{exc}")
        finally:
            self._recovery_pending = False

    def _confirm_discard(self):
        if os.environ.get("PTT_SMOKE") == "1" or self._document_snapshot() == self._saved_snapshot:
            return True
        result = messagebox.askyesnocancel("未保存的工作", "是否先保存当前项目？", parent=self)
        return self._save_project() if result is True else result is False

    def _save_project(self, save_as=False, path=None):
        self._commit_table_edit()
        path = path or (None if save_as else self.project_path)
        path = path or filedialog.asksaveasfilename(title="保存绘图项目", defaultextension=".ptproj",
                                                   filetypes=[("绘图项目", "*.ptproj")])
        if not path:
            return False
        try:
            snapshot = self._document_snapshot()
            write_document(path, snapshot)
            self.project_path, self._saved_snapshot = str(path), snapshot
            self._remove_draft()
            self.status_var.set(f"项目已保存：{path}")
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc))
            return False

    def _open_project(self, path=None):
        if not self._confirm_discard():
            return False
        path = path or filedialog.askopenfilename(title="打开绘图项目", filetypes=[("绘图项目", "*.ptproj")])
        if not path:
            return False
        before = self._document_snapshot()
        try:
            snapshot = read_document(path)
            self._restore_document(snapshot)
            self.project_path = str(path)
            self._saved_snapshot = self._document_snapshot()
            self._history = History(self._saved_snapshot)
            self._remove_draft()
            self.status_var.set(f"项目已打开：{path}")
            return True
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._restore_document(before)
            messagebox.showerror("打开失败", str(exc))
            return False

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    def _table_changed(self):
        """表格编辑后：同步统一数据源并刷新预览。"""
        # 旧预设中的未知符号不能因编辑其他元素而被静默删除。
        unknown = {s: v for s, v in self.data.items() if s not in SYMBOLS}
        self.data = {**unknown, **self.table.get_data()}
        self._refresh_preview()

    def _clear_data(self):
        self.data = {}
        self.table.clear()
        self._refresh_preview()

    def _load_demo(self):
        self._stash_excel_group()
        self._excel_attached = False
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
            filetypes=[("数据文件", "*.xlsx *.txt *.csv *.tsv *.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                self._import_excel(path)
                return
            with open(path, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
            self._import_text(text, os.path.basename(path))
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _import_excel(self, path):
        from application.excel_import import ExcelImportService, legacy_data
        from ui.import_wizard import ExcelImportDialog
        service = ExcelImportService(path)
        def choose(result):
            candidate = DatasetCollection.from_snapshot(self.excel_collection.snapshot())
            ids = candidate.append(result)
            self._stash_excel_group()
            if self._excel_attached:
                candidate.set_manual_data(self.data, self.excel_collection.active_dataset_id)
            self.excel_collection = candidate
            self._select_excel_group(ids[0])
            self._show_excel_groups()
        ExcelImportDialog(self, service.sheets, service.preview, choose)

    def _stash_excel_group(self):
        if getattr(self, "_excel_attached", False) and not self._restoring:
            self.excel_collection.set_manual_data(self.data)

    def _select_excel_group(self, dataset_id):
        self._commit_table_edit()
        self._stash_excel_group()
        self.excel_collection.select(dataset_id)
        self.data = self.excel_collection.effective_data()
        self.table.set_data(self.data)
        self._excel_attached = True
        self._refresh_preview()

    def _show_excel_groups(self):
        snapshot = self.excel_collection.snapshot()
        datasets = snapshot["datasets"]
        if not datasets:
            self.status_var.set("请先导入Excel数据组。")
            return
        labels = {c["id"]: c["label"] for c in snapshot["conditions"]}
        metrics = {m["id"]: m["name"] for m in snapshot["metrics"]}
        window = tk.Toplevel(self)
        window.title("选择绘图数据组")
        window.geometry("460x300")
        choices = tk.Listbox(window, exportselection=False)
        choices.pack(fill="both", expand=True, padx=10, pady=8)
        for index, data in enumerate(datasets):
            choices.insert("end", f'{metrics[data["metric_id"]]} · {labels[data["condition_id"]]}')
            if data["id"] == snapshot["active_dataset_id"]:
                choices.selection_set(index)
        def apply():
            if choices.curselection():
                self._select_excel_group(datasets[choices.curselection()[0]]["id"])
                window.destroy()
        ttk.Button(window, text="载入当前图", command=apply).pack(pady=8)

    def _import_text(self, text, source="粘贴数据"):
        """文件与粘贴的共同入口；解析失败时保持原数据不变。"""
        data = parse_data(text, preserve_text=True)
        if not data:
            raise ValueError("没有可解析的数据")
        unknown = [s for s in data if s not in SYMBOLS]
        if unknown:
            raise ValueError("未知元素：" + ", ".join(unknown) + "；请修正后再导入")
        self._stash_excel_group()
        self._excel_attached = False
        self.data = data
        self.table.set_data(data)
        self.status_var.set(f"已从 {source} 导入 {len(data)} 条数据")
        self._refresh_preview()
        return data

    def _paste_data(self):
        dialog = tk.Toplevel(self)
        dialog.title("粘贴数据")
        dialog.geometry("560x400")
        dialog.minsize(360, 260)
        dialog.transient(self)
        ttk.Label(dialog, text="粘贴 CSV、JSON、Python 字典或“元素 数值”文本；导入将替换当前数据。",
                  wraplength=500, padding=8).pack(fill="x")
        text = tk.Text(dialog, wrap="word", undo=True, height=10)
        text.pack(fill="both", expand=True, padx=8)
        error = tk.StringVar()
        ttk.Label(dialog, textvariable=error, foreground="#b42318", wraplength=500).pack(fill="x", padx=8)
        def apply():
            try:
                self._import_text(text.get("1.0", "end"))
            except (ValueError, TypeError) as exc:
                error.set(str(exc))
                return
            dialog.destroy()
        buttons = ttk.Frame(dialog, padding=8)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="导入数据", command=apply).pack(side="right")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=6)
        try:
            text.insert("1.0", self.clipboard_get())
        except tk.TclError:
            pass
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        text.focus_set()
        dialog.grab_set()
        return dialog

    def _commit_table_edit(self):
        if self.table._edit_entry is not None:
            self.table._commit_edit(self.table._edit_item, self.table._edit_entry)

    def _validated_data(self, kind):
        return convert_data(self.data, kind)

    def _auto_range(self):
        self._commit_table_edit()
        try:
            data = self._validated_data("heatmap")
            if not data:
                raise ValueError("请先输入数值数据")
            low, high = min(data.values()), max(data.values())
            if low == high:
                padding = max(abs(low) * .05, .5)
                low, high = low - padding, high + padding
            center = 0.0 if low < 0 < high else low / 2 + high / 2
            self.param_vars["vmin"].set(format(low, ".17g"))
            self.param_vars["vcenter"].set(format(center, ".17g") if low < center < high else "")
            self.param_vars["vmax"].set(format(high, ".17g"))
            self.status_var.set(f"已按 {len(data)} 个数值设置范围：{low:g} ～ {high:g}")
            self._refresh_preview()
            return True
        except ValueError as exc:
            self.status_var.set(f"自动范围失败：{exc}")
            return False

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
        self.data_notebook.select(self.mark_tab)

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
        rgb, _ = colorchooser.askcolor(color=_rgb_to_hex(self.custom_colors[idx]),
                                       title=f"选择第 {idx + 1} 个颜色")
        if rgb:
            self.custom_colors[idx] = tuple(c / 255 for c in rgb)
            self._build_color_row(self.color_frame)
            self.param_vars["cmap"].set("自定义")
            self._refresh_preview()

    def _add_color(self):
        rgb, _ = colorchooser.askcolor(color="#888888", title="添加一个颜色")
        if rgb:
            self.custom_colors.append(tuple(c / 255 for c in rgb))
            self._build_color_row(self.color_frame)
            self.param_vars["cmap"].set("自定义")
            self._refresh_preview()

    def _remove_color(self):
        if len(self.custom_colors) > 2:
            self.custom_colors.pop()
            self._build_color_row(self.color_frame)
            self.param_vars["cmap"].set("自定义")
            self._refresh_preview()
        else:
            messagebox.showinfo("提示", "至少保留 2 个颜色。")

    def _reset_colors(self):
        self.custom_colors = list(DEFAULT_COLORS)
        self._build_color_row(self.color_frame)
        self.param_vars["cmap"].set("自定义")
        self._refresh_preview()

    # ------------------------------------------------------------------
    # 颜色条标注（刻度与标签自定义）
    # ------------------------------------------------------------------
    def _cbar_current_entries(self):
        """当前生效的标注列表（覆盖值优先，否则样式自带，否则空）。"""
        if self.cbar_override is not None:
            return list(self.cbar_override["ticks"]), list(self.cbar_override["labels"])
        cfg = STYLES[self._current_style_id()].get("cbar")
        if cfg:
            return list(cfg["ticks"]), list(cfg["labels"])
        return [], []

    def _cbar_select(self, event=None):
        selection = self.cbar_tree.selection()
        if selection:
            value, label, *_ = self.cbar_tree.item(selection[0], "values")
            self.cbar_value_var.set(value)
            self.cbar_label_var.set(label)

    def _cbar_refresh_tree(self):
        """把当前标注刷新到 Treeview 显示。"""
        ticks, labels = self._cbar_current_entries()
        self.cbar_tree.delete(*self.cbar_tree.get_children())
        visible = self._cbar_visibility(len(ticks))
        for t, l, v in zip(ticks, labels, visible):
            self.cbar_tree.insert("", "end", values=(str(t), str(l), "是" if v else "否"))

    def _cbar_visibility(self, count):
        return list((self.cbar_override or {}).get("visible", [True] * count))

    def _cbar_toggle(self):
        selection = self.cbar_tree.selection()
        if not selection:
            return
        ticks, labels = self._cbar_current_entries()
        visible = self._cbar_visibility(len(ticks))
        index = self.cbar_tree.index(selection[0])
        visible[index] = not visible[index]
        self._cbar_apply(ticks, labels, visible)

    def _cbar_sort(self):
        ticks, labels = self._cbar_current_entries()
        rows = sorted(zip(ticks, labels, self._cbar_visibility(len(ticks))))
        self._cbar_apply([r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows])

    def _cbar_apply(self, ticks, labels, visible=None):
        """写入覆盖并刷新预览。"""
        cfg = STYLES[self._current_style_id()].get("cbar")
        fontsize = cfg["fontsize"] if cfg else 8
        candidate = {"ticks": ticks, "labels": labels, "fontsize": fontsize,
                     "visible": visible if visible is not None else [True] * len(ticks)}
        try:
            colorbar_config(candidate)
        except ValueError as exc:
            self.status_var.set(str(exc))
            return False
        self.cbar_override = candidate
        self._cbar_refresh_tree()
        self._refresh_preview()
        self.status_var.set(f"颜色条标注：{len(ticks)} 个刻度")

    def _cbar_add(self):
        try:
            val = float(self.cbar_value_var.get().strip())
        except ValueError:
            messagebox.showwarning("提示", "刻度值必须是数字。")
            return
        if not math.isfinite(val):
            messagebox.showwarning("提示", "刻度值必须是有限数字。")
            return
        label = self.cbar_label_var.get().strip()
        ticks, labels = self._cbar_current_entries()
        visible = self._cbar_visibility(len(ticks)) + [True]
        ticks.append(val)
        labels.append(label)
        self._cbar_apply(ticks, labels, visible)

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
        if not math.isfinite(val):
            messagebox.showwarning("提示", "刻度值必须是有限数字。")
            return
        label = self.cbar_label_var.get().strip()
        idx = self.cbar_tree.index(sel[0])
        ticks, labels = self._cbar_current_entries()
        ticks[idx] = val
        labels[idx] = label
        self._cbar_apply(ticks, labels, self._cbar_visibility(len(ticks)))

    def _cbar_delete(self):
        sel = self.cbar_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先在列表中选择一行。")
            return
        idx = self.cbar_tree.index(sel[0])
        ticks, labels = self._cbar_current_entries()
        visible = self._cbar_visibility(len(ticks))
        ticks.pop(idx)
        labels.pop(idx)
        visible.pop(idx)
        self._cbar_apply(ticks, labels, visible)

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
            "compatibility": self.compat_var.get(),
            "output_format": self.fmt_var.get(),
            "output_dir": self.out_var.get(),
            "mode_id": self._current_style_id(),
            "params": {k: var.get() for k, var in self.param_vars.items()},
            "display": {k: var.get() for k, var in self.bool_vars.items()},
            "show_cbar_labels": self.show_cbar_labels_var.get(),
            "show_cbar": self.show_cbar_var.get(),
            "cbar_override": self.cbar_override,
            "custom_colors": self.custom_colors,
            "data": self.data,
        }

    def _preset_save(self):
        self._commit_table_edit()
        name = self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先输入预设名。")
            return
        try:
            path = self.presets.save(name, self._current_preset_payload())
        except (ValueError, OSError) as exc:
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
            return
        self._commit_table_edit()
        before = self._document_snapshot()
        try:
            payload = self.presets.load(name)
            payload.setdefault("mode_id", "custom")
            self._validate_payload(payload)
            snapshot = {"schema": 1, "current": payload,
                        "styles": copy.deepcopy(self._style_states),
                        "excel_collection": before["excel_collection"],
                        "excel_attached": False}
            self._restore_document(snapshot)
            self.status_var.set(f"已加载预设 {name}")
        except Exception as exc:
            self._restore_document(before)
            messagebox.showerror("加载失败", str(exc))

    def _preset_delete(self):
        name = self.preset_combo.get() or self.preset_name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请选择要删除的预设名。")
            return
        if messagebox.askyesno("删除预设", f"确定删除预设「{name}」吗？"):
            try:
                self.presets.delete(name)
            except (ValueError, OSError) as exc:
                messagebox.showerror("删除失败", str(exc))
                return
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
        return self._validated_data(self._current_work_style().get("kind"))

    def _cancel_refresh(self):
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

    def _edge_preset_changed(self, *args):
        if self._restoring:
            return
        self.param_vars["edge_width"].set("0.5" if self.param_vars["edge"].get() == "黑色细线" else "0")
        self.param_vars["edge_color"].set("black")

    def _record_document_change(self, *args):
        if self._restoring or self._history is None:
            return
        self._history.record(self._document_snapshot())
        if self._draft_job is not None:
            self.after_cancel(self._draft_job)
        self._draft_job = self.after(800, self._save_draft)

    def _refresh_preview(self, *args):
        """合并连续输入；同步调用方使用 _refresh_preview_now。"""
        self._cancel_refresh()
        if self._restoring:
            return
        self._record_document_change()
        if self._job_mode in ("export", "batch", "cmap"):
            self._pending_preview = True
            return
        # Immediately invalidate an older preview, even during the debounce window.
        if self._job_mode == "preview":
            self._worker.invalidate()
            self.preview.set_stale(True)
        self._refresh_job = self.after(300, self._refresh_preview_async)

    def _refresh_preview_now(self):
        """同步验证并更新预览，成功返回 True，失败保留旧图并明确标记。"""
        self._cancel_refresh()
        self._cancel_job(quiet=True)
        style_id = self._current_style_id()
        try:
            if style_id == "cmap_preview":
                # 本模式无周期表预览：显示占位说明，避免残留旧预览误导
                import matplotlib.pyplot as plt
                empty_fig = plt.figure(figsize=(8, 3))
                ax = empty_fig.add_subplot(111)
                ax.text(0.5, 0.5, "颜色映射预览模式：点击「生成图片」输出全部色图预览",
                        ha="center", va="center", fontsize=12)
                ax.axis("off")
                self.preview.show(empty_fig, {})
                self._preview_error = None
                self.preview.set_stale(False)
                return True
            style = self._current_work_style()
            title = (self.param_vars["title"].get().strip()
                     if style.get("customizable") else "")
            fig = render_table(style, self._preview_data(), title=title or None,
                               show_cbar=self.show_cbar_var.get(),
                               figsize=style.get("figsize", (10, 5)))
            try:
                self.preview.show(fig, self._build_hit_map(), tight=style.get("bbox_tight", True))
            except Exception:
                import matplotlib.pyplot as plt
                plt.close(fig)
                raise
            if self._preview_error is not None:
                self.status_var.set("预览已更新")
            warnings = range_warnings(style, self._preview_data())
            if warnings:
                self.status_var.set("注意：" + "；".join(warnings))
            self._preview_error = None
            self.preview.set_stale(False)
            return True
        except Exception as exc:
            self._preview_error = str(exc)
            self.preview.set_stale(True)
            self.status_var.set(f"预览失败（保留旧预览）：{exc}")
            return False

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def _render_request(self, mode):
        style = self._current_work_style()
        data = self._validated_data(style.get("kind"))
        if mode != "preview" and not data:
            raise ValueError("请先输入数据")
        return {"mode": mode, "style": style, "data": data,
                "title": self.param_vars["title"].get() if style.get("customizable") else "",
                "show_cbar": self.show_cbar_var.get(), "hit_map": self._build_hit_map(),
                "format": self.fmt_var.get()}

    def _refresh_preview_async(self):
        self._refresh_job = None
        if self._current_style_id() == "cmap_preview":
            self._refresh_preview_now()
            return
        try:
            self._start_job(self._render_request("preview"))
            self.preview.set_stale(True)
        except Exception as exc:
            self._preview_error = str(exc)
            self.preview.set_stale(True)
            self.status_var.set(f"预览失败：{exc}")

    def _start_job(self, request):
        self.diagnostics.record("INFO", "render.requested", "提交绘图任务", module="render")
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._cancel_refresh()
        if request["mode"] in ("export", "batch"):
            self._pending_preview = True
            self.preview.set_stale(True)
        self._job_mode = request["mode"]
        self._job_request = copy.deepcopy(request)
        self._job_output = self.out_var.get().strip() or self.out_dir
        try:
            self._worker.start(request)
        except Exception:
            self._cancel_job(quiet=True)
            raise
        self.progress.configure(value=0)
        self.status_var.set("正在绘图…" if self._job_mode == "preview" else "正在导出，可取消…")
        self._poll_job = self.after(60, self._poll_render_job)

    def _cancel_job(self, quiet=False):
        pending = self._pending_preview
        self._pending_preview = False
        self._cancel_refresh()
        if self._poll_job is not None:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        active = self._worker.active
        self._worker.cancel()
        self._job_mode = None
        if active and not quiet:
            self.status_var.set("任务已取消；已保留上次预览")
        if pending and not quiet:
            self._refresh_preview()

    def _poll_render_job(self):
        self._poll_job = None
        message = self._worker.poll()
        if message is None or message[0] in ("progress", "obsolete"):
            if message and message[0] == "progress":
                self.progress.configure(value=100 * message[1] / message[2])
            if message and message[0] == "obsolete" and not self._worker.active:
                self._job_mode = None
                return
            self._poll_job = self.after(60, self._poll_render_job)
            return
        mode = self._job_mode
        try:
            if message[0] == "error":
                raise ValueError(message[1])
            result = message[1]
            if mode == "preview":
                self.preview.show_packet(result["png"], result["hits"])
                self.preview.set_stale(False)
                self._preview_error = None
                warnings = range_warnings(self._job_request["style"], self._job_request["data"])
                self.status_var.set("注意：" + "；".join(warnings) if warnings else "预览已更新 · 滚轮缩放 / 右键平移")
            else:
                import shutil
                published = []
                try:
                    for source, name in result["files"]:
                        destination = auto_name(self._job_output, name, os.path.splitext(source)[1])
                        published.append(destination)
                        shutil.copyfile(source, destination)
                except Exception:
                    for path in published:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                    raise
                self.last_output = published[-1] if published else self._job_output
                self._preview_error = None
                self.status_var.set(f"已生成 {len(published)} 个文件：{self.last_output}")
            self.progress.configure(value=100)
        except Exception as exc:
            self._preview_error = str(exc)
            self.preview.set_stale(True)
            self.status_var.set(f"任务失败：{exc}")
        finally:
            self._job_mode = None
        if self._pending_preview:
            self._pending_preview = False
            self._refresh_preview()

    def generate_async(self):
        self._commit_table_edit()
        try:
            if self._current_style_id() == "cmap_preview":
                self._start_job({"mode": "cmap"})
            else:
                request = self._render_request("export")
                warnings = range_warnings(request["style"], request["data"])
                if warnings and not messagebox.askyesno("色标范围提示", "；".join(warnings) + "\n仍按当前固定色标导出？", parent=self):
                    return
                self._start_job(request)
        except Exception as exc:
            self.status_var.set(f"导出失败：{exc}")
            messagebox.showerror("导出失败", str(exc))

    def _batch_export(self, paths=None):
        self._commit_table_edit()
        paths = paths or filedialog.askopenfilenames(title="选择多组数据（使用当前固定色标）",
                                                     filetypes=[("数据", "*.txt *.csv *.tsv *.json")])
        if not paths:
            return
        try:
            if self._current_style_id() == "cmap_preview":
                raise ValueError("请先选择周期表绘图样式")
            request = self._render_request("preview")
            request["mode"] = "batch"
            items = []
            for path in paths:
                with open(path, encoding="utf-8-sig") as stream:
                    data = convert_data(parse_data(stream.read(), preserve_text=True), request["style"]["kind"])
                if not data:
                    raise ValueError(f"{path} 没有有效数据")
                items.append((os.path.splitext(os.path.basename(path))[0], data))
            warnings = [f"{name}: {'；'.join(range_warnings(request['style'], data))}"
                        for name, data in items if range_warnings(request["style"], data)]
            if warnings and not messagebox.askyesno("共用固定色标", "\n".join(warnings) + "\n仍按当前色标批量导出？", parent=self):
                return
            request["items"] = items
            self._start_job(request)
        except Exception as exc:
            messagebox.showerror("批量导出失败", str(exc))

    def generate(self):
        self._commit_table_edit()
        self._cancel_refresh()
        style_id = self._current_style_id()
        style = STYLES[style_id]
        out_dir = self.out_var.get().strip() or self.out_dir
        fig = None

        try:
            if style_id == "cmap_preview":
                self._generate_cmap_preview(out_dir)
                return

            if not self.data:
                self._refresh_preview_now()
                messagebox.showwarning("提示", "请先输入数据：表格编辑、图形化标注、导入文件或载入示例。")
                return

            # 导出前同步刷新：提交后的当前数据必须与看到的图完全一致。
            if not self._refresh_preview_now():
                raise ValueError(self._preview_error)
            work_style = self._current_work_style()
            fmt = self.fmt_var.get()
            fig = self.preview.fig
            path = save_figure(
                fig, out_dir, "periodic_table", fmt,
                bbox_inches="tight" if work_style.get("bbox_tight", True) else None,
                dpi=work_style.get("dpi", 100),
                transparent=work_style.get("transparent", False))
            self.last_output = path
            self.status_var.set(f"已生成：{path}")

        except Exception as exc:
            self.status_var.set(f"导出失败：{exc}")
            messagebox.showerror("生成失败", str(exc))
        finally:
            if fig is not None:
                import matplotlib.pyplot as plt
                plt.close(fig)

    def _generate_cmap_preview(self, out_dir):
        paths = render_cmap_preview(out_dir)
        self.last_output = out_dir
        self.status_var.set(f"已生成 {len(paths)} 张颜色映射预览图 → {out_dir}")


    def _apply_custom_params(self, style):
        import copy
        import math
        work = copy.deepcopy(style)
        work["kind"] = KIND_CHOICES.get(self.param_vars["kind"].get(), "heatmap")
        cmap_name = self.param_vars["cmap"].get().strip()
        try:
            vmin = float(self.param_vars["vmin"].get()) if work["kind"] == "heatmap" else 0.0
            vmax = float(self.param_vars["vmax"].get()) if work["kind"] == "heatmap" else 1.0
            center_text = self.param_vars["vcenter"].get().strip() if work["kind"] == "heatmap" else ""
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
        work["font"] = self.param_vars["font"].get().strip() or "Arial"
        edge = EDGE_CHOICES.get(self.param_vars["edge"].get(), "none")
        work["edge"] = None if edge == "none" else (0.5, "black")
        work["empty"] = EMPTY_CHOICES.get(self.param_vars["empty"].get(),
                                          "#f0f0f0")
        work["dpi"] = DPI_CHOICES.get(self.param_vars["dpi"].get(), 100)
        fs = self.param_vars["figsize"].get().strip().lower().replace("×", "x")
        try:
            fw, fh = (float(value.strip()) for value in fs.split("x"))
        except (ValueError, TypeError) as exc:
            raise ValueError("画幅尺寸应为 宽x高（英寸），例如 10x5") from exc
        if not (math.isfinite(fw) and math.isfinite(fh) and 2 <= fw <= 40 and 1 <= fh <= 40):
            raise ValueError("画幅宽度须为 2～40 英寸，高度须为 1～40 英寸")
        work["figsize"] = (fw, fh)
        work["bbox_tight"] = False
        for key, var in self.bool_vars.items():
            work[key] = var.get()
        for key in ("symbol_fs", "number_fs", "value_fs"):
            try:
                value = float(self.param_vars[key].get())
            except ValueError as exc:
                raise ValueError(f"{key} 必须是正数字号") from exc
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} 必须是有限正数")
            work[key] = value
        from matplotlib.colors import is_color_like
        for key, low, high in (("edge_width", 0, 20), ("value_dx", -2, 2),
                               ("value_dy", -2, 2), ("label_wrap", 0, 200),
                               ("cbar_fraction", .005, .5), ("cbar_pad", 0, .5),
                               ("cbar_shrink", .05, 1)):
            try:
                value = float(self.param_vars[key].get())
            except ValueError as exc:
                raise ValueError(f"{key} 必须是数字") from exc
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} 应在 {low}～{high} 之间")
            work[key] = value
        if not work["label_wrap"].is_integer():
            raise ValueError("每行字符数必须为整数")
        work["label_wrap"] = int(work["label_wrap"])
        color = self.param_vars["edge_color"].get().strip()
        if not is_color_like(color):
            raise ValueError("边框颜色无效")
        if work["edge_width"] > 0:
            work["edge"] = (work["edge_width"], color)
        work["unit"] = self.param_vars["unit"].get()
        nodes = self.param_vars["color_nodes"].get().strip()
        if nodes:
            try:
                pairs = sorted((float(row.split(":", 1)[0]), row.split(":", 1)[1].strip())
                               for row in nodes.replace("；", ";").split(";") if row.strip())
            except (ValueError, IndexError) as exc:
                raise ValueError("颜色节点格式：0:#0000ff;0.5:#ffffff;1:#ff0000") from exc
            if (len(pairs) < 2 or pairs[0][0] != 0 or pairs[-1][0] != 1 or
                    len({p for p, c in pairs}) != len(pairs) or
                    any(not math.isfinite(p) or not 0 <= p <= 1 or not is_color_like(c) for p, c in pairs)):
                raise ValueError("颜色节点须从 0 到 1，位置不重复，颜色有效")
            work["cmap"] = ("custom", pairs)
        work["cbar_orientation"] = self.param_vars["cbar_orientation"].get()
        location = self.param_vars["cbar_location"].get()
        work["cbar_location"] = ("bottom" if work["cbar_orientation"] == "horizontal" else "right") if location == "auto" else location
        work["cbar_label"] = self.param_vars["cbar_label"].get()
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
    # 打包验收可指定独立目录，实际经过应用导入、预览及三种格式导出。
    if os.environ.get("PTT_SMOKE") == "1":
        app.withdraw()
        smoke_steps = iter(["preview", *FORMATS])
        def finish_smoke(error=None):
            _smoke_log("smoke:failed:" + repr(error) if error else "smoke:passed")
            app.destroy()
        def wait_smoke(step):
            try:
                if app._job_mode is not None or app._worker.active:
                    app.after(100, lambda: wait_smoke(step))
                    return
                if app._preview_error:
                    raise RuntimeError(app._preview_error)
                if step == "preview":
                    if app.preview._source is None:
                        raise RuntimeError("后台预览未生成")
                    _smoke_log("preview:passed")
                else:
                    if not app.last_output or not os.path.isfile(app.last_output):
                        raise RuntimeError("后台导出未生成文件")
                    if not app.last_output.endswith("." + step):
                        raise RuntimeError("后台导出格式不匹配")
                    _smoke_log("export:" + step)
                next_smoke()
            except Exception as exc:
                finish_smoke(exc)
        def next_smoke():
            step = next(smoke_steps, None)
            if step is None:
                finish_smoke()
                return
            try:
                app._cancel_refresh()
                if step == "preview":
                    app._refresh_preview_async()
                else:
                    app.last_output = None
                    app.fmt_var.set(step)
                    app.generate_async()
                app.after(100, lambda: wait_smoke(step))
            except Exception as exc:
                finish_smoke(exc)
        def smoke():
            try:
                destination = os.environ.get("PTT_SMOKE_EXPORT_DIR")
                if destination:
                    def fail(title, detail, **kwargs):
                        raise RuntimeError(f"{title}: {detail}")
                    messagebox.showerror = fail
                    messagebox.askyesno = lambda *args, **kwargs: True
                    app._cancel_job(quiet=True)
                    app._import_text("H,0\nC,-1\nFe,1", "打包验收")
                    app.out_var.set(destination)
                    next_smoke()
                else:
                    finish_smoke()
            except Exception as exc:
                finish_smoke(exc)
        app.after(1500, smoke)
    _smoke_log("before_mainloop")
    app.mainloop()
    _smoke_log("after_mainloop")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
