import matplotlib.patches as patches
import matplotlib.pyplot as plt
from mendeleev import element

# 用户提供的底部标注数据（键为元素符号，值为要显示的文本）
bottom_labels = {
'Sc': '3c1', 'Y': '3c2', 'Ti': '1b', 'Zr': '3c1', 'Hf': '3c1', 'V': '1b', 'Nb': '3c1', 'Ta': '3c2', 'Cr': '3c2', 'Mo': '1b', 'W': '1c', 'Mn': '1c', 'Tc': '1c', 'Re': '1c', 'Fe': '1a', 'Ru': '1b', 'Os': '1b', 'Co': '1a', 'Rh': '1c', 'Ir': '1a', 'Ni': '1b', 'Pd': '3c2', 'Pt': '3c1', 'Cu': '3c2', 'Ag': '3c1', 'Au': '3c2', 'Zn': '3c2', 'Cd': '3c1', 'Mg': '3c1', 'Al': '1b', 'Ga': '1b', 'Ge': '1c'

}

# 元素周期表布局配置
cell_length = 1
cell_gap = 0.1

# 获取元素数据（跳过镧系和锕系）
elements = []
for i in range(1, 119):
    if (57 <= i <= 71) or (89 <= i <= 103):
        continue
    ele = element(i)
    ele_group, ele_period = ele.group_id, ele.period

    # 处理可能缺失的族号
    if ele_group is None:
        ele_group = 0

    # 从用户数据中获取底部标注（若不存在则设为 None，表示不显示）
    bottom_text = bottom_labels.get(ele.symbol, None)

    elements.append([
        i,
        ele.symbol,
        ele_group,
        ele_period,
        bottom_text   # 自定义底部标注，可能为 None
    ])

# 添加镧系和锕系的标注块（使用元组存储三行文本）
markers = [
    [None, ('57~71 ', 'La~Lu', 'Lanthanide'), 3, 6, None],  # 第6周期第3族
    [None, ('86~103', 'Ac~Lr', 'Actinide'),   3, 7, None]   # 第7周期第3族
]
elements.extend(markers)

# 计算画布大小
max_period = max(elem[3] for elem in elements if elem[3] is not None)
xy_bounds = (20, (cell_length + cell_gap) * max_period + 1)

# 初始化画布
fig, ax = plt.subplots(figsize=(10, 5))
ax.set_xlim(0, xy_bounds[0])
ax.set_ylim(0, xy_bounds[1])
ax.set_aspect('equal')
ax.axis('off')

# 绘制元素格子和文字
for elem in elements:
    num, symbol, group, period, label = elem

    if group is None:
        continue

    x = (cell_length + cell_gap) * (group - 1)
    y = xy_bounds[1] - (cell_length + cell_gap) * period

    # 所有格子背景统一为浅灰色
    rect = patches.Rectangle(
        (x, y), cell_length, cell_length,
        linewidth=0, edgecolor='none', facecolor='#f0f0f0'
    )
    ax.add_patch(rect)

    # 文本通用属性（不含颜色）
    text_props = {
        'fontfamily': 'Arial',
        'va': 'center',
        'ha': 'center'
    }

    if num is not None:
        # 普通元素：原子序数（左上，黑色）
        ax.text(x + 0.2, y + 0.8, str(num), fontsize=6, color='black', **text_props)
        # 元素符号（正中，黑色，加粗）
        ax.text(x + 0.5, y + 0.5, symbol, fontsize=9, weight='bold', color='black', **text_props)
        # 底部标注：如果存在数据，则显示为深灰色（8pt），否则不显示
        if label is not None:
            ax.text(x + 0.5, y + 0.12, label, fontsize=8, color='#666666', **text_props)
    else:
        # 标注块：三行独立文本
        line1, line2, line3 = symbol
        # 第一行（范围）—— 对应原子序数位置（黑色）
        ax.text(x + 0.4, y + 0.8, line1, fontsize=6, color='black', **text_props)
        # 第二行（符号范围）—— 对应元素符号位置（黑色，加粗）
        ax.text(x + 0.5, y + 0.5, line2, fontsize=9, weight='bold', color='black', **text_props)
        # 第三行（系列名称）—— 对应底部标注位置（深灰色，字号8pt）
        ax.text(x + 0.5, y + 0.12, line3, fontsize=7, color='#666666', **text_props)

plt.tight_layout()
plt.savefig('./periodic_table.svg', bbox_inches='tight')
plt.show()