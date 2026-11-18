"""Script-independent plotting use cases shared by API and future GUI adapters."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from domain.plot_spec import PlotSpec


def prepare_plot(plot, data):
    """Return validated spec, converted measurements and non-destructive warnings."""
    from core.dataio import convert_data
    spec = plot if isinstance(plot, PlotSpec) else PlotSpec.from_dict(plot)
    config = spec.to_dict()
    from infrastructure.rendering.colors import validate_colors, make_cmap, make_norm
    validate_colors(config)
    make_cmap(config['cmap'])
    make_norm(config['norm'])
    if not isinstance(data, dict):
        raise ValueError('data must map element symbols to text or numbers')
    if any(not isinstance(key, str) or type(value) not in (str, int, float) for key, value in data.items()):
        raise ValueError('data values must be text or numbers; use patch.data null to remove an element')
    values = convert_data(data, config['kind'])
    warnings = []
    if config['layout'] == 'compact':
        from domain.plot_layout import build_layout
        hidden_symbols = set(build_layout('compact').hidden_elements)
        hidden = [symbol for symbol in values if symbol in hidden_symbols]
        if hidden:
            warnings.append(f"折叠布局未显示 {len(hidden)} 个已输入元素：{', '.join(hidden)}")
    if config['kind'] == 'heatmap':
        low, high = config['norm'][1], config['norm'][-1]
        outside = [s for s, v in values.items() if (v < low or v > high)
                   and config['element_overrides'].get(s, {}).get('show_color', True)]
        if outside:
            warnings.append(f"{len(outside)} 个数值超出色标范围：{', '.join(outside)}")
        cbar = config['cbar']
        if cbar and any((t < low or t > high) and visible for t, visible in
                        zip(cbar['ticks'], cbar['visible'])):
            warnings.append('颜色条刻度超出色标范围')
    return spec, values, warnings


def plot_fingerprint(spec, data):
    raw = json.dumps({'plot': spec.to_dict(), 'data': data}, sort_keys=True,
                     ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def render(plot, data):
    from infrastructure.rendering.renderer import render_plot
    from core.layout_diagnostics import inspect_layout, layout_warnings
    import matplotlib.pyplot as plt
    spec, values, warnings = prepare_plot(plot, data)
    fig = render_plot(spec, values)
    try:
        issues = inspect_layout(fig) if spec.to_dict()['check_label_overlap'] else []
        return fig, {'warnings': warnings + layout_warnings(issues),
                     'layout_issues': issues, 'plot_fingerprint': plot_fingerprint(spec, values)}
    except BaseException:
        plt.close(fig)
        raise


def export_plots(plot, items, output_dir, formats=('svg',), base='periodic_table',
                 allow_out_of_range=False):
    """Preflight all groups; rollback only this operation's files on any failure."""
    from core.imaging import save_options
    from core.saver import save_figure
    from .agent_api import ApiError
    import matplotlib.pyplot as plt
    if (not isinstance(formats, (tuple, list)) or not formats or
            any(f not in ('png', 'svg', 'pdf') for f in formats) or len(set(formats)) != len(formats)):
        raise ApiError('INVALID_REQUEST', 'formats must be a unique nonempty png/svg/pdf list')
    if not isinstance(base, str) or not re.fullmatch(r'[\w-]{1,80}', base):
        raise ApiError('INVALID_REQUEST', 'base must contain 1–80 letters/digits/underscores/hyphens')
    if type(allow_out_of_range) is not bool:
        raise ApiError('INVALID_REQUEST', 'allow_out_of_range must be boolean')
    if not isinstance(output_dir, (str, Path)) or not str(output_dir).strip():
        raise ApiError('INVALID_REQUEST', 'output_dir must be a path')
    spec = PlotSpec.from_dict(plot) if not isinstance(plot, PlotSpec) else plot
    config = spec.to_dict()
    if config['figsize'][0] * config['figsize'][1] * config['dpi'] ** 2 > 64_000_000:
        raise ApiError('OUTPUT_TOO_LARGE', 'Requested canvas exceeds 64 million pixels')
    prepared = []
    for metadata, data in items:
        _, values, warnings = prepare_plot(spec, data)
        if not values:
            raise ApiError('EMPTY_DATA', 'No plot data')
        if warnings and not allow_out_of_range:
            raise ApiError('RANGE_WARNING', '; '.join(warnings))
        prepared.append((deepcopy(metadata), values))
    if not prepared or len(prepared) > 100:
        raise ApiError('INVALID_REQUEST', 'Select 1–100 data groups')
    created, results = [], []
    try:
        for index, (metadata, values) in enumerate(prepared, 1):
            fig, details = render(spec, values)
            try:
                files = []
                stem = base if len(prepared) == 1 else f'{base}_{index:03d}'
                for fmt in formats:
                    path = Path(save_figure(fig, str(Path(output_dir).resolve()), stem, fmt,
                                            **save_options(config)))
                    created.append(path)
                    files.append({'path': str(path), 'bytes': path.stat().st_size,
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                results.append({**metadata, **details, 'files': files})
            finally:
                plt.close(fig)
        return results
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
