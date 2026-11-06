"""Cell values and source dataset snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import re

from ._validation import DTO, choice, coordinate, fields, number, require, string

# Importing core.elements_data would execute core/__init__.py and load rendering.
_SYMBOLS = frozenset("""
H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu
Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs
Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl
Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh
Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og
""".split())


def _attribute_id(key, code="DTO_INVALID"):
    string(key, "attribute ID", nonempty=True, code=code)
    require(key != "value" and key not in _SYMBOLS,
            "Attribute IDs cannot use value or an element symbol", code)


@dataclass(frozen=True)
class CellRef(DTO):
    source_id: str
    sheet: str
    address: str

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("source_id", "sheet", "address"), name="CellRef")
        for key in ("source_id", "sheet"):
            string(data[key], key, nonempty=True)
        coordinate(data["address"])
        return cls(**data)


@dataclass(frozen=True)
class CellValue(DTO):
    kind: str
    raw_text: str | None = None
    numeric: int | float | None = None
    formula: str | None = None
    cached: int | float | str | bool | None = None
    format_code: str | None = None
    source: CellRef | None = None

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("kind",), dict.fromkeys(
            ("raw_text", "numeric", "formula", "cached", "format_code", "source")
        ), name="CellValue")
        kind = data["kind"]
        choice(kind, ("number", "text", "missing", "error"), "cell kind")
        for key in ("raw_text", "formula", "format_code"):
            string(data[key], key, nullable=key != "raw_text" or kind != "text")
        if kind == "number":
            number(data["numeric"], "numeric")
        else:
            require(data["numeric"] is None, "Only number cells can have numeric values")
        formula, cached = data["formula"], data["cached"]
        if formula is None:
            require(cached is None, "Cached results require a formula")
        else:
            require(formula.startswith("="), "Formula must start with =")
            require(data["raw_text"] != formula, "Formula must not be duplicated in raw_text")
        if cached is not None and type(cached) not in (str, bool):
            number(cached, "cached")
        if data["source"] is not None:
            data["source"] = CellRef.from_dict(data["source"])
        return cls(**data)


@dataclass(frozen=True)
class ElementRecord(DTO):
    element: str
    value: CellValue
    attributes: dict[str, CellValue] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("element", "value"), {"attributes": {}}, name="ElementRecord")
        choice(data["element"], _SYMBOLS, "element symbol", "ELEMENT_UNKNOWN")
        data["value"] = CellValue.from_dict(data["value"])
        attrs = data["attributes"]
        require(type(attrs) is dict, "attributes must be an object")
        data["attributes"] = {}
        for key, value in attrs.items():
            _attribute_id(key)
            data["attributes"][key] = CellValue.from_dict(value)
        return cls(**data)


_UTC = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T(?:[01][0-9]|2[0-3]):"
    r"[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?Z"
)


@dataclass(frozen=True)
class Provenance(DTO):
    mapping_id: str | None
    source_hash: str | None
    transform_version: str
    created_at: str

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("mapping_id", "source_hash", "transform_version", "created_at"),
                      name="Provenance")
        mapping_id, source_hash = data["mapping_id"], data["source_hash"]
        string(mapping_id, "mapping_id", nonempty=True, nullable=True)
        require((mapping_id is None) == (source_hash is None),
                "mapping_id and source_hash must both be present or both be null")
        if source_hash is not None:
            require(type(source_hash) is str and re.fullmatch(r"[0-9a-f]{64}", source_hash),
                    "Invalid source_hash")
            choice(data["transform_version"], ("import-v1",), "import transform version")
        else:
            string(data["transform_version"], "transform_version", nonempty=True)
            require(data["transform_version"] != "import-v1", "Import provenance requires a source")
        timestamp = data["created_at"]
        match = _UTC.fullmatch(timestamp) if type(timestamp) is str else None
        require(match is not None, "created_at must be a UTC timestamp")
        try:
            date(*map(int, match.groups()))
        except ValueError:
            require(False, "created_at must use a valid calendar date")
        return cls(**data)


@dataclass(frozen=True)
class Dataset(DTO):
    id: str
    metric_id: str
    condition_id: str
    records: dict[str, ElementRecord]
    provenance: Provenance

    @classmethod
    def from_dict(cls, data):
        data = fields(data, ("id", "metric_id", "condition_id", "records", "provenance"),
                      name="Dataset")
        for key in ("id", "metric_id", "condition_id"):
            string(data[key], key, nonempty=True)
        records = data["records"]
        require(type(records) is dict and records, "records must be a nonempty object")
        data["records"] = {}
        for key, value in records.items():
            record = ElementRecord.from_dict(value)
            require(type(key) is str and key == record.element, "Record key must match element")
            # Invalid previews can carry error records; successful commit checks
            # diagnostics and values at the application boundary.
            data["records"][key] = record
        data["provenance"] = Provenance.from_dict(data["provenance"])
        return cls(**data)
