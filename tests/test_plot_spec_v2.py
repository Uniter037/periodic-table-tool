"""Data-only configuration contracts; no GUI or Matplotlib required."""
from copy import deepcopy
import json
import subprocess
import sys

import pytest

from domain.plot_spec import PlotSpec, PlotSpecError


def test_snapshot_is_immutable_detached_and_roundtrips():
    incoming = {'cbar': {'ticks': [-1, 0, 1], 'labels': ['low', 'hidden', 'high'],
                         'visible': [True, False, True]}, 'element_overrides': {'Fe': {'show_color': False}}}
    before = deepcopy(incoming)
    spec = PlotSpec.from_dict(incoming)
    assert incoming == before
    incoming['cbar']['labels'].clear()
    output = spec.to_dict()
    output['element_overrides']['Fe']['show_color'] = True
    assert spec.to_dict()['element_overrides']['Fe']['show_color'] is False
    assert spec.to_dict()['cbar']['labels'] == before['cbar']['labels']
    assert spec == PlotSpec.from_dict(json.loads(json.dumps(spec.to_dict())))


@pytest.mark.parametrize('patch,path', [
    ({'compatibility': False}, 'plot'), ({'layout': 'classic'}, 'layout'),
    ({'show_cbar': 1}, 'show_cbar'), ({'dpi': True}, 'dpi'),
    ({'dpi': float('nan')}, 'dpi'), ({'dpi': float('inf')}, 'dpi'),
    ({'dpi': 10 ** 400}, 'dpi'), ({'norm': ['twoslope', 0, 0, 1]}, 'norm'),
    ({'norm': ['normalize', False, 1]}, 'norm[1]'),
    ({'cmap': 'some.module:payload'}, 'cmap'),
    ({'cmap': ['custom', [[.1, 'red'], [1, 'blue']]]}, 'cmap'),
    ({'edge': [1, [True, 0, 0]]}, 'edge[1][0]'),
    ({'margins': [.7, 0, .5, 1]}, 'margins'),
    ({'cbar_box': [.9, 0, .2, .8]}, 'cbar_box'),
    ({'cbar_location': 'top'}, 'cbar_location'),
    ({'cbar': {'ticks': [0, 0], 'labels': ['a', 'b']}}, 'cbar.ticks'),
    ({'cbar': {'ticks': [0], 'labels': ['a'], 'visible': [1]}}, 'cbar.visible[0]'),
    ({'element_overrides': {'Xx': {}}}, 'element_overrides.Xx'),
    ({'element_overrides': {'Fe': {'show_value': 1}}}, 'element_overrides.Fe.show_value'),
    ({'label_wrap': .5}, 'label_wrap'),
])
def test_invalid_fields_have_actionable_paths(patch, path):
    with pytest.raises(PlotSpecError) as error:
        PlotSpec.from_dict(patch)
    assert error.value.path == path


def test_color_nodes_are_sorted_without_mutating_input():
    colors = [[1, 'red'], [0, 'blue'], [.5, 'white']]
    spec = PlotSpec.from_dict({'cmap': ['custom', colors]})
    assert spec.to_dict()['cmap'][1] == [[0, 'blue'], [.5, 'white'], [1, 'red']]
    assert colors[0][0] == 1


def test_domain_import_does_not_load_rendering_or_gui():
    code = '''
import sys
from domain.plot_spec import PlotSpec
assert PlotSpec.from_dict({}).to_dict()['layout'] == 'expanded'
assert not any(n == 'core' or n.startswith(('core.', 'matplotlib', 'tkinter')) for n in sys.modules)
'''
    subprocess.run([sys.executable, '-c', code], check=True, timeout=20)
