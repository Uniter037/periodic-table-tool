import pytest

from application.state import ProjectStore


def edit(value):
    return lambda state: state["data"].update(Fe=value)


def test_failed_transaction_and_replacement_leave_document_history_unchanged():
    def validate(state):
        if state["data"]["Fe"] < 0:
            raise ValueError("invalid")
    store = ProjectStore({"data": {"Fe": 0}}, validate)
    store.transact("edit", edit(1))
    before = store.snapshot()
    with pytest.raises(ValueError):
        store.transact("edit", edit(-1))
    with pytest.raises(ValueError):
        store.replace({"data": {"Fe": -2}})
    assert store.snapshot() == before and store.revision == 1
    store.undo()
    assert store.snapshot()["data"]["Fe"] == 0 and not store.dirty


def test_rejected_stale_preview_does_not_call_operation():
    store = ProjectStore({"data": {"Fe": 0}})
    store.transact("edit", edit(1))
    with pytest.raises(ValueError, match="重新预览"):
        store.transact("import", lambda state: pytest.fail("stale executed"), expected_revision=0)
    assert store.revision == 1


def test_snapshots_detached_and_no_nonfinite_values():
    original = {"data": {"Fe": 0}}
    store = ProjectStore(original)
    original["data"]["Fe"] = 99
    store.snapshot()["data"]["Fe"] = 88
    assert store.snapshot()["data"]["Fe"] == 0
    with pytest.raises(ValueError):
        store.transact("bad", edit(float("nan")))
    assert store.revision == 0


def test_coalescing_and_saved_boundary_and_redo_branch():
    store = ProjectStore({"data": {"Fe": 0}})
    store.transact("type", edit(1), merge_key="Fe")
    store.transact("type", edit(12), merge_key="Fe")
    store.mark_saved()
    store.transact("type", edit(123), merge_key="Fe")
    store.undo()
    assert not store.dirty and store.snapshot()["data"]["Fe"] == 12
    store.undo()
    assert store.snapshot()["data"]["Fe"] == 0
    store.redo()
    store.transact("new branch", edit(9), merge_key="Fe")
    assert not store.can_redo
    store.undo()
    assert store.snapshot()["data"]["Fe"] == 12


def test_async_save_marks_written_snapshot_not_current():
    store = ProjectStore({"data": {"Fe": 0}})
    store.transact("edit", edit(1))
    written = store.snapshot()
    store.transact("edit", edit(2))
    store.mark_saved(written)
    assert store.dirty
    store.undo()
    assert not store.dirty


def test_observer_failure_and_reentrancy_do_not_corrupt_commit():
    store = ProjectStore({"data": {"Fe": 0}})
    received = []
    store.subscribe(lambda event: store.transact("recursive", edit(77)))
    store.subscribe(received.append)
    store.transact("edit", edit(1))
    assert store.snapshot()["data"]["Fe"] == 1
    assert len(received) == 1 and store.observer_errors == ["RuntimeError"]


def test_history_budget_retains_current_and_replacement_resets_history():
    store = ProjectStore({"data": {"Fe": 0}}, history_limit=2)
    for value in range(1, 5):
        store.transact("edit", edit(value))
    store.undo(); store.undo()
    assert not store.can_undo and store.snapshot()["data"]["Fe"] == 2
    store.replace({"data": {"Fe": 10}})
    assert not store.can_undo and not store.can_redo and not store.dirty
    small = ProjectStore({"data": {"Fe": 0}}, history_bytes=1)
    small.transact("edit", edit(1))
    assert small.snapshot()["data"]["Fe"] == 1 and not small.can_undo
