"""Independent PlotSpec API; v1 projects cross only the explicit migrate boundary."""
from copy import deepcopy
import json
import os

from .agent_api import (ApiError, _path, _read, _decode, _fingerprint, _write_new,
                        _expect, _revision_conflict, _excel_preview)
from .plot_service import prepare_plot, export_plots
from domain.plot_spec import PlotSpec, PlotSpecError

ACTIONS = {
    'describe': set(),
    'render': {'plot', 'data', 'output_dir', 'formats', 'base', 'allow_out_of_range'},
    'create': {'project', 'plot', 'data', 'preset'},
    'inspect': {'project'},
    'validate': {'project', 'patch', 'expected_revision', 'dataset_id'},
    'update': {'project', 'output_project', 'patch', 'expected_revision', 'dataset_id'},
    'export': {'project', 'expected_revision', 'output_dir', 'formats', 'base', 'allow_out_of_range'},
    'batch_export': {'project', 'expected_revision', 'dataset_ids', 'output_dir', 'formats', 'base', 'allow_out_of_range'},
    'migrate': {'project', 'output_project', 'expected_revision', 'dry_run'},
    'excel_preview': {'workbook', 'sheet', 'elements_range', 'conditions_range', 'values_range', 'direction'},
    'import_excel': {'project', 'output_project', 'expected_revision', 'workbook', 'sheet',
                     'elements_range', 'conditions_range', 'values_range', 'direction', 'dataset_index'},
}


def validate_document(document):
    from .dataset_collection import DatasetCollection
    if (not isinstance(document, dict) or type(document.get('schema')) is not int or
            document['schema'] != 2 or not isinstance(document.get('styles'), dict)):
        raise ApiError('MIGRATION_REQUIRED', 'Expected schema=2; use migrate for a schema=1 project')
    result = deepcopy(document)
    for payload in [result.get('current'), *result['styles'].values()]:
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict) or 'plot' not in payload:
            raise ApiError('INVALID_PROJECT', 'Each state requires plot and data')
        spec, _, _ = prepare_plot(payload['plot'], payload['data'])
        payload['plot'] = spec.to_dict()
    collection = DatasetCollection.from_snapshot(result['excel_collection']) if 'excel_collection' in result else DatasetCollection()
    attached = result.get('excel_attached', False)
    if type(attached) is not bool or (attached and collection.active_dataset_id is None):
        raise ApiError('INVALID_PROJECT', 'Invalid Excel association')
    json.dumps(result, allow_nan=False)
    return result, collection


def _summary(path, document, revision):
    spec, _, warnings = prepare_plot(document['current']['plot'], document['current']['data'])
    return {'project': str(path), 'revision': revision, 'document': document,
            'resolved_plot': spec.to_dict(), 'warnings': warnings}


def _patch(document, patch):
    if not isinstance(patch, dict) or set(patch) - {'plot', 'data', 'replace_data'}:
        raise ApiError('INVALID_PATCH', 'Supported patch fields: plot, data, replace_data')
    if 'replace_data' in patch and type(patch['replace_data']) is not bool:
        raise ApiError('INVALID_PATCH', 'replace_data must be boolean')
    current = document['current']
    if 'plot' in patch:
        if not isinstance(patch['plot'], dict):
            raise ApiError('INVALID_PATCH', 'plot must be an object')
        # Flat spec: nested configurations such as cbar are replaced atomically.
        current['plot'] = PlotSpec.from_dict({**current['plot'], **patch['plot']}).to_dict()
    if 'data' in patch:
        if not isinstance(patch['data'], dict):
            raise ApiError('INVALID_PATCH', 'data must be an object')
        values = {} if patch.get('replace_data', False) else deepcopy(current['data'])
        for symbol, value in patch['data'].items():
            if value is None:
                values.pop(symbol, None)
            else:
                values[symbol] = value
        current['data'] = values
    prepare_plot(current['plot'], current['data'])


def _save(request, path, document, revision):
    from core.document import write_document
    document, _ = validate_document(document)
    target = _path(request.get('output_project', str(path)), 'output_project')
    lock = path.with_name(path.name + '.agent-lock')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ApiError('PROJECT_BUSY', 'Another API writer holds the project lock') from exc
    try:
        os.close(fd)
        actual = _fingerprint(_read(path))
        if actual != revision:
            _revision_conflict(revision, actual, 'Project changed before writing')
        if target != path:
            return target, _write_new(target, document)
        write_document(path, document)
        return path, _fingerprint(_read(path))
    finally:
        lock.unlink(missing_ok=True)


def _exports(request, current, items):
    return export_plots(current['plot'], items, request.get('output_dir', 'output'),
                        request.get('formats', ['svg']), request.get('base', 'periodic_table'),
                        request.get('allow_out_of_range', False))


def _execute(request):
    from .dataset_collection import DatasetCollection
    from .plot_presets import preset, describe_presets
    if not isinstance(request, dict) or type(request.get('api_version')) is not int or request['api_version'] != 2:
        raise ApiError('API_VERSION', 'Expected api_version=2')
    action = request.get('action')
    if not isinstance(action, str) or action not in ACTIONS:
        raise ApiError('UNKNOWN_ACTION', 'Call describe for supported actions')
    if set(request) - ACTIONS[action] - {'action', 'api_version', 'request_id'}:
        raise ApiError('INVALID_REQUEST', 'Unknown request fields')
    if 'request_id' in request and type(request['request_id']) not in (str, int):
        raise ApiError('INVALID_REQUEST', 'request_id must be a string or integer')
    if action == 'describe':
        return {'schema': 2, 'engine': 'independent', 'defaults': PlotSpec.from_dict({}).to_dict(),
                'actions': {key: sorted(value) for key, value in ACTIONS.items()},
                'presets': describe_presets(), 'patch_fields': ['plot', 'data', 'replace_data'],
                'migration': 'Explicit schema=1 conversion; source never overwritten',
                'concurrency': 'Use inspect.revision as expected_revision; GUI is not live synchronized',
                'patch_semantics': 'plot fields merge; nested values replace; data null removes; replace_data clears first'}
    if action == 'excel_preview':
        return _excel_preview(request)
    if action == 'render':
        current = {'plot': request.get('plot', {}), 'data': request.get('data', {})}
        return _exports(request, current, [({}, current['data'])])[0]
    if action == 'create':
        path = _path(request.get('project'), 'project')
        options = request.get('plot', {})
        if not isinstance(options, dict):
            raise ApiError('INVALID_REQUEST', 'plot must be an object')
        current = {'plot': PlotSpec.from_dict({**preset(request.get('preset', 'diverging')), **options}).to_dict(),
                   'data': deepcopy(request.get('data', {}))}
        document, _ = validate_document({'schema': 2, 'current': current, 'styles': {},
                            'excel_collection': DatasetCollection().snapshot(), 'excel_attached': False})
        return _summary(path, document, _write_new(path, document))
    path = _path(request.get('project'), 'project')
    raw = _read(path)
    document, revision = _decode(raw), _fingerprint(raw)
    if action == 'migrate':
        from .project_migrations import migrate_document
        _expect(request, revision, required=False)
        dry = request.get('dry_run', True)
        if type(dry) is not bool:
            raise ApiError('INVALID_REQUEST', 'dry_run must be boolean')
        result = migrate_document(document)
        if dry:
            return {**result, 'dry_run': True, 'source_revision': revision}
        _expect(request, revision)
        converted, _ = validate_document(result['document'])
        target = _path(request.get('output_project', str(path.with_name(path.stem + '-migrated.ptproj'))), 'output_project')
        if target == path:
            raise ApiError('PATH_CONFLICT', 'Migration must not overwrite the source')
        actual = _fingerprint(_read(path))
        if actual != revision:
            _revision_conflict(revision, actual, 'Source changed during migration')
        new_revision = _write_new(target, converted)
        return {**_summary(target, converted, new_revision), 'report': result['report'], 'source_revision': revision}
    document, collection = validate_document(document)
    if action == 'inspect':
        return _summary(path, document, revision)
    _expect(request, revision, required=action in ('update', 'import_excel'))
    if action in ('update', 'validate', 'import_excel'):
        if document.get('excel_attached'):
            collection.set_manual_data(document['current']['data'])
        details = {}
        if action == 'import_excel':
            preview = _excel_preview(request)
            if preview['status'] != 'ready':
                raise ApiError('EXCEL_INVALID', 'Excel selection is not ready', preview)
            index = request.get('dataset_index', 0)
            if type(index) is not int or not 0 <= index < len(preview['datasets']):
                raise ApiError('INVALID_REQUEST', 'Invalid dataset_index')
            ids = collection.append(preview)
            collection.select(ids[index])
            document['excel_attached'] = True
            document['current']['data'] = collection.effective_data()
            details = {'dataset_ids': ids, 'import_stats': preview['stats']}
        elif 'dataset_id' in request:
            collection.select(request['dataset_id'])
            document['excel_attached'] = True
            document['current']['data'] = collection.effective_data()
        _patch(document, request.get('patch', {}))
        if document.get('excel_attached'):
            collection.set_manual_data(document['current']['data'])
        document['excel_collection'] = collection.snapshot()
        document, _ = validate_document(document)
        if action == 'validate':
            result = _summary(path, document, revision)
            result['base_revision'] = result.pop('revision')
            return {**result, 'dry_run': True}
        target, new_revision = _save(request, path, document, revision)
        return {**_summary(target, document, new_revision), **details}
    if action == 'export':
        result = _exports(request, document['current'], [({}, document['current']['data'])])[0]
        return {'project': str(path), 'revision': revision, **result}
    if action == 'batch_export':
        from .batch_datasets import plan_dataset_batch
        if document.get('excel_attached'):
            collection.set_manual_data(document['current']['data'])
        snapshot = collection.snapshot()
        ids = request.get('dataset_ids', [item['id'] for item in snapshot['datasets']])
        if (not isinstance(ids, list) or not ids or len(ids) > 100 or
                any(not isinstance(k, str) for k in ids) or len(set(ids)) != len(ids)):
            raise ApiError('INVALID_REQUEST', 'Select 1–100 unique dataset IDs')
        indexed = {item['id']: item for item in snapshot['datasets']}
        if any(key not in indexed for key in ids) or len({indexed[k]['metric_id'] for k in ids}) != 1:
            raise ApiError('INVALID_REQUEST', 'Select known datasets with the same metric')
        planned = plan_dataset_batch(snapshot, ids)
        items = [({'dataset_id': key, 'name': name}, data)
                 for key, (name, data) in zip(ids, planned)]
        results = _exports(request, document['current'], items)
        return {'project': str(path), 'revision': revision, 'dataset_ids': ids, 'datasets': results,
                'files': [f for result in results for f in result['files']],
                'warnings': [w for result in results for w in result['warnings']]}


def execute(request):
    response = {'api_version': 2}
    if isinstance(request, dict) and type(request.get('request_id')) in (str, int):
        response['request_id'] = request['request_id']
    try:
        json.dumps(request, allow_nan=False)
        response.update(ok=True, result=_execute(deepcopy(request)))
    except ApiError as exc:
        response.update(ok=False, error={'code': exc.code, 'message': str(exc)})
        if exc.details is not None:
            response['error']['details'] = exc.details
    except PlotSpecError as exc:
        response.update(ok=False, error={'code': 'VALIDATION_ERROR', 'message': str(exc), 'path': exc.path})
    except (ValueError, TypeError, KeyError) as exc:
        if hasattr(exc, 'report'):
            response.update(ok=False, error={'code': 'MIGRATION_BLOCKED', 'message': str(exc),
                                            'details': exc.report})
        else:
            response.update(ok=False, error={'code': 'VALIDATION_ERROR', 'message': str(exc)})
    except OSError as exc:
        response.update(ok=False, error={'code': 'IO_ERROR', 'message': str(exc)})
    except Exception as exc:
        response.update(ok=False, error={'code': 'INTERNAL_ERROR', 'message': str(exc)})
    return response
