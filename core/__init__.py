# -*- coding: utf-8 -*-
"""元素周期表绘图工具 - 核心模块。"""
from .ptable import build_elements, xy_bounds_for
from .fonts import contains_cjk, font_family_for_text, resolve_font_family
from .styles import STYLES, render_table, render_cmap_preview
from .dataio import parse_data, validate_data, demo_data, known_symbols
from .saver import auto_name, save_figure
from .presets import PresetStore

__all__ = [
    "STYLES",
    "build_elements",
    "xy_bounds_for",
    "contains_cjk",
    "font_family_for_text",
    "resolve_font_family",
    "render_table",
    "render_cmap_preview",
    "parse_data",
    "validate_data",
    "demo_data",
    "known_symbols",
    "auto_name",
    "save_figure",
    "PresetStore",
]
