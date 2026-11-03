import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from mendeleev import element

# 绘制热力图数据
plot_data = {
    'Sc': 0.74, 'Y': 0.75, 'Ti': 0.74, 'Zr': 0.75, 'Hf': 0.74, 'V': 0.73, 'Nb': 0.73, 'Ta': 0.74, 'Cr': 0.74,
    'Mo': 0.73, 'W': 0.73, 'Mn': 0.73, 'Tc': 0.73, 'Re': 0.73, 'Fe': 0.73, 'Ru': 0.74, 'Os': 0.74, 'Co': 0.73,
    'Rh': 0.74, 'Ir': 0.73, 'Ni': 0.73, 'Pd': 0.73, 'Pt': 0.74, 'Cu': 0.74, 'Ag': 0.73, 'Au': 0.74, 'Zn': 0.74,
    'Cd': 0.73, 'Hg': 0.74, 'Al': 0.74, 'Mg': 0.74
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
cmap = mpl.colormaps['coolwarm']  # 使用 coolwarm 颜色映射，两端颜色不同，中间为白色
norm = TwoSlopeNorm(vmin=-0.05, vcenter=0, vmax=0.05)  # 设置双斜率归一化，中间基准点为 0
mappable = cm.ScalarMappable(norm=norm, cmap=cmap)

# 创建颜色条
cbar = fig.colorbar(mappable, ax=ax, drawedges=False, orientation='vertical', fraction=0.046, pad=0.04)
cbar.set_ticks([0.61, 0.73, 0.77])  # 定义刻度位置
cbar.set_ticklabels(['0.61', '0.73', '0.77'])  # 定义刻度标签
cbar.ax.set_yticklabels(['0.61', '0.73', '0.77'], fontsize=8)  # 设置刻度字体大小

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
            linewidth=0,  # 去除边框
            edgecolor='none',  # 去除边框颜色
            facecolor=cmap(norm(value)) if value else '#f0f0f0'  # 如果没有数据，显示淡灰色
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