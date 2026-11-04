"""JSON-only document snapshots, bounded history and atomic persistence.

Contract: schema=1, current=preset payload, styles={style_id: payload}.
No Tk objects or Figures may enter a snapshot. Output files are not undoable.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile


def user_directory():
    return Path(os.environ.get("PTT_USER_DIR") or
                (Path.home() / ".periodic-table-tool"))


def write_document(path, snapshot):
    path = Path(path)
    encoded = json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_document(path):
    with open(path, encoding="utf-8") as stream:
        result = json.load(stream)
    if not isinstance(result, dict) or result.get("schema") != 1:
        raise ValueError("不支持的项目格式或版本")
    if not isinstance(result.get("styles"), dict):
        raise ValueError("项目样式列表无效")
    for payload in [result.get("current"), *result["styles"].values()]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data", {}), dict):
            raise ValueError("项目数据无效")
        for key in ("params", "display"):
            if not isinstance(payload.get(key, {}), dict):
                raise ValueError("项目参数无效")
    # Also reject NaN/Infinity accepted by Python's JSON decoder.
    json.dumps(result, allow_nan=False)
    return result


class History:
    def __init__(self, initial, limit=100):
        self.limit = limit
        self.entries = [copy.deepcopy(initial)]
        self.index = 0

    def record(self, snapshot):
        if snapshot == self.entries[self.index]:
            return False
        del self.entries[self.index + 1:]
        self.entries.append(copy.deepcopy(snapshot))
        if len(self.entries) > self.limit:
            self.entries.pop(0)
        self.index = len(self.entries) - 1
        return True

    def step(self, direction):
        self.index = max(0, min(len(self.entries) - 1, self.index + direction))
        return copy.deepcopy(self.entries[self.index])
