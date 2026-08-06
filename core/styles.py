# -*- coding: utf-8 -*-
"""绘图样式定义与渲染核心。

13 种样式逐一对应原始脚本，参数与原脚本保持完全一致
（布局、颜色映射、归一化、字体、边框、刻度、空值格颜色等），
保证渲染结果与输入文件一致。另加 1 种"自定义"扩展样式。
"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.cm as cm
import matplotlib.patches as patches
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm

from .ptable import build_elements, xy_bounds_for, CELL_STEP

# ---------------------------------------------------------------------------
# 样式定义
# ---------------------------------------------------------------------------

# 重构系列统一使用的自定义颜色（蓝 -> 白 -> 红）
CUSTOM_BWR = [(0.1726, 0.2941, 0.4588), (1, 1, 1), (0.5686, 0.1333, 0.1098)]
# 图9 使用的经典蓝 -> 白 -> 红
CLASSIC_BWR = [(0, 0, 1), (1, 1, 1), (1, 0, 0)]


def _cbar_standard(ticks, labels, fontsize=8):
    """colorbar 标准样式（重构系列 / 图6、8、9 等）：fraction=0.046, pad=0.04。"""
    return {
        "ticks": ticks,
        "labels": labels,
        "fontsize": fontsize,
    }


STYLES = {
    # ---------------- 重构系列（文件 1~3）----------------
    "reconstruct_percent": {
        "id": "reconstruct_percent",
        "name": "蓝白红·百分比热力图（镧锕三行块）",
        "file": "Hui_Tu_Chong_gou_1-260227.py",
        "layout": "reconstructed",
        "kind": "heatmap",
        "cmap": ("custom", CUSTOM_BWR),
        "norm": ("twoslope", 0.0048, 0.0125, 0.0142),
        "fmt": "percent2",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": _cbar_standard([0.0048, 0.0125, 0.0142],
                               ["0.48%", "1.25%", "1.42%"]),
        "cbar_style": "standard",
    },
    "reconstruct_2f_a": {
        "id": "reconstruct_2f_a",
        "name": "蓝白红·两位小数热力图 A（镧锕三行块）",
        "file": "Hui_Tu_Chong_gou_2-260303.py",
        "layout": "reconstructed",
        "kind": "heatmap",
        "cmap": ("custom", CUSTOM_BWR),
        "norm": ("twoslope", -64.95, -38.53, -12.11),
        "fmt": "2f",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": _cbar_standard([-64.95, -38.53, -12.11],
                               ["", "-38.53", "-12.11"]),
        "cbar_style": "standard",
    },
    "reconstruct_2f_b": {
        "id": "reconstruct_2f_b",
        "name": "蓝白红·两位小数热力图 B（镧锕三行块）",
        "file": "Hui_Tu_Chong_gou_3-260303 - 副本.py",
        "layout": "reconstructed",
        "kind": "heatmap",
        "cmap": ("custom", CUSTOM_BWR),
        "norm": ("twoslope", -26.68, -21.81, 1.98),
        "fmt": "2f",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": _cbar_standard([-26.68, -21.81, 1.98],
                               ["-26.68", "-21.81", "1.98"]),
        "cbar_style": "standard",
    },
    # ---------------- 明城系列（文件 4）----------------
    "labels_light": {
        "id": "labels_light",
        "name": "浅灰底·文本标注图（镧锕三行块）",
        "file": "Hui_Tu_Min_Cheng_01.py",
        "layout": "reconstructed",
        "kind": "labels",
        "font": "Arial",
        "edge": None,
        "bg": "#f0f0f0",
        "label_color": "#666666",
        "label_fs": 8,
        "label_dy": 0.12,
    },
    # ---------------- 经典系列：图1~9（文件 5~13）----------------
    "classic_ylorrd_orig": {
        "id": "classic_ylorrd_orig",
        "name": "橙黄红·整数热力图（黑框·原始版）",
        "file": "Hui_Tu-1.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "YlOrRd",
        "norm": ("normalize", 1, 10),
        "under": "None",
        "fmt": "raw",
        "font": "Helvetica",
        "edge": (0.5, "black"),
        "empty": "none",          # 0 值绘制 under 色（透明）
        "cbar": None,
        "cbar_style": "plain",    # 原脚本 plt.colorbar(cmmapable, drawedges=False)
        "num_x": 0.04,
        "num_ha": "left",
        "text_always": True,      # 原脚本：对标记元素也绘制三行文本
        "bbox_tight": False,
    },
    "classic_ylorrd": {
        "id": "classic_ylorrd",
        "name": "橙黄红·整数热力图（黑框·重构版）",
        "file": "Hui_Tu-2.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "YlOrRd",
        "norm": ("normalize", 1, 10),
        "under": "none",
        "fmt": "raw",
        "font": "Helvetica",
        "edge": (0.5, "black"),
        "empty": "none",
        "cbar": None,
        "cbar_style": "ax_plain",   # fig.colorbar(mappable, ax=ax, drawedges=False)
        "num_x": 0.04,
        "num_ha": "left",
        "text_always": False,
        "bbox_tight": True,
    },
    "classic_blues": {
        "id": "classic_blues",
        "name": "蓝色系·整数热力图（黑框）",
        "file": "Hui_Tu-3.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "Blues",
        "norm": ("normalize", 1, 10),
        "under": "none",
        "fmt": "raw",
        "font": "Arial",
        "edge": (0.5, "black"),
        "empty": "none",
        "cbar": None,
        "cbar_style": "ax_plain",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
    },
    "cmap_preview": {
        "id": "cmap_preview",
        "name": "色图预览器（生成全部色图）",
        "file": "Hui_Tu-4.py",
        "layout": "classic",
        "kind": "cmap",
        "cmap": "viridis",
        "norm": None,
        "fmt": "raw",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": None,
        "cbar_style": "standard",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
    },
    "classic_ylgn": {
        "id": "classic_ylgn",
        "name": "绿色系·原始数值热力图（黑框）",
        "file": "Hui_Tu-5.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "YlGn",
        "norm": ("normalize", 0, 0.05),
        "under": "w",
        "fmt": "raw",
        "font": "Arial",
        "edge": (0.5, "black"),
        "empty": "w",
        "cbar": None,
        "cbar_style": "ax_plain",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
    },
    "classic_coolwarm": {
        "id": "classic_coolwarm",
        "name": "红蓝冷暖·两位小数热力图（无框）",
        "file": "Hui_Tu-6.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "coolwarm",
        "norm": ("twoslope", -0.05, 0, 0.05),
        "fmt": "2f",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": _cbar_standard([0.61, 0.73, 0.77],
                               ["0.61", "0.73", "0.77"]),
        "cbar_style": "standard",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
    },
    "classic_coolwarm3": {
        "id": "classic_coolwarm3",
        "name": "红蓝冷暖·三位小数热力图（无框）",
        "file": "Hui_Tu8.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "coolwarm",
        "norm": ("twoslope", 0.61, 0.73, 0.77),
        "fmt": "3f",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": _cbar_standard([0.61, 0.73, 0.77],
                               ["0.61", "0.73", "0.77"]),
        "cbar_style": "standard",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
    },
    "classic_bwr3": {
        "id": "classic_bwr3",
        "name": "经典蓝白红·三位小数热力图（无框）",
        "file": "Hui_Tu-9.py",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": ("custom", CLASSIC_BWR),
        "norm": ("twoslope", 0, 0.03268, 0.05),
        "fmt": "3f",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": _cbar_standard([0.000, 0.033, 0.050],
                               ["0.000", "0.033", "0.050"]),
        "cbar_style": "standard",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
    },
    # ---------------- 标注系列（文件 11）----------------
    "labels_highlight": {
        "id": "labels_highlight",
        "name": "高亮标注图（深蓝底白字）",
        "file": "Hui_Tu-7.py",
        "layout": "classic",
        "kind": "labels",
        "font": "Arial",
        "edge": None,
        "highlight_bg": "#73C0ED",
        "highlight_fg": "white",
        "plain_bg": "#f0f0f0",
        "plain_fg": "black",
        "label_fs": 8,
        "label_dy": 0.14,
        "text_always": False,
        "bbox_tight": True,
    },
    # ---------------- 自定义（扩展）----------------
    "custom": {
        "id": "custom",
        "name": "自定义热力图（全部参数可调）",
        "file": "扩展功能",
        "layout": "classic",
        "kind": "heatmap",
        "cmap": "coolwarm",
        "norm": ("twoslope", 0.6, 0.73, 0.78),
        "fmt": "3f",
        "font": "Arial",
        "edge": None,
        "empty": "#f0f0f0",
        "cbar": None,
        "cbar_style": "standard",
        "num_x": 0.2,
        "num_ha": "center",
        "text_always": False,
        "bbox_tight": True,
        "customizable": True,
    },
}

# 图4（文件8）使用的全部 matplotlib 颜色映射列表（修正原脚本 'pectral' 笔误）
CMAP_PREVIEW_LIST = [
    'Accent', 'Accent_r', 'Blues', 'Blues_r', 'BrBG', 'BrBG_r',
    'BuGn', 'BuGn_r', 'BuPu', 'BuPu_r', 'CMRmap', 'CMRmap_r',
    'Dark2', 'Dark2_r', 'GnBu', 'GnBu_r', 'Grays', 'Greens', 'Greens_r',
    'Greys', 'Greys_r', 'OrRd', 'OrRd_r', 'Oranges', 'Oranges_r',
    'PRGn', 'PRGn_r', 'Paired', 'Paired_r', 'Pastel1', 'Pastel1_r',
    'Pastel2', 'Pastel2_r', 'PiYG', 'PiYG_r', 'PuBu', 'PuBuGn', 'PuBuGn_r', 'PuBu_r',
    'PuOr', 'PuOr_r', 'PuRd', 'PuRd_r', 'Purples', 'Purples_r', 'RdBu', 'RdBu_r',
    'RdGy', 'RdGy_r', 'RdPu', 'RdPu_r', 'RdYlBu', 'RdYlBu_r', 'RdYlGn', 'RdYlGn_r',
    'Reds', 'Reds_r', 'Set1', 'Set1_r', 'Set2', 'Set2_r', 'Set3', 'Set3_r',
    'Spectral', 'Spectral_r', 'Wistia', 'Wistia_r', 'YlGn', 'YlGnBu', 'YlGnBu_r', 'YlGn_r',
    'YlOrBr', 'YlOrBr_r', 'YlOrRd', 'YlOrRd_r', 'afmhot', 'afmhot_r', 'autumn', 'autumn_r',
    'binary', 'binary_r', 'bone', 'bone_r', 'brg', 'brg_r', 'bwr', 'bwr_r', 'cividis',
    'cividis_r', 'cool', 'cool_r', 'coolwarm', 'coolwarm_r', 'copper', 'copper_r',
    'cubehelix', 'cubehelix_r', 'flag', 'flag_r', 'gist_earth', 'gist_earth_r',
    'gist_gray', 'gist_gray_r', 'gist_grey', 'gist_heat', 'gist_heat_r', 'gist_ncar',
    'gist_ncar_r', 'gist_rainbow', 'gist_rainbow_r', 'gist_stern', 'gist_stern_r',
    'gist_yarg', 'gist_yarg_r', 'gist_yerg', 'gnuplot', 'gnuplot2', 'gnuplot2_r',
    'gnuplot_r', 'gray', 'gray_r', 'grey', 'hot', 'hot_r', 'hsv', 'hsv_r', 'inferno',
    'inferno_r', 'jet', 'jet_r', 'magma', 'magma_r', 'nipy_spectral', 'nipy_spectral_r',
    'ocean', 'ocean_r', 'pink', 'pink_r', 'plasma', 'plasma_r', 'prism', 'prism_r',
    'rainbow', 'rainbow_r', 'seismic', 'seismic_r', 'spring', 'spring_r', 'summer',
    'summer_r', 'tab10', 'tab10_r', 'tab20', 'tab20_r', 'tab20b', 'tab20b_r', 'tab20c',
    'tab20c_r', 'terrain', 'terrain_r', 'turbo', 'turbo_r', 'twilight', 'twilight_r',
    'twilight_shifted', 'twilight_shifted_r', 'viridis', 'viridis_r', 'winter', 'winter_r',
]


# ---------------------------------------------------------------------------
# 渲染核心
# ---------------------------------------------------------------------------

def _make_cmap(style):
    """根据样式配置创建颜色映射对象。"""
    spec = style["cmap"]
    if isinstance(spec, tuple) and spec[0] == "custom":
        cmap = LinearSegmentedColormap.from_list("custom_cmap", spec[1])
    else:
        # 校验：仅接受已注册的颜色映射名称。
        # matplotlib 3.6+ 的 ColormapRegistry 会对未命中名称尝试按
        # "module:qualname" 解析（触发 importlib.import_module），
        # 白名单校验可避免任意模块加载。
        if not isinstance(spec, str) or ":" in spec or spec not in mpl.colormaps:
            raise ValueError(f"未知颜色映射: {spec!r}")
        cmap = mpl.colormaps[spec]
    under = style.get("under")
    if under is not None:
        cmap.set_under(under)
    return cmap


def _make_norm(style):
    """根据样式配置创建归一化对象。"""
    spec = style["norm"]
    if spec is None:
        return None
    if spec[0] == "twoslope":
        _, vmin, vcenter, vmax = spec
        return TwoSlopeNorm(vmin=vmin, vcenter=vcenter, vmax=vmax)
    if spec[0] == "normalize":
        _, vmin, vmax = spec
        return Normalize(vmin, vmax)
    raise ValueError(f"未知归一化: {spec[0]}")


def _fmt_value(value, fmt):
    """按样式格式化数值文本。"""
    if fmt == "percent2":
        return f"{value * 100:.2f}%"
    if fmt == "2f":
        return f"{value:.2f}"
    if fmt == "3f":
        return f"{value:.3f}"
    if fmt == "4f":
        return f"{value:.4f}"
    return str(value)   # raw / g


def render_table(style: dict, data: dict, title: str = None,
                 show_cbar: bool = True, figsize=(10, 5)):
    """渲染元素周期表（热力图或标注图），返回 matplotlib Figure。

    :param style:      STYLES 中的样式字典
    :param data:       数据字典，{元素符号: 值}；标注类模式值为字符串
    :param title:      可选图标题（仅自定义模式使用；原脚本无标题）
    :param show_cbar:  是否显示颜色条（False 时不创建 colorbar；原脚本行为为 True）
    :param figsize:    图尺寸（英寸，宽, 高）；默认 (10, 5) 与原脚本一致
    """
    layout = style["layout"]
    elements = build_elements(layout, data)
    xy_bounds = xy_bounds_for(layout)
    kind = style["kind"]

    fig, ax = plt.subplots(figsize=figsize)
    ax.set_xlim(0, xy_bounds[0])
    ax.set_ylim(0, xy_bounds[1])
    ax.set_aspect("equal")
    ax.axis("off")

    # ---- 颜色映射 / 归一化 / 颜色条（与原脚本一样先建颜色条）----
    cmap = norm = mappable = cbar = None
    if kind == "heatmap":
        cmap = _make_cmap(style)
        norm = _make_norm(style)
        mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
        if show_cbar:
            cbar_style = style.get("cbar_style", "standard")
            if cbar_style == "plain":
                # 图1：plt.colorbar(cmmapable, drawedges=False)
                # （matplotlib 3.11 起需显式 ax，否则报错）
                cbar = fig.colorbar(mappable, ax=ax, drawedges=False)
            elif cbar_style == "ax_plain":
                # 图2/3/5：fig.colorbar(mappable, ax=ax, drawedges=False)
                cbar = fig.colorbar(mappable, ax=ax, drawedges=False)
            else:
                # 重构系列 / 图6/8/9：fraction=0.046, pad=0.04, vertical
                cbar = fig.colorbar(mappable, ax=ax, drawedges=False,
                                    orientation="vertical", fraction=0.046, pad=0.04)
            if style.get("cbar"):
                cfg = style["cbar"]
                cbar.set_ticks(cfg["ticks"])
                cbar.set_ticklabels(cfg["labels"])
                cbar.ax.set_yticklabels(cfg["labels"], fontsize=cfg["fontsize"])

    # ---- 通用绘制参数 ----
    edge = style.get("edge")
    font = style.get("font", "Arial")
    text_always = style.get("text_always", False)
    num_x = style.get("num_x", 0.2)
    num_ha = style.get("num_ha", "center")

    # ---- 绘制格子与文本 ----
    for elem in elements:
        num, symbol, group, period, value = elem
        if group is None:
            continue

        x = CELL_STEP * (group - 1)
        y = xy_bounds[1] - CELL_STEP * period
        if period >= 8:                     # 镧系/锕系行上移半格
            y -= 0.5

        # ----- 格子 -----
        # 注意：重构系列的原脚本对镧系/锕系标注块（symbol 为 tuple、num 为 None）
        # 也画一个浅灰背景格子（add_patch 无条件执行）；经典系列的 LA/AC 标记不画。
        draw_cell = num is not None or isinstance(symbol, tuple)
        if draw_cell:
            if kind == "heatmap":
                if text_always:
                    # 图1：所有有原子序数的元素都画矩形（0 值 → under 色）
                    facecolor = cmap(norm(value))
                else:
                    facecolor = cmap(norm(value)) if value else style["empty"]
            elif kind == "labels":
                if "highlight_bg" in style:
                    facecolor = style["highlight_bg"] if value else style["plain_bg"]
                else:
                    facecolor = style.get("bg", "#f0f0f0")

            if edge:
                lw, ec = edge
            else:
                lw, ec = 0, "none"

            rect = patches.Rectangle((x, y), 1, 1,
                                     linewidth=lw, edgecolor=ec, facecolor=facecolor)
            ax.add_patch(rect)

        # ----- 文本 -----
        # 注意：text_props 只含 fontfamily / va（ha 与 color 均显式传递），
        # 避免与原脚本中"显式 ha / color + 重复键"的 bug 冲突。
        text_props = {"fontfamily": font, "va": "center"}

        if kind == "heatmap":
            base_color = "black"
        elif kind == "labels":
            if "highlight_bg" in style:
                base_color = style["highlight_fg"] if value else style["plain_fg"]
            else:
                base_color = "black"

        if num is not None:
            ax.text(x + num_x, y + 0.8, str(num), fontsize=6, ha=num_ha,
                    color=base_color, **text_props)
        elif text_always:
            # 图1 原行为：对标记元素也画文本（matplotlib 将 None 显示为空）
            ax.text(x + num_x, y + 0.8, num, fontsize=6, ha=num_ha,
                    color=base_color, **text_props)

        if isinstance(symbol, tuple):
            # 重构系列的三行标注块
            line1, line2, line3 = symbol
            if kind == "labels":
                ax.text(x + 0.4, y + 0.8, line1, fontsize=6, ha="center",
                        color="black", **text_props)
                ax.text(x + 0.5, y + 0.5, line2, fontsize=9, weight="bold",
                        ha="center", color="black", **text_props)
                ax.text(x + 0.5, y + 0.12, line3, fontsize=7,
                        color=style.get("label_color", "#666666"), ha="center", **text_props)
            else:
                ax.text(x + 0.4, y + 0.8, line1, fontsize=6, ha="center",
                        color="black", **text_props)
                ax.text(x + 0.5, y + 0.5, line2, fontsize=9, weight="bold",
                        ha="center", color="black", **text_props)
                ax.text(x + 0.5, y + 0.12, line3, fontsize=6, ha="center",
                        color="black", **text_props)
        else:
            ax.text(x + 0.5, y + 0.5, symbol, fontsize=9, weight="bold",
                    ha="center", color=base_color, **text_props)

            if kind == "heatmap" and text_always:
                # 图1 原行为：无条件绘制数值文本（0 值显示 '0'，None 显示空）
                if value is None:
                    ax.text(x + 0.5, y + 0.12, None, fontsize=6, ha="center",
                            color=base_color, **text_props)
                else:
                    ax.text(x + 0.5, y + 0.12, _fmt_value(value, style["fmt"]),
                            fontsize=6, ha="center", color=base_color, **text_props)
            elif kind == "heatmap" and value:
                text = _fmt_value(value, style["fmt"])
                ax.text(x + 0.5, y + 0.12, text, fontsize=6, ha="center",
                        color=base_color, **text_props)
            elif kind == "labels" and value:
                if "highlight_bg" in style:
                    # 高亮标注：文字颜色随格子（深蓝底白字 / 浅灰底黑字）
                    label_color = base_color
                else:
                    # 浅灰底标注（明城01）：标注文本为深灰色 #666666
                    label_color = style.get("label_color", "#666666")
                ax.text(x + 0.5, y + style.get("label_dy", 0.12), value,
                        fontsize=style.get("label_fs", 8), ha="center",
                        color=label_color, **text_props)

    if title:
        fig.suptitle(title, fontsize=14)

    plt.tight_layout()
    return fig


def render_cmap_preview(out_dir: str, cmaps=None):
    """图4：生成所有（或指定）matplotlib 颜色映射的预览图。

    返回实际生成的文件路径列表。
    """
    import numpy as np
    from .saver import auto_name

    data = np.random.rand(10, 10)
    if cmaps is None:
        cmaps = CMAP_PREVIEW_LIST

    generated = []
    skipped = []
    for color_map in cmaps:
        if color_map not in mpl.colormaps:
            skipped.append(color_map)
            continue
        fig, ax = plt.subplots()
        im = ax.imshow(data, cmap=color_map)
        fig.colorbar(im, ax=ax)
        ax.set_title(color_map)
        path = auto_name(out_dir, f"cmap_{color_map}", "png")
        fig.savefig(path)
        plt.close(fig)
        generated.append(path)

    if skipped:
        print(f"[警告] 跳过的无效颜色映射: {', '.join(skipped)}")
    return generated
