"""Renderer geometry and real-export contracts for advisory layout diagnostics."""
from copy import deepcopy
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pytest

from application.agent_api import execute
from core.layout_diagnostics import inspect_layout, layout_warnings
from core.styles import STYLES, render_table
from test_agent_extensions import batch_project, patch
from test_dataset_collection import service


@pytest.fixture
def canvas():
    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    ax.set(xlim=(0, 1), ylim=(0, 1))
    yield fig, ax
    plt.close(fig)


def label(ax, x, y, element='H', role='value', cell=(0, 0, 1, 1), **kwargs):
    text = ax.text(x, y, 'sample', fontsize=12, ha='center', va='center', **kwargs)
    text._ptable_element = element
    text._ptable_role = role
    text._ptable_cell = cell
    return text


def test_overlap_reports_both_labels_and_figure_fraction_bounds(canvas):
    fig, ax = canvas
    first = label(ax, .4, .5)
    second = label(ax, .4, .5, element='He', role='symbol')
    issues = inspect_layout(fig)
    assert [item['code'] for item in issues] == ['TEXT_OVERLAP']
    issue = issues[0]
    assert issue['suggestion']
    by_element = {item['element']: item for item in (issue['text'], issue['other'])}
    for text in (first, second):
        item = by_element[text._ptable_element]
        assert item['role'] == text._ptable_role
        expected = text.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted()).bounds
        assert item['bounds'] == pytest.approx(expected, abs=1e-9)
        x, y, width, height = item['bounds']
        assert 0 < x < 1 and 0 < y < 1 and width > 0 and height > 0
    before = deepcopy(issues)
    warnings = layout_warnings(issues)
    assert warnings and all(isinstance(warning, str) and warning for warning in warnings)
    assert issues == before
    assert layout_warnings([]) == []


def test_separated_hidden_empty_and_unannotated_text_are_ignored(canvas):
    fig, ax = canvas
    label(ax, .2, .5)
    label(ax, .8, .5, element='He')
    label(ax, .2, .5, element='Li', visible=False)
    empty = label(ax, .2, .5, element='Be')
    empty.set_text('')
    ax.text(.2, .5, 'unannotated', fontsize=30)
    assert inspect_layout(fig) == []


def test_cell_overflow_without_overlap(canvas):
    fig, ax = canvas
    label(ax, .75, .5, cell=(.1, .1, .2, .8))
    issues = inspect_layout(fig)
    assert len(issues) == 1
    assert issues[0]['code'] == 'TEXT_OUTSIDE_CELL'
    assert issues[0]['text']['element'] == 'H'
    assert issues[0]['suggestion']


def test_inspection_does_not_mutate_artists_or_axes(canvas):
    fig, ax = canvas
    label(ax, .5, .5)
    label(ax, .5, .5, element='He')
    fig.canvas.draw()

    def snapshot():
        return (ax.get_position().bounds, ax.get_xlim(), ax.get_ylim(),
                tuple((id(t), t.get_text(), t.get_position(), t.get_visible(),
                       t.get_fontsize(), t.get_color(), t._ptable_element,
                       t._ptable_role, t._ptable_cell) for t in ax.texts),
                tuple(map(id, fig.axes)), tuple(map(id, ax.patches)))

    before = snapshot()
    first = inspect_layout(fig)
    assert first
    assert inspect_layout(fig) == first
    assert snapshot() == before


def test_per_element_offsets_have_exact_data_and_figure_transform():
    style = dict(STYLES['custom'], value_dx=.1, value_dy=.2)
    data = {'H': .25, 'He': .5}
    edited = deepcopy(style)
    edited['element_overrides'] = {'H': {'value_dx': .3, 'value_dy': -.4}}
    before = deepcopy((edited, data))
    figures = []
    try:
        for settings in (style, edited):
            fig = render_table(settings, data, show_cbar=False)
            figures.append(fig)
            fig.canvas.draw()
        def texts(fig):
            return {(t._ptable_element, t._ptable_role): t for t in fig.axes[0].texts}
        baseline, moved = map(texts, figures)
        assert ('H', 'value') in baseline
        for key, original in baseline.items():
            actual = moved[key]
            delta = np.array((.3, -.4) if key == ('H', 'value') else (0., 0.))
            assert actual.get_position() == pytest.approx(np.array(original.get_position()) + delta, abs=1e-10)
            old_bounds = original.get_window_extent().transformed(figures[0].transFigure.inverted()).bounds
            new_bounds = actual.get_window_extent().transformed(figures[1].transFigure.inverted()).bounds
            transform = figures[1].axes[0].transData + figures[1].transFigure.inverted()
            expected_delta = transform.transform(delta) - transform.transform((0, 0))
            assert np.array(new_bounds[:2]) - old_bounds[:2] == pytest.approx(expected_delta, abs=1e-9)
            assert new_bounds[2:] == pytest.approx(old_bounds[2:], abs=1e-9)
        assert (edited, data) == before
    finally:
        for fig in figures:
            plt.close(fig)


def api(action, **fields):
    response = execute(dict(api_version=1, action=action, **fields))
    assert response['ok'], response
    return response['result']


@pytest.mark.parametrize('action', ['render', 'export'])
@pytest.mark.parametrize('enabled', [None, False])
def test_real_export_layout_advisories_need_no_range_acknowledgement(tmp_path, action, enabled):
    # Large in-range numeric labels guarantee overflow without range warnings.
    patch = {'params': {'figsize': '4x2', 'dpi': '100', 'font': 'DejaVu Sans',
                        'value_fs': '60'}, 'data': {'H': .25}, 'show_cbar': False}
    if enabled is not None:
        patch['display'] = {'check_label_overlap': enabled}
    if action == 'export':
        project = tmp_path / 'layout.ptproj'
        api('create', project=str(project), patch=patch)
        original = project.read_bytes()
        fields = {'project': str(project)}
    else:
        fields = {'patch': patch}
    request_before = deepcopy(fields)
    result = api(action, output_dir=str(tmp_path / 'out'), formats=['svg'], **fields)
    assert fields == request_before
    assert result['files']
    for entry in result['files']:
        assert Path(entry['path']).read_text(encoding='utf-8').find('<svg') >= 0
    if enabled is False:
        assert result['layout_issues'] == []
        assert result['warnings'] == []
    else:
        assert any(issue['code'] == 'TEXT_OUTSIDE_CELL' for issue in result['layout_issues'])
        assert result['warnings'] == layout_warnings(result['layout_issues'])
    if action == 'export':
        assert project.read_bytes() == original


def test_validate_does_not_render(tmp_path, monkeypatch):
    import core.styles
    project = tmp_path / 'validate.ptproj'
    api('create', project=str(project), patch={'data': {'H': .25}})
    monkeypatch.setattr(core.styles, 'render_table', lambda *a, **kw: pytest.fail('validate rendered'))
    api('validate', project=str(project), patch={'display': {'check_label_overlap': True}})


def test_batch_reports_layout_issues_per_dataset(batch_project, tmp_path):
    import json
    project, ids = batch_project
    document = json.loads(project.read_text(encoding='utf-8'))
    document['current']['params']['value_fs'] = '60'
    project.write_text(json.dumps(document), encoding='utf-8')
    original = project.read_bytes()
    result = api('batch_export', project=str(project), output_dir=str(tmp_path / 'batch-layout'),
                 formats=['svg'])
    assert [item['dataset_id'] for item in result['datasets']] == ids
    for dataset in result['datasets']:
        assert dataset['layout_issues']
        assert any(issue['code'] == 'TEXT_OUTSIDE_CELL' for issue in dataset['layout_issues'])
        assert all(warning in dataset['warnings'] for warning in layout_warnings(dataset['layout_issues']))
        assert len(dataset['files']) == 1
        assert Path(dataset['files'][0]['path']).is_file()
    assert project.read_bytes() == original
