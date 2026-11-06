"""Shared validation for JSON DTO boundaries."""
from dataclasses import asdict
from math import isfinite
import re


class ContractError(ValueError):
    """A validation failure with a stable diagnostic code."""

    def __init__(self, message, code="DTO_INVALID"):
        super().__init__(message)
        self.code = code


def require(ok, message, code="DTO_INVALID"):
    if not ok:
        raise ContractError(message, code)


def fields(data, required=(), defaults=None, *, name="object", code="DTO_INVALID"):
    defaults = {} if defaults is None else defaults
    require(type(data) is dict, f"{name} must be an object", code)
    require(all(key in data for key in required), f"{name} has missing fields", code)
    require(all(type(key) is str and (key in required or key in defaults) for key in data),
            f"{name} has unknown fields", code)
    return {**defaults, **data}


def string(value, name, *, nonempty=False, nullable=False, code="DTO_INVALID"):
    require((nullable and value is None) or
            (type(value) is str and (not nonempty or bool(value))),
            f"{name} must be a valid string", code)


def choice(value, allowed, name, code="DTO_INVALID"):
    require(type(value) is str and value in allowed, f"Invalid {name}", code)


def number(value, name, code="DTO_INVALID"):
    require(type(value) in (int, float), f"{name} must be a number", code)
    require(type(value) is int or isfinite(value), f"{name} must be finite",
            "NON_FINITE_NUMBER" if code == "DTO_INVALID" else code)


MAX_ROW = 1048576
MAX_COLUMN = 16384


def column(value, code):
    require(type(value) is str and re.fullmatch(r"[A-Z]{1,3}", value),
            "Invalid column letters", code)
    index = 0
    for letter in value:
        index = index * 26 + ord(letter) - ord("A") + 1
    require(index <= MAX_COLUMN, "Column exceeds address boundary", code)
    return index


def coordinate(value, code="DTO_INVALID"):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", value) if type(value) is str else None
    require(match is not None, "Invalid A1 coordinate", code)
    letters, digits = match.groups()
    row = int(digits)
    require(row <= MAX_ROW, "Row exceeds address boundary", code)
    return row, column(letters, code)


class DTO:
    """Dataclass DTO with validated, detached JSON encoding."""

    def to_dict(self):
        data = asdict(self)
        return asdict(type(self).from_dict(data))
