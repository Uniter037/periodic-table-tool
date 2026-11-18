"""Artist-level and Agg regressions for the independent PlotSpec renderer."""
import json
import subprocess
import sys

import pytest
from matplotlib.colors import to_rgba

from domain.plot_layout import build_layout
from domain.plot_spec import PlotSpec
from infrastructure.rendering.renderer import render_plot
from infrastructure.rendering.text import format_value


def render(data=None, **options):
    return render_plot(PlotSpec.from_dict({'font': 'DejaVu Sans', **options}), data or {})


def artists(fig, role):
    return {a._ptable_element: a for a in
            [*fig.axes[0].patches, *fig.axes[0].texts]
            if getattr(a, '_ptable_role', None) == role}


def test_expanded_layout_identity_geometry_and_purity():
    from core.elements_data import ALL_SYMBOLS
    layout = build_layout('expanded')
    assert [c.symbol for c in layout.cells] == list(ALL_SYMBOLS)
    assert [c.number for c in layout.cells] == list(range(1, 119))
    assert len({(c.x, c.y) for c in layout.cells}) == 118
    assert not layout.hidden_elements
    cells = {c.symbol: c for c in layout.cells}
    for symbol, group, period in [('H', 1, 1), ('He', 18, 1), ('B', 13, 2),
                                   ('Hf', 4, 6), ('Rn', 18, 6), ('Rf', 4, 7),
                                   ('Og', 18, 7), ('La', 3, 8), ('Lu', 17, 8),
                                   ('Ac', 3, 9), ('Lr', 17, 9)]:
        cell = cells[symbol]
        assert (cell.group, cell.period) == (group, period)
    for cell in layout.cells:
        assert 0 <= cell.x < cell.x + cell.width <= layout.bounds[2]
        assert 0 <= cell.y < cell.y + cell.height <= layout.bounds[3]
        assert not hasattr(cell, 'value')
    with pytest.raises(ValueError):
        build_layout('classic')


def test_compact_series_and_hidden_elements():
    layout = build_layout('compact')
    assert len(layout.cells) == 88 and len(layout.hidden_elements) == 30
    assert layout.hidden_elements[0:2] == ('La', 'Ce')
    assert layout.hidden_elements[-1] == 'Lr'
    assert [m.lines for m in layout.markers] == [
        ('57–71', 'La–Lu', 'Lanthanide'), ('89–103', 'Ac–Lr', 'Actinide')]
    fig = render({'La': 1, 'Hf': 0}, layout='compact')
    assert len(artists(fig, 'cell')) == 88
    assert set(artists(fig, 'value')) == {'Hf'}


@pytest.mark.parametrize('kind', ['heatmap', 'labels'])
def test_zero_empty_null_and_metadata(kind):
    fig = render({'H': 0, 'He': '', 'Li': None, 'Be': '  '}, kind=kind)
    fig.canvas.draw()
    cells = artists(fig, 'cell')
    assert len(cells) == 118
    assert set(artists(fig, 'value')) == {'H'}
    assert artists(fig, 'value')['H'].get_text() == ('0.000' if kind == 'heatmap' else '0')
    assert cells['He'].get_facecolor() == to_rgba('#f0f0f0')
    if kind == 'heatmap':
        assert cells['H'].get_facecolor() != cells['He'].get_facecolor()
    for symbol, text in artists(fig, 'symbol').items():
        assert text._ptable_cell == cells[symbol]._ptable_cell
    with pytest.raises(ValueError):
        render({'Unknown': None}, kind=kind)


def test_colorbar_hidden_rows_and_fontsize():
    rows = {'ticks': [1, -1, 0], 'labels': ['high', 'low', 'hidden'],
            'visible': [True, True, False], 'fontsize': 13}
    spec = PlotSpec.from_dict({'font': 'DejaVu Sans', 'cbar': rows})
    fig = render_plot(spec, {'H': 0})
    fig.canvas.draw()
    bar = fig._ptable_colorbar
    assert list(bar.get_ticks()) == [-1, 1]
    assert [t.get_text() for t in bar.ax.get_yticklabels()] == ['low', 'high']
    assert all(t.get_fontsize() == 13 for t in bar.ax.get_yticklabels())
    assert spec.to_dict()['cbar'] == rows


@pytest.mark.parametrize('orientation,location', [('vertical', 'left'), ('horizontal', 'top')])
def test_colorbar_hide_labels_and_exact_box(orientation, location):
    box = [.12, .15, .08, .65] if orientation == 'vertical' else [.2, .8, .6, .05]
    fig = render(cbar_orientation=orientation, cbar_location=location,
                 cbar_box=box, show_cbar_labels=False)
    fig.canvas.draw()
    bar = fig._ptable_colorbar
    assert bar.ax.get_position().bounds == pytest.approx(box, abs=1e-12)
    assert not any(t.get_visible() for t in
                   bar.ax.get_xticklabels() + bar.ax.get_yticklabels())
    fig.canvas.draw()
    assert bar.ax.get_position().bounds == pytest.approx(box, abs=1e-12)


def test_colorbar_space_reservation_and_all_hidden_ticks():
    visible = render()
    reserved = render(show_cbar=False, preserve_cbar_space=True)
    removed = render(show_cbar=False)
    for fig in (visible, reserved, removed):
        fig.canvas.draw()
    assert reserved.axes[0].get_position().bounds == pytest.approx(visible.axes[0].get_position().bounds)
    assert not reserved._ptable_colorbar.ax.get_visible()
    assert removed._ptable_colorbar is None and len(removed.axes) == 1
    assert removed.axes[0].get_position().bounds != pytest.approx(reserved.axes[0].get_position().bounds)
    fig = render(cbar={'ticks': [0], 'labels': ['zero'], 'visible': [False]})
    fig.canvas.draw()
    assert len(fig._ptable_colorbar.get_ticks()) == 0


@pytest.mark.parametrize('field', ['empty', 'bg', 'label_color', 'highlight_bg',
                                  'highlight_fg', 'plain_bg', 'plain_fg'])
def test_invalid_backend_colors_even_if_unused(field):
    with pytest.raises(ValueError, match=field):
        render(**{field: 'not-a-color'})


@pytest.mark.parametrize('cmap', ['missing-colormap', ['custom', ['red', 'not-a-color']]])
def test_invalid_colormaps(cmap):
    with pytest.raises(ValueError, match='cmap'):
        render(cmap=cmap)


@pytest.mark.parametrize('cmap', [['custom', ['red', 'blue']],
                                 ['custom', [[0, '#ff0000'], [1, [0, 0, 1, .5]]]]])
def test_custom_colors_and_edges(cmap):
    fig = render({'H': 0}, cmap=cmap, edge=[2, [0, .5, 1, 1]], empty=[.1, .2, .3])
    fig.canvas.draw()
    assert artists(fig, 'cell')['He'].get_facecolor() == to_rgba([.1, .2, .3])
    assert artists(fig, 'cell')['H'].get_linewidth() == 2


@pytest.mark.parametrize('value,fmt,expected', [(2.675, '2f', '2.68'), (-2.675, '2f', '-2.68'),
    (.01005, 'percent2', '1.01%'), (0, '3f', '0.000'), (1e30, '2f', '1000000000000000000000000000000.00')])
def test_half_up(value, fmt, expected):
    assert format_value(value, fmt, 'half_up') == expected
    assert format_value(value, fmt, 'python') == (
        format(value * 100 if fmt == 'percent2' else value, '.2f' if fmt != '3f' else '.3f')
        + ('%' if fmt == 'percent2' else ''))


def test_element_overrides_visibility_offsets_and_explicit_range():
    options = {'element_overrides': {'H': {'show_value': False},
               'He': {'show_color': False, 'value_dx': .2, 'value_dy': -.1,
                      'include_in_range': False}}, 'value_dx': .1, 'value_dy': .2}
    fig = render({'H': 0, 'He': 1}, **options)
    assert set(artists(fig, 'value')) == {'He'}
    patch = artists(fig, 'cell')['He']
    assert patch.get_facecolor() == to_rgba('#f0f0f0')
    assert artists(fig, 'value')['He'].get_position() == pytest.approx((patch.get_x() + .8, patch.get_y() + .22))
    assert (fig._ptable_colorbar.norm.vmin, fig._ptable_colorbar.norm.vmax) == (-1, 1)
    assert not artists(render({'H': 0}, show_value=False), 'value')


def test_labels_fonts_wrapping_and_highlight():
    fig = render({'H': 'abcdef'}, kind='labels', label_fs=17, value_fs=3,
                 symbol_fs=12, number_fs=7, label_wrap=3, label_dy=.3,
                 highlight_bg='yellow', highlight_fg='navy', plain_bg='white', plain_fg='green')
    fig.canvas.draw()
    value = artists(fig, 'value')['H']
    assert value.get_fontsize() == 17 and value.get_text() == 'abc\ndef'
    assert value.get_position()[1] == pytest.approx(artists(fig, 'cell')['H'].get_y() + .3)
    assert value.get_color() == 'navy'
    assert artists(fig, 'symbol')['He'].get_color() == 'green'
    assert artists(fig, 'symbol')['H'].get_fontsize() == 12
    assert artists(fig, 'number')['H'].get_fontsize() == 7
    assert artists(fig, 'cell')['H'].get_facecolor() == to_rgba('yellow')
    assert artists(fig, 'cell')['He'].get_facecolor() == to_rgba('white')
    assert fig._ptable_colorbar is None


def test_renderer_imports_no_historical_modules():
    code = '''
import json, sys
from domain.plot_spec import PlotSpec
from infrastructure.rendering.renderer import render_plot
fig = render_plot(PlotSpec.from_dict({'font': 'DejaVu Sans'}), {'H': 0})
fig.canvas.draw()
print(json.dumps(sorted(set(sys.modules) & {'core.styles', 'core.scientific', 'core.options', 'core.ptable'})))
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == []


@pytest.mark.parametrize('value,expected', [(1.2345, '1.235e+00'), (-1.2345, '-1.235e+00'),
    (9.9995, '1.000e+01'), (-9.9995, '-1.000e+01'), (.00099995, '1.000e-03'),
    (0, '0.000e+00'), (1e-300, '1.000e-300'), (1e300, '1.000e+300')])
def test_scientific_half_up_and_mantissa_carry(value, expected):
    assert format_value(value, 'scientific', 'half_up') == expected
    assert format_value(value, 'scientific', 'python') == format(value, '.3e')


@pytest.mark.parametrize('rounding', ['half_up', 'python'])
def test_general_format_contract(rounding):
    for value in (0, 1.23456789, 1e-20, 1e30):
        assert format_value(value, 'g', rounding) == format(value, 'g')


@pytest.mark.parametrize('orientation,location', [('vertical', 'right'), ('vertical', 'left'),
    ('horizontal', 'bottom'), ('horizontal', 'top')])
def test_automatic_margins_keep_visible_colorbar_text_in_figure(orientation, location):
    from matplotlib.text import Text
    fig = render({'H': 0}, title='Independent rendering', cbar_orientation=orientation,
                 cbar_location=location, cbar_label='Measurement units',
                 cbar={'ticks': [-1, 0, 1], 'labels': ['minus one', 'zero', 'plus one'], 'fontsize': 12})
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text in fig.findobj(match=Text):
        if not text.get_visible() or not text.get_text():
            continue
        box = text.get_window_extent(renderer)
        assert box.x0 >= -.5 and box.y0 >= -.5, text.get_text()
        assert box.x1 <= fig.bbox.width + .5 and box.y1 <= fig.bbox.height + .5, text.get_text()


def test_explicit_margins_and_box_are_not_adjusted():
    margins = [.1, .2, .8, .9]
    box = [.9, .1, .04, .8]
    fig = render(margins=margins, cbar_box=box)
    fig.canvas.draw()
    assert [fig.subplotpars.left, fig.subplotpars.bottom, fig.subplotpars.right,
            fig.subplotpars.top] == margins
    assert fig._ptable_colorbar.ax.get_position().bounds == pytest.approx(box)


@pytest.mark.parametrize('fill,expected', [('black', 'white'), ('white', 'black')])
def test_heatmap_default_text_contrasts_with_fill(fill, expected):
    fig = render({'H': 0}, cmap=['custom', [fill, fill]], label_color='auto')
    for role in ('number', 'symbol', 'value'):
        assert artists(fig, role)['H'].get_color() == expected
    assert all(t.get_color() == 'black' for t in artists(fig, 'series').values())


@pytest.mark.parametrize('kind', ['heatmap', 'labels'])
@pytest.mark.parametrize('label_color', ['#666666', 'black', 'red'])
def test_explicit_value_color_is_preserved(kind, label_color):
    fig = render({'H': 0}, kind=kind, label_color=label_color)
    assert artists(fig, 'value')['H'].get_color() == label_color
    if kind == 'labels':
        highlighted = render({'H': 0}, kind=kind, label_color=label_color, highlight_fg='navy')
        assert artists(highlighted, 'value')['H'].get_color() == 'navy'


def test_auto_labels_use_foreground_and_preserve_highlight_override():
    fig = render({'H': 'annotation'}, kind='labels', label_color='auto')
    assert artists(fig, 'value')['H'].get_color() == 'black'
    fig = render({'H': 'annotation'}, kind='labels', label_color='auto', highlight_fg='navy')
    assert artists(fig, 'value')['H'].get_color() == 'navy'


@pytest.mark.parametrize('field', ['empty', 'bg', 'highlight_fg'])
def test_auto_is_only_a_label_color_sentinel(field):
    with pytest.raises(ValueError, match=field):
        render(**{field: 'auto'})


def test_overlap_diagnostics_can_use_renderer_metadata_without_moving_text():
    from core.layout_diagnostics import inspect_layout
    fig = render({'H': 'long annotation that crosses multiple cells'}, kind='labels', label_fs=30)
    text = artists(fig, 'value')['H']
    position = text.get_position()
    issues = inspect_layout(fig)
    assert any(i['code'] == 'TEXT_OUTSIDE_CELL' and i['text']['element'] == 'H' for i in issues)
    assert text.get_position() == position and text.get_fontsize() == 30


def test_actual_agent_example_colorbar_labels_fit_figure():
    from pathlib import Path
    example = json.loads((Path(__file__).resolve().parents[1] /
                          'examples/agent-v2-render.json').read_text(encoding='utf-8'))
    fig = render_plot(PlotSpec.from_dict(example['plot']), example['data'])
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for text in fig._ptable_colorbar.ax.get_yticklabels():
        box = text.get_window_extent(renderer)
        assert 0 <= box.x0 <= box.x1 <= fig.bbox.width
        assert 0 <= box.y0 <= box.y1 <= fig.bbox.height


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), 'nan', 'Infinity', []])
def test_invalid_measurements_are_rejected(value):
    with pytest.raises(ValueError):
        render({'H': value})


def test_render_preserves_inputs_rc_and_pyplot_registry():
    from copy import deepcopy
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    data = {'H': '0', 'He': None}
    spec = PlotSpec.from_dict({'font': 'DejaVu Sans', 'show_symbol': False,
                               'show_number': False, 'transparent': True})
    before_data, before_spec = deepcopy(data), spec.to_dict()
    before_rc, before_figures = dict(mpl.rcParams), plt.get_fignums()
    fig = render_plot(spec, data)
    fig.canvas.draw()
    assert not artists(fig, 'number') and not artists(fig, 'symbol')
    assert fig.patch.get_alpha() == 0
    assert data == before_data and spec.to_dict() == before_spec
    assert dict(mpl.rcParams) == before_rc and plt.get_fignums() == before_figures
