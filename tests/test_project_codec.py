import copy
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from application.project_codec import (default_payload, resolve_payload,
                                       validate_payload, PARAM_DEFAULTS, PARAM_CHOICES)
from core.styles import STYLES


@pytest.mark.parametrize('mode', STYLES)
def test_defaults_all_modes(mode):
    payload = default_payload(mode)
    assert set(payload['params']) == set(PARAM_DEFAULTS)
    assert payload['data'] == {}
    assert json.loads(json.dumps(validate_payload(payload))) == json.loads(json.dumps(payload))
    resolve_payload(payload)
    payload['compatibility'] = True
    resolve_payload(payload)


def test_extensions_and_legacy_missing_fields():
    source = dict(mode_id='custom', params={'edge': '黑色细线'},
                  data={'H': '0.000'}, extension={'version': 3})
    before = copy.deepcopy(source)
    result = validate_payload(source)
    assert result['extension'] == source['extension']
    assert result['data'] == {'H': '0.000'}
    assert result['params']['edge_width'] == '0.5'
    assert source == before
    assert resolve_payload(source)['edge'] == (0.5, 'black')


@pytest.mark.parametrize('change', [
    {'params': {'typo': '1'}}, {'display': {'typo': True}},
    {'params': {'layout': 'classic'}}, {'params': {'dpi': '600'}},
    {'params': {'vmax': 'nan'}}, {'params': {'figsize': '0x0'}},
    {'params': {'margins': '0,0,2,2'}}, {'params': {'cmap': 'bad:cmap'}},
    {'params': {'rounding': 'half_up'}}, {'params': {'vmin': 0}},
    {'display': {'show_value': 1}}, {'show_cbar': 1},
    {'output_format': 'jpg'}, {'data': {'Xx': '1'}},
    {'data': {'H': 'oops'}}, {'data': {'H': True}},
    {'element_overrides': {'H': {'typo': False}}},
    {'custom_colors': [[0, 0, 0]]},
    {'cbar_override': {'ticks': [0], 'labels': []}},
])
def test_invalid_payload(change):
    with pytest.raises(ValueError):
        validate_payload(dict(mode_id='custom', **change))


def test_labels_preserve_raw_data_and_colorbar_visibility():
    payload = default_payload()
    payload['params']['kind'] = '标注图（文本）'
    payload['data'] = {'H': '  3c1\n氢  '}
    payload['element_overrides'] = {'H': {'show_color': False, 'value_dx': .1}}
    payload['cbar_override'] = dict(ticks=[1, 0], labels=['one', 'zero'], visible=[False, True])
    before = copy.deepcopy(payload)
    style = resolve_payload(payload)
    assert style['element_overrides'] == payload['element_overrides']
    assert style['cbar']['ticks'] == [0]
    assert style['cbar']['labels'] == ['zero']
    payload['show_cbar_labels'] = False
    assert resolve_payload(payload)['cbar']['labels'] == ['']
    payload['show_cbar_labels'] = True
    assert payload == before
    assert validate_payload(payload)['data'] == before['data']


def test_corrected_and_legacy_policy():
    payload = default_payload('classic_coolwarm')
    assert resolve_payload(payload)['norm'] == ('twoslope', .61, .73, .77)
    payload['compatibility'] = True
    style = resolve_payload(payload)
    assert style['norm'] == STYLES['classic_coolwarm']['norm']
    assert not style.get('corrected')


def test_app_fake_object_uses_same_function():
    from main import App
    from core.scientific import corrected_style
    payload = default_payload()
    def variable(value):
        return SimpleNamespace(get=lambda: value)
    fake = SimpleNamespace(param_vars={k: variable(v) for k, v in payload['params'].items()},
        bool_vars={k: variable(v) for k, v in payload['display'].items()},
        compat_var=variable(False), custom_colors=payload['custom_colors'],
        element_overrides=payload['element_overrides'])
    actual = App._apply_custom_params(fake, corrected_style(STYLES['custom']))
    expected = resolve_payload(payload)
    expected.pop('show_cbar')
    assert actual == expected


def test_import_does_not_load_gui():
    subprocess.run([sys.executable, '-c',
        "import sys; import application.project_codec; "
        "assert 'main' not in sys.modules; assert 'tkinter' not in sys.modules; "
        "assert not any(k == 'ui' or k.startswith('ui.') for k in sys.modules)"], check=True)


@pytest.mark.parametrize('mode', STYLES)
@pytest.mark.parametrize('compatibility', [False, True])
def test_real_app_snapshot_matches_work_style(app, mode, compatibility):
    app._style_states.clear()
    app.mode_combo.current(list(STYLES).index(mode))
    app._on_style_change()
    app._cancel_refresh()
    app.compat_var.set(compatibility)
    app.data = {'H': '001.00'}
    app.element_overrides = {'H': {'show_color': False, 'value_dx': .15}}
    for override, labels_visible, cbar_visible in (
            (None, True, True),
            (dict(ticks=[1, 0], labels=['一', '零'], visible=[False, True]), True, True),
            (dict(ticks=[1, 0], labels=['一', '零'], visible=[False, True]), False, False)):
        app.cbar_override = override
        app.show_cbar_labels_var.set(labels_visible)
        app.show_cbar_var.set(cbar_visible)
        payload = copy.deepcopy(app._current_preset_payload())
        payload['extension'] = {'keep': ['原值']}
        before = copy.deepcopy(payload)
        expected = copy.deepcopy(app._current_work_style())
        actual = resolve_payload(payload)
        assert actual.pop('show_cbar') is cbar_visible
        assert actual == expected
        validated = validate_payload(payload)
        assert validated['data'] == before['data']
        assert validated['extension'] == before['extension']
        assert payload == before

@pytest.mark.parametrize('mode', ['labels_light', 'labels_highlight', 'custom'])
@pytest.mark.parametrize('compatibility', [False, True])
def test_missing_and_empty_format_use_gui_fallback(mode, compatibility):
    payload = default_payload(mode)
    payload['compatibility'] = compatibility
    payload['data'] = {'H': '001.00'}
    payload['extension'] = {'raw': ['unchanged']}
    expected = resolve_payload(payload)
    for missing in (False, True):
        candidate = copy.deepcopy(payload)
        if missing:
            candidate['params'].pop('fmt')
        else:
            candidate['params']['fmt'] = ''
        before = copy.deepcopy(candidate)
        assert resolve_payload(candidate) == expected
        validated = validate_payload(candidate)
        assert validated['data'] == payload['data']
        assert validated['extension'] == payload['extension']
        assert candidate == before


@pytest.mark.parametrize('mode,key,value', [
    ('labels_light', 'fmt', '3ff'),
    ('labels_highlight', 'fmt', ' '),
    ('labels_light', 'kind', 'None'),
    ('custom', 'kind', 'None'),
    ('cmap_preview', 'kind', 'none'),
    ('cmap_preview', 'kind', ''),
    ('cmap_preview', 'layout', 'None'),
    ('labels_light', 'dpi', ''),
])
def test_placeholder_compatibility_does_not_accept_typos(mode, key, value):
    payload = default_payload(mode)
    payload['params'][key] = value
    with pytest.raises(ValueError):
        validate_payload(payload)
