"""Colorbar placement and visibility; hidden rows remain in the source spec."""


def add_colorbar(fig, ax, mappable, config):
    if not (config['show_cbar'] or config['preserve_cbar_space']):
        return None
    orientation = config['cbar_orientation']
    location = config['cbar_location']
    if location == 'auto':
        location = 'right' if orientation == 'vertical' else 'bottom'
    box = config['cbar_box']
    if box is not None:
        cax = fig.add_axes(box)
        cax.set_in_layout(False)
        bar = fig.colorbar(mappable, cax=cax, orientation=orientation, ticklocation=location)
        cax.set_axes_locator(None)
        cax.set_box_aspect(None)
        cax.set_aspect('auto')
        cax.set_position(box)
    else:
        bar = fig.colorbar(mappable, ax=ax, location=location,
                           fraction=config['cbar_fraction'], pad=config['cbar_pad'],
                           shrink=config['cbar_shrink'])
        bar.ax.set_box_aspect(None)
    rows = config['cbar']
    if rows is not None:
        selected = sorted((t, label) for t, label, visible in
                          zip(rows['ticks'], rows['labels'], rows['visible']) if visible)
        bar.set_ticks([t for t, _ in selected], labels=[label for _, label in selected])
    bar.ax.tick_params(labelsize=rows['fontsize'] if rows else 8)
    if not config['show_cbar_labels']:
        bar.ax.tick_params(labelleft=False, labelright=False, labeltop=False, labelbottom=False)
    bar.set_label(config['cbar_label'], fontfamily=config['font'])
    for label in bar.ax.get_xticklabels() + bar.ax.get_yticklabels():
        label.set_fontfamily(config['font'])
    # Invisible axes retain the reserved geometry without removing the subplot.
    bar.ax.set_visible(config['show_cbar'])
    return bar
