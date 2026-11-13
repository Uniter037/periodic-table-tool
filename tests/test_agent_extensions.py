"""Agent render/batch contracts exercised through real, small figure exports."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
import pytest

from application.agent_api import execute
from application.dataset_collection import DatasetCollection
from test_dataset_collection import _preview, service


def call(action, **fields):
    return execute(dict(api_version=1, action=action, **fields))


def success(response):
    assert response['api_version'] == 1
    assert response['ok'], response
    return response['result']


def failure(response, code=None):
    assert not response['ok'], response
    error = response['error']
    assert error['message']
    assert error['code'] != 'INTERNAL_ERROR', response
    if code:
        assert error['code'] == code, response
    return error


@pytest.fixture
def patch():
    return {'params': {'figsize': '4x2', 'dpi': '100', 'font': 'DejaVu Sans'},
            'data': {'H': .125, 'He': .5}}


@pytest.fixture
def batch_project(tmp_path, service, patch):
    path = tmp_path / 'batch.ptproj'
    document = success(call('create', project=str(path), patch=patch))['document']
    collection = DatasetCollection()
    ids = collection.append(_preview(service))
    collection.select(ids[1])
    collection.set_manual_data({'He': .75})
    collection.select(ids[0])
    collection.set_manual_data({'H': -.5})
    document['excel_collection'] = collection.snapshot()
    document['excel_attached'] = True
    # Simulate native GUI edits newer than the collection's cached manual data.
    document['current']['data'] = {'H': .25}
    path.write_text(json.dumps(document), encoding='utf-8')
    return path, ids


def verify_files(result, directory, count):
    files = result['files']
    assert len(files) == count
    assert len({entry['path'] for entry in files}) == count
    for entry in files:
        path = Path(entry['path'])
        raw = path.read_bytes()
        assert path.parent == directory
        assert entry['bytes'] == len(raw) > 100
        assert entry['sha256'] == hashlib.sha256(raw).hexdigest()
        if path.suffix == '.png':
            with Image.open(path) as image:
                assert image.size == (400, 200)
                image.verify()
        else:
            assert path.suffix == '.svg'
            assert ET.fromstring(raw).tag.endswith('svg')
    return {Path(entry['path']): Path(entry['path']).read_bytes() for entry in files}


def test_render_is_stateless_and_does_not_mutate_request(tmp_path, patch):
    directory = tmp_path / 'render'
    request = dict(api_version=1, action='render', request_id='render-1', patch=patch,
                   output_dir=str(directory), formats=['png', 'svg'], base='tiny')
    before = deepcopy(request)
    figures = plt.get_fignums()
    response = execute(request)
    result = success(response)
    assert response['request_id'] == 'render-1'
    assert request == before
    assert not list(tmp_path.rglob('*.ptproj'))
    assert 'project' not in result and 'revision' not in result
    files = verify_files(result, directory, 2)
    again = verify_files(success(execute(request)), directory, 2)
    assert files.keys().isdisjoint(again)
    assert all(path.read_bytes() == raw for path, raw in files.items())
    assert plt.get_fignums() == figures
    failure(call('render', output_dir=str(tmp_path / 'empty')), 'EMPTY_DATA')


@pytest.mark.parametrize('show_cbar,show_labels', [(False, False), (True, False), (True, True)])
def test_render_honors_hidden_values_and_colorbar(tmp_path, patch, monkeypatch, show_cbar, show_labels):
    import core.saver
    save = core.saver.save_figure
    observed = []

    def capture(fig, *args, **kwargs):
        fig.canvas.draw()
        texts = [text.get_text() for text in fig.axes[0].texts]
        assert '0.125' not in texts
        assert '0.500' in texts
        assert len(fig.axes) == (2 if show_cbar else 1)
        if show_cbar:
            labels = [t.get_text() for t in fig.axes[1].get_yticklabels()]
            assert any(labels) == show_labels
        observed.append(True)
        return save(fig, *args, **kwargs)

    monkeypatch.setattr(core.saver, 'save_figure', capture)
    patch.update(show_cbar=show_cbar, show_cbar_labels=show_labels,
                 element_overrides={'H': {'show_value': False}})
    success(call('render', patch=patch, output_dir=str(tmp_path), formats=['svg']))
    assert observed == [True]


@pytest.mark.parametrize('fields', [
    {'formats': []}, {'formats': ['svg', 'svg']}, {'formats': ['jpg']},
    {'formats': 'png'}, {'base': '../escape'}, {'base': ''},
    {'allow_out_of_range': 1}, {'project': 'forbidden.ptproj'}, {'typo': True},
])
def test_render_rejects_invalid_request_without_files(tmp_path, patch, fields):
    failure(call('render', patch=patch, output_dir=str(tmp_path), **fields), 'INVALID_REQUEST')
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('bad_patch', [
    {'data': {'Xx': 1}}, {'show_cbar': 1}, {'params': {'typo': 'x'}},
    {'data': {'H': True}}, {'replace_data': True},
    {'element_overrides': {'H': {'show_value': 1}}},
])
def test_render_reuses_patch_validation(tmp_path, bad_patch):
    failure(call('render', patch=bad_patch, output_dir=str(tmp_path)))
    assert not list(tmp_path.iterdir())


def test_render_range_acknowledgement_and_canvas_limit(tmp_path, patch):
    patch['data'] = {'H': 100}
    fields = dict(patch=patch, output_dir=str(tmp_path), formats=['svg'])
    failure(call('render', **fields), 'RANGE_WARNING')
    assert not list(tmp_path.iterdir())
    assert success(call('render', **fields, allow_out_of_range=True))['warnings']
    patch['data'] = {'H': 0}
    patch['params'].update(figsize='40x40', dpi='300')
    failure(call('render', **fields), 'OUTPUT_TOO_LARGE')


@pytest.mark.parametrize('selection', ['all', 'reverse', 'one'])
def test_batch_real_exports_preserve_attached_edits_and_selection(batch_project, tmp_path, monkeypatch, selection):
    import core.styles
    path, ids = batch_project
    raw = path.read_bytes()
    render = core.styles.render_table
    seen = []

    def capture(style, data, **kwargs):
        seen.append(deepcopy(data))
        return render(style, data, **kwargs)

    monkeypatch.setattr(core.styles, 'render_table', capture)
    selected = ids if selection == 'all' else ids[::-1] if selection == 'reverse' else ids[1:]
    fields = {} if selection == 'all' else {'dataset_ids': selected, 'expected_revision': hashlib.sha256(raw).hexdigest()}
    request = dict(api_version=1, action='batch_export', project=str(path),
                   output_dir=str(tmp_path / 'out'), formats=['png', 'svg'], base='groups', **fields)
    before = deepcopy(request)
    result = success(execute(request))
    assert result['dataset_ids'] == selected
    assert [item['dataset_id'] for item in result['datasets']] == selected
    assert result['revision'] == hashlib.sha256(raw).hexdigest()
    assert seen == [{'H': .25} if key == ids[0] else {'He': .75} for key in selected]
    verify_files(result, tmp_path / 'out', 2 * len(selected))
    assert execute(dict(api_version=1, action='inspect', project=str(path)))['ok']
    assert path.read_bytes() == raw
    assert request == before


@pytest.mark.parametrize('selection', ['duplicate', 'unknown', 'empty', 'string', 'too_many'])
def test_batch_invalid_selection_writes_nothing(batch_project, tmp_path, selection):
    path, ids = batch_project
    raw = path.read_bytes()
    values = {'duplicate': [ids[0], ids[0]], 'unknown': ['missing'], 'empty': [],
              'string': ids[0], 'too_many': [f'group-{n}' for n in range(101)]}
    directory = tmp_path / 'out'
    failure(call('batch_export', project=str(path), dataset_ids=values[selection], output_dir=str(directory)))
    assert not directory.exists() or not list(directory.iterdir())
    assert path.read_bytes() == raw


@pytest.mark.parametrize('action', ['render', 'batch_export'])
def test_export_failure_rolls_back_only_owned_files(action, batch_project, tmp_path, patch, monkeypatch):
    import core.saver
    path, _ = batch_project
    raw = path.read_bytes()
    directory = tmp_path / 'rollback'
    directory.mkdir()
    sentinel = directory / 'unrelated.svg'
    sentinel.write_bytes(b'keep me')
    save = core.saver.save_figure
    saved = []
    figures = plt.get_fignums()

    def fail_after_first(fig, *args, **kwargs):
        if saved:
            assert Path(saved[0]).is_file()
            raise OSError('injected second save failure')
        result = save(fig, *args, **kwargs)
        saved.append(result)
        return result

    monkeypatch.setattr(core.saver, 'save_figure', fail_after_first)
    fields = {'patch': patch} if action == 'render' else {'project': str(path)}
    # Batch fails in the second dataset, after the first was fully published.
    formats = ['png', 'svg'] if action == 'render' else ['svg']
    failure(call(action, output_dir=str(directory), formats=formats, **fields), 'IO_ERROR')
    assert saved
    assert list(directory.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b'keep me'
    assert path.read_bytes() == raw
    assert plt.get_fignums() == figures


@pytest.mark.parametrize('action', ['update', 'validate', 'export', 'batch_export'])
def test_revision_conflicts_provide_recovery(batch_project, tmp_path, action):
    path, _ = batch_project
    raw = path.read_bytes()
    error = failure(call(action, project=str(path), expected_revision='0' * 64), 'REVISION_CONFLICT')
    assert error['details']['current_revision'] == hashlib.sha256(raw).hexdigest()
    assert error['details']['expected_revision'] == '0' * 64
    assert error['details']['recovery'] == 'inspect_and_review'
    assert path.read_bytes() == raw


def test_describe_keeps_existing_choices_and_adds_option_arrays():
    from application.project_codec import PARAM_CHOICES
    info = success(call('describe'))
    assert info['parameter_choices'] == PARAM_CHOICES
    assert set(PARAM_CHOICES) <= info['parameter_options'].keys()
    for name, choices in PARAM_CHOICES.items():
        assert info['parameter_options'][name] == list(choices)
    assert {'patch', 'output_dir', 'formats', 'base', 'allow_out_of_range'} == set(info['actions']['render'])
    assert {'project', 'expected_revision', 'dataset_ids', 'output_dir', 'formats', 'base', 'allow_out_of_range'} == set(info['actions']['batch_export'])
    assert info['action_required_fields']['render'] == []
    assert info['action_required_fields']['batch_export'] == ['project']
    assert set(info['action_required_fields']['update']) == {'project', 'expected_revision'}
    assert info['action_metadata']['batch_export']['max_groups'] == 100


@pytest.mark.parametrize('explicit', [False, True])
def test_batch_limit_counts_valid_groups(batch_project, tmp_path, explicit):
    path, _ = batch_project
    document = json.loads(path.read_text(encoding='utf-8'))
    snapshot = document['excel_collection']
    template = snapshot['datasets'][0]
    for index in range(99):
        dataset = deepcopy(template)
        dataset['id'] = f'extra-{index}'
        snapshot['datasets'].append(dataset)
    # Prove the fixture is valid, so rejection cannot be an unknown ID error.
    DatasetCollection.from_snapshot(snapshot)
    path.write_text(json.dumps(document), encoding='utf-8')
    raw = path.read_bytes()
    fields = {'dataset_ids': [item['id'] for item in snapshot['datasets']]} if explicit else {}
    directory = tmp_path / 'limit'
    error = failure(call('batch_export', project=str(path), output_dir=str(directory), **fields), 'INVALID_REQUEST')
    assert '100' in error['message']
    assert not directory.exists() or not list(directory.iterdir())
    assert path.read_bytes() == raw


def test_batch_preflights_later_range_warning_before_saving(batch_project, tmp_path, monkeypatch):
    import core.saver
    path, ids = batch_project
    document = json.loads(path.read_text(encoding='utf-8'))
    document['excel_collection']['manual_data'][ids[1]] = {'He': 100}
    path.write_text(json.dumps(document), encoding='utf-8')
    raw = path.read_bytes()
    directory = tmp_path / 'range'
    with monkeypatch.context() as guarded:
        guarded.setattr(core.saver, 'save_figure', lambda *a, **kw: pytest.fail('Saved before validating all groups'))
        failure(call('batch_export', project=str(path), output_dir=str(directory)), 'RANGE_WARNING')
    assert not directory.exists() or not list(directory.iterdir())
    result = success(call('batch_export', project=str(path), output_dir=str(directory),
                          formats=['svg'], allow_out_of_range=True))
    assert result['warnings']
    verify_files(result, directory, 2)
    assert path.read_bytes() == raw


def test_batch_rejects_mixed_metrics_but_accepts_single_metric_selection(batch_project, tmp_path):
    path, ids = batch_project
    document = json.loads(path.read_text(encoding='utf-8'))
    snapshot = document['excel_collection']
    metric = deepcopy(snapshot['metrics'][0])
    metric['id'] = 'different-metric'
    snapshot['metrics'].append(metric)
    snapshot['datasets'][1]['metric_id'] = metric['id']
    DatasetCollection.from_snapshot(snapshot)
    path.write_text(json.dumps(document), encoding='utf-8')
    raw = path.read_bytes()
    directory = tmp_path / 'mixed'
    for fields in ({}, {'dataset_ids': ids[::-1]}):
        error = failure(call('batch_export', project=str(path), output_dir=str(directory),
                             formats=['svg'], **fields), 'INVALID_REQUEST')
        assert 'metric' in error['message']
        assert not directory.exists() or not list(directory.iterdir())
    result = success(call('batch_export', project=str(path), dataset_ids=ids[1:],
                          output_dir=str(directory), formats=['svg']))
    verify_files(result, directory, 1)
    assert path.read_bytes() == raw
