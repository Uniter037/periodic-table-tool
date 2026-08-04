# -*- coding: utf-8 -*-
"""GUI 冒烟测试：界面可实例化、生成流程端到端可用。

注意：连续创建多个 tkinter 根窗口在部分 Windows 环境会失败，
因此所有测试共享一个 App 实例（module-scoped fixture）。
"""
from __future__ import annotations

import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pytest

matplotlib_backend_ok = True
try:
    import matplotlib
except Exception:
    matplotlib_backend_ok = False


@pytest.fixture(scope="module")
def app():
    """创建共享 GUI 实例；GUI 环境不可用时整个模块跳过。"""
    if not matplotlib_backend_ok:
        pytest.skip("matplotlib 不可用")
    try:
        import main
    except Exception as exc:
        pytest.skip(f"tkinter/matplotlib GUI 环境不可用: {exc}")
    instance = main.App()
    instance.withdraw()
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass


def test_gui_can_instantiate(app):
    assert len(app.table.tree.get_children()) == 118


def test_gui_generate_end_to_end(app, monkeypatch):
    """端到端：选模式 → 载入示例 → 生成 → 输出自动改名文件。"""
    import main
    out_dir = tempfile.mkdtemp(prefix="pt_gui_out_")
    # 禁用弹窗与浏览器打开
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *a, **k: False)
    monkeypatch.setattr(main.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *a, **k: None)

    app.mode_combo.current(0)          # 重构1 · 蓝白红热力图（百分比）
    app._on_style_change()
    app.table.set_data(main.demo_data("reconstruct_percent"))
    app.out_var.set(out_dir)
    app.fmt_var.set("svg")
    app.generate()
    files = [f for f in os.listdir(out_dir) if f.startswith("periodic_table_")]
    assert files, "未生成输出文件"
    # 再次生成：文件名自动改名，不覆盖（目录中文件数 +1）
    app.generate()
    files2 = [f for f in os.listdir(out_dir) if f.startswith("periodic_table_")]
    assert len(files2) == len(files) + 1, \
        f"第二次生成应自动改名不覆盖：期望 {len(files) + 1} 个，实际 {len(files2)} 个"
    # 生成结果可正常读取（非空 SVG）
    assert os.path.getsize(os.path.join(out_dir, files2[-1])) > 0


def test_gui_import_file(app, monkeypatch, tmp_path):
    """导入数据文件入口可用。"""
    import main
    data_file = tmp_path / "data.txt"
    data_file.write_text("Ag, 0.0101\nAu = 0.0111\n", encoding="utf-8")
    monkeypatch.setattr(main.filedialog, "askopenfilename",
                        lambda **k: str(data_file))
    app._import_file()
    data = app.table.get_data()
    assert data.get("Ag") == "0.0101"
    assert data.get("Au") == "0.0111"
