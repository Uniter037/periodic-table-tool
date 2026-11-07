"""Public agent API contracts, real exports, CLI isolation and native GUI interop."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from application.agent_api import execute

ROOT = Path(__file__).resolve().parents[1]


def call(action, **fields):
    return execute(dict(api_version=1, action=action, **fields))


def success(response):
    assert response['api_version'] == 1
    assert response['ok'] is True, response
    return response['result']


def failure(response, code=None):
    assert response['ok'] is False, response
    assert response['error']['message']
    assert response['error']['code'] != 'INTERNAL_ERROR', response
    if code:
        assert response['error']['code'] == code, response


@pytest.fixture
def project(tmp_path):
    path = tmp_path / '项目.ptproj'
    result = success(call('create', project=str(path), patch={'data': {'H': '0.000', 'Fe': .5}}))
    return path, result


def update(path, revision, patch, **fields):
    return call('update', project=str(path), expected_revision=revision, patch=patch, **fields)


def test_describe_create_inspect_revision_and_input_immutability(tmp_path):
    info = success(call('describe', request_id='契约'))
    assert {'describe', 'create', 'inspect', 'update', 'export'} <= info['actions'].keys()
    assert 'expected_revision' in info['actions']['update']
    assert {'data', 'replace_data', 'element_overrides'} <= set(info['patch_fields'])
    assert info['default_payload']['mode_id'] in {s['id'] for s in info['styles']}
    path = tmp_path / 'native.ptproj'
    request = dict(api_version=1, action='create', request_id=17, project=str(path),
                   patch={'params': {'title': '原始数据'}, 'data': {'H': '0.000', 'Fe': .5}})
    before = copy.deepcopy(request)
    response = execute(request)
    result = success(response)
    assert request == before
    assert response['request_id'] == 17
    assert result['project'] == str(path.resolve())
    assert result['revision'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert re.fullmatch('[0-9a-f]{64}', result['revision'])
    assert json.loads(json.dumps(result['document'])) == json.loads(path.read_text(encoding='utf-8'))
    assert result['document']['schema'] == 1
    assert result['document']['current']['data'] == request['patch']['data']
    assert json.loads(json.dumps(success(call('inspect', project=str(path))))) == json.loads(json.dumps(result))
    raw = path.read_bytes()
    failure(execute(request), 'OUTPUT_EXISTS')
    assert path.read_bytes() == raw


@pytest.mark.parametrize('fields,code', [
    ({}, 'REVISION_REQUIRED'), ({'expected_revision': None}, 'REVISION_REQUIRED'),
    ({'expected_revision': True}, 'REVISION_REQUIRED'),
    ({'expected_revision': 'not-a-sha'}, 'REVISION_CONFLICT'),
    ({'expected_revision': '0' * 64}, 'REVISION_CONFLICT'),
])
def test_update_requires_matching_sha_and_is_atomic(project, fields, code):
    path, _ = project
    raw = path.read_bytes()
    failure(call('update', project=str(path), patch={'data': {'H': 1}}, **fields), code)
    assert path.read_bytes() == raw


def test_data_merge_delete_replace_and_stale_revision(project):
    path, original = project
    merged = success(update(path, original['revision'], {'data': {'H': None, 'C': '0.25'}}))
    assert merged['document']['current']['data'] == {'Fe': .5, 'C': '0.25'}
    raw = path.read_bytes()
    failure(update(path, original['revision'], {'data': {'Fe': 1}}), 'REVISION_CONFLICT')
    assert path.read_bytes() == raw
    replaced = success(update(path, merged['revision'], {'replace_data': True, 'data': {'He': '0'}}))
    assert replaced['document']['current']['data'] == {'He': '0'}
    cleared = success(update(path, replaced['revision'], {'replace_data': True, 'data': {}}))
    assert cleared['document']['current']['data'] == {}
    assert cleared['revision'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_element_overrides_merge_preserves_raw_data(project):
    path, result = project
    raw_data = result['document']['current']['data']
    result = success(update(path, result['revision'], {'element_overrides': {
        'H': {'show_color': False, 'value_dx': .1}, 'Fe': {'show_value': False}}}))
    result = success(update(path, result['revision'], {'element_overrides': {'H': {'show_value': False}, 'Fe': None}}))
    assert result['document']['current']['element_overrides'] == {
        'H': {'show_color': False, 'value_dx': .1, 'show_value': False}}
    assert result['document']['current']['data'] == raw_data
    assert success(call('inspect', project=str(path)))['document'] == result['document']


@pytest.mark.parametrize('patch', [
    {'typo': True}, {'params': {'typo': '1'}}, {'display': {'typo': True}},
    {'element_overrides': {'H': {'typo': True}}},
    {'data': {'Xx': 1}}, {'element_overrides': {'Xx': {'show_value': False}}},
    {'data': {'H': True}}, {'data': {'H': float('nan')}},
    {'data': {'H': float('inf')}}, {'data': {'H': -float('inf')}},
    {'data': {'H': 'nan'}}, {'data': {'H': 'Infinity'}},
    {'params': {'vmin': True}}, {'params': {'vmax': 'nan'}},
    {'element_overrides': {'H': {'value_dx': True}}},
    {'element_overrides': {'H': {'value_dx': float('inf')}}},
    {'element_overrides': {'H': {'show_value': 1}}},
    {'show_cbar': 1}, {'display': {'show_symbol': 1}},
    {'replace_data': 1}, {'replace_data': True}, {'data': []},
])
def test_invalid_patch_rejected_without_writes(project, tmp_path, patch):
    path, result = project
    raw = path.read_bytes()
    target = tmp_path / 'invalid.ptproj'
    failure(update(path, result['revision'], patch, output_project=str(target)))
    assert path.read_bytes() == raw
    assert not target.exists()


@pytest.mark.parametrize('api_request,code', [
    ({'api_version': True, 'action': 'describe'}, 'API_VERSION'),
    ({'api_version': 2, 'action': 'describe'}, 'API_VERSION'),
    ({'api_version': 1, 'action': 'nope'}, 'UNKNOWN_ACTION'),
    ({'api_version': 1, 'action': 'describe', 'typo': 1}, 'INVALID_REQUEST'),
])
def test_request_validation(api_request, code):
    failure(execute(api_request), code)


def test_update_save_as_preserves_source_and_existing_target(project, tmp_path):
    path, result = project
    original = path.read_bytes()
    target = tmp_path / '另存.ptproj'
    saved = success(update(path, result['revision'], {'data': {'C': '0.1'}}, output_project=str(target)))
    assert path.read_bytes() == original
    assert saved['project'] == str(target.resolve())
    assert saved['revision'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert success(call('inspect', project=str(target)))['document']['current']['data']['C'] == '0.1'
    existing = target.read_bytes()
    failure(update(path, result['revision'], {'data': {'C': .2}}, output_project=str(target)), 'OUTPUT_EXISTS')
    assert path.read_bytes() == original
    assert target.read_bytes() == existing


def test_native_project_gui_roundtrip(app, project, tmp_path):
    path, result = project
    assert app._open_project(path=path)
    assert app.data == result['document']['current']['data']
    assert app.param_vars['vmin'].get() == result['document']['current']['params']['vmin']
    target = tmp_path / 'gui.ptproj'
    assert app._save_project(path=target)
    inspected = success(call('inspect', project=str(target)))
    assert inspected['document']['current'] == json.loads(json.dumps(result['document']['current']))
    changed = success(update(target, inspected['revision'], {'params': {'title': 'API 往返'},
        'element_overrides': {'H': {'show_color': False}}, 'data': {'C': '0.0010'}}))
    assert app._open_project(path=target)
    assert app.data == changed['document']['current']['data']
    assert app.element_overrides == changed['document']['current']['element_overrides']
    assert app.param_vars['title'].get() == 'API 往返'


def test_real_export_formats_auto_names_and_no_overwrite(project, tmp_path, monkeypatch):
    monkeypatch.setenv('MPLBACKEND', 'Agg')
    from PIL import Image
    path, result = project
    original = path.read_bytes()
    directory = tmp_path / 'exports'
    previous = {}
    for _ in range(2):
        exported = success(call('export', project=str(path), expected_revision=result['revision'],
                                output_dir=str(directory), formats=['png', 'svg', 'pdf']))
        assert len(exported['files']) == 3
        assert not exported['warnings']
        for entry in exported['files']:
            output = Path(entry['path'])
            raw = output.read_bytes()
            assert output.parent == directory
            assert re.fullmatch(r'periodic_table_\d{8}_\d{6}(?:_\d+)?\.(png|svg|pdf)', output.name)
            assert output not in previous
            assert entry['bytes'] == len(raw) > 100
            assert entry['sha256'] == hashlib.sha256(raw).hexdigest()
            if output.suffix == '.png':
                with Image.open(output) as image:
                    image.verify()
            elif output.suffix == '.svg':
                assert ET.fromstring(raw).tag.endswith('svg')
            else:
                assert raw.startswith(b'%PDF-') and b'%%EOF' in raw[-1024:]
            previous[output] = raw
        assert all(p.read_bytes() == raw for p, raw in previous.items())
    assert path.read_bytes() == original


def test_export_range_requires_explicit_boolean_confirmation(project, tmp_path):
    path, result = project
    result = success(update(path, result['revision'], {'data': {'H': 100}}))
    original = path.read_bytes()
    directory = tmp_path / 'range-export'
    fields = dict(project=str(path), output_dir=str(directory), formats=['svg'])
    failure(call('export', **fields), 'RANGE_WARNING')
    failure(call('export', **fields, allow_out_of_range=False), 'RANGE_WARNING')
    failure(call('export', **fields, allow_out_of_range=1), 'INVALID_REQUEST')
    assert not directory.exists() or not list(directory.iterdir())
    exported = success(call('export', **fields, allow_out_of_range=True))
    assert exported['warnings'] and Path(exported['files'][0]['path']).stat().st_size > 100
    assert path.read_bytes() == original


def run_python(*args, input=None):
    env = dict(os.environ, MPLBACKEND='Agg', PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, input=input,
                          encoding='utf-8', capture_output=True, timeout=90)


def test_pure_execute_does_not_import_tkinter(tmp_path):
    script = r'''
import json, sys
from application.agent_api import execute
path = sys.argv[1]
def invoke(action, **kw):
    response = execute(dict(api_version=1, action=action, **kw))
    assert response['ok'], response
    return response['result']
invoke('describe')
r = invoke('create', project=path, patch={'data': {'H': '0.0'}})
invoke('inspect', project=path)
invoke('update', project=path, expected_revision=r['revision'], patch={'data': {'C': .1}})
assert 'tkinter' not in sys.modules
assert 'main' not in sys.modules
assert not any(k == 'ui' or k.startswith('ui.') for k in sys.modules)
print(json.dumps({'ok': True}))
'''
    process = run_python('-c', script, str(tmp_path / 'headless.ptproj'))
    assert process.returncode == 0, process.stderr + process.stdout
    assert json.loads(process.stdout) == {'ok': True}


def test_cli_json_stdin_file_and_error_exit(tmp_path):
    process = run_python('-m', 'application.agent_api', '--request', '-',
                         input=json.dumps(dict(api_version=1, action='describe', request_id='cli')))
    assert process.returncode == 0, process.stderr
    response = json.loads(process.stdout)
    success(response)
    assert response['request_id'] == 'cli'
    request = tmp_path / 'request.json'
    response_path = tmp_path / 'response.json'
    path = tmp_path / 'cli.ptproj'
    request.write_text(json.dumps(dict(api_version=1, action='create', project=str(path),
                                      patch={'data': {'H': '0'}})), encoding='utf-8')
    process = run_python('-m', 'application.agent_api', '--agent-request', str(request),
                         '--agent-response', str(response_path))
    assert process.returncode == 0, process.stderr + process.stdout
    assert not process.stdout.strip()
    result = success(json.loads(response_path.read_text(encoding='utf-8')))
    assert result['revision'] == hashlib.sha256(path.read_bytes()).hexdigest()
    process = run_python('-m', 'application.agent_api', '--request', '-', input='{"api_version":1,"action":"unknown"}')
    assert process.returncode == 2
    failure(json.loads(process.stdout), 'UNKNOWN_ACTION')
    process = run_python('-m', 'application.agent_api', '--request', '-', input='{"api_version":1,"api_version":1}')
    assert process.returncode == 2
    failure(json.loads(process.stdout), 'INVALID_JSON')





def test_validate_dry_run_preserves_original_bytes(project):
    path, original = project
    raw = path.read_bytes()
    for revision_fields in ({}, {'expected_revision': original['revision']}):
        result = success(call('validate', project=str(path),
            patch={'data': {'H': None, 'C': '0.250'}, 'params': {'title': 'dry run'}},
            **revision_fields))
        assert result['dry_run'] is True
        assert result['base_revision'] == hashlib.sha256(raw).hexdigest()
        assert 'revision' not in result
        assert result['document']['current']['data'] == {'Fe': .5, 'C': '0.250'}
        assert result['document']['current']['params']['title'] == 'dry run'
        assert isinstance(result['resolved_style'], dict)
        assert isinstance(result['warnings'], list)
        assert path.read_bytes() == raw
    assert success(call('inspect', project=str(path)))['document']['current']['data'] == {'H': '0.000', 'Fe': .5}
