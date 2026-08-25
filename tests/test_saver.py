# -*- coding: utf-8 -*-
"""自动改名保存器测试。"""
from __future__ import annotations

import os
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.saver import auto_name, save_figure


def test_auto_name_unique_in_same_second():
    """同一秒内连续生成，文件名不冲突（追加序号）。"""
    d = tempfile.mkdtemp()
    p1 = auto_name(d, "periodic_table", "svg")
    p2 = auto_name(d, "periodic_table", "svg")
    p3 = auto_name(d, "periodic_table", "svg")
    assert p1 != p2 != p3
    for p in (p1, p2, p3):
        assert p.startswith(os.path.join(d, "periodic_table_"))
        assert p.endswith(".svg")
        assert os.path.exists(os.path.dirname(p))


def test_auto_name_appends_counter_when_collision():
    """已存在同名文件时自动追加 _2 序号，不覆盖。"""
    d = tempfile.mkdtemp()
    p1 = auto_name(d, "fig", "png")
    assert os.path.exists(p1)
    # 人为再创建一个与 p1 同基准名的文件（模拟再次生成）
    p2 = auto_name(d, "fig", "png")
    assert p2 != p1
    assert not os.path.samefile(p1, p2)


def test_save_figure_returns_existing_path():
    """save_figure 保存成功且返回的文件确实存在。"""
    d = tempfile.mkdtemp()
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    path = save_figure(fig, d, "periodic_table", "svg")
    plt.close(fig)
    assert os.path.exists(path)
    assert os.path.basename(path).startswith("periodic_table_")
    assert path.endswith(".svg")
    assert os.path.getsize(path) > 0


def test_save_figure_cleans_placeholder_on_failure():
    """保存失败时清理占位文件，不残留空文件占用名字。"""
    d = tempfile.mkdtemp()
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3])
    before = set(os.listdir(d))
    try:
        save_figure(fig, d, "periodic_table", "xyz")   # 未知格式 → 保存失败
    except Exception:
        pass
    plt.close(fig)
    assert set(os.listdir(d)) == before, "保存失败后应无残留文件"
