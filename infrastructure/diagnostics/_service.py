"""Synchronous, single-instance JSONL diagnostics."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import re
from threading import RLock, Timer, TIMEOUT_MAX
import time
from tempfile import NamedTemporaryFile
from typing import Optional
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from ._bundle import _DETAIL_COUNTS, _IDS, bundle_event, bundle_metadata
from ._privacy import exception_details, identifier, safe_text

_LEVELS = {name: getattr(logging, name) for name in
           ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")}
_FILENAME = re.compile(r"events-[0-9]{12}\.jsonl")
_MAX_EVENT_BYTES = 32 * 1024


@dataclass(frozen=True)
class DiagnosticSettings:
    enabled: bool = True
    level: str = "INFO"
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 20 * 1024 * 1024
    retention_days: int = 7

    def __post_init__(self):
        if self.level not in _LEVELS:
            raise ValueError("Invalid diagnostic level")
        if not 0 < self.max_file_bytes <= self.max_total_bytes or self.retention_days <= 0:
            raise ValueError("Invalid diagnostic retention limits")


@dataclass(frozen=True)
class LogPage:
    entries: tuple
    next_cursor: Optional[tuple] = None


@dataclass(frozen=True)
class ClearResult:
    removed: int
    failed: tuple = ()


class DiagnosticService:
    """Own one session directory. Use static messages and opaque correlation IDs.

    Writes are synchronous. A disk failure disables writes for this instance;
    write_failed exposes that state without logging the underlying exception.
    """

    def __init__(self, directory=None, settings=None, *, process_role="main"):
        if directory is None:
            from core.document import user_directory
            directory = user_directory() / "logs"
        self.session_id = uuid4().hex
        self.directory = Path(directory).resolve() / self.session_id
        self._role = identifier(process_role) or "unknown"
        self._settings = settings if settings is not None else DiagnosticSettings()
        self._lock = RLock()
        self._closed = False
        self._write_failed = False
        self._stream = None
        self._sequence = 0
        self._size = 0
        self._started = time.monotonic()
        self._session_timer = None
        self._session_token = None
        self._session_deadline = None

    @property
    def write_failed(self):
        return self._write_failed

    def configure(self, settings):
        """Apply in-memory settings immediately."""
        with self._lock:
            self.stop_session()
            self._settings = settings
            if not settings.enabled:
                self._finish_file()

    def start_session(self, duration_minutes=30):
        """Temporarily enable DEBUG; starting again resets the deadline."""
        if type(duration_minutes) not in (int, float) or not 0 < duration_minutes < TIMEOUT_MAX / 60:
            raise ValueError("Invalid diagnostic session duration")
        seconds = duration_minutes * 60
        with self._lock:
            if self._closed:
                raise RuntimeError("Diagnostic service is closed")
            token = object()

            def expire():
                with self._lock:
                    if self._session_token is token:
                        self.stop_session()

            timer = Timer(seconds, expire)
            timer.daemon = True
            timer.start()
            if self._session_timer is not None:
                self._session_timer.cancel()
            self._session_timer = timer
            self._session_token = token
            self._session_deadline = time.monotonic() + seconds

    def stop_session(self):
        """End temporary DEBUG and restore the configured settings."""
        with self._lock:
            if self._session_timer is not None:
                self._session_timer.cancel()
                self._session_timer = None
                self._session_token = None
                self._session_deadline = None
                if not self._settings.enabled:
                    self._finish_file()

    def _effective_settings(self):
        if self._session_deadline is not None:
            if time.monotonic() < self._session_deadline:
                return replace(self._settings, enabled=True, level="DEBUG")
            self.stop_session()
        return self._settings

    def _finish_file(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.close()
            except OSError:
                self._write_failed = True

    def _files(self):
        if self.directory.is_symlink() or getattr(self.directory, "is_junction", lambda: False)():
            return []
        return sorted((path for path in self.directory.glob("events-*.jsonl")
                       if _FILENAME.fullmatch(path.name)
                       and not path.is_symlink() and path.is_file()), reverse=True)

    def _prune(self):
        cutoff = time.time() - self._settings.retention_days * 86400
        total = 0
        for path in self._files():
            stat = path.stat()
            active = self._stream is not None and path.name == self._filename()
            if not active and (stat.st_mtime < cutoff or
                               total + stat.st_size > self._settings.max_total_bytes):
                path.unlink()
            else:
                total += stat.st_size

    def _filename(self):
        return f"events-{self._sequence:012d}.jsonl"

    def record(self, level, event_code, message, *, module=None, details=None,
               exception=None, project_revision=None, duration_ms=None, **ids):
        """Return whether the event was persisted. Unknown details are omitted."""
        level = level.upper()
        with self._lock:
            settings = self._effective_settings()
            if (self._closed or self._write_failed or not settings.enabled or
                    _LEVELS[level] < _LEVELS[settings.level]):
                return False
            event = {
                "schema_version": 1,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "monotonic_ms": int((time.monotonic() - self._started) * 1000),
                "level": level,
                "event_code": identifier(event_code) or "redacted",
                "message": safe_text(message),
                "session_id": self.session_id,
                "process_role": self._role,
            }
            for key, value in (("module", module), *((key, ids.get(key)) for key in _IDS)):
                cleaned = identifier(value)
                if cleaned is not None:
                    event[key] = cleaned
            if type(project_revision) is int and 0 <= project_revision < 2**63:
                event["project_revision"] = project_revision
            if (type(duration_ms) in (int, float) and 0 <= duration_ms < 2**63
                    and math.isfinite(duration_ms)):
                event["duration_ms"] = duration_ms
            clean_details = {}
            if type(details) is dict:
                for key in _DETAIL_COUNTS:
                    value = details.get(key)
                    if type(value) is int and 0 <= value < 2**63:
                        clean_details[key] = value
            if isinstance(exception, BaseException):
                clean_details["exception"] = exception_details(exception)
            if clean_details:
                event["details"] = clean_details
            payload = (json.dumps(event, ensure_ascii=False) + "\n").encode(
                "utf-8", errors="backslashreplace")
            if len(payload) > min(_MAX_EVENT_BYTES, settings.max_file_bytes):
                return False
            try:
                if self._stream is None or self._size + len(payload) > settings.max_file_bytes:
                    self._finish_file()
                    if self._write_failed:
                        return False
                    if self._sequence == 0:
                        self.directory.mkdir(parents=True, exist_ok=False)
                    self._sequence += 1
                    self._stream = (self.directory / self._filename()).open("xb")
                    self._size = 0
                self._stream.write(payload)
                self._stream.flush()
                self._size += len(payload)
                self._prune()
            except OSError:
                self._write_failed = True
                self._finish_file()
                return False
            return True

    def query(self, filters=None, cursor=None, *, limit=1000):
        """Read newest first, filtering by exact fields, UTC bounds or keyword."""
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        filters = filters or {}
        entries = []
        last = None
        with self._lock:
            for path in self._files():
                if cursor is not None and path.name > cursor[0]:
                    continue
                with path.open("rb") as stream:
                    lines = stream.readlines()
                for index in range(len(lines) - 1, -1, -1):
                    position = (path.name, index)
                    if cursor is not None and position >= cursor:
                        continue
                    try:
                        event = json.loads(lines[index])
                    except (ValueError, UnicodeError):
                        continue
                    if not isinstance(event, dict) or not self._matches(event, filters):
                        continue
                    if len(entries) == limit:
                        return LogPage(tuple(entries), last)
                    entries.append(event)
                    last = position
        return LogPage(tuple(entries))

    @staticmethod
    def _matches(event, filters):
        for key, value in filters.items():
            if key == "keyword":
                if value.casefold() not in json.dumps(event, ensure_ascii=False).casefold():
                    return False
            elif key == "since":
                if event.get("timestamp_utc", "") < value:
                    return False
            elif key == "until":
                if event.get("timestamp_utc", "") > value:
                    return False
            elif event.get(key) != value:
                return False
        return True

    def export_bundle(self, selection, directory):
        """Export this instance's logs using the same filters as query."""
        filters = dict(selection) if selection is not None else {}
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=directory, prefix=".diagnostics-", suffix=".tmp",
                                delete=False) as temporary:
            staging = Path(temporary.name)
        try:
            with self._lock, ZipFile(staging, "w", compression=ZIP_DEFLATED) as archive:
                count = 0
                with archive.open("events.jsonl", "w") as output:
                    for path in reversed(self._files()):
                        with path.open("rb") as source:
                            for line in source:
                                if len(line) > _MAX_EVENT_BYTES:
                                    continue
                                try:
                                    event = bundle_event(json.loads(line))
                                except (ValueError, OverflowError, RecursionError):
                                    continue
                                if event is not None and self._matches(event, filters):
                                    output.write((json.dumps(event, ensure_ascii=True) + "\n").encode("ascii"))
                                    count += 1
                metadata = bundle_metadata(
                    self.session_id, asdict(self._effective_settings()), count)
                archive.writestr("metadata.json", json.dumps(metadata, indent=2))
            # Publish only a complete archive and claim the name atomically.
            stem = f"diagnostics-{self.session_id}"
            index = 0
            while True:
                name = stem if index == 0 else f"{stem}-{index}"
                destination = directory / f"{name}.zip"
                try:
                    os.link(staging, destination)
                except FileExistsError:
                    index += 1
                else:
                    return destination
        finally:
            staging.unlink(missing_ok=True)

    def clear_history(self):
        with self._lock:
            self._finish_file()
            removed, failed = 0, []
            for path in self._files():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    failed.append(path.name)
            return ClearResult(removed, tuple(failed))

    def close(self):
        """Stop writes permanently; existing logs remain queryable."""
        with self._lock:
            self._closed = True
            self.stop_session()
            self._finish_file()
