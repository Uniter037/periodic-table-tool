"""Non-mutating, renderer-based text layout diagnostics for GUI and agents."""
from matplotlib.transforms import Bbox


def inspect_layout(fig):
    """Return bounding-box suggestions, with bounds in Figure fractions.

    Origin is bottom-left. No user settings or text positions are changed.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inverse = fig.transFigure.inverted()
    entries, issues = [], []
    for ax in fig.axes:
        for text in ax.texts:
            if not hasattr(text, '_ptable_element') or not text.get_visible() or not text.get_text():
                continue
            box = text.get_window_extent(renderer)
            if box.width <= 0 or box.height <= 0:
                continue
            item = {'element': text._ptable_element, 'role': text._ptable_role,
                    'bounds': list(box.transformed(inverse).bounds)}
            cell = Bbox.from_bounds(*text._ptable_cell).transformed(ax.transData)
            tolerance = fig.dpi / 144  # Half a point avoids rounding noise.
            if (box.x0 < cell.x0 - tolerance or box.y0 < cell.y0 - tolerance
                    or box.x1 > cell.x1 + tolerance or box.y1 > cell.y1 + tolerance):
                issues.append({'code': 'TEXT_OUTSIDE_CELL', 'text': item,
                               'suggestion': '缩小字号、换行或调整该标注位置'})
            entries.append((box, item))
    entries.sort(key=lambda entry: entry[0].x0)
    for index, (box, item) in enumerate(entries):
        for other_box, other_item in entries[index + 1:]:
            if other_box.x0 >= box.x1:
                break
            intersection = Bbox.intersection(box, other_box)
            if intersection is not None and min(intersection.width, intersection.height) > fig.dpi / 144:
                issues.append({'code': 'TEXT_OVERLAP', 'text': item, 'other': other_item,
                               'suggestion': '调整标注位置或缩小字号；保留手动布局'})
    return issues


def layout_warnings(issues):
    if not issues:
        return []
    elements = list(dict.fromkeys(issue['text']['element'] for issue in issues))
    return [f"排版提示：发现 {len(issues)} 处文字可能重叠或越出单元格（{', '.join(elements[:8])}）；可调整字号或标注位置"]
