"""Pure GUI option vocabulary and shared style application rules."""
import math

LAYOUT_CHOICES = {"镧锕三行块（重构）": "reconstructed",
                  "展开 8-9 行（经典）": "classic"}
KIND_CHOICES = {"热力图": "heatmap", "标注图（文本）": "labels"}
FONT_CHOICES = {"Arial": "Arial", "Helvetica": "Helvetica",
                "DejaVu Sans": "DejaVu Sans"}
EDGE_CHOICES = {"无边框": "none", "黑色细线": "black"}
EMPTY_CHOICES = {"浅灰": "#f0f0f0", "白色": "white", "白色(w)": "w", "透明": "none"}
FMT_CHOICES = {"百分比 2 位": "percent2", "两位小数": "2f", "三位小数": "3f",
               "四位小数": "4f", "科学计数法": "scientific", "原始": "raw"}
DPI_CHOICES = {"72": 72, "100": 100, "150": 150, "300": 300}

def parse_figure_size(text):
    text = str(text).strip().lower().replace("×", "x")
    factor = 25.4 if text.endswith("mm") else 1.0
    if factor != 1:
        text = text[:-2].strip()
    try:
        width, height = (float(value.strip()) / factor for value in text.split("x"))
    except (ValueError, TypeError) as exc:
        raise ValueError("画幅请输入 10x5（英寸）或 254x127 mm") from exc
    if not (math.isfinite(width) and math.isfinite(height) and 2 <= width <= 40 and 1 <= height <= 40):
        raise ValueError("画幅宽度须为 50.8～1016 mm，高度须为 25.4～1016 mm")
    return width, height


def parse_box(text):
    try:
        values = [float(value.strip()) for value in text.replace("，", ",").split(",")]
    except (ValueError, AttributeError) as exc:
        raise ValueError("位置参数必须是四个逗号分隔的数字") from exc
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        raise ValueError("位置参数必须是四个有限数字")
    return values



def apply_custom_params(style, params, display, custom_colors, element_overrides, compatibility=False):
    import copy
    import math
    work = copy.deepcopy(style)
    work["kind"] = KIND_CHOICES.get(params["kind"], "heatmap")
    cmap_name = params["cmap"].strip()
    try:
        vmin = float(params["vmin"]) if work["kind"] == "heatmap" else 0.0
        vmax = float(params["vmax"]) if work["kind"] == "heatmap" else 1.0
        center_text = params["vcenter"].strip() if work["kind"] == "heatmap" else ""
        vcenter = float(center_text) if center_text else None
    except (ValueError, TypeError) as exc:
        raise ValueError("vmin / vcenter / vmax 必须是数字") from exc
    # 拒绝 NaN / Infinity，避免污染 norm 与渲染
    if (not math.isfinite(vmin) or not math.isfinite(vmax) or
            (vcenter is not None and not math.isfinite(vcenter))):
        raise ValueError("vmin / vcenter / vmax 必须是有限数值")
    work["norm"] = (("twoslope", vmin, vcenter, vmax) if vcenter is not None
                    else ("normalize", vmin, vmax))
    # 范围顺序校验：vmin < vcenter < vmax（normalize 时 vmin < vmax）
    if vcenter is not None:
        if not (vmin < vcenter < vmax):
            raise ValueError("范围顺序应为 vmin < vcenter < vmax")
    elif vmin >= vmax:
        raise ValueError("vmin 必须小于 vmax")
    work["fmt"] = FMT_CHOICES.get(params["fmt"], "3f")
    # 自定义颜色优先；否则按输入的名称取预置色图
    if cmap_name.strip().startswith("自定义"):
        work["cmap"] = ("custom", [tuple(c) for c in custom_colors])
    elif cmap_name.strip():
        work["cmap"] = cmap_name.strip()
    else:
        work["cmap"] = ("custom", [tuple(c) for c in custom_colors])

    # ---- 高级参数（渲染自由度）----
    work["layout"] = LAYOUT_CHOICES.get(params["layout"],
                                        "classic")
    work["kind"] = KIND_CHOICES.get(params["kind"],
                                    "heatmap")
    work["font"] = params["font"].strip() or "Arial"
    edge = EDGE_CHOICES.get(params["edge"], "none")
    work["edge"] = None if edge == "none" else (0.5, "black")
    work["empty"] = EMPTY_CHOICES.get(params["empty"],
                                      "#f0f0f0")
    work["dpi"] = DPI_CHOICES.get(params["dpi"], 100)
    fw, fh = parse_figure_size(params["figsize"])
    work["figsize"] = (fw, fh)
    work["bbox_tight"] = params["crop_mode"] == "紧裁切"
    work["rounding"] = ("legacy" if compatibility or params["rounding"] == "原脚本浮点舍入"
                        else "half_up")
    work["element_overrides"] = copy.deepcopy(element_overrides)
    for key in ("margins", "cbar_box"):
        value = params[key].strip()
        if value:
            work[key] = parse_box(value)
    for key, value in display.items():
        work[key] = value
    for key in ("symbol_fs", "number_fs", "value_fs"):
        try:
            value = float(params[key])
        except ValueError as exc:
            raise ValueError(f"{key} 必须是正数字号") from exc
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} 必须是有限正数")
        work[key] = value
    from matplotlib.colors import is_color_like
    for key, low, high in (("edge_width", 0, 20), ("value_dx", -2, 2),
                           ("value_dy", -2, 2), ("label_wrap", 0, 200),
                           ("cbar_fraction", .005, .5), ("cbar_pad", 0, .5),
                           ("cbar_shrink", .05, 1)):
        try:
            value = float(params[key])
        except ValueError as exc:
            raise ValueError(f"{key} 必须是数字") from exc
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} 应在 {low}～{high} 之间")
        work[key] = value
    if not work["label_wrap"].is_integer():
        raise ValueError("每行字符数必须为整数")
    work["label_wrap"] = int(work["label_wrap"])
    color = params["edge_color"].strip()
    if not is_color_like(color):
        raise ValueError("边框颜色无效")
    if work["edge_width"] > 0:
        work["edge"] = (work["edge_width"], color)
    work["unit"] = params["unit"]
    nodes = params["color_nodes"].strip()
    if nodes:
        try:
            pairs = sorted((float(row.split(":", 1)[0]), row.split(":", 1)[1].strip())
                           for row in nodes.replace("；", ";").split(";") if row.strip())
        except (ValueError, IndexError) as exc:
            raise ValueError("颜色节点格式：0:#0000ff;0.5:#ffffff;1:#ff0000") from exc
        if (len(pairs) < 2 or pairs[0][0] != 0 or pairs[-1][0] != 1 or
                len({p for p, c in pairs}) != len(pairs) or
                any(not math.isfinite(p) or not 0 <= p <= 1 or not is_color_like(c) for p, c in pairs)):
            raise ValueError("颜色节点须从 0 到 1，位置不重复，颜色有效")
        work["cmap"] = ("custom", pairs)
    work["cbar_orientation"] = params["cbar_orientation"]
    location = params["cbar_location"]
    work["cbar_location"] = ("bottom" if work["cbar_orientation"] == "horizontal" else "right") if location == "auto" else location
    work["cbar_label"] = params["cbar_label"]
    # 标注图类型：注入 labels 专属默认键（浅灰底 + 深灰标注）
    if work["kind"] == "labels":
        work.setdefault("bg", "#f0f0f0")
        work.setdefault("label_color", "#666666")
        work.setdefault("label_fs", 8)
        work.setdefault("label_dy", 0.12)
    return work

