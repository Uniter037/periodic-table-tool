# -*- coding: utf-8 -*-
"""颜色条标注自定义测试：自定义 ticks/labels 渲染与 GUI 编辑器。"""
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
# core：自定义 cbar ticks/labels 渲染
# ---------------------------------------------------------------------------
def test_render_table_custom_cbar():
    """style['cbar'] 自定义刻度与标签被应用。"""
    style = dict(STYLES["reconstruct_percent"])
    style["cbar"] = {"ticks": [0.005, 0.010, 0.014],
                     "labels": ["低", "中", "高"], "fontsize": 8}
    fig = render_table(style, {"Ag": 0.0101})
    try:
        cbar_ax = fig.axes[-1]
        import numpy as np
        assert np.allclose(cbar_ax.get_yticks(), [0.005, 0.010, 0.014])
        labels = [t.get_text() for t in cbar_ax.get_yticklabels()]
        assert labels == ["低", "中", "高"]
    finally:
        plt.close(fig)


def test_render_table_cbar_none_uses_auto():
    """cbar=None 时走 matplotlib 自动刻度（不崩）。"""
    style = dict(STYLES["classic_ylorrd"])
    style["cbar"] = None
    fig = render_table(style, {"Fe": 7})
    try:
        assert len(fig.axes) == 2
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# GUI：cbar_override 注入与恢复
# ---------------------------------------------------------------------------
def _gui_available():
    return main is not None


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_cbar_override_injected(app):
    """cbar_override 注入到工作样式（自定义与非自定义模式）。"""
    ids = list(main.STYLES.keys())
    app.mode_combo.current(ids.index("custom"))
    app._on_style_change()
    app.cbar_override = {"ticks": [0.1, 0.5, 0.9],
                         "labels": ["a", "b", "c"], "fontsize": 8}
    work = app._current_work_style()
    assert work["cbar"]["ticks"] == [0.1, 0.5, 0.9]
    # 非自定义模式：注入且不污染全局 STYLES
    app.mode_combo.current(ids.index("reconstruct_percent"))
    app._on_style_change()
    assert app.cbar_override is None  # 切换样式不能沿用旧范围的刻度。
    app.cbar_override = {"ticks": [0.1, 0.5, 0.9],
                         "labels": ["a", "b", "c"], "fontsize": 8}
    work2 = app._current_work_style()
    assert work2["cbar"]["labels"] == ["a", "b", "c"]
    assert main.STYLES["reconstruct_percent"]["cbar"]["labels"] != ["a", "b", "c"]
    # 恢复默认（None）→ 回到样式自带标注
    app.cbar_override = None
    work3 = app._current_work_style()
    assert work3["cbar"]["labels"] == ["0.48%", "1.25%", "1.42%"]


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_cbar_editor_flow(app, monkeypatch):
    """编辑器：添加 → 删除 → 恢复默认。"""
    import main as _main
    ids = list(_main.STYLES.keys())
    app.mode_combo.current(ids.index("custom"))
    app._on_style_change()
    monkeypatch.setattr(_main.messagebox, "showwarning", lambda *a, **k: None)
    # 添加两个标注
    app.cbar_value_var.set("0.2")
    app.cbar_label_var.set("低")
    app._cbar_add()
    app.cbar_value_var.set("0.8")
    app.cbar_label_var.set("高")
    app._cbar_add()
    assert app.cbar_override["ticks"] == [0.2, 0.8]
    assert app.cbar_override["labels"] == ["低", "高"]
    assert len(app.cbar_tree.get_children()) == 2
    # 非法刻度值 → 拒绝
    app.cbar_value_var.set("abc")
    app._cbar_add()
    assert len(app.cbar_override["ticks"]) == 2
    # NaN 刻度值 → 拒绝（有限值校验）
    app.cbar_value_var.set("nan")
    app._cbar_add()
    assert len(app.cbar_override["ticks"]) == 2
    # 删除第一行
    first = app.cbar_tree.get_children()[0]
    app.cbar_tree.selection_set(first)
    app._cbar_delete()
    assert app.cbar_override["ticks"] == [0.8]
    # 恢复默认
    app._cbar_reset()
    assert app.cbar_override is None
    assert len(app.cbar_tree.get_children()) == 0


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_cbar_preset_roundtrip(app, tmp_path, monkeypatch):
    """预设保存/加载包含 cbar_override。"""
    import json
    import main as _main
    from core import PresetStore
    app.presets = PresetStore(str(tmp_path))
    app.cbar_override = {"ticks": [0.1, 0.9], "labels": ["x", "y"], "fontsize": 8}
    app.preset_name_var.set("cbar预设")
    app._preset_save()
    cfg = json.loads((tmp_path / "cbar预设.json").read_text(encoding="utf-8"))
    assert cfg["cbar_override"]["ticks"] == [0.1, 0.9]
    # 加载恢复
    app.cbar_override = None
    app.preset_combo.set("cbar预设")
    app._preset_load()
    assert app.cbar_override["ticks"] == [0.1, 0.9]
    assert len(app.cbar_tree.get_children()) == 2   # tree 同步刷新
    # 损坏预设必须明确报错，并保留完整的现有工作，不能静默丢弃标签。
    before = app._document_snapshot()
    errors = []
    monkeypatch.setattr(_main.messagebox, "showerror", lambda *a, **kw: errors.append(a))
    invalid = [
        {"ticks": [1], "labels": ["a", "b"]},
        {"ticks": ["nan"], "labels": ["x"]},
        {"ticks": [1.0], "labels": ["x"], "fontsize": "big"},
        {"ticks": [True], "labels": ["x"]},
        {"ticks": [1.0], "labels": ["x"], "fontsize": True},
    ]
    for index, config in enumerate(invalid):
        name = f"invalid_{index}"
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"cbar_override": config}), encoding="utf-8")
        app.preset_combo.set(name)
        app._preset_load()
        assert len(errors) == index + 1
        assert app._document_snapshot() == before
