# -*- coding: utf-8 -*-
"""字体解析与回退。

matplotlib 在 Linux 上常常缺少 Arial/Helvetica；本模块在渲染前把系统
可用字体（含 WSL 挂载的 Windows 字体）注册进 matplotlib，并提供按文本
内容选择字体族的回退逻辑：
- 西文文本：优先使用样式指定字体（Arial/Helvetica），缺失时回退 DejaVu Sans；
- CJK 文本：优先使用微软雅黑，缺失时回退 DejaVu Sans。

这样既保持原脚本的西文字体一致性，又避免 CJK 字形缺失告警。
"""
from __future__ import annotations

import os
import re
import sys

import matplotlib as mpl
from matplotlib import font_manager

# CJK 统一表意文字、日文假名、谚文等区块（用于判断文本是否需要中文字体）
_CJK_RE = re.compile(
    r"[\u2e80-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)

# 希望在 WSL / Windows 原生环境下注册的字体文件
# 只注册中文字体；Arial/Helvetica 若缺失由 resolve_font_family 回退到
# DejaVu Sans（本地字体，渲染更快，且与原脚本在 Linux 上的回退行为一致）。
_WINDOWS_FONT_FILES = (
    "msyh.ttc",
    "msyhbd.ttc",
    "simhei.ttf",
    "simsun.ttc",
    "Deng.ttf",
    "Dengb.ttf",
)

_WESTERN_FALLBACKS = ("DejaVu Sans", "Arial", "Helvetica")
_CJK_FALLBACKS = ("Microsoft YaHei", "SimHei", "SimSun", "DengXian",
                  "DejaVu Sans")

_loaded_paths = set()
_available_family_cache = None


def _windows_font_dirs() -> list:
    """返回可能的 Windows 字体目录列表。"""
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        return [os.path.join(windir, "Fonts")]
    return [f"/mnt/{drive}/Windows/Fonts" for drive in ("c", "d", "e")]


def ensure_fonts_loaded():
    """把可用的 Windows 字体注册到 matplotlib（幂等，失败不抛）。"""
    global _available_family_cache
    for font_dir in _windows_font_dirs():
        if not os.path.isdir(font_dir):
            continue
        for filename in _WINDOWS_FONT_FILES:
            path = os.path.join(font_dir, filename)
            if not os.path.isfile(path) or path in _loaded_paths:
                continue
            try:
                font_manager.fontManager.addfont(path)
                _loaded_paths.add(path)
            except Exception:
                pass
    _available_family_cache = None


def available_families() -> set:
    """返回当前 matplotlib 可用字体族集合。"""
    global _available_family_cache
    if _available_family_cache is not None:
        return _available_family_cache
    ensure_fonts_loaded()
    _available_family_cache = {f.name for f in font_manager.fontManager.ttflist}
    return _available_family_cache


def resolve_font_family(requested: str) -> str:
    """把样式字体名解析为当前环境真实可用的字体族。

    Arial/Helvetica 缺失时回退 DejaVu Sans；仍无可用则返回原请求值。
    """
    if not requested:
        requested = "DejaVu Sans"
    families = available_families()
    if requested in families:
        return requested
    if requested in ("Arial", "Helvetica"):
        for family in _WESTERN_FALLBACKS:
            if family in families:
                return family
    return requested


def contains_cjk(text) -> bool:
    """判断文本是否包含 CJK/日文/谚文等需要中文字体的字符。"""
    return bool(text) and bool(_CJK_RE.search(str(text)))


def font_family_for_text(base_font: str, text) -> str:
    """根据文本内容选择字体族。

    - CJK 文本：优先微软雅黑/中文字体，缺失时回退 DejaVu Sans；
    - 其他文本：使用 base_font。
    """
    if not contains_cjk(text):
        return base_font
    families = available_families()
    for family in _CJK_FALLBACKS:
        if family in families:
            return family
    return base_font
