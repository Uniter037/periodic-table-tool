"""Migration acceptance tests use only synthetic, non-private snapshots."""
from copy import deepcopy

import pytest

from application.project_codec import default_payload, resolve_payload
from application.project_migrations import MigrationError, migrate_document
from core.styles import STYLES
from domain.plot_spec import PlotSpec


def document(payload=None):
    return dict(schema=1, current=payload or default_payload(), styles={})


@pytest.mark.parametrize('mode', list(STYLES))
@pytest.mark.parametrize('compatibility', [False, True])
def test_every_legacy_style_uses_effective_configuration(mode, compatibility):
    payload = default_payload(mode)
    payload['compatibility'] = compatibility
    old = resolve_payload(payload)
    source = document(payload)
    before = deepcopy(source)
    if mode == 'cmap_preview':
        with pytest.raises(MigrationError) as error:
            migrate_document(source)
        assert error.value.report['unsupported_fields'][0]['value'] == 'cmap'
    else:
        result = migrate_document(source)
        plot = result['document']['current']['plot']
        assert plot == PlotSpec.from_dict(plot).to_dict()
        assert plot['layout'] == {'classic': 'expanded', 'reconstructed': 'compact'}[old['layout']]
        if old.get('norm'):
            assert plot['norm'] == list(old['norm'])
        for field in ('kind', 'font', 'fmt', 'empty', 'num_x', 'num_ha'):
            if field in old:
                assert plot[field] == old[field]
        assert not {'id', 'customizable', 'corrected', 'text_always', 'under'} & plot.keys()
        assert result['document']['current']['migration_source'] == payload
        assert not {'mode_id', 'compatibility', 'params', 'display'} & result['document']['current'].keys()
    assert source == before


def test_all_states_extensions_excel_groups_and_raw_values_survive():
    source = document()
    source['current'].update(data={'H': '001', 'Fe': '1.00', 'Au': '1e3'},
                             extra={'nested': [1, {'x': True}]}, vendor={'raw': [2]})
    source['styles'] = {'named.with.dots': default_payload('labels_light'),
                        'other': default_payload('classic_blues')}
    source.update(excel_groups=[{'data': {'H': '001'}, 'edits': {'H': {'show_value': False}}}],
                  unknown={'future': [1, 2]})
    before = deepcopy(source)
    result = migrate_document(source)['document']
    assert result['excel_groups'] == source['excel_groups']
    assert result['unknown'] == source['unknown']
    for old, new in [(source['current'], result['current'])] + [
        (value, result['styles'][name]) for name, value in source['styles'].items()]:
        assert new['data'] == old['data']
        assert new['migration_source'] == old
        for key in ('data', 'output_dir', 'output_format', 'extra', 'vendor'):
            if key in old:
                assert new[key] == old[key]
        assert 'mode_id' not in new and 'compatibility' not in new
    result['current']['extra']['nested'].append(9)
    result['excel_groups'][0]['data']['H'] = 'changed'
    assert source == before


@pytest.mark.parametrize('labels', [True, False])
def test_hidden_colorbar_rows_and_global_label_switch(labels):
    payload = default_payload()
    payload['show_cbar_labels'] = labels
    payload['cbar_override'] = dict(ticks=[1, -1, 0], labels=['high', 'low', 'zero'],
                                    visible=[True, False, True], fontsize=11)
    plot = migrate_document(document(payload))['document']['current']['plot']
    assert plot['cbar'] == payload['cbar_override']
    assert plot['show_cbar_labels'] is labels


def test_disabled_labels_do_not_destroy_inherited_labels():
    payload = default_payload('reconstruct_percent')
    payload.update(compatibility=True, show_cbar_labels=False)
    expected = resolve_payload({**payload, 'show_cbar_labels': True})['cbar']
    plot = migrate_document(document(payload))['document']['current']['plot']
    assert plot['cbar']['labels'] == expected['labels']
    assert plot['show_cbar_labels'] is False


def test_compatibility_ignored_candidates_never_activate():
    payload = default_payload('classic_blues')
    payload.update(compatibility=True, element_overrides={'H': {'show_value': False}})
    payload['params'].update(title='ignored', unit='ignored', symbol_fs='24',
                             margins='0.1,0.1,0.9,0.9', cbar_box='0.1,0.1,0.1,0.4',
                             vmin='-100', vcenter='', vmax='100')
    payload['display'].update(show_symbol=False, transparent=True)
    result = migrate_document(document(payload))
    plot = result['document']['current']['plot']
    assert plot['norm'] == ['normalize', 1, 10]
    assert plot['rounding'] == 'python'
    assert plot['title'] == plot['unit'] == ''
    assert plot['symbol_fs'] == 9
    assert plot['show_symbol'] is True and plot['transparent'] is False
    assert plot['element_overrides'] == {}
    assert plot['margins'] is None and plot['cbar_box'] is None
    assert {'compatibility_parameters', 'zero_missing', 'series_labels', 'under_color'} <= {
        row['code'] for row in result['report']['warnings']}


def test_explicit_range_and_outside_ticks_are_not_corrected():
    payload = default_payload()
    payload['params'].update(vmin='-123', vcenter='-12', vmax='7')
    payload['cbar_override'] = dict(ticks=[-200, 0, 20], labels=['a', 'b', 'c'])
    result = migrate_document(document(payload))
    assert result['document']['current']['plot']['norm'] == ['twoslope', -123, -12, 7]
    assert any(row['code'] == 'ticks_outside_range' for row in result['report']['warnings'])


def test_preview_in_saved_state_blocks_whole_document():
    source = document()
    source['styles'] = {'preview': default_payload('cmap_preview')}
    before = deepcopy(source)
    with pytest.raises(MigrationError) as error:
        migrate_document(source)
    assert error.value.report['unsupported_fields'][0]['path'] == 'styles.preview.kind'
    assert source == before


def test_deterministic_idempotent_and_independent_schema2():
    source = document()
    first = migrate_document(source)
    assert migrate_document(source) == first
    second = migrate_document(first['document'])
    assert second['document'] == first['document']
    assert second['report'] == dict(source_schema=2, target_schema=2,
                                    changed_fields=[], warnings=[], unsupported_fields=[])
    second['document']['current']['data']['H'] = 'new'
    assert first['document']['current']['data'] == {}


@pytest.mark.parametrize('break_it', [
    lambda d: d.update(schema=True),
    lambda d: d.update(schema=3),
    lambda d: d.update(styles=[]),
    lambda d: d['current'].update(plot={'unknown': True}),
    lambda d: d['current']['plot'].update(dpi=True),
    lambda d: d['current'].update(data={'H': float('nan')}),
    lambda d: d['styles'].update(bad={'data': {}}),
])
def test_schema2_strict_validation(break_it):
    source = migrate_document(document())['document']
    break_it(source)
    with pytest.raises(MigrationError):
        migrate_document(source)

@pytest.mark.parametrize('schema', [1, 2])
@pytest.mark.parametrize('state', ['current', 'saved'])
@pytest.mark.parametrize('data', [{'XYZ': '1'}, {'Fe': 'abc'}, {'Fe': 'NaN'}, {'Fe': '1e999'}, {'Fe': True}])
def test_invalid_render_data_blocks_both_schemas_and_all_states(schema, state, data):
    source = document()
    if schema == 2:
        source = migrate_document(source)['document']
    if state == 'saved':
        source['styles']['saved'] = deepcopy(source['current'])
        source['styles']['saved']['data'] = data
    else:
        source['current']['data'] = data
    before = deepcopy(source)
    with pytest.raises(MigrationError):
        migrate_document(source)
    assert source == before


@pytest.mark.parametrize('schema', [1, 2])
def test_labels_accept_annotations_and_preserve_lexical_data(schema):
    payload = default_payload('labels_light')
    payload['data'] = {'Fe': 'abc', 'H': '001', 'Au': '1e3', 'Cu': '1.00', 'He': ''}
    source = document(payload)
    if schema == 2:
        source = migrate_document(source)['document']
    before = deepcopy(source)
    result = migrate_document(source)['document']
    assert result['current']['data'] == payload['data']
    assert source == before


@pytest.mark.parametrize('field', ['plot', 'migration_source'])
def test_reserved_legacy_extension_collision_is_reported_and_archived(field):
    source = document()
    original = {'vendor': ['opaque', {'value': 1}]}
    source['current'][field] = deepcopy(original)
    source['styles']['named'] = deepcopy(source['current'])
    result = migrate_document(source)
    for path, payload in [('current', result['document']['current']),
                           ('styles.named', result['document']['styles']['named'])]:
        assert payload['migration_source'][field] == original
        assert any(row['path'] == f'{path}.{field}' and row['code'] == 'reserved_field_collision'
                   for row in result['report']['warnings'])
    assert source['current'][field] == original


@pytest.fixture
def excel_snapshot(tmp_path):
    from application.dataset_collection import DatasetCollection
    from application.excel_import import ExcelImportService
    from test_xlsx_reader import MAIN, fixture_zip

    sheet = f'''<worksheet xmlns="{MAIN}"><sheetData>
        <row r="1"><c r="B1" t="inlineStr"><is><t>H</t></is></c></row>
        <row r="2"><c r="A2"><v>1</v></c><c r="B2"><v>2</v></c></row>
        </sheetData></worksheet>'''
    path = tmp_path / 'synthetic.xlsx'
    path.write_bytes(fixture_zip(**{'sheets/value sheet.xml': sheet}))
    collection = DatasetCollection()
    collection.append(ExcelImportService(path).preview('Values', 'B1:B1', 'A2:A2', 'B2:B2', 'matrix_rows'))
    collection.set_manual_data({'H': '001', 'Fe': '1.00'})
    return collection.snapshot()


@pytest.mark.parametrize('schema', [1, 2])
def test_excel_collection_and_edits_are_preserved_without_normalizing(schema, excel_snapshot):
    source = document()
    source.update(excel_collection=excel_snapshot, excel_attached=True)
    source['current']['data'] = {'H': '001', 'Fe': '1.00'}
    if schema == 2:
        source = migrate_document(source)['document']
    before = deepcopy(source)
    result = migrate_document(source)['document']
    assert result['excel_collection'] == excel_snapshot
    assert result['excel_attached'] is True
    result['excel_collection']['manual_data'].clear()
    assert source == before


@pytest.mark.parametrize('schema', [1, 2])
@pytest.mark.parametrize('damage', ['active', 'manual', 'metric', 'condition', 'mapping', 'source', 'attached_type', 'attached_empty', 'attached_missing'])
def test_invalid_excel_references_block_migration(schema, damage, excel_snapshot):
    from application.dataset_collection import DatasetCollection

    source = document()
    if schema == 2:
        source = migrate_document(source)['document']
    source.update(excel_collection=deepcopy(excel_snapshot), excel_attached=True)
    collection = source['excel_collection']
    if damage == 'active':
        collection['active_dataset_id'] = 'missing'
    elif damage == 'manual':
        collection['manual_data']['missing'] = {'H': '1'}
    elif damage in ('metric', 'condition'):
        collection['datasets'][0][f'{damage}_id'] = 'missing'
    elif damage == 'mapping':
        collection['datasets'][0]['provenance']['mapping_id'] = 'missing'
    elif damage == 'source':
        collection['mappings'][0]['source_id'] = 'missing'
    elif damage == 'attached_type':
        source['excel_attached'] = 'true'
    elif damage == 'attached_empty':
        source['excel_collection'] = DatasetCollection().snapshot()
    else:
        del source['excel_collection']
    before = deepcopy(source)
    with pytest.raises(MigrationError):
        migrate_document(source)
    assert source == before
