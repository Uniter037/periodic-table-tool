"""Explicit corrected rendering policy; legacy STYLES are never mutated."""
from copy import deepcopy
import math


def corrected_style(style):
    work = deepcopy(style)
    work.update(corrected=True, customizable=True, text_always=False, bbox_tight=False)
    # Original coolwarm script accidentally used +/- .05 for .73 data.
    if style.get("id") == "classic_coolwarm":
        work["norm"] = ("twoslope", .61, .73, .77)
    # Legacy transparent/white under-colors can hide a supplied zero.
    work.pop("under", None)
    return work


def colorbar_config(config):
    """Validate all rows; visibility affects rendering, never stored labels."""
    if config is None:
        return None
    if not isinstance(config, dict):
        raise ValueError("颜色条配置必须为字典")
    try:
        if any(not isinstance(config[key], (list, tuple)) for key in ("ticks", "labels")):
            raise ValueError("颜色条刻度和标签必须为列表")
        if "visible" in config and not isinstance(config["visible"], (list, tuple)):
            raise ValueError("颜色条显示状态必须为列表")
        ticks, labels = list(config["ticks"]), list(config["labels"])
        visible = list(config.get("visible", [True] * len(ticks)))
    except (KeyError, TypeError) as exc:
        raise ValueError("颜色条需要刻度和标签列表") from exc
    if not (len(ticks) == len(labels) == len(visible)):
        raise ValueError("颜色条刻度、标签和显示状态数量不一致")
    if any(not isinstance(label, str) for label in labels):
        raise ValueError("颜色条标签必须为文本")
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in ticks):
        raise ValueError("颜色条刻度必须为有限数字")
    if len(set(ticks)) != len(ticks):
        raise ValueError("颜色条刻度不能重复")
    if any(not isinstance(v, bool) for v in visible):
        raise ValueError("颜色条显示状态必须为 bool")
    fontsize = config.get("fontsize", 8)
    if not _finite_number(fontsize) or fontsize <= 0:
        raise ValueError("颜色条字号必须为有限正数")
    rows = sorted((t, l) for t, l, v in zip(ticks, labels, visible) if v)
    return {"ticks": [r[0] for r in rows], "labels": [r[1] for r in rows],
            "fontsize": fontsize}


def _finite_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def color_nodes(nodes):
    """Validate and sort positioned colors; keep their explicit positions."""
    from matplotlib.colors import is_color_like
    try:
        if isinstance(nodes, str):
            nodes = [row.split(":", 1) for row in nodes.replace("；", ";").split(";")
                     if row.strip()]
            nodes = [(float(position), color.strip()) for position, color in nodes]
        else:
            nodes = list(nodes)
        if any(len(row) != 2 or not _finite_number(row[0]) or
               not 0 <= row[0] <= 1 or not is_color_like(row[1]) for row in nodes):
            raise ValueError
        nodes = sorted((position, color) for position, color in nodes)
        if (len(nodes) < 2 or nodes[0][0] != 0 or nodes[-1][0] != 1 or
                len({position for position, _ in nodes}) != len(nodes)):
            raise ValueError
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("颜色节点须从 0 到 1，位置不重复，颜色有效") from exc
    return nodes


def validate_render_options(style):
    """Resolve the custom/corrected field contract without changing the input."""
    from matplotlib.colors import is_color_like
    work = dict(style)
    for key in ("symbol_fs", "number_fs", "value_fs", "label_fs"):
        if key in work and (not _finite_number(work[key]) or work[key] <= 0):
            raise ValueError(f"{key} 必须是有限正数")
    for key in ("show_symbol", "show_number", "show_value", "transparent"):
        if key in work and not isinstance(work[key], bool):
            raise ValueError(f"{key} 必须为 bool")
    for key, low, high in (("edge_width", 0, 20), ("value_dx", -2, 2),
                           ("value_dy", -2, 2), ("label_wrap", 0, 200),
                           ("cbar_fraction", .005, .5), ("cbar_pad", 0, .5),
                           ("cbar_shrink", .05, 1)):
        if key in work and (not _finite_number(work[key]) or not low <= work[key] <= high):
            raise ValueError(f"{key} 应在 {low}～{high} 之间")
    if work.get("label_wrap", 0) != int(work.get("label_wrap", 0)):
        raise ValueError("label_wrap 必须为整数")
    if not isinstance(work.get("unit", ""), str):
        raise ValueError("unit 必须为文本")
    if work.get("fmt", "raw") not in ("raw", "g", "percent2", "2f", "3f", "4f", "scientific"):
        raise ValueError("fmt 数值格式无效")
    edge = work.get("edge")
    if edge is not None:
        try:
            width, color = edge
        except (ValueError, TypeError) as exc:
            raise ValueError("edge 必须为 (线宽, 颜色)") from exc
        if not _finite_number(width) or not 0 <= width <= 20 or not is_color_like(color):
            raise ValueError("edge 线宽或颜色无效")
    if "edge_color" in work and not is_color_like(work["edge_color"]):
        raise ValueError("edge_color 颜色无效")
    if "edge_width" in work or "edge_color" in work:
        width = work.get("edge_width", edge[0] if edge else 0)
        color = work.get("edge_color", edge[1] if edge else "black")
        work["edge"] = (width, color) if width else None
    orientation = work.get("cbar_orientation", "vertical")
    if orientation not in ("vertical", "horizontal"):
        raise ValueError("cbar_orientation 必须为 vertical 或 horizontal")
    if "cbar_location" in work:
        location = work["cbar_location"]
        if location == "auto":
            location = "bottom" if orientation == "horizontal" else "right"
        if location not in ("left", "right", "top", "bottom"):
            raise ValueError("cbar_location 颜色条位置无效")
        work["cbar_location"] = location
    nodes = work.get("color_nodes", "")
    if nodes:
        work["cmap"] = ("custom", color_nodes(nodes))
    if work.get("cbar") is not None:
        work["cbar"] = colorbar_config(work["cbar"])
    return work


def range_warnings(style, data):
    norm = style.get("norm")
    if style.get("kind") != "heatmap" or not norm:
        return []
    low, high = norm[1], norm[-1]
    warnings = []
    outside = [s for s, value in data.items() if value < low or value > high]
    if outside:
        warnings.append(f"{len(outside)} 个数值超出色标范围（{', '.join(outside[:8])}）；可使用自动范围")
    cfg = style.get("cbar")
    if cfg and any(t < low or t > high for t in cfg["ticks"]):
        warnings.append("颜色条刻度超出色标范围，请编辑刻度或调整范围")
    return warnings
