"""Desktop v2 session contract and transactional failure coverage."""
from copy import deepcopy
import json
import math
import subprocess
import sys

import pytest

from application.agent_api import ApiError
from application.workbench_session import MigrationRequired, WorkbenchSession
from test_dataset_collection import service, _preview


@pytest.fixture
def session(tmp_path):
    return WorkbenchSession(tmp_path / 'user')


def test_snapshots_history_and_failed_patch(session):
    assert not session.dirty and session.path is None and session.revision is None
    original = session.document
    snapshot = session.document
    snapshot['current']['data']['Fe'] = 2
    assert session.document == original
    session.patch(data={'Fe': '001', 'Ni': 2})
    session.patch(data={'Ni': None})
    session.patch(plot={'title': 'Changed'})
    before = session.document
    with pytest.raises(ValueError):
        session.patch(plot={'dpi': True}, data={'Fe': 9})
    assert session.document == before
    assert session.undo() and session.plot['title'] == ''
    assert session.undo() and session.data == {'Fe': '001', 'Ni': 2}
    assert session.redo() and session.data == {'Fe': '001'}
    session.patch(replace_data=True)
    assert session.data == {} and not session.redo()
    with pytest.raises(ValueError):
        session.patch(replace_data=1)


def test_save_revision_foreign_target_and_api_lock(session, tmp_path):
    path = tmp_path / 'project.ptproj'
    session.patch(data={'Fe': 0})
    assert session.save(path) == path
    assert not session.dirty and session.revision
    session.patch(plot={'title': 'new'})
    lock = path.with_name(path.name + '.agent-lock')
    lock.touch()
    before = (session.document, session.path, session.revision)
    with pytest.raises(ApiError, match='lock'):
        session.save()
    assert before == (session.document, session.path, session.revision)
    lock.unlink()
    session.save()
    assert not session.dirty
    session.undo()
    assert session.dirty
    session.redo()
    assert not session.dirty
    foreign = tmp_path / 'foreign.ptproj'
    foreign.write_text('keep')
    with pytest.raises(ApiError) as error:
        session.save(foreign)
    assert error.value.code == 'OUTPUT_EXISTS' and foreign.read_text() == 'keep'
    path.write_text(path.read_text() + '\n')
    with pytest.raises(ApiError) as error:
        session.save()
    assert error.value.code == 'REVISION_CONFLICT'
    assert session.path == path


def test_new_save_never_overwrites_and_honors_lock(session, tmp_path):
    target = tmp_path / 'new.ptproj'
    lock = target.with_name(target.name + '.agent-lock')
    lock.touch()
    with pytest.raises(ApiError) as error:
        session.save(target)
    assert error.value.code == 'PROJECT_BUSY'
    lock.unlink()
    target.write_text('foreign')
    with pytest.raises(ApiError):
        session.save(target)
    assert session.path is None and target.read_text() == 'foreign'


def test_excel_edits_preset_selection_history_and_batch(session, service):
    ids = session.import_excel(_preview(service))
    session.patch(data={'H': '001', 'Li': 7})
    before_style = session.collection.snapshot()
    session.patch(plot={'title': 'Style'})
    assert session.collection.snapshot() == before_style
    session.apply_preset({'plot': {'dpi': 72}})
    assert session.data == {'H': '001', 'Li': 7}
    assert session.collection.active_dataset_id == ids[0]
    session.select_dataset(ids[1])
    session.patch(data={'He': None})
    assert session.data == {'H': 2}
    assert session.undo() and session.data == {'H': 2, 'He': 3}
    assert session.redo() and session.data == {'H': 2}
    items = session.batch_items(ids[::-1])
    assert [m['dataset_id'] for m, _ in items] == ids[::-1]
    assert [data for _, data in items] == [{'H': 2}, {'H': '001', 'Li': 7}]
    detached = session.collection
    detached.set_manual_data({'H': 9})
    assert session.data == {'H': 2}
    before = session.document
    with pytest.raises(ValueError):
        session.import_excel(_preview(service), True)
    with pytest.raises(ValueError):
        session.select_dataset('missing')
    with pytest.raises(ValueError):
        session.batch_items([ids[0], ids[0]])
    assert session.document == before
    session.select_dataset(ids[0])
    assert session.data == {'H': '001', 'Li': 7}


def test_presets_draft_and_recovery(session, tmp_path):
    assert session.user_dir == tmp_path / 'user'
    assert not session.recover_draft()
    session.patch(data={'Fe': 1}, plot={'title': 'Saved'})
    session.save_preset('中文')
    assert session.list_presets() == ['中文']
    assert session.save_preset('with-data', True).parent.name == 'presets-v2'
    with pytest.raises(ValueError):
        session.save_preset('../escape')
    session.patch(data={'Fe': 2})
    session.load_preset('中文')
    assert session.data == {'Fe': 2}
    session.load_preset('with-data', True)
    assert session.data == {'Fe': 1}
    source = session.save(tmp_path / 'source.ptproj')
    original = source.read_bytes()
    session.patch(data={'Ni': 3})
    session.save_draft()
    other = WorkbenchSession(session.user_dir)
    assert other.recover_draft() is True
    assert other.document == session.document
    assert other.path is None and other.revision is None and other.dirty
    assert source.read_bytes() == original
    other.clear_draft()
    assert other.recover_draft() is False
    session.delete_preset('中文')
    assert session.list_presets() == ['with-data']


def test_invalid_load_draft_and_preset_are_atomic(session, tmp_path):
    session.patch(data={'Fe': 0})
    before = session.document
    bad = tmp_path / 'bad.ptproj'
    bad.write_text('{"schema":2,"current":{}}')
    with pytest.raises(ValueError):
        session.load(bad)
    session.draft_path.parent.mkdir(parents=True)
    session.draft_path.write_text(bad.read_text())
    with pytest.raises(ValueError):
        session.recover_draft()
    with pytest.raises(ValueError):
        session.apply_preset({'plot': {'dpi': 1}, 'data': {'Fe': 9}}, True)
    assert session.document == before and session.undo() and session.data == {}


@pytest.mark.parametrize('kind', ['normalize', 'twoslope'])
@pytest.mark.parametrize('values', [(0, 0), (5, 5), (1e308, 1e308),
    (sys.float_info.max, sys.float_info.max), (-sys.float_info.max, -sys.float_info.max),
    (-sys.float_info.max, sys.float_info.max), (1, math.nextafter(1, math.inf)), (0, 5e-324)])
def test_auto_range_finite_constants_extremes(session, kind, values):
    norm = ['normalize', -1, 1] if kind == 'normalize' else ['twoslope', -1, 0, 1]
    session.patch(plot={'norm': norm}, data={'Fe': values[0], 'Ni': values[1]})
    result = session.auto_range()
    assert result[0] == kind
    assert all(math.isfinite(v) for v in result[1:])
    assert all(a < b for a, b in zip(result[1:], result[2:]))
    assert result[1] <= min(values) <= max(values) <= result[-1]


def test_auto_range_filter_and_invalid_kind(session):
    session.patch(data={'Fe': 0, 'Ni': 100}, plot={'norm': ['normalize', -1, 1],
        'element_overrides': {'Ni': {'include_in_range': False}}})
    assert session.auto_range()[-1] < 100
    session.patch(plot={'kind': 'labels'}, data={'Fe': 'text'}, replace_data=True)
    before = session.document
    with pytest.raises(ValueError):
        session.auto_range()
    assert session.document == before
    session.patch(plot={'kind': 'heatmap'}, data={}, replace_data=True)
    with pytest.raises(ValueError):
        session.auto_range()


def test_migration_requires_explicit_boundary(session, tmp_path):
    from application.project_codec import default_payload
    source = tmp_path / 'legacy.ptproj'
    source.write_text(json.dumps({'schema': 1, 'current': default_payload(), 'styles': {}}))
    original = source.read_bytes()
    before = session.document
    with pytest.raises(MigrationRequired) as error:
        session.load(source)
    assert error.value.report['source_schema'] == 1 and session.document == before
    report = session.load(source, migrate=True)
    assert report['target_schema'] == 2 and session.source_path == source
    assert session.path is None and session.revision is None and session.dirty
    with pytest.raises(ApiError):
        session.save(source)
    assert source.read_bytes() == original
    saved = session.save(tmp_path / 'converted.ptproj')
    session.load(saved)
    assert session.source_path is None and not session.dirty


def test_native_session_has_no_legacy_or_tk_imports(tmp_path):
    code = '''
import sys
from application.workbench_session import WorkbenchSession, MigrationRequired
s = WorkbenchSession(sys.argv[1])
s.patch(data={'Fe': 0})
s.auto_range()
s.save_preset('test')
s.save_draft()
s.recover_draft()
assert not {'tkinter','core.styles','core.options','core.scientific','application.project_codec'} & set(sys.modules)
'''
    subprocess.run([sys.executable, '-c', code, str(tmp_path)], check=True, timeout=60)


def test_save_as_target_lock_and_write_failure_are_atomic(session, tmp_path, monkeypatch):
    import application.agent_api_v2 as api
    import core.document as persistence
    source = session.save(tmp_path / 'source.ptproj')
    session.patch(data={'Fe': 1})
    before = (session.document, session.path, session.revision, session.dirty)
    target = tmp_path / 'another.ptproj'
    lock = target.with_name(target.name + '.agent-lock')
    lock.touch()
    with pytest.raises(ApiError) as error:
        session.save(target)
    assert error.value.code == 'PROJECT_BUSY'
    lock.unlink()
    original = source.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('disk failed')
    monkeypatch.setattr(persistence, 'write_document', fail)
    with pytest.raises(OSError, match='disk failed'):
        session.save()
    assert source.read_bytes() == original
    assert before == (session.document, session.path, session.revision, session.dirty)
    assert not source.with_name(source.name + '.agent-lock').exists()
    monkeypatch.setattr(api, '_write_new', fail)
    with pytest.raises(OSError):
        session.save(target)
    assert not lock.exists() and not target.exists()
    assert before == (session.document, session.path, session.revision, session.dirty)


def test_excel_project_and_draft_round_trip(session, service, tmp_path):
    ids = session.import_excel(_preview(service), 1)
    session.patch(data={'H': None, 'Li': 4})
    saved = session.save(tmp_path / 'excel.ptproj')
    other = WorkbenchSession(tmp_path / 'other')
    assert other.load(saved) is None
    assert other.document == session.document and not other.dirty
    other.select_dataset(ids[0])
    assert other.data == {'H': 0}
    other.select_dataset(ids[1])
    assert other.data == {'He': 3, 'Li': 4}
    other.save_draft()
    assert other.recover_draft() and other.collection.active_dataset_id == ids[1]
    assert other.data == {'He': 3, 'Li': 4}
