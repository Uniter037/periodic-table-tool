# -*- coding: utf-8 -*-
"""将提取的 JSON 布局数据固化为 Python 模块 core/elements_data.py"""
import json
import os

here = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(here, "elem_layout.json"), "r", encoding="utf-8") as fh:
    layout = json.load(fh)

# 118 个元素符号（含镧系/锕系）
LANTHANIDE_SYMBOLS = [
    "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy",
    "Ho", "Er", "Tm", "Yb", "Lu",
]
ACTINIDE_SYMBOLS = [
    "Ac", "Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf",
    "Es", "Fm", "Md", "No", "Lr",
]
# 完整 118 个符号（按原子序数）：
# 非镧锕元素按 layout 中的原始顺序插入，镧系/锕系固定插入。
fixed = []
for i in range(1, 119):
    if 57 <= i <= 71:
        fixed.append(LANTHANIDE_SYMBOLS[i - 57])
    elif 89 <= i <= 103:
        fixed.append(ACTINIDE_SYMBOLS[i - 89])
    else:
        # 非镧锕符号在 layout 中按原序排列
        idx = i - 1
        offset = 0
        for j in range(1, i):
            if 57 <= j <= 71 or 89 <= j <= 103:
                offset += 1
        fixed.append(list(layout.keys())[i - 1 - offset])

# 校验：固定顺序应与提取顺序一致（跳过镧锕）
extracted_order = list(layout.keys())
non_ln_ac = [s for s in fixed if s not in LANTHANIDE_SYMBOLS + ACTINIDE_SYMBOLS]
assert non_ln_ac == extracted_order, f"顺序不一致: {non_ln_ac[:5]} != {extracted_order[:5]}"

lines = [
    "# -*- coding: utf-8 -*-",
    '"""内置元素布局数据（从 mendeleev 1.2.0 提取，标准周期表数据）。',
    "",
    "结构:",
    "- ELEM_LAYOUT: {元素符号: [族号, 周期]}，仅含非镧系/锕系元素",
    "  （镧系/锕系在原脚本中由布局逻辑特殊处理）",
    "- ALL_SYMBOLS: 按原子序数排列的全部 118 个元素符号",
    '"""',
    "",
    "# 非镧系/锕系元素的 [族号, 周期]",
    "ELEM_LAYOUT = {",
]
for sym, gp in layout.items():
    lines.append(f"    {sym!r}: {gp},")
lines.append("}")
lines.append("")
lines.append("# 按原子序数排列的全部 118 个元素符号")
lines.append("ALL_SYMBOLS = [")
for i, sym in enumerate(fixed, start=1):
    comma = "," if i < 118 else ""
    lines.append(f"    {sym!r}{comma}")
lines.append("]")
lines.append("")

out_path = os.path.join(here, "..", "core", "elements_data.py")
with open(out_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print(f"生成 {out_path}，含 {len(layout)} 个布局条目、{len(fixed)} 个符号")
