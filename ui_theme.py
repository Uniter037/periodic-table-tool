# -*- coding: utf-8 -*-
"""GUI 主题与视觉 token。

集中管理颜色、字体、间距，并通过 ttk.Style 应用全局样式。
仅使用 Tkinter 标准库，不新增第三方依赖。

用法：
    import ui_theme
    colors = ui_theme.get_colors("light")
    ui_theme.apply_theme(root, scale=1.0, theme="light")
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---------------------------------------------------------------------------
# 调色板
# ---------------------------------------------------------------------------

_LIGHT_PALETTE = {
    "BG": "#f5f6fa",              # 窗口/画布背景
    "SURFACE": "#ffffff",         # 卡片/表格背景
    "SURFACE_ALT": "#eef2f7",     # 次要背景（状态栏/表头）
    "PRIMARY": "#0b6bcb",         # 主色（强调、选中、焦点）
    "PRIMARY_DARK": "#084f99",    # 主色加深（标题/按压）
    "PRIMARY_SOFT": "#e8f1fb",    # 主色浅底（选中行/提示）
    "TEXT": "#1f2933",            # 主文本
    "TEXT_MUTED": "#6b7280",      # 次要文本
    "TEXT_HINT": "#8a94a6",       # 提示文本
    "TEXT_ON_PRIMARY": "#ffffff", # 主色上的文字
    "BORDER": "#e5e7eb",          # 边框/分隔线
    "ROW_ALT": "#f8fafc",         # 表格斑马纹
    "HEADER_BG": "#eef2f7",       # 表头背景
    "HEADER_FG": "#334155",       # 表头文字
    "SELECT_BG": "#dbeafe",       # 选中行背景
    "SELECT_FG": "#1e3a5f",       # 选中行文字
    "SUCCESS": "#16a34a",
    "WARNING": "#d97706",
    "ERROR": "#dc2626",
    "PLACEHOLDER_BG": "#fafbfc",
    "PLACEHOLDER_FG": "#8a94a6",
}

_DARK_PALETTE = {
    "BG": "#111827",
    "SURFACE": "#1f2937",
    "SURFACE_ALT": "#273244",
    "PRIMARY": "#3b82f6",
    "PRIMARY_DARK": "#60a5fa",
    "PRIMARY_SOFT": "#1e3a5f",
    "TEXT": "#e5e7eb",
    "TEXT_MUTED": "#9ca3af",
    "TEXT_HINT": "#9ca3af",
    "TEXT_ON_PRIMARY": "#ffffff",
    "BORDER": "#374151",
    "ROW_ALT": "#1f2937",
    "HEADER_BG": "#273244",
    "HEADER_FG": "#e5e7eb",
    "SELECT_BG": "#1e3a5f",
    "SELECT_FG": "#e5e7eb",
    "SUCCESS": "#22c55e",
    "WARNING": "#f59e0b",
    "ERROR": "#ef4444",
    "PLACEHOLDER_BG": "#1f2937",
    "PLACEHOLDER_FG": "#9ca3af",
}

THEME_PALETTES = {"light": _LIGHT_PALETTE, "dark": _DARK_PALETTE}


class Palette:
    """属性式调色板：palette.BG 等价于 palette["BG"]。"""

    def __init__(self, values: dict):
        self._values = dict(values)

    def __getattr__(self, name: str) -> str:
        try:
            return self._values[name]
        except KeyError as exc:
            raise AttributeError(f"未知颜色 token: {name}") from exc

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __contains__(self, key: str) -> bool:
        return key in self._values


def get_colors(theme: str = "light") -> Palette:
    """返回指定主题的调色板对象；未知主题回退浅色。"""
    return Palette(THEME_PALETTES.get(theme, _LIGHT_PALETTE))


# ---------------------------------------------------------------------------
# 字体
# ---------------------------------------------------------------------------

# 中文/西文混合场景优先使用可读性较好的字体族，按平台顺序尝试。
FONT_FAMILIES = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Segoe UI",
    "DejaVu Sans",
)

FONT_BASE_SIZE = 10
FONT_TITLE_SIZE = 12
FONT_SMALL_SIZE = 8


def pick_font_family(root) -> str:
    """选择第一个系统可用的字体族（公开接口）。"""
    try:
        families = set(tkfont.families(root))
    except Exception:
        return "TkDefaultFont"
    for family in FONT_FAMILIES:
        if family in families:
            return family
    # 回退：Tk 默认字体名（保证不抛异常）
    return tkfont.nametofont("TkDefaultFont").cget("family")


# ---------------------------------------------------------------------------
# 间距与尺寸
# ---------------------------------------------------------------------------

SPACING = {
    "xs": 2,
    "sm": 4,
    "md": 8,
    "lg": 12,
    "xl": 16,
}

MIN_BUTTON_WIDTH = 64
MIN_INPUT_HEIGHT = 28
TREE_ROW_HEIGHT_BASE = 24
TREE_ROW_HEIGHT_MIN = 20


# ---------------------------------------------------------------------------
# 样式应用
# ---------------------------------------------------------------------------

def apply_theme(root, scale: float = 1.0, theme: str = "light",
                font=None):
    """在指定根窗口上应用统一主题样式。

    :param root:  tk.Tk / tk.Toplevel 根窗口
    :param scale: 全局缩放系数（0.8~1.5），用于计算字号与行高
    :param theme: 主题名：'light' 或 'dark'
    :param font:  可选 tkfont.Font 对象；缺省时按 scale 创建
    :returns:     tkfont.Font 对象，供 main.py 复用
    """
    colors = get_colors(theme)
    family = pick_font_family(root)
    font_size = max(8, round(FONT_BASE_SIZE * scale))

    if font is None:
        font = tkfont.Font(root=root, family=family, size=font_size)
    else:
        font.configure(family=family, size=font_size)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    # ---- 基础字体 ----
    for s in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton",
              "TCombobox", "TEntry", "TNotebook", "TNotebook.Tab",
              "TLabelframe", "TLabelframe.Label", "TScrollbar",
              "Horizontal.TProgressbar", "Vertical.TProgressbar"):
        try:
            style.configure(s, font=font)
        except tk.TclError:
            pass

    # ---- 颜色/背景 ----
    try:
        style.configure("TFrame", background=colors.SURFACE)
    except tk.TclError:
        pass

    try:
        style.configure("App.TFrame", background=colors.BG)
    except tk.TclError:
        pass

    try:
        style.configure("TLabel", background=colors.SURFACE,
                        foreground=colors.TEXT)
    except tk.TclError:
        pass

    try:
        style.configure("App.TLabel", background=colors.BG,
                        foreground=colors.TEXT_MUTED)
    except tk.TclError:
        pass

    try:
        style.configure("Hint.TLabel", background=colors.SURFACE,
                        foreground=colors.TEXT_HINT)
    except tk.TclError:
        pass

    try:
        style.configure("Card.TLabelframe", background=colors.SURFACE,
                        bordercolor=colors.BORDER, borderwidth=1,
                        relief="solid")
    except tk.TclError:
        pass

    try:
        style.configure("Card.TLabelframe.Label", background=colors.SURFACE,
                        foreground=colors.PRIMARY_DARK, font=font)
    except tk.TclError:
        pass

    # ---- 按钮 ----
    try:
        style.configure("TButton", background=colors.SURFACE,
                        foreground=colors.TEXT,
                        bordercolor=colors.BORDER, borderwidth=1,
                        focusthickness=1, focuscolor=colors.PRIMARY,
                        padding=(10, 5))
        style.map("TButton",
                  background=[("pressed", colors.PRIMARY_SOFT),
                              ("active", colors.PRIMARY_SOFT)],
                  foreground=[("disabled", colors.TEXT_HINT)],
                  bordercolor=[("focus", colors.PRIMARY),
                               ("active", colors.PRIMARY)])
    except tk.TclError:
        pass

    try:
        style.configure("Accent.TButton", background=colors.PRIMARY,
                        foreground=colors.TEXT_ON_PRIMARY,
                        bordercolor=colors.PRIMARY, borderwidth=1,
                        focusthickness=1, focuscolor=colors.PRIMARY_DARK,
                        padding=(10, 5))
        style.map("Accent.TButton",
                  background=[("pressed", colors.PRIMARY_DARK),
                              ("active", colors.PRIMARY_DARK)],
                  foreground=[("disabled", colors.TEXT_ON_PRIMARY)])
    except tk.TclError:
        pass

    # ---- 输入与下拉 ----
    try:
        style.configure("TEntry", fieldbackground=colors.SURFACE,
                        foreground=colors.TEXT,
                        bordercolor=colors.BORDER, borderwidth=1,
                        insertcolor=colors.TEXT,
                        padding=3)
        style.map("TEntry",
                  bordercolor=[("focus", colors.PRIMARY)],
                  fieldbackground=[("focus", colors.SURFACE)])
    except tk.TclError:
        pass

    try:
        style.configure("TCombobox", fieldbackground=colors.SURFACE,
                        background=colors.SURFACE,
                        foreground=colors.TEXT,
                        bordercolor=colors.BORDER, borderwidth=1,
                        padding=3)
        style.map("TCombobox",
                  bordercolor=[("focus", colors.PRIMARY)],
                  fieldbackground=[("readonly", colors.SURFACE)])
    except tk.TclError:
        pass

    # ---- 标签页 ----
    try:
        style.configure("TNotebook", background=colors.SURFACE,
                        borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background=colors.SURFACE_ALT,
                        foreground=colors.TEXT_MUTED,
                        padding=(12, 6), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", colors.SURFACE)],
                  foreground=[("selected", colors.PRIMARY)],
                  expand=[("selected", (1, 1, 1, 0))])
    except tk.TclError:
        pass

    # ---- 表格 ----
    rowheight = max(TREE_ROW_HEIGHT_MIN, round(TREE_ROW_HEIGHT_BASE * scale))
    try:
        style.configure("Treeview", background=colors.SURFACE,
                        fieldbackground=colors.SURFACE,
                        foreground=colors.TEXT,
                        bordercolor=colors.BORDER,
                        rowheight=rowheight)
        style.configure("Treeview.Heading", background=colors.HEADER_BG,
                        foreground=colors.HEADER_FG,
                        bordercolor=colors.BORDER,
                        padding=(6, 4), font=font)
        style.map("Treeview",
                  background=[("selected", colors.SELECT_BG)],
                  foreground=[("selected", colors.SELECT_FG)])
        style.map("Treeview.Heading",
                  background=[("active", colors.SELECT_BG)],
                  foreground=[("active", colors.PRIMARY_DARK)])
    except tk.TclError:
        pass

    # ---- 状态栏 ----
    try:
        style.configure("Status.TFrame", background=colors.SURFACE_ALT)
    except tk.TclError:
        pass

    try:
        style.configure("Status.TLabel", background=colors.SURFACE_ALT,
                        foreground=colors.TEXT)
    except tk.TclError:
        pass

    # ---- 分隔线 ----
    try:
        style.configure("Separator.TSeparator", background=colors.BORDER)
    except tk.TclError:
        pass

    # ---- 框架/标签框的 Label 默认字体 ----
    try:
        style.configure("TLabel", font=font)
    except tk.TclError:
        pass

    return font
