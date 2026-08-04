# -*- coding: utf-8 -*-
"""v1.1 迭代功能测试：show_cbar / 自定义颜色 / 预设 CRUD / GUI 预览与图形化标注。"""
from __future__ import annotations

import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from core import STYLES, render_table, PresetStore
from core.presets import PresetStore as _PresetStore


def _gui_available():
    try:
        import main  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# core：show_cbar
# ---------------------------------------------------------------------------
def test_render_table_show_cbar_off():
    """show_cbar=False 时不创建颜色条（fig 仅 1 个 axes）。"""
    style = STYLES["reconstruct_percent"]
    fig = render_table(style, {"Ag": 0.0101}, show_cbar=False)
    try:
        assert len(fig.axes) == 1
    finally:
        plt.close(fig)


def test_render_table_show_cbar_default_on():
    """默认 show_cbar=True 保持原行为（热力图含颜色条）。"""
    style = STYLES["reconstruct_percent"]
    fig = render_table(style, {"Ag": 0.0101})
    try:
        assert len(fig.axes) == 2
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# core：自定义颜色序列
# ---------------------------------------------------------------------------
def test_render_table_custom_colors():
    """任意数量自定义颜色序列可正常渲染。"""
    style = dict(STYLES["custom"])
    style["cmap"] = ("custom", [(0.1, 0.1, 0.1), (0.5, 0.5, 0.5),
                                (0.9, 0.9, 0.9), (1.0, 0.0, 0.0)])
    fig = render_table(style, {"Fe": 0.7, "Cu": 0.73})
    try:
        assert len(fig.axes) >= 1
    finally:
        plt.close(fig)


def test_render_table_custom_colors_invalid_name_rejected():
    """含 ':' 的颜色映射名被拒绝（防 module:qualname 导入）。"""
    style = dict(STYLES["custom"])
    style["cmap"] = "os:system"
    with pytest.raises(ValueError):
        render_table(style, {"Fe": 0.7})


# ---------------------------------------------------------------------------
# core：预设 CRUD
# ---------------------------------------------------------------------------
def test_preset_store_roundtrip(tmp_path):
    store = PresetStore(str(tmp_path))
    store.save("我的预设", {"mode": "custom", "data": {"Fe": 0.7}})
    store.save("preset-2", {"mode": "reconstruct_percent"})
    assert store.list() == ["preset-2", "我的预设"]
    assert store.load("我的预设") == {"mode": "custom", "data": {"Fe": 0.7}}
    store.delete("preset-2")
    assert store.list() == ["我的预设"]


def test_preset_store_rejects_bad_name(tmp_path):
    store = PresetStore(str(tmp_path))
    with pytest.raises(ValueError):
        store.save("../evil", {"a": 1})
    with pytest.raises(ValueError):
        store.save("", {"a": 1})


# ---------------------------------------------------------------------------
# GUI：预览与图形化标注
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_gui_preview_canvas(app):
    """预览画布能渲染并建立命中表。"""
    app.mode_combo.current(0)
    app._on_style_change()
    app._load_demo()
    assert app.preview.hit_map, "预览命中表不应为空"
    # 命中表覆盖实际元素坐标：H 格（重构布局 group1/period1，y=8.7-1.1=7.6）
    hit = app.preview.hit_test(0.5, 8.0)
    assert hit == "H"


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_gui_graphical_marking(app):
    """图形化标注：点击元素 → 应用数值 → 数据同步到统一数据源。"""
    app.data = {}
    app.table.set_data({})
    app.mark_mode_var.set(True)
    app.mark_symbol_var.set("Fe")
    app.mark_value_var.set("0.75")
    app._apply_mark()
    assert app.data.get("Fe") == "0.75"
    # 清除
    app.mark_value_var.set("")
    app._apply_mark()
    assert "Fe" not in app.data


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_gui_colorbar_toggle(app, monkeypatch):
    """颜色条开关影响预览渲染结果（关闭后 fig 无颜色条）。"""
    import main
    app.mode_combo.current(0)
    app._on_style_change()
    app._load_demo()
    monkeypatch.setattr(main.messagebox, "showwarning", lambda *a, **k: None)
    app.show_cbar_var.set(False)
    app._refresh_preview()
    assert app.preview.fig is not None
    assert len(app.preview.fig.axes) == 1
    app.show_cbar_var.set(True)
    app._refresh_preview()
    assert len(app.preview.fig.axes) == 2


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_gui_preset_flow(app, tmp_path, monkeypatch):
    """预设保存 → 修改 → 加载 恢复。"""
    import main
    app.presets = _PresetStore(str(tmp_path))
    app.mode_combo.current(0)
    app._on_style_change()
    app._load_demo()
    app.preset_name_var.set("测试预设")
    app._preset_save()
    assert "测试预设" in app.presets.list()

    # 修改数据并切换模式
    app.data = {"Fe": 9.9}
    app.mode_combo.current(2)
    app._on_style_change()

    # 加载预设恢复
    monkeypatch.setattr(main.messagebox, "showwarning", lambda *a, **k: None)
    app.preset_combo.set("测试预设")
    app._preset_load()
    assert app._current_style_id() == "reconstruct_percent"
    assert "Fe" in app.data
    assert app.data["Fe"] == "0.75" or app.data["Fe"] != 9.9
