import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from mendeleev import element

# 绘制热力图数据
plot_data = {  'Sc': 0.02631, 'Y': 0.01993, 'Ti': 0.00854, 'Zr': 0.02513, 'Hf': 0.03409,
    'V': 0.04348, 'Nb': 0.04132, 'Ta': 0.03714, 'Cr': 0.03544, 'Mo': 0.0061,
    'W': 0.00981, 'Mn': 0.04773, 'Tc': 0.01885, 'Re': 0.00753, 'Fe': 0.01284,
    'Ru': 0.03721, 'Os': 0.01031, 'Co': 0.03128, 'Rh': 0.01512, 'Ir': 0.01961,
    'Ni': 0.02203, 'Pd': 0.03444, 'Pt': 0.0386, 'Cu': 0.03278, 'Ag': 0.03364,
    'Au': 0.03685, 'Zn': 0.03727, 'Cd': 0.03297, 'Hg': 0.03558, 'Al': 0.01879,
    'Mg': 0.000197}

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
        plot_data.get(ele.symbol, 0)
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

# 配置颜色映射
cmap = mpl.colormaps['YlGn']
cmap.set_under('w')  # 将没有数据的格子设置为 darkgrey 颜色
norm = Normalize(0, 0.05)
mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
fig.colorbar(mappable, ax=ax, drawedges=False)

# 绘制元素格子
for elem in elements:
    num, symbol, group, period, value = elem

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
        rect = patches.Rectangle(
            (x, y), cell_length, cell_length,
            linewidth=cell_edge_width,
            edgecolor='black',
            facecolor=cmap(norm(value)) if value else 'w'  # 如果没有数据，显示 darkgrey
        )
        ax.add_patch(rect)

    # 添加文字
    text_props = {
        'fontfamily': 'Arial',
        'color': 'black',
        'va': 'center',
        'ha': 'center'  # 将 ha 参数统一放在这里
    }

    if num:
        ax.text(x + 0.2, y + 0.8, str(num),
                fontsize=6, **text_props)  # 不再单独指定 ha='left'

    ax.text(x + 0.5, y + 0.5, symbol,
            fontsize=9, weight='bold', **text_props)

    if value:
        ax.text(x + 0.5, y + 0.12, str(value),
                fontsize=6, **text_props)

plt.tight_layout()
plt.savefig('./periodic_table.svg', bbox_inches='tight')
plt.show()