import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from mendeleev import element

# 绘制热力图数据
plot_data = {
    'Ag': 0.0101, 'Au': 0.0111, 'Pd': 0.0112, 'Pt': 0.0119, 'Cd': 0.0113, 'Co': 0.0104, 'Cr': 0.0121, 'Cu': 0.0110, 'Fe': 0.0115, 'Ir': 0.0135, 'Mn': 0.0118, 'Mo': 0.0095, 'Os': 0.0120, 'Re': 0.0123, 'Rh': 0.0115, 'Ru': 0.0109, 'Tc': 0.0110, 'Ti': 0.0109, 'W': 0.0114, 'Zn': 0.0103, 'Al': 0.0114, 'Mg': 0.0113, 'Zr': 0.0112, 'Ga': 0.0092, 'Ge': 0.0059, 'Nb': 0.0128, 'Ni': 0.0089, 'Sc': 0.0110, 'Ta': 0.0142, 'V': 0.0119, 'Y': 0.0107
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
# colors = [(0, 0, 1), (1, 1, 1), (1, 0, 0)
colors = [(0.1726, 0.2941, 0.4588), (1, 1, 1), (0.5686, 0.1333, 0.1098)]
cmap = LinearSegmentedColormap.from_list('custom_cmap', colors)
norm = TwoSlopeNorm(vmin=0.0048, vcenter=0.0125, vmax=0.0142)
mappable = cm.ScalarMappable(norm=norm, cmap=cmap)

# 创建颜色条
cbar = fig.colorbar(mappable, ax=ax, drawedges=False, orientation='vertical', fraction=0.046, pad=0.04)
cbar.set_ticks([0.0048, 0.0125, 0.0142])
cbar.set_ticklabels(['0.48%', '1.25%', '1.42%'])
cbar.ax.set_yticklabels(['0.48%', '1.25%', '1.42%'], fontsize=8)

# 绘制元素格子和文字
for elem in elements:
    num, symbol, group, period, value = elem

    if group is None:
        continue

    # 根据族和周期计算元素格子的画布坐标位置
    x = (cell_length + cell_gap) * (group - 1)
    y = xy_bounds[1] - (cell_length + cell_gap) * period

    # 根据元素类型设置矩形样式：普通元素使用热力图颜色，标注块使用统一背景色
    if num is not None:
        edgecolor = 'none'
        linewidth = 0
        facecolor = cmap(norm(value)) if value else '#f0f0f0'
    else:
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
            formatted_value = f"{value * 100:.2f}%"
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