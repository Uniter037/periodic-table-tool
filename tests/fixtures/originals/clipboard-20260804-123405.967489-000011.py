import matplotlib as mpl
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from mendeleev import element

# 要标注的数据
label_data = {'Sc': '3c1', 'Y': '3c2', 'Ti': '1b', 'Zr': '3c1', 'Hf': '3c1', 'V': '1b', 'Nb': '3c1', 'Ta': '3c2', 'Cr': '3c2', 'Mo': '1b', 'W': '1c', 'Mn': '1c', 'Tc': '1c', 'Re': '1c', 'Fe': '1a', 'Ru': '1b', 'Os': '1b', 'Co': '1a', 'Rh': '1c', 'Ir': '1a', 'Ni': '1b', 'Pd': '3c2', 'Pt': '3c1', 'Cu': '3c2', 'Ag': '3c1', 'Au': '3c2', 'Zn': '3c2', 'Cd': '3c1', 'Mg': '3c1', 'Al': '1b', 'Ga': '1b', 'Ge': '1c'
              }

# 元素周期表布局配置
cell_length = 1
cell_gap = 0.1
cell_edge_width = 0.5

# 获取元素数据
elements = []
for i in range(1, 119):
    ele = element(i)
    ele_group, ele_period = ele.group_id, ele.period

    # 调整镧系和锕系位置
    if 57 <= i <= 71:
        ele_group = i - 57 + 3
        ele_period = 8
    elif 89 <= i <= 103:
        ele_group = i - 89 + 3
        ele_period = 9

    elements.append([
        i,
        ele.symbol,
        ele_group if ele_group is not None else 0,  # 处理可能的None值
        ele_period,
        label_data.get(ele.symbol, None)  # 获取标注数据
    ])

# 添加定位标记
markers = [
    [None, 'LA', 3, 6, None],
    [None, 'AC', 3, 7, None],
    [None, 'LA', 2, 8, None],
    [None, 'AC', 2, 9, None]
]
elements.extend(markers)

# 初始化画布
fig, ax = plt.subplots(figsize=(10, 5))
xy_bounds = (20, 11)
ax.set_xlim(0, xy_bounds[0])
ax.set_ylim(0, xy_bounds[1])
ax.set_aspect('equal')
ax.axis('off')

# 绘制元素格子
for elem in elements:
    num, symbol, group, period, label = elem

    if group is None:
        continue

    # 计算坐标
    x = (cell_length + cell_gap) * (group - 1)
    y = xy_bounds[1] - (cell_length + cell_gap) * period

    # 调整镧系锕系位置
    if period >= 8:
        y -= cell_length * 0.5

    # 绘制格子
    if num is not None:
        rect_color = '#73C0ED' if label else '#f0f0f0'  # 有标注的元素用深蓝色，无标注的用淡灰色
        rect = patches.Rectangle(
            (x, y), cell_length, cell_length,
            linewidth=0,  # 去除边框
            edgecolor='none',  # 去除边框颜色
            facecolor=rect_color
        )
        ax.add_patch(rect)

    # 添加文字
    text_props = {
        'fontfamily': 'Arial',
        'va': 'center',
        'ha': 'center'  # 将 ha 参数统一放在这里
    }

    # 根据格子颜色调整字体颜色
    text_color = 'white' if label else 'black'

    # 添加原子序数
    if num:
        ax.text(x + 0.2, y + 0.8, str(num),
                fontsize=6, color=text_color, **text_props)

    # 添加元素符号
    ax.text(x + 0.5, y + 0.5, symbol,
            fontsize=9, weight='bold', color=text_color, **text_props)

    # 添加自定义文字标注（放大字号）
    if label:
        ax.text(x + 0.5, y + 0.14, label,
                fontsize=8, color=text_color, **text_props)

plt.tight_layout()
plt.savefig('./periodic_table.svg', bbox_inches='tight')
plt.show()