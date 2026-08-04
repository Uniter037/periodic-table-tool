# -*- coding: utf-8 -*-
"""从 mendeleev 一次性提取 118 元素的标准布局数据（符号, 族, 周期）。

镧系/锕系（57-71, 89-103）在原脚本中被特殊处理（重构系列跳过、经典系列放第 8/9 行），
其族号/周期由脚本逻辑覆盖，此处仅提取其余元素的数据。
输出 JSON 到 stdout，用于固化到 core/ptable.py。
"""
import json
import sys

sys.path.insert(0, ".")
from mendeleev import element

out = {}
for i in range(1, 119):
    if (57 <= i <= 71) or (89 <= i <= 103):
        continue
    e = element(i)
    out[e.symbol] = [e.group_id if e.group_id is not None else 0, e.period]

print(json.dumps(out, separators=(",", ":")))
