# -*- coding: utf-8 -*-
"""UI 布局功能测试：布局切换、自动调整、配置持久化。"""
from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pytest


def _gui_available():
    try:
        import main
        return True
    except Exception:
        return False


try:
    import main
except Exception:
    main = None


# ---------------------------------------------------------------------------
# 布局切换与自动调整（GUI）
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_layout_switch_manual(app):
    """手动选择左右/上下布局后，控件 grid 位置随之变化（含 rowspan 无残留）。"""
    # 左右分栏：left 在 column 0，right 在 column 1
    app.layout_mode = "split-h"
    app.layout_var.set("split-h")
    app._apply_layout()
    assert app._left.grid_info()["column"] == 0
    assert app._left.grid_info()["rowspan"] == 2
    assert app._right.grid_info()["column"] == 1
    # 上下分栏：left 在 row 0，right 在 row 1；rowspan 必须重置为 1（无重叠）
    app.layout_mode = "split-v"
    app.layout_var.set("split-v")
    app._apply_layout()
    assert app._left.grid_info()["row"] == 0
    assert app._left.grid_info()["rowspan"] == 1
    assert app._right.grid_info()["row"] == 1
    assert app._right.grid_info()["column"] == 0
    assert app._right.grid_info()["rowspan"] == 1
    # 再切回左右：rowspan 恢复 2
    app.layout_mode = "split-h"
    app.layout_var.set("split-h")
    app._apply_layout()
    assert app._left.grid_info()["rowspan"] == 2


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_layout_auto_threshold(app, monkeypatch):
    """自动模式：窗口宽度低于阈值用上下分栏，高于用左右分栏（含边界值）。"""
    app.layout_mode = "auto"
    app.layout_var.set("auto")
    # 模拟窄窗口
    monkeypatch.setattr(app, "winfo_width", lambda: 800)
    app._apply_layout()
    assert app._right.grid_info()["row"] == 1      # 上下
    # 模拟宽窗口
    monkeypatch.setattr(app, "winfo_width", lambda: 1400)
    app._apply_layout()
    assert app._right.grid_info()["column"] == 1   # 左右
    # 边界值：恰好等于阈值 → 左右分栏
    monkeypatch.setattr(app, "winfo_width",
                        lambda: main.AUTO_SPLIT_THRESHOLD)
    app._apply_layout()
    assert app._right.grid_info()["column"] == 1
    # 未映射窗口（width<=1）→ 默认左右，避免启动闪变
    monkeypatch.setattr(app, "winfo_width", lambda: 1)
    app._apply_layout()
    assert app._right.grid_info()["column"] == 1


@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_layout_state_preserved_after_switch(app):
    """切换布局不丢失用户数据与设置。"""
    import main
    app.data = {"Fe": "0.75"}
    app.layout_mode = "split-v"
    app._apply_layout()
    assert app.data == {"Fe": "0.75"}
    app.layout_mode = "split-h"
    app._apply_layout()
    assert app.data == {"Fe": "0.75"}


# ---------------------------------------------------------------------------
# 配置持久化
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _gui_available(), reason="GUI 环境不可用")
def test_config_roundtrip(app, tmp_path, monkeypatch):
    """布局模式与窗口尺寸保存后可从配置恢复。"""
    import main
    cfg_file = tmp_path / "cfg.json"
    monkeypatch.setattr(main, "CONFIG_PATH", str(cfg_file))

    app.layout_mode = "split-v"
    app.geometry("900x700+10+10")
    app._save_config()
    assert cfg_file.exists()
    cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert cfg["layout"] == "split-v"
    assert "+10+10" in cfg["geometry"]   # 位置信息保留（测试环境窗口未渲染，尺寸为 1x1）

    # 重新加载
    app.layout_mode = "auto"
    app._config = {}
    app._load_config()
    assert app.layout_mode == "split-v"
