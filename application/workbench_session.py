"""Transactional, Tk-free desktop session for schema-2 projects."""
from copy import deepcopy
import math
import os
from pathlib import Path

from core.document import History, user_directory, write_document
from core.presets import PresetStore
from domain.plot_spec import PlotSpec
from .agent_api import ApiError, _decode, _fingerprint, _path, _read, _write_new
from .agent_api_v2 import validate_document, _patch, _save
from .dataset_collection import DatasetCollection
from .plot_service import prepare_plot


class MigrationRequired(ValueError):
    """A legacy file needs explicit user consent before conversion."""

    def __init__(self, report):
        self.report = deepcopy(report)
        super().__init__('Schema 1 requires explicit migration')


class WorkbenchSession:
    def __init__(self, user_dir=None):
        self._user_dir = Path(user_dir).expanduser().resolve() if user_dir is not None else user_directory().resolve()
        self._document, _ = validate_document({
            'schema': 2, 'current': {'plot': PlotSpec().to_dict(), 'data': {}},
            'styles': {}, 'excel_collection': DatasetCollection().snapshot(),
            'excel_attached': False})
        self._history = History(self._document)
        self._saved = deepcopy(self._document)
        self._path = self._revision = self._source_path = None

    @property
    def document(self):
        return deepcopy(self._document)

    @property
    def plot(self):
        return deepcopy(self._document['current']['plot'])

    @property
    def data(self):
        return deepcopy(self._document['current']['data'])

    @property
    def collection(self):
        return DatasetCollection.from_snapshot(self._document['excel_collection'])

    @property
    def path(self):
        return self._path

    @property
    def revision(self):
        return self._revision

    @property
    def source_path(self):
        return self._source_path

    @property
    def user_dir(self):
        return self._user_dir

    @property
    def draft_path(self):
        return self.user_dir / 'drafts-v2' / 'workbench.json'

    @property
    def dirty(self):
        return self._saved is None or self._document != self._saved

    def _commit(self, document):
        candidate, _ = validate_document(document)
        self._history.record(candidate)
        self._document = candidate

    def _working(self):
        document = self.document
        collection = self.collection
        if document['excel_attached']:
            collection.set_manual_data(document['current']['data'])
        return document, collection

    def patch(self, plot=None, data=None, replace_data=False):
        if type(replace_data) is not bool:
            raise ValueError('replace_data must be boolean')
        document, collection = self._working()
        change = {'replace_data': replace_data}
        if plot is not None:
            change['plot'] = plot
        if data is not None or replace_data:
            change['data'] = {} if data is None else data
        _patch(document, change)
        if document['excel_attached'] and 'data' in change:
            collection.set_manual_data(document['current']['data'])
        # A style-only operation must not create a new Excel edit buffer.
        if 'data' in change:
            document['excel_collection'] = collection.snapshot()
        self._commit(document)

    def apply_preset(self, payload, include_data=False):
        if type(include_data) is not bool or not isinstance(payload, dict) or 'plot' not in payload:
            raise ValueError('Expected a preset containing plot and a boolean include_data')
        document = self.document
        document['current']['plot'] = PlotSpec.from_dict(payload['plot']).to_dict()
        if include_data and 'data' in payload:
            _patch(document, {'data': payload['data'], 'replace_data': True})
            if document['excel_attached']:
                collection = self.collection
                collection.set_manual_data(document['current']['data'])
                document['excel_collection'] = collection.snapshot()
        self._commit(document)

    def _step(self, direction):
        index = self._history.index
        target = index + direction
        if not 0 <= target < len(self._history.entries):
            return False
        candidate, _ = validate_document(self._history.entries[target])
        self._document = candidate
        self._history.index = target
        return True

    def undo(self):
        return self._step(-1)

    def redo(self):
        return self._step(1)

    def load(self, path, migrate=False):
        if type(migrate) is not bool:
            raise ValueError('migrate must be boolean')
        path = _path(os.fspath(path), 'path')
        raw = _read(path)
        document = _decode(raw)
        report = None
        legacy = isinstance(document, dict) and type(document.get('schema')) is int and document['schema'] == 1
        if legacy:
            from .project_migrations import migrate_document
            result = migrate_document(document)
            if not migrate:
                raise MigrationRequired(result['report'])
            document, report = result['document'], result['report']
        candidate, collection = validate_document(document)
        candidate.setdefault('excel_collection', collection.snapshot())
        candidate.setdefault('excel_attached', False)
        self._document = candidate
        self._history = History(candidate)
        self._saved = None if legacy else deepcopy(candidate)
        self._path = None if legacy else path
        self._revision = None if legacy else _fingerprint(raw)
        self._source_path = path if legacy else None
        return report

    def save(self, path=None):
        target = self.path if path is None else _path(os.fspath(path), 'path')
        if target is None:
            raise ValueError('Choose a project path before saving')
        document, _ = validate_document(self._document)
        if target == self.source_path:
            raise ApiError('PATH_CONFLICT', 'Migration must not overwrite its source')
        if self.path is not None and target == self.path:
            target, revision = _save({}, self.path, document, self.revision)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            lock = target.with_name(target.name + '.agent-lock')
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise ApiError('PROJECT_BUSY', 'Another API writer holds the project lock') from exc
            try:
                os.close(fd)
                if self.path is None:
                    revision = _write_new(target, document)
                else:
                    target, revision = _save({'output_project': str(target)}, self.path, document, self.revision)
            finally:
                lock.unlink(missing_ok=True)
        self._path, self._revision = target, revision
        self._saved = deepcopy(document)
        return target

    def import_excel(self, preview, index=0):
        if not isinstance(preview, dict) or preview.get('status') != 'ready':
            raise ValueError('Excel preview must be ready')
        if type(index) is not int or not 0 <= index < len(preview.get('datasets', [])):
            raise ValueError('Invalid dataset index')
        document, collection = self._working()
        ids = collection.append(deepcopy(preview))
        collection.select(ids[index])
        document.update(excel_collection=collection.snapshot(), excel_attached=True)
        document['current']['data'] = collection.effective_data()
        self._commit(document)
        return ids

    def select_dataset(self, id):
        document, collection = self._working()
        collection.select(id)
        document.update(excel_collection=collection.snapshot(), excel_attached=True)
        document['current']['data'] = collection.effective_data()
        self._commit(document)

    def batch_items(self, ids=None):
        from .batch_datasets import plan_dataset_batch
        _, collection = self._working()
        snapshot = collection.snapshot()
        indexed = {item['id']: item for item in snapshot['datasets']}
        if isinstance(ids, (str, bytes)):
            raise ValueError('Expected dataset IDs')
        ids = list(indexed if ids is None else ids)
        if (not ids or len(ids) > 100 or any(type(key) is not str for key in ids)
                or len(set(ids)) != len(ids) or any(key not in indexed for key in ids)):
            raise ValueError('Select 1–100 unique known datasets')
        if len({indexed[key]['metric_id'] for key in ids}) != 1:
            raise ValueError('Datasets must share a metric')
        planned = plan_dataset_batch(snapshot, ids)
        return [({'dataset_id': key, 'name': name}, data)
                for key, (name, data) in zip(ids, planned)]

    def auto_range(self):
        plot = self.plot
        if plot['kind'] != 'heatmap':
            raise ValueError('Auto range requires numeric heatmap data')
        _, values, _ = prepare_plot(plot, self.data)
        values = [float(value) for symbol, value in values.items()
                  if plot['element_overrides'].get(symbol, {}).get('include_in_range', True)]
        if not values:
            raise ValueError('No numeric data included in range')
        low, high = min(values), max(values)
        if low == high:
            delta = max(abs(low) * .05, 1e-6)
            a, b = low - delta, high + delta
            low = a if math.isfinite(a) else low
            high = b if math.isfinite(b) else high
        if plot['norm'][0] == 'twoslope':
            center = plot['norm'][2]
            # Keep the configured center when interior; otherwise use a midpoint.
            if not low < center < high:
                center = low / 2 + high / 2
            if not low < center < high:
                # Adjacent floats have no interior value: expand finite endpoints.
                a, b = math.nextafter(low, -math.inf), math.nextafter(high, math.inf)
                if math.isfinite(a):
                    low = a
                if math.isfinite(b):
                    high = b
                center = low / 2 + high / 2
            norm = ['twoslope', low, center, high]
        else:
            norm = ['normalize', low, high]
        self.patch(plot={'norm': norm})
        return self.plot['norm']

    def _presets(self):
        return PresetStore(str(self.user_dir / 'presets-v2'))

    def save_preset(self, name, include_data=False):
        if type(include_data) is not bool:
            raise ValueError('include_data must be boolean')
        payload = {'plot': self.plot}
        if include_data:
            payload['data'] = self.data
        return Path(self._presets().save(name, payload))

    def load_preset(self, name, include_data=False):
        self.apply_preset(self._presets().load(name), include_data)

    def list_presets(self):
        return self._presets().list()

    def delete_preset(self, name):
        self._presets().delete(name)

    def save_draft(self):
        document, _ = validate_document(self._document)
        write_document(self.draft_path, document)
        return self.draft_path

    def recover_draft(self):
        if not self.draft_path.exists():
            return False
        candidate, collection = validate_document(_decode(_read(self.draft_path)))
        candidate.setdefault('excel_collection', collection.snapshot())
        candidate.setdefault('excel_attached', False)
        self._document = candidate
        self._history = History(candidate)
        self._saved = None
        self._path = self._revision = self._source_path = None
        return True

    def clear_draft(self):
        self.draft_path.unlink(missing_ok=True)
