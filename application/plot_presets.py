"""Small editable starting points; no preset identity reaches the renderer."""
from domain.plot_spec import PlotSpec

PRESETS = {
    'diverging': ('中心发散热力图', {}),
    'sequential': ('连续数值热力图', {'cmap': 'viridis', 'norm': ['normalize', 0, 1]}),
    'percentage': ('百分比热力图', {'cmap': 'Blues', 'norm': ['normalize', 0, 1], 'fmt': 'percent2'}),
    'labels': ('文本标注图', {'kind': 'labels', 'show_cbar': False, 'label_color': '#666666'}),
    'highlight_labels': ('高亮文本标注图', {'kind': 'labels', 'show_cbar': False,
        'highlight_bg': '#234c75', 'highlight_fg': 'white', 'plain_bg': '#f0f0f0', 'plain_fg': 'black'}),
}


def preset(name='diverging'):
    if name not in PRESETS:
        raise ValueError(f'Unknown preset: {name}')
    return PlotSpec.from_dict(PRESETS[name][1]).to_dict()


def describe_presets():
    return [{'id': name, 'name': label, 'plot': preset(name)} for name, (label, _) in PRESETS.items()]
