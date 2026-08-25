# -*- coding: utf-8 -*-
"""元素周期表布局构建。

两种布局风格（与原脚本保持一致）：
- 'reconstructed'（重构系列 Hui_Tu_Chong_gou_1~3 / Hui_Tu_Min_Cheng_01）：
  镧系/锕系元素主体不展开，仅在第 6/7 周期第 3 族放置两行三行标注块
  （57~71 La~Lu Lanthanide / 86~103 Ac~Lr Actinide）。
- 'classic'（图1~9 系列 Hui_Tu-1~9 / Hui_Tu8）：
  镧系元素排到第 8 行、锕系排到第 9 行，并放置 LA / AC 定位标记。

布局数据来自 mendeleev 1.2.0 的标准周期表（见 core/elements_data.py），
与原脚本查询结果完全一致；内置固化后无需在运行时查询数据库。
"""
from __future__ import annotations

from .elements_data import ELEM_LAYOUT, ALL_SYMBOLS

# 镧系 / 锕系原子序数区间
LANTHANIDE = (57, 71)
ACTINIDE = (89, 103)

# 周期表格子布局常量（与原脚本一致）
CELL_LENGTH = 1.0
CELL_GAP = 0.1
CLASSIC_Y_BOUNDS = (20, 11)          # 经典布局：x 0~20, y 0~11
CELL_STEP = CELL_LENGTH + CELL_GAP   # 1.1

# 布局缓存：元素几何布局（num/symbol/group/period）与数据无关，可复用
_LAYOUT_CACHE = {}


def build_elements(layout: str, data: dict) -> list:
    """构建元素列表。

    返回列表，每个元素为 [num, symbol, group, period, value]：
    - num 为 None 表示标记块 / 定位标记（不画格子，仅画文字），其 value 为 None；
    - value 来自 data（dict: 元素符号 -> 值），缺失时为 0。
    """
    base = _get_layout(layout)
    return [e[:4] + [None if e[0] is None else data.get(e[1], 0)] for e in base]


def _get_layout(layout: str) -> list:
    """获取（并缓存）元素几何布局模板。"""
    if layout not in _LAYOUT_CACHE:
        if layout == "reconstructed":
            _LAYOUT_CACHE[layout] = _build_reconstructed()
        elif layout == "classic":
            _LAYOUT_CACHE[layout] = _build_classic()
        else:
            raise ValueError(f"未知布局: {layout!r}")
    return _LAYOUT_CACHE[layout]


def _build_reconstructed() -> list:
    """重构系列布局：跳过镧系/锕系，放置三行标注块。"""
    elements = []
    for i in range(1, 119):
        if LANTHANIDE[0] <= i <= LANTHANIDE[1] or ACTINIDE[0] <= i <= ACTINIDE[1]:
            continue
        sym = ALL_SYMBOLS[i - 1]
        group, period = ELEM_LAYOUT[sym]
        elements.append([i, sym, group, period, 0])

    # 镧系 / 锕系标注块（三行文本元组），位于第 6/7 周期第 3 族
    markers = [
        [None, ("57~71 ", "La~Lu", "Lanthanide"), 3, 6, None],
        [None, ("86~103", "Ac~Lr", "Actinide"), 3, 7, None],
    ]
    elements.extend(markers)
    return elements


def _build_classic() -> list:
    """经典布局：镧系/锕系展开到第 8/9 行，并放置 LA/AC 定位标记。"""
    elements = []
    for i in range(1, 119):
        sym = ALL_SYMBOLS[i - 1]
        if LANTHANIDE[0] <= i <= LANTHANIDE[1]:
            group, period = i - LANTHANIDE[0] + 3, 8
        elif ACTINIDE[0] <= i <= ACTINIDE[1]:
            group, period = i - ACTINIDE[0] + 3, 9
        else:
            group, period = ELEM_LAYOUT[sym]
        elements.append([i, sym, group, period, 0])

    markers = [
        [None, "LA", 3, 6, None],
        [None, "AC", 3, 7, None],
        [None, "LA", 2, 8, None],
        [None, "AC", 2, 9, None],
    ]
    elements.extend(markers)
    return elements


def xy_bounds_for(layout: str) -> tuple:
    """画布范围。重构系列按实际最大周期计算，经典布局固定 (20, 11)。"""
    if layout == "classic":
        return CLASSIC_Y_BOUNDS
    elements = _get_layout("reconstructed")
    max_period = max(e[3] for e in elements if e[3] is not None)
    return (20, CELL_STEP * max_period + 1)
