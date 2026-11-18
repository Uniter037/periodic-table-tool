"""Backend color validation; names are registry keys, never Python imports."""
from matplotlib import colormaps
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm, to_rgba


def validate_colors(config):
    for key in ('empty', 'bg', 'label_color', 'highlight_bg', 'highlight_fg', 'plain_bg', 'plain_fg'):
        if key == 'label_color' and config[key] == 'auto':
            continue
        if config[key] is not None:
            color(config[key], key)
    if config['edge'] is not None:
        color(config['edge'][1], 'edge')


def color(value, path):
    try:
        return to_rgba(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{path}: invalid Matplotlib color {value!r}') from exc


def make_cmap(value):
    if isinstance(value, str):
        if ':' in value or value not in colormaps:
            raise ValueError(f'cmap: unknown registered colormap {value!r}')
        return colormaps[value]
    if value[0] != 'custom':
        raise ValueError('cmap: expected registered name or custom colors')
    nodes = value[1]
    positioned = isinstance(nodes[0], (list, tuple)) and len(nodes[0]) == 2
    colors = [(p, color(c, 'cmap')) for p, c in nodes] if positioned else [color(c, 'cmap') for c in nodes]
    return LinearSegmentedColormap.from_list('plot_spec_custom', colors)


def make_norm(value):
    if value[0] == 'twoslope':
        return TwoSlopeNorm(vmin=value[1], vcenter=value[2], vmax=value[3])
    return Normalize(vmin=value[1], vmax=value[2])
