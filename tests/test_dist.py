# -*- coding: utf-8 -*-
"""发行包完整性测试：make_dist.py 的 INCLUDE 清单必须覆盖全部运行时模块。"""
from __future__ import annotations

import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _include_list() -> list:
    text = (ROOT / "make_dist.py").read_text(encoding="utf-8")
    m = re.search(r"INCLUDE = \[(.*?)\]", text, re.S)
    assert m, "make_dist.py 中未找到 INCLUDE 列表"
    return re.findall(r'"([^"]+)"', m.group(1))


def test_dist_includes_all_core_modules():
    """core/__init__.py 导入的每个子模块都必须打包。"""
    includes = _include_list()
    init = (ROOT / "core" / "__init__.py").read_text(encoding="utf-8")
    imported = re.findall(r"from \.(\w+) import", init)
    assert imported, "core/__init__.py 未解析到子模块导入"
    for mod in imported:
        assert f"core/{mod}.py" in includes, \
            f"发行包缺少 core/{mod}.py（core/__init__.py 导入了它）"


def test_dist_includes_required_files():
    """基础文件必须打包。"""
    includes = _include_list()
    for f in ("main.py", "README.md", "requirements.txt", "pyproject.toml"):
        assert f in includes, f"发行包缺少 {f}"
