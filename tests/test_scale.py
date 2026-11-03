# -*- coding: utf-8 -*-
"""界面缩放与预览自适应测试。"""
from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pytest

try:
    import main
except Exception:
    main = None


def _gui_available():
    return main is not None


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_scale_manual(app):
    """手动缩放：字号与缩放状态随比例变化。"""
    app.scale_mode = "1.25"
    app.scale_var.set("1.25")
    app._current_scale = None
    app._apply_scale()
    expected = round(main.BASE_FONT_SIZE * 1.25)
    assert app._current_scale == expected
    assert app._app_font is not None
    assert app._app_font.cget("size") == expected
    # Treeview 行高通过样式配置
    from tkinter import ttk
    rh = int(ttk.Style(app).lookup("Treeview", "rowheight"))
    assert rh >= 20


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_scale_debounce(app, monkeypatch):
    """auto 缩放防抖：字号未变（宽度小幅变化）不重复应用样式。"""
    app.scale_mode = "auto"
    app.scale_var.set("auto")
    # 先确保字体已创建（避免 None is None 使断言失效）
    app._current_scale = None
    app._apply_scale()
    font_before = app._app_font
    assert font_before is not None
    # 宽度小幅变化（1200~1360 内字号取整仍为 10）→ 不触发字体重建
    monkeypatch.setattr(app, "winfo_width", lambda: 1300)
    app._apply_scale()
    assert app._app_font is font_before


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_config_malformed_values(app, tmp_path, monkeypatch):
    """畸形 config（layout/scale 为 list）不导致启动崩溃，回退默认。"""
    import json
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(json.dumps({"layout": [], "scale": {},
                                    "preview_ratio": "x"}), encoding="utf-8")
    monkeypatch.setattr(main, "CONFIG_PATH", str(cfg_file))
    app._config = {}
    app._load_config()          # 不应抛异常
    assert app.layout_mode == "auto"
    assert app.scale_mode == "auto"
    assert app.preview_ratio == 0.72


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_scale_auto(app, monkeypatch):
    """自动缩放：窗口越宽字号越大（clamp 到上下限）。"""
    app.scale_mode = "auto"
    app.scale_var.set("auto")
    # 窄窗口 → 下限
    monkeypatch.setattr(app, "winfo_width", lambda: 800)
    assert app._effective_scale() == main.SCALE_RANGE[0]
    # 宽窗口 → 上限
    monkeypatch.setattr(app, "winfo_width", lambda: 3000)
    assert app._effective_scale() == main.SCALE_RANGE[1]
    # 基准窗口 → 1.0
    monkeypatch.setattr(app, "winfo_width", lambda: main.BASE_WINDOW_WIDTH)
    assert app._effective_scale() == 1.0


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_preview_ratio(app):
    """Ratio menu moves a real sash; manual dragging preserves the figure size."""
    app.geometry("1024x768")
    app.deiconify()
    app.update()
    try:
        app.preview_ratio = 0.6
        app._apply_preview_ratio()
        app.update_idletasks()
        first = app._right.sash_coord(0)[1]
        app.preview_ratio = 0.4
        app._apply_preview_ratio()
        app.update_idletasks()
        second = app._right.sash_coord(0)[1]
        assert second < first
        assert app.preview.winfo_height() >= 160
        app._remember_preview_ratio()
        assert app.preview_ratio == pytest.approx(second / app._right.winfo_height())
    finally:
        app.preview_ratio = .72
        app._apply_preview_ratio()
        app.withdraw()


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_resize_preview_no_crash(app):
    """预览画布无内容时自适应不崩溃。"""
    app._resize_preview()   # 不应抛异常


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_config_scale_roundtrip(app, tmp_path, monkeypatch):
    """缩放与预览比例持久化往返。"""
    cfg_file = tmp_path / "cfg.json"
    monkeypatch.setattr(main, "CONFIG_PATH", str(cfg_file))
    app.scale_mode = "1.5"
    app.preview_ratio = 0.6
    app._save_config()
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert cfg["scale"] == "1.5"
    assert cfg["preview_ratio"] == 0.6
    # 恢复
    app.scale_mode = "auto"
    app.preview_ratio = 0.5
    app._config = {}
    app._load_config()
    assert app.scale_mode == "1.5"
    assert app.preview_ratio == 0.6
