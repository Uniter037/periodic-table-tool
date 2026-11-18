# -*- coding: utf-8 -*-
"""元素周期表绘图工具 - 核心模块。"""
from importlib import import_module

# Importing a data/font/IO utility must not load the historical renderer.
# Keep the public v1 imports available while migration callers transition.
_EXPORTS = {
    **dict.fromkeys(('build_elements', 'xy_bounds_for'), 'ptable'),
    **dict.fromkeys(('STYLES', 'render_table', 'render_cmap_preview'), 'styles'),
    **dict.fromkeys(('parse_data', 'validate_data', 'demo_data', 'known_symbols'), 'dataio'),
    **dict.fromkeys(('auto_name', 'save_figure'), 'saver'),
    'PresetStore': 'presets',
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(f'.{_EXPORTS[name]}', __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "STYLES",
    "build_elements",
    "xy_bounds_for",
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
