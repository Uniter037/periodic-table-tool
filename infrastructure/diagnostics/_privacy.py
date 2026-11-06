"""Sanitize diagnostic text without collecting exception messages or locals."""

import os
import re
import traceback

_SECRET = re.compile(
    r"(?i)\b(?:password|passwd|token|secret|api[_-]?key|authorization|"
    r"clipboard|cell(?:[_ ](?:value|text|content))?|annotation|"
    r"username|user[_ -]?name)\s*[:=][^\r\n]*"
)
_PATH = re.compile(
    r"""(?i)(?:file:(?://)?|[a-z]:[\\/]|[\\/]{2}|(?<![\w<>/])(?:~|\.{1,2})?[\\/])[^\r\n"'<>|,;)]*"""
)
_PATH_EXTENSION = re.compile(
    r"""(?i)(?<![\w.])[\w.-]+\.(?:xlsx?|xlsm|csv|tsv|json|png|pdf|pyw?)\b"""
)
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:<>{}@+-]{1,128}\Z")


def identifier(value):
    if type(value) is str and _IDENTIFIER.fullmatch(value):
        cleaned = safe_text(value)
        if cleaned == value:
            return value
    return None


def safe_text(value):
    if type(value) is not str:
        return "[redacted]"
    # Redact before truncation so a path at the boundary cannot leak a prefix.
    value = _SECRET.sub("<REDACTED>", value)
    value = _PATH.sub("<SOURCE>", value)
    value = _PATH_EXTENSION.sub("<SOURCE>", value)
    for name in {os.environ.get(key) for key in ("USERNAME", "USER", "LOGNAME")}:
        if name:
            value = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", "<USER>",
                           value, flags=re.IGNORECASE)
    return value[:2048]


def exception_details(error):
    """Keep only the exception type and bounded frame coordinates."""
    frames = []
    for frame, line in traceback.walk_tb(error.__traceback__):
        frames.append({
            "file": "<SOURCE>",
            "function": identifier(frame.f_code.co_name) or "<redacted>",
            "line": line,
        })
        if len(frames) == 100:
            break
    return {
        "type": identifier(type(error).__name__) or "Exception",
        "frames": frames,
    }
