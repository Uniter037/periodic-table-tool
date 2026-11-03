import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from mendeleev import element

# 绘制热力图数据
plot_data = {'O': 9, 'Te': 9, 'F': 9, 'S': 9, 'Na': 9, 'K': 9, 'N': 8, 'Li': 8,
             'I': 8, 'Rb': 8, 'Si': 7, 'Cd': 7, 'Cl': 7, 'Zn': 7, 'H': 7,
             'Bi': 7, 'Br': 7, 'P': 6, 'Sn': 6, 'Ca': 6, 'Au': 6, 'Al': 5,
             'As': 5, 'Ga': 5, 'C': 5, 'Ge': 5, 'Sr': 5, 'Se': 5, 'Be': 5,
             'B': 5, 'Cs': 5, 'Mg': 5, 'Ag': 5, 'Pb': 4, 'In': 4, 'Ti': 4,
             'Cu': 4, 'Zr': 4, 'Sb': 4, 'Tl': 4, 'Sc': 4, 'Y': 4, 'Hg': 4,
             'Ba': 4, 'La': 4, 'Hf': 4, 'Og': 1}

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
cmap = mpl.colormaps['YlOrRd']
cmap.set_under('none')
norm = Normalize(1, 10)
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
            facecolor=cmap(norm(value)) if value else 'none'
        )
        ax.add_patch(rect)

    # 添加文字
    text_props = {
        'fontfamily': 'Helvetica',
        'color': 'black',
        'va': 'center',
        'ha': 'center'
    }

    if num:
        ax.text(x + 0.04, y + 0.8, str(num),
                fontsize=6, ha='left', **text_props)

    ax.text(x + 0.5, y + 0.5, symbol,
            fontsize=9, weight='bold', **text_props)

    if value:
        ax.text(x + 0.5, y + 0.12, str(value),
                fontsize=6, **text_props)

plt.tight_layout()
plt.savefig('./periodic_table.svg', bbox_inches='tight')
plt.show()