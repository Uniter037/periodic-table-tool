# -*- coding: utf-8 -*-
"""字体解析与回退测试。"""
from __future__ import annotations

import os
import sys
import warnings

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from core.fonts import (available_families, contains_cjk,
                        font_family_for_text, resolve_font_family)
from core.styles import STYLES, render_table


def test_resolve_font_family_returns_available():
    """解析后的字体族必须真实可用。"""
    resolved = resolve_font_family("Arial")
    assert resolved in available_families()


def test_resolve_font_family_dejavu_known():
    """DejaVu Sans 是 matplotlib 内置字体，应原样返回。"""
    assert resolve_font_family("DejaVu Sans") == "DejaVu Sans"


def test_contains_cjk():
    assert contains_cjk("低")
    assert contains_cjk("测试 中")
    assert not contains_cjk("Fe")
    assert not contains_cjk("0.0101")
    assert not contains_cjk(None)


def test_font_family_for_text_returns_available_family():
    """无论是否有 CJK 字体，返回的字体族都必须在可用集合中。"""
    base = resolve_font_family("Arial")
    for text in ("Fe", "0.0101", "低", "测试中"):
        family = font_family_for_text(base, text)
        assert family in available_families()


@pytest.mark.skipif(
    "Microsoft YaHei" not in available_families(),
    reason="当前环境没有可用的 CJK 字体，跳过字形告警测试")
def test_render_cjk_labels_without_missing_glyph_warnings():
    """CJK 颜色条标签不应产生 missing glyph / missing font 警告。"""
    style = dict(STYLES["reconstruct_percent"])
    style["cbar"] = {"ticks": [0.005, 0.010, 0.014],
                     "labels": ["低", "中", "高"], "fontsize": 8}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig = render_table(style, {"Ag": 0.0101})
    finally_guard = True
    try:
        warnings_text = "\n".join(str(w.message) for w in caught)
        assert "Glyph" not in warnings_text, warnings_text
        assert "Font family" not in warnings_text, warnings_text
    finally:
        if "fig" in dir():
            plt.close(fig)
