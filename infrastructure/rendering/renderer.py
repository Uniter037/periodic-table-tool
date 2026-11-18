"""Modern renderer. PlotSpec is the sole configuration input."""
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.cm import ScalarMappable
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from core.dataio import convert_data
from core.fonts import apply_text_fallbacks
from domain.plot_layout import build_layout
from domain.plot_spec import PlotSpec
from .colors import color, make_cmap, make_norm, validate_colors
from .colorbar import add_colorbar
from .text import draw_text, measurement_text, tag


def render_plot(spec: PlotSpec, data: dict) -> Figure:
    """Return an Agg-capable Figure without pyplot registration or global rc edits.

    Figure ``_ptable_layout`` exposes immutable geometry/hidden elements.
    Element patches and text expose element, role and cell bounds for hit tests.
    Range exclusion is an application auto-range concern: explicit spec.norm wins.
    """
    config = spec.to_dict()
    validate_colors(config)
    cmap = make_cmap(config['cmap'])  # Validate even for labels, consistently.
    norm = make_norm(config['norm'])
    # JSON null denotes an empty measurement, while numeric zero is present.
    # Keep keys for validation, including unknown elements with empty values.
    values = convert_data({key: '' if value is None else value
                           for key, value in data.items()}, config['kind'])
    layout = build_layout(config['layout'])
    fig = Figure(figsize=config['figsize'], dpi=config['dpi'])
    FigureCanvasAgg(fig)
    fig._ptable_layout = layout
    fig._ptable_spec = config
    ax = fig.add_subplot(111)
    margins = config['margins'] or (.025, .025, .975, .92 if config['title'] else .975)
    fig.subplots_adjust(left=margins[0], bottom=margins[1], right=margins[2], top=margins[3])
    ax.set(xlim=(layout.bounds[0], layout.bounds[2]), ylim=(layout.bounds[1], layout.bounds[3]), aspect='equal')
    ax.set_axis_off()
    fig._ptable_colorbar = (add_colorbar(fig, ax, ScalarMappable(norm=norm, cmap=cmap), config)
                           if config['kind'] == 'heatmap' else None)
    edge = config['edge'] or (0, 'none')
    for cell in layout.cells:
        symbol, x, y = cell.symbol, cell.x, cell.y
        edit = config['element_overrides'].get(symbol, {})
        present = symbol in values
        if config['kind'] == 'heatmap':
            background = cmap(norm(values[symbol])) if present else config['empty']
            foreground = 'black'
        else:
            background = (config['highlight_bg'] if present else config['plain_bg'])
            background = config['bg'] if background is None else background
            foreground = (config['highlight_fg'] if present else config['plain_fg']) or 'black'
        if not edit.get('show_color', True):
            background = config['empty']
        if config['kind'] == 'heatmap':
            rgba = color(background, 'cell')
            # Composite transparent fills against the white figure background.
            rgb = [channel * rgba[3] + 1 - rgba[3] for channel in rgba[:3]]
            linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
            luminance = sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
            foreground = 'black' if luminance > .179 else 'white'
        patch = Rectangle((x, y), 1, 1, facecolor=background, edgecolor=edge[1], linewidth=edge[0])
        ax.add_patch(tag(patch, symbol, 'cell', cell.bounds))
        if config['show_number']:
            draw_text(ax, config, symbol, 'number', cell.bounds, x + config['num_x'], y + .8,
                      str(cell.number), config['number_fs'], foreground, ha=config['num_ha'])
        if config['show_symbol']:
            draw_text(ax, config, symbol, 'symbol', cell.bounds, x + .5, y + .5,
                      symbol, config['symbol_fs'], foreground, ha='center', weight='bold')
        if present and config['show_value'] and edit.get('show_value', True):
            label = config['kind'] == 'labels'
            label_color = (config['highlight_fg'] if present else config['plain_fg']) if label else None
            draw_text(ax, config, symbol, 'value', cell.bounds,
                      x + .5 + config['value_dx'] + edit.get('value_dx', 0),
                      y + (config['label_dy'] if label else .12) + config['value_dy'] + edit.get('value_dy', 0),
                      measurement_text(values[symbol], config), config['label_fs'] if label else config['value_fs'],
                      label_color or (foreground if config['label_color'] == 'auto'
                                      else config['label_color']), ha='center')
    for marker in layout.markers:
        bounds = (marker.x, marker.y, 1, 1)
        identity = '|'.join(marker.lines)
        if marker.boxed:
            ax.add_patch(tag(Rectangle((marker.x, marker.y), 1, 1, facecolor=config['empty'],
                                      edgecolor=edge[1], linewidth=edge[0]), identity, 'series', bounds))
        for line, dy, fs in zip(marker.lines, (.8, .5, .12) if marker.boxed else (.5,),
                                (config['number_fs'], config['symbol_fs'], config['value_fs'])
                                if marker.boxed else (config['symbol_fs'],)):
            draw_text(ax, config, identity, 'series', bounds, marker.x + .5, marker.y + dy,
                      line, fs, 'black' if config['label_color'] == 'auto'
                      else config['label_color'], ha='center')
    if config['title']:
        fig.suptitle(config['title'], fontsize=14, fontfamily=config['font'])
    if config['transparent']:
        fig.patch.set_alpha(0)
        for axes in fig.axes:
            axes.patch.set_alpha(0)
    apply_text_fallbacks(fig)
    if config['margins'] is None and config['cbar_box'] is None:
        # Layout the same visible colorbar before hiding a reserved placeholder.
        # Invisible tick labels otherwise disappear from tight_layout's extents.
        bar = fig._ptable_colorbar
        visible = bar.ax.get_visible() if bar else None
        if bar:
            bar.ax.set_visible(True)
        try:
            fig.tight_layout(pad=1.08)
        finally:
            if bar:
                bar.ax.set_visible(visible)
    return fig
