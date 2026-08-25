# -*- coding: utf-8 -*-
"""GUI 主题模块测试：调色板、主题应用与缩放。"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pytest

try:
    import ui_theme
except Exception:
    ui_theme = None


@pytest.mark.skipif(ui_theme is None, reason="主题模块不可用")
def test_get_colors_light_and_dark():
    light = ui_theme.get_colors("light")
    dark = ui_theme.get_colors("dark")
    assert light.BG != dark.BG
    assert light.TEXT != dark.TEXT
    # 未知主题回退浅色
    fallback = ui_theme.get_colors("unknown")
    assert fallback.BG == light.BG


@pytest.mark.skipif(ui_theme is None, reason="主题模块不可用")
def test_palette_required_tokens():
    required = ("BG", "SURFACE", "PRIMARY", "TEXT", "TEXT_MUTED",
                "TEXT_HINT", "BORDER", "ROW_ALT", "HEADER_BG", "HEADER_FG",
                "SELECT_BG", "SELECT_FG")
    for theme in ("light", "dark"):
        colors = ui_theme.get_colors(theme)
        for token in required:
            assert token in colors, f"{theme} 缺少 token {token}"
            assert isinstance(colors[token], str)


def test_apply_theme_configures_styles(app):
    """主题应用不抛异常，且 Treeview 行高随缩放变化。"""
    from tkinter import ttk
    ui_theme.apply_theme(app, scale=1.25, theme="light")
    style = ttk.Style(app)
    assert style.theme_use() == "clam"
    rowheight = int(style.lookup("Treeview", "rowheight"))
    assert rowheight >= 20
    # 缩放 1.25 对应的 Treeview 行高应为 30
    assert rowheight == round(ui_theme.TREE_ROW_HEIGHT_BASE * 1.25)


def test_gui_theme_switch(app):
    """GUI 主题切换：深色/浅色往返。"""
    original = app.theme_mode
    try:
        app.theme_var.set("dark")
        app._on_theme_change()
        assert app.theme_mode == "dark"
        assert app.colors.BG == ui_theme.get_colors("dark").BG
        app.theme_var.set("light")
        app._on_theme_change()
        assert app.theme_mode == "light"
        assert app.colors.BG == ui_theme.get_colors("light").BG
    finally:
        app.theme_var.set(original)
        app._on_theme_change()
