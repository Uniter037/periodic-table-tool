import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from mendeleev import element

# 绘制热力图数据
plot_data = {
    'Sc': -7.06, 'Y': -4.71,  'Zr': -4.88, 'Hf': -8.52, 'V': -2.87, 'Nb': -4.72, 'Ta': -3.81, 'Cr': -11.49,
    'Mo': -9.70, 'W': -8.64, 'Mn': -16.26, 'Tc': -16.56, 'Re': -10.48, 'Fe': -17.93, 'Ru': -16.73, 'Os': -16.20,
    'Co': -19.06, 'Rh': -17.28, 'Ir': -17.73, 'Pd': -18.80, 'Pt': -20.30, 'Cu': -20.81, 'Ag': -20.31,
    'Au': -18.92, 'Zn': -19.65, 'Cd': -22.21, 'Mg': -3.76, 'Al': -11.92, 'Ga': -6.39, 'Ge': -10.06
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

    # 调整镧系和锕系位置（此处已跳过，但保留原逻辑以防未来需要）
    if 57 <= i <= 71:
        ele_group = i - 57 + 3
        ele_period = 8
    elif 89 <= i <= 103:
        ele_group = i - 89 + 3
        ele_period = 9

    elements.append([
        i,
        ele.symbol,
        ele_group if ele_group is not None else 0,
        ele_period,
        plot_data.get(ele.symbol, 0)
    ])

# 添加镧系和锕系的标注块（使用元组存储三行文本）
markers = [
    [None, ('57~71 ', 'La~Lu', 'Lanthanide'), 3, 6, None],  # 第6周期第3族
    [None, ('86~103', 'Ac~Lr', 'Actinide'),   3, 7, None]   # 第7周期第3族
]
elements.extend(markers)

# 计算画布大小（根据实际最大周期）
max_period = max(elem[3] for elem in elements if elem[3] is not None)
xy_bounds = (20, (cell_length + cell_gap) * max_period + 1)  # 加一点边距

# 初始化画布
fig, ax = plt.subplots(figsize=(10, 5))
ax.set_xlim(0, xy_bounds[0])
ax.set_ylim(0, xy_bounds[1])
ax.set_aspect('equal')
ax.axis('off')

# 自定义颜色映射：蓝色 -> 白色 -> 红色
# colors = [(0, 0, 1), (1, 1, 1), (1, 0, 0)]
colors = [(0.1726, 0.2941, 0.4588), (1, 1, 1), (0.5686, 0.1333, 0.1098)]
cmap = LinearSegmentedColormap.from_list('custom_cmap', colors)
norm = TwoSlopeNorm(vmin=-26.68, vcenter=-21.81, vmax=1.98)
mappable = cm.ScalarMappable(norm=norm, cmap=cmap)

# 创建颜色条
cbar = fig.colorbar(mappable, ax=ax, drawedges=False, orientation='vertical', fraction=0.046, pad=0.04)
cbar.set_ticks([-26.68, -21.81 , 1.98 ])
cbar.set_ticklabels(['-26.68', '-21.81', '1.98'])
cbar.ax.set_yticklabels(['-26.68', '-21.81', '1.98'], fontsize=8)

# 绘制元素格子和文字
for elem in elements:
    num, symbol, group, period, value = elem

    if group is None:
        continue

    x = (cell_length + cell_gap) * (group - 1)
    y = xy_bounds[1] - (cell_length + cell_gap) * period

    # 绘制格子
    if num is not None:
        # 普通元素格子：无边框，颜色由数值决定
        edgecolor = 'none'
        linewidth = 0
        facecolor = cmap(norm(value)) if value else '#f0f0f0'
    else:
        # 标注块：无边框，背景色与其他无数据元素一致
        edgecolor = 'none'
        linewidth = 0
        facecolor = '#f0f0f0'

    rect = patches.Rectangle(
        (x, y), cell_length, cell_length,
        linewidth=linewidth, edgecolor=edgecolor, facecolor=facecolor
    )
    ax.add_patch(rect)

    # 文本通用属性
    text_props = {
        'fontfamily': 'Arial',
        'color': 'black',
        'va': 'center',
        'ha': 'center'
    }

    if num is not None:
        # 普通元素：原子序数
        ax.text(x + 0.2, y + 0.8, str(num), fontsize=6, **text_props)
        # 元素符号
        ax.text(x + 0.5, y + 0.5, symbol, fontsize=9, weight='bold', **text_props)
        # 数值（如果有数据）
        if value:
            formatted_value = f"{value:.2f}"
            ax.text(x + 0.5, y + 0.12, formatted_value, fontsize=6, **text_props)
    else:
        # 标注块：symbol 是一个元组 (line1, line2, line3)
        line1, line2, line3 = symbol
        # 第一行（范围）—— 对应原子序数位置和样式
        ax.text(x + 0.4, y + 0.8, line1, fontsize=6, **text_props)
        # 第二行（符号范围）—— 对应元素符号位置和样式
        ax.text(x + 0.5, y + 0.5, line2, fontsize=9, weight='bold', **text_props)
        # 第三行（系列名称）—— 对应数据值位置和样式
        ax.text(x + 0.5, y + 0.12, line3, fontsize=6, **text_props)

plt.tight_layout()
plt.savefig('./periodic_table.svg', bbox_inches='tight')
plt.show()