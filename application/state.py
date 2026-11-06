"""Transactional JSON state with detached snapshots and bounded undo history.

The controller owns this store on one thread. Validators and operations run on
copies; a rejected transaction cannot alter the active document or history.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Optional


def _encode(snapshot: dict) -> bytes:
    if not isinstance(snapshot, dict):
        raise ValueError("项目状态必须是对象")
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class Change:
    revision: int
    command: str
    dirty: bool


class ProjectStore:
    def __init__(self, initial: dict, validator: Optional[Callable] = None,
                 history_limit: int = 100, history_bytes: int = 64 * 1024 * 1024):
        if history_limit < 1 or history_bytes < 1:
            raise ValueError("历史记录限制必须为正数")
        self._validator = validator
        encoded = self._prepare(initial)
        self._entries = [encoded]
        self._index = 0
        self._saved_hash = self._hash(encoded)
        self._revision = 0
        self._limit = history_limit
        self._budget = history_bytes
        self._listeners = []
        self.observer_errors = []
        self._notifying = False
        self._merge_key = None

    def _prepare(self, snapshot):
        encoded = _encode(snapshot)
        detached = json.loads(encoded)
        if self._validator:
            self._validator(detached)
        # Validation has no authority to silently transform the document.
        return encoded

    @staticmethod
    def _hash(encoded):
        return hashlib.sha256(encoded).hexdigest()

    @property
    def revision(self):
        return self._revision

    @property
    def dirty(self):
        return self._hash(self._entries[self._index]) != self._saved_hash

    @property
    def can_undo(self):
        return self._index > 0

    @property
    def can_redo(self):
        return self._index + 1 < len(self._entries)

    def snapshot(self):
        return json.loads(self._entries[self._index])

    def subscribe(self, callback):
        self._listeners.append(callback)
        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)
        return unsubscribe

    def _check(self, expected_revision):
        if self._notifying:
            raise RuntimeError("状态通知期间不能执行新事务")
        if expected_revision is not None and expected_revision != self.revision:
            raise ValueError("项目已改变，请重新预览后提交")

    def _notify(self, command):
        change = Change(self.revision, command, self.dirty)
        self._notifying = True
        try:
            for callback in tuple(self._listeners):
                try:
                    callback(change)
                except Exception as exc:
                    # A failed observer cannot turn an already committed command
                    # into an apparent failed transaction. Bound retained errors.
                    self.observer_errors.append(type(exc).__name__)
                    self.observer_errors[:] = self.observer_errors[-20:]
        finally:
            self._notifying = False
        return change

    def transact(self, command, operation, *, expected_revision=None, merge_key=None):
        self._check(expected_revision)
        candidate = self.snapshot()
        operation(candidate)
        encoded = self._prepare(candidate)
        if encoded == self._entries[self._index]:
            return None
        had_redo = self.can_redo
        del self._entries[self._index + 1:]
        if merge_key is not None and merge_key == self._merge_key and self.can_undo and not had_redo:
            self._entries[self._index] = encoded
        else:
            self._entries.append(encoded)
            self._index += 1
        while len(self._entries) > 1 and (len(self._entries) > self._limit + 1
                                        or sum(map(len, self._entries)) > self._budget):
            self._entries.pop(0)
            self._index -= 1
        self._merge_key = merge_key
        self._revision += 1
        return self._notify(command)

    def end_edit(self):
        self._merge_key = None

    def undo(self):
        self._check(None)
        self.end_edit()
        if not self.can_undo:
            return None
        self._index -= 1
        self._revision += 1
        return self._notify("undo")

    def redo(self):
        self._check(None)
        self.end_edit()
        if not self.can_redo:
            return None
        self._index += 1
        self._revision += 1
        return self._notify("redo")

    def mark_saved(self, snapshot=None):
        """Mark exactly what was written, even if a later edit already exists."""
        self._check(None)
        encoded = self._entries[self._index] if snapshot is None else self._prepare(snapshot)
        self._saved_hash = self._hash(encoded)
        self.end_edit()
        return self._notify("saved")

    def replace(self, snapshot, *, saved=True, expected_revision=None):
        self._check(expected_revision)
        encoded = self._prepare(copy.deepcopy(snapshot))
        self._entries, self._index = [encoded], 0
        self._saved_hash = self._hash(encoded) if saved else None
        self.end_edit()
        self._revision += 1
        return self._notify("replace")
