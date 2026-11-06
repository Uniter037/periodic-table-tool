"""Allowlist persisted event fields and metadata for diagnostic exports."""

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import platform

from ._privacy import identifier, safe_text

_IDS = ("trace_id", "job_id", "item_id", "request_id", "error_id")
_DETAIL_COUNTS = {"count", "group_count", "row_count", "column_count", "diagnostic_count"}


def _count(value):
    return type(value) is int and 0 <= value < 2**63


def bundle_event(event):
    if not isinstance(event, dict) or event.get("schema_version") != 1:
        return None
    timestamp = event.get("timestamp_utc")
    if not isinstance(timestamp, str) or len(timestamp) > 40:
        return None
    timestamp = datetime.fromisoformat(timestamp)
    if timestamp.utcoffset() is None:
        return None
    clean = {
        "schema_version": 1,
        "timestamp_utc": timestamp.astimezone(timezone.utc).isoformat(),
        "message": safe_text(event.get("message")),
    }
    for key in ("level", "event_code", "session_id", "process_role", "module", *_IDS):
        value = identifier(event.get(key))
        if value is not None:
            clean[key] = value
    for key in ("monotonic_ms", "project_revision"):
        value = event.get(key)
        if _count(value):
            clean[key] = value
    duration = event.get("duration_ms")
    if type(duration) in (int, float) and 0 <= duration < 2**63:
        clean["duration_ms"] = duration
    details = event.get("details")
    if isinstance(details, dict):
        filtered = {key: details[key] for key in _DETAIL_COUNTS if _count(details.get(key))}
        error = details.get("exception")
        if isinstance(error, dict):
            frames = error.get("frames")
            filtered["exception"] = {
                "type": identifier(error.get("type")) or "Exception",
                "frames": [
                    {"file": "<SOURCE>",
                     "function": identifier(frame.get("function")) or "<redacted>",
                     "line": frame["line"]}
                    for frame in (frames[:100] if isinstance(frames, list) else [])
                    if isinstance(frame, dict) and _count(frame.get("line"))
                ],
            }
        if filtered:
            clean["details"] = filtered
    return clean


def _package_version(name):
    try:
        return identifier(version(name))
    except PackageNotFoundError:
        return None


def bundle_metadata(session_id, settings, count):
    return {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "app_version": _package_version("periodic-table-tool"),
        "os": {"system": safe_text(platform.system()), "release": safe_text(platform.release())},
        "python": platform.python_version(),
        "dependencies": {name: _package_version(name)
                         for name in ("matplotlib", "numpy", "Pillow")},
        "settings": settings,
        "event_count": count,
        "files": ["events.jsonl", "metadata.json"],
    }
