# -*- coding: utf-8 -*-
"""自定义模式高级参数测试：布局/类型/字体/边框/空值色/格式/figsize/dpi。"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from core import STYLES, render_table

try:
    import main
except Exception:
    main = None


# ---------------------------------------------------------------------------
# core：figsize 与 4f 格式
# ---------------------------------------------------------------------------
def test_render_table_figsize():
    """figsize 参数生效（默认仍为 10x5）。"""
    style = STYLES["custom"]
    fig = render_table(style, {"Fe": 0.7}, figsize=(6, 4))
    try:
        w, h = fig.get_size_inches()
        assert (round(w), round(h)) == (6, 4)
    finally:
        plt.close(fig)
    fig = render_table(style, {"Fe": 0.7})
    try:
        w, h = fig.get_size_inches()
        assert (round(w), round(h)) == (10, 5)
    finally:
        plt.close(fig)


def test_fmt_4f():
    """四位小数格式。"""
    from core.styles import _fmt_value
    assert _fmt_value(0.12345, "4f") == "0.1235"


# ---------------------------------------------------------------------------
# GUI：自定义模式高级参数映射
# ---------------------------------------------------------------------------
def _gui_available():
    return main is not None


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_custom_advanced_params(app):
    """布局/类型/字体/边框/空值色/格式/dpi/图尺寸全部映射到样式。"""
    ids = list(main.STYLES.keys())
    app.mode_combo.current(ids.index("custom"))
    app._on_style_change()

    app.param_vars["layout"].set("镧锕三行块（重构）")
    app.param_vars["kind"].set("标注图（文本）")
    app.param_vars["font"].set("Helvetica")
    app.param_vars["edge"].set("黑色细线")
    app.param_vars["empty"].set("白色")
    app.param_vars["fmt"].set("百分比 2 位")
    app.param_vars["dpi"].set("300")
    app.param_vars["figsize"].set("12x6")
    app.data = {"Fe": "1a", "Cu": "2b"}
    work = app._apply_custom_params(main.STYLES["custom"])
    assert work["layout"] == "reconstructed"
    assert work["kind"] == "labels"
    assert work["font"] == "Helvetica"
    assert work["edge"] == (0.5, "black")
    assert work["empty"] == "white"
    assert work["fmt"] == "percent2"
    assert work["dpi"] == 300
    assert work["figsize"] == (12.0, 6.0)


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_custom_labels_reconstructed_render(app):
    """自定义模式：标注图 + 镧锕三行块布局可正常渲染（预览与命中表）。"""
    ids = list(main.STYLES.keys())
    app.mode_combo.current(ids.index("custom"))
    app._on_style_change()
    app.param_vars["layout"].set("镧锕三行块（重构）")
    app.param_vars["kind"].set("标注图（文本）")
    app.data = {"Fe": "1a", "Cu": "2b"}
    # 清空旧预览状态，防止旧 figure 残留导致误报
    app.preview.fig = None
    app.preview.hit_map = {}
    app._refresh_preview_now()
    assert "预览失败" not in app.status_var.get(), app.status_var.get()
    assert app.preview.fig is not None
    assert app.preview.hit_map, "重构布局命中表不应为空"
    # 重构布局 y 上界约 8.7（classic 布局为 11）
    max_y1 = max(v[3] for v in app.preview.hit_map)
    assert max_y1 < 10


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_custom_nan_and_inf_rejected(app):
    """非法范围和画幅明确拒绝，不能静默改变用户的输出尺寸。"""
    ids = list(main.STYLES.keys())
    app.mode_combo.current(ids.index("custom"))
    app._on_style_change()
    app.data = {"Fe": 0.7}
    # NaN vmin → 抛错
    app.param_vars["vmin"].set("nan")
    with pytest.raises(ValueError):
        app._apply_custom_params(main.STYLES["custom"])
    # inf vmax → 抛错
    app.param_vars["vmin"].set("0")
    app.param_vars["vmax"].set("inf")
    with pytest.raises(ValueError):
        app._apply_custom_params(main.STYLES["custom"])
    # figsize 超上限、非有限数及错误格式均明确拒绝。
    app.param_vars["vmax"].set("1")
    app.param_vars["vcenter"].set("0.5")
    for invalid_size in ("100x100", "nanx5", "abc"):
        app.param_vars["figsize"].set(invalid_size)
        with pytest.raises(ValueError):
            app._apply_custom_params(main.STYLES["custom"])
    app.param_vars["figsize"].set("12x6")
    assert app._apply_custom_params(main.STYLES["custom"])["figsize"] == (12, 6)
    # 范围顺序非法 → 抛错（vmin >= vmax）
    app.param_vars["vmin"].set("5")
    app.param_vars["vmax"].set("1")
    with pytest.raises(ValueError):
        app._apply_custom_params(main.STYLES["custom"])
    # vmin == vcenter == vmax 全相等 → 抛错（TwoSlopeNorm 退化）
    app.param_vars["vmin"].set("1")
    app.param_vars["vcenter"].set("1")
    app.param_vars["vmax"].set("1")
    with pytest.raises(ValueError):
        app._apply_custom_params(main.STYLES["custom"])


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_generate_passes_dpi_and_figsize(app, monkeypatch, tmp_path):
    """generate 将 dpi 与 figsize 传给保存与渲染。"""
    import main as _main
    ids = list(_main.STYLES.keys())
    app.mode_combo.current(ids.index("custom"))
    app._on_style_change()
    app.data = {"Fe": 0.7, "Cu": 0.73}
    app.param_vars["dpi"].set("300")
    app.param_vars["figsize"].set("8x4")
    app.out_var.set(str(tmp_path))
    app.fmt_var.set("png")

    captured = {}
    orig_save = _main.save_figure

    def spy_save(fig, out_dir, base, fmt, **kwargs):
        captured.update(kwargs)
        return orig_save(fig, out_dir, base, fmt, **kwargs)

    monkeypatch.setattr(_main, "save_figure", spy_save)
    monkeypatch.setattr(_main.messagebox, "askyesno", lambda *a, **k: False)
    monkeypatch.setattr(_main.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(_main.messagebox, "showerror", lambda *a, **k: None)
    app.generate()
    assert captured.get("dpi") == 300
    files = [f for f in os.listdir(tmp_path) if f.startswith("periodic_table_")]
    assert files, "未生成输出文件"
