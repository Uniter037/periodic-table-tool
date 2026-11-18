"""End-to-end contracts for the script-independent application boundary."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from application.agent_api import execute
from test_dataset_collection import service


def call(action, **fields):
    return execute({'api_version': 2, 'action': action, **fields})


def ok(action, **fields):
    response = call(action, **fields)
    assert response['ok'], response
    return response['result']


def test_create_update_revision_and_presets_are_plain_options(tmp_path):
    path = str(tmp_path / 'new.ptproj')
    created = ok('create', project=path, preset='labels', data={'Ni': '001'})
    assert created['document']['schema'] == 2
    assert created['resolved_plot']['kind'] == 'labels'
    assert 'mode_id' not in created['resolved_plot']
    updated = ok('update', project=path, expected_revision=created['revision'],
                 patch={'plot': {'value_fs': 12}, 'data': {'Fe': 'A'}})
    assert updated['document']['current']['data'] == {'Ni': '001', 'Fe': 'A'}
    assert updated['resolved_plot']['value_fs'] == 12
    assert call('update', project=path, expected_revision=created['revision'], patch={})['error']['code'] == 'REVISION_CONFLICT'
    original = Path(path).read_bytes()
    dry = ok('validate', project=path, patch={'data': {'Ni': None}})
    assert dry['document']['current']['data'] == {'Fe': 'A'}
    assert Path(path).read_bytes() == original
    assert call('create', project=path)['error']['code'] == 'OUTPUT_EXISTS'


def test_schema_one_requires_explicit_non_overwriting_migration(tmp_path):
    from application.project_codec import default_payload
    path = tmp_path / 'old.ptproj'
    payload = default_payload()
    payload['data'] = {'Fe': 0, 'Ni': '.5'}
    original = json.dumps({'schema': 1, 'current': payload, 'styles': {}}).encode()
    path.write_bytes(original)
    assert call('inspect', project=str(path))['error']['code'] == 'MIGRATION_REQUIRED'
    dry = ok('migrate', project=str(path))
    assert dry['document']['current']['data'] == payload['data']
    assert dry['dry_run']
    assert not (tmp_path / 'old-migrated.ptproj').exists()
    refused = call('migrate', project=str(path), expected_revision=dry['source_revision'],
                   dry_run=False, output_project=str(path))
    assert refused['error']['code'] == 'PATH_CONFLICT'
    saved = ok('migrate', project=str(path), expected_revision=dry['source_revision'], dry_run=False)
    assert Path(saved['project']).exists()
    assert path.read_bytes() == original
    assert ok('inspect', project=saved['project'])['document']['schema'] == 2


def test_native_render_never_imports_historical_engine(tmp_path):
    # A fresh interpreter detects eager imports that in-process tests cannot.
    code = '''
import sys
from application.agent_api import execute
result = execute({'api_version':2, 'action':'render', 'plot': {'dpi':72},
                  'data':{'Fe':0, 'Ni':.5}, 'formats':['png','svg'], 'output_dir':sys.argv[1]})
assert result['ok'], result
assert not {'core.styles','core.ptable','core.options','core.scientific','application.project_codec'} & set(sys.modules)
assert all(item['bytes'] > 0 for item in result['result']['files'])
'''
    subprocess.run([sys.executable, '-c', code, str(tmp_path)], check=True, timeout=90)
    assert len(list(tmp_path.iterdir())) == 2


def test_render_labels_colorbar_and_file_naming(tmp_path):
    plot = {'kind': 'labels', 'show_cbar': False, 'value_fs': 9, 'title': 'Samples'}
    first = ok('render', plot=plot, data={'Ni': '001', 'Ti': 'A'}, formats=['svg'], output_dir=str(tmp_path))
    second = ok('render', plot=plot, data={'Ni': '001', 'Ti': 'A'}, formats=['svg'], output_dir=str(tmp_path))
    assert first['files'][0]['path'] != second['files'][0]['path']
    assert first['plot_fingerprint'] == second['plot_fingerprint']
    assert Path(first['files'][0]['path']).stat().st_size > 1000


@pytest.mark.parametrize('fields,code', [
    ({'plot': {'dpi': True}}, 'VALIDATION_ERROR'),
    ({'plot': {'compatibility': True}}, 'VALIDATION_ERROR'),
    ({'formats': ['exe']}, 'INVALID_REQUEST'),
    ({'base': '../escape'}, 'INVALID_REQUEST'),
    ({'plot': {'figsize': [40, 40], 'dpi': 1200}}, 'OUTPUT_TOO_LARGE'),
    ({'data': {'Fe': 5}}, 'RANGE_WARNING'),
    ({'data': []}, 'VALIDATION_ERROR'),
    ({'data': {'Fe': True}}, 'VALIDATION_ERROR'),
    ({'plot': {'label_color': 'not_a_color'}}, 'VALIDATION_ERROR'),
])
def test_invalid_requests_publish_nothing(tmp_path, fields, code):
    request = {'data': {'Fe': 0}, 'output_dir': str(tmp_path), **fields}
    result = call('render', **request)
    assert not result['ok'], result
    assert result['error']['code'] == code
    assert not list(tmp_path.iterdir())


def test_service_rolls_back_only_its_files(tmp_path, monkeypatch):
    from application.plot_service import export_plots
    from core import saver
    original = saver.save_figure
    existing = tmp_path / 'keep.svg'
    existing.write_text('user file')
    def fail_pdf(fig, directory, base, fmt, **kwargs):
        if fmt == 'pdf':
            raise OSError('simulated disk failure')
        return original(fig, directory, base, fmt, **kwargs)
    monkeypatch.setattr(saver, 'save_figure', fail_pdf)
    with pytest.raises(OSError, match='disk failure'):
        export_plots({}, [({}, {'Fe': 0})], tmp_path, ['svg', 'pdf'])
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_text() == 'user file'


def test_excel_edits_switch_and_shared_scale_batch(service, tmp_path, monkeypatch):
    project = str(tmp_path / 'excel.ptproj')
    created = ok('create', project=project, plot={'norm': ['normalize', 0, 10], 'dpi': 72})
    imported = ok('import_excel', project=project, expected_revision=created['revision'],
                  workbook=str(service._path), sheet='Values', elements_range='B1:C1',
                  conditions_range='A2:A3', values_range='B2:C3', direction='matrix_rows')
    ids = imported['dataset_ids']
    edit = ok('update', project=project, expected_revision=imported['revision'],
              patch={'data': {'H': '001'}})
    switched = ok('update', project=project, expected_revision=edit['revision'], dataset_id=ids[1])
    assert switched['document']['current']['data'] == {'H': 2, 'He': 3}
    from infrastructure.rendering import renderer
    original = renderer.render_plot
    seen = []
    def observe(spec, data):
        seen.append((spec.to_dict()['norm'], dict(data)))
        return original(spec, data)
    monkeypatch.setattr(renderer, 'render_plot', observe)
    before = Path(project).read_bytes()
    result = ok('batch_export', project=project, dataset_ids=ids[::-1],
                expected_revision=switched['revision'], output_dir=str(tmp_path / 'images'), formats=['png'])
    assert seen == [(['normalize', 0, 10], {'H': 2, 'He': 3}), (['normalize', 0, 10], {'H': 1})]
    assert result['dataset_ids'] == ids[::-1]
    assert len(result['files']) == 2
    assert Path(project).read_bytes() == before


def test_migration_block_returns_structured_report(tmp_path):
    from application.project_codec import default_payload
    path = tmp_path / 'preview.ptproj'
    path.write_text(json.dumps({'schema': 1, 'current': default_payload('cmap_preview'), 'styles': {}}))
    response = call('migrate', project=str(path))
    assert response['error']['code'] == 'MIGRATION_BLOCKED'
    assert response['error']['details']['unsupported_fields']
