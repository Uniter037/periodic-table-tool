# -*- coding: utf-8 -*-
"""一致性验证脚本。

对 12 种样式（文件8 cmap 预览单独验证；文件6 的已知 bug 在内存中修补）：
1. 在临时目录原样执行原始脚本（Agg 后端、show 无操作），取其渲染结果 PNG；
2. 用 core.render_table 以相同数据 + 相同样式渲染 PNG；
3. 逐像素对比两张 PNG，输出 PASS / FAIL 与差异统计。

用法: python tests/verify.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile

# 允许从项目根导入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from core.styles import STYLES, render_table

# 注入 mendeleev 模拟模块：使用内置布局数据（与 mendeleev 1.2.0 同一来源），
# 避免原脚本 exec 时 118 次数据库查询（约 28 秒/脚本）。
import types
from unittest.mock import patch
from core.elements_data import ELEM_LAYOUT, ALL_SYMBOLS


class _FakeElem:
    def __init__(self, num, sym):
        self.symbol = sym
        if sym in ELEM_LAYOUT:
            self.group_id, self.period = ELEM_LAYOUT[sym]
        else:   # 镧系/锕系：原脚本会覆盖 group/period，原始值无关紧要
            self.group_id, self.period = None, None


_fake_mendeleev = types.ModuleType("mendeleev")
_fake_mendeleev.element = lambda num: _FakeElem(num, ALL_SYMBOLS[num - 1])

ATTACH_DIR = os.path.join(PROJECT_ROOT, "tests", "fixtures", "originals")

# 附件文件名 -> 样式 id
FILE_STYLE = {
    "clipboard-20260804-123351.833165-000001.py": "reconstruct_percent",
    "clipboard-20260804-123351.842688-000002.py": "reconstruct_2f_a",
    "clipboard-20260804-123351.851072-000003.py": "reconstruct_2f_b",
    "clipboard-20260804-123351.859262-000004.py": "labels_light",
    "clipboard-20260804-123405.911890-000005.py": "classic_ylorrd_orig",
    "clipboard-20260804-123405.919243-000006.py": "classic_ylorrd",
    "clipboard-20260804-123405.928502-000007.py": "classic_blues",
    "clipboard-20260804-123405.948615-000009.py": "classic_ylgn",
    "clipboard-20260804-123405.955698-000010.py": "classic_coolwarm",
    "clipboard-20260804-123405.967489-000011.py": "labels_highlight",
    "clipboard-20260804-123405.977546-000012.py": "classic_coolwarm3",
    "clipboard-20260804-123405.984963-000013.py": "classic_bwr3",
}

# 原脚本数据变量名
DATA_VAR = {
    "reconstruct_percent": "plot_data",
    "reconstruct_2f_a": "plot_data",
    "reconstruct_2f_b": "plot_data",
    "labels_light": "bottom_labels",
    "classic_ylorrd_orig": "plot_data",
    "classic_ylorrd": "plot_data",
    "classic_blues": "plot_data",
    "classic_ylgn": "plot_data",
    "classic_coolwarm": "plot_data",
    "labels_highlight": "label_data",
    "classic_coolwarm3": "plot_data",
    "classic_bwr3": "plot_data",
}


def fix_classic_ylorrd_bug(code: str) -> str:
    """修复原脚本在新版 matplotlib 下的兼容性问题：

    1. 图1（Hui_Tu-1.py）使用 cm.get_cmap()（matplotlib 3.11 已移除），
       替换为 mpl.colormaps['名称']；
    2. 图1 的 plt.colorbar(cmmapable) 未关联 axes（matplotlib 3.11 报错），
       补 ax=plt.gca()；
    3. 图2（Hui_Tu-2.py）text_props 含 'ha': 'center'，同时显式传
       ha='left'，导致 TypeError。修复：删除 text_props 中的 'ha' 键
       （保留显式 ha='left' 的意图），并在符号/值文本调用处补回 ha='center'。
    """
    code = re.sub(r"cm\.get_cmap\(\s*'([^']+)'\s*\)", r"mpl.colormaps['\1']", code)
    code = code.replace("plt.colorbar(cmmapable, drawedges=False)",
                        "plt.colorbar(cmmapable, ax=plt.gca(), drawedges=False)")
    code = re.sub(r"(\s+)'ha': 'center',?\n", "\n", code)
    # 符号文本与数值文本补回居中（原 text_props 提供）
    code = re.sub(r"(fontsize=9, weight='bold'), \*\*text_props\)",
                  r"\1, ha='center', **text_props)", code)
    code = re.sub(r"(str\(value\),\s*fontsize=6), \*\*text_props\)",
                  r"\1, ha='center', **text_props)", code)
    return code


def run_original(code: str, workdir: str, style_id: str) -> tuple:
    """在临时目录原样执行原脚本，返回其渲染结果的 PNG 路径。"""
    if style_id in ("classic_ylorrd_orig", "classic_ylorrd"):
        code = fix_classic_ylorrd_bug(code)
    ns = {}
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        with patch.dict(sys.modules, {"mendeleev": _fake_mendeleev}), patch.object(plt, "show"):
            exec(compile(code, "<original>", "exec"), ns)
        fig = plt.gcf()
        png = os.path.join(workdir, "orig.png")
        bbox = STYLES[style_id].get("bbox_tight", True)
        fig.savefig(png, dpi=100, bbox_inches="tight" if bbox else None)
        plt.close("all")
        return png, ns
    finally:
        plt.close("all")
        os.chdir(cwd)


def render_mine(style_id: str, data: dict, workdir: str) -> str:
    """用 core 渲染相同数据，返回 PNG 路径。"""
    style = STYLES[style_id]
    fig = render_table(style, data)
    png = os.path.join(workdir, "mine.png")
    bbox = style.get("bbox_tight", True)
    fig.savefig(png, dpi=100, bbox_inches="tight" if bbox else None)
    plt.close("all")
    return png


def compare_png(a_path: str, b_path: str) -> tuple:
    """逐像素对比，返回 (是否一致, 差异统计文本)。"""
    a = plt.imread(a_path)
    b = plt.imread(b_path)
    if a.shape != b.shape:
        return False, f"尺寸不同: {a.shape} vs {b.shape}"
    if np.array_equal(a, b):
        return True, "逐像素完全一致"
    diff = np.abs(a.astype(float) - b.astype(float))
    n = int((diff > 1 / 255).sum())
    return False, f"尺寸相同但像素不同: 差异像素 {n} / {a.size} (最大差 {diff.max():.4f})"


def compare_style(style_id: str) -> tuple:
    """渲染单个模式并与原脚本输出逐像素对比，返回 (是否一致, 说明)。"""
    fname = None
    for fn, sid in FILE_STYLE.items():
        if sid == style_id:
            fname = fn
            break
    if fname is None:
        return False, f"未知样式: {style_id}"

    src = os.path.join(ATTACH_DIR, fname)
    if not os.path.exists(src):
        return False, f"基准脚本缺失: {fname}"
    with open(src, "r", encoding="utf-8") as fh:
        code = fh.read()

    workdir = tempfile.mkdtemp(prefix="pt_verify_")
    try:
        try:
            orig_png, ns = run_original(code, workdir, style_id)
        except Exception as exc:
            return False, f"原脚本无法运行: {exc}"
        data = ns.get(DATA_VAR[style_id])
        if data is None:
            return False, f"未找到数据变量 {DATA_VAR[style_id]}"
        mine_png = render_mine(style_id, data, workdir)
        ok, msg = compare_png(orig_png, mine_png)
        return ok, msg
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def verify_cmap_preview() -> tuple:
    """验证图4 cmap 预览：生成文件数量与有效 cmap 数一致。"""
    workdir = tempfile.mkdtemp(prefix="pt_verify_")
    try:
        from core.styles import CMAP_PREVIEW_LIST, render_cmap_preview
        paths = render_cmap_preview(os.path.join(workdir, "cmap_out"))
        valid = [c for c in CMAP_PREVIEW_LIST if c in matplotlib.colormaps]
        if len(paths) == len(valid) and all(os.path.exists(p) for p in paths):
            return True, f"生成 {len(paths)} 个预览文件"
        return False, f"期望 {len(valid)} 个，实际 {len(paths)} 个"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def verify_all() -> list:
    """逐一验证所有模式，返回 [(样式id, 状态, 说明)]。"""
    results = []
    for fname, style_id in FILE_STYLE.items():
        ok, msg = compare_style(style_id)
        results.append((style_id, "PASS" if ok else "FAIL", msg))
    ok, msg = verify_cmap_preview()
    results.append(("cmap_preview", "PASS" if ok else "FAIL", msg))
    return results


def main():
    results = verify_all()

    print("=" * 60)
    print("一致性验证结果")
    print("=" * 60)
    n_pass = 0
    for style_id, status, msg in results:
        print(f"[{status:>5}] {style_id:<24} {msg}")
        if status == "PASS":
            n_pass += 1
    print("-" * 60)
    print(f"通过 {n_pass} / {len(results)}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
