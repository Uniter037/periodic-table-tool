"""Stable diagnostic codes and JSON Pointer targets."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from ._validation import DTO, choice, fields, require, string
from .data import CellRef


_SEVERITIES = dict.fromkeys("""
DTO_INVALID SCHEMA_UNSUPPORTED ID_DUPLICATE REFERENCE_INVALID SOURCE_UNREADABLE
SOURCE_INVALID SOURCE_CHANGED READ_LIMIT_EXCEEDED SHEET_NOT_FOUND REGION_INVALID
MAPPING_INVALID MAPPING_SHAPE_MISMATCH MERGED_REGION_UNSUPPORTED TRANSFORM_INVALID
NUMERIC_PARSE_FAILED NON_FINITE_NUMBER VALUE_KIND_MISMATCH ELEMENT_MISSING
ELEMENT_UNKNOWN ELEMENT_DUPLICATE CONDITION_MISSING CATEGORY_MISSING EMPTY_DATASET
CELL_ERROR FORMULA_CACHE_MISSING PREVIEW_INVALID REVISION_CONFLICT IMPORT_BLOCKED
COMMAND_INVALID STATE_REENTRANT DATASET_MISMATCH COMMAND_FAILED
""".split(), "error")
_SEVERITIES.update(dict.fromkeys("""
FORMULA_CACHE_USED DUPLICATES_AGGREGATED SCAN_TRUNCATED OBSERVER_FAILED
""".split(), "warning"))
_SEVERITIES.update(dict.fromkeys(("HIDDEN_INCLUDED", "IMPORT_CANCELLED"), "info"))


@dataclass(frozen=True)
class DiagnosticTarget(DTO):
    kind: str
    id: str | None
    path: str

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("kind", "id", "path"), name="DiagnosticTarget")
        choice(data["kind"], ("mapping", "dataset", "plot", "project", "command"), "target kind")
        string(data["id"], "target ID", nonempty=True, nullable=True)
        path = data["path"]
        require(type(path) is str and re.fullmatch(r"(?:/(?:[^~/]|~[01])*)*", path),
                "Invalid target JSON Pointer")
        return cls(**data)


@dataclass(frozen=True)
class Diagnostic(DTO):
    code: str
    severity: str
    message: str
    locations: list[CellRef] = field(default_factory=list)
    target: DiagnosticTarget | None = None
    remedy: str | None = None

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("code", "severity", "message"),
                      {"locations": [], "target": None, "remedy": None}, name="Diagnostic")
        choice(data["code"], _SEVERITIES, "diagnostic code")
        choice(data["severity"], (_SEVERITIES[data["code"]],), "severity for diagnostic code")
        string(data["message"], "message", nonempty=True)
        string(data["remedy"], "remedy", nullable=True)
        require(type(data["locations"]) is list, "locations must be an array")
        data["locations"] = [CellRef.from_dict(location) for location in data["locations"]]
        if data["target"] is not None:
            data["target"] = DiagnosticTarget.from_dict(data["target"])
        return cls(**data)
