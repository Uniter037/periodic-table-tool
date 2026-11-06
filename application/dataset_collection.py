"""Project-local Excel datasets and their independent legacy editor buffers."""
from __future__ import annotations

from copy import deepcopy
import re

from domain import CellValue, Dataset, Diagnostic, ImportMapping
from domain._validation import choice, fields, number, require, string
from domain.data import _SYMBOLS

from .excel_import import legacy_data

_COLLECTIONS = ("datasets", "conditions", "metrics", "sources", "mappings")
_SNAPSHOT_FIELDS = (*_COLLECTIONS, "active_dataset_id", "manual_data")
_METRIC_KINDS = {"numeric": "number", "text": "text", "category": "text"}


def _reference(key, items, name):
    string(key, name, nonempty=True, code="REFERENCE_INVALID")
    require(key in items, f"Unknown {name}: {key}", "REFERENCE_INVALID")
    return items[key]


def _metric(data):
    data = fields(data, ("id", "name", "value_kind"), {"unit": None}, name="Metric")
    string(data["name"], "metric name", nonempty=True)
    string(data["unit"], "metric unit", nullable=True)
    choice(data["value_kind"], _METRIC_KINDS, "metric value kind")
    return data


def _condition(data):
    data = fields(data, ("id", "label"), {"attributes": {}}, name="Condition")
    string(data["label"], "condition label", nonempty=True)
    require(type(data["attributes"]) is dict, "Condition attributes must be an object")
    attrs = {}
    for name, raw in data["attributes"].items():
        string(name, "condition attribute", nonempty=True)
        attrs[name] = CellValue.from_dict(raw).to_dict()
    return {**data, "attributes": attrs}


def _source(data):
    data = fields(data, ("id", "kind", "display_name", "locator", "fingerprint"), name="Source")
    choice(data["kind"], ("xlsx",), "source kind")
    string(data["display_name"], "source display name", nonempty=True)
    string(data["locator"], "source locator", nullable=True)
    fingerprint = fields(data["fingerprint"], ("sha256", "size", "mtime"), name="Fingerprint")
    digest = fingerprint["sha256"]
    require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest),
            "Invalid source fingerprint hash")
    size = fingerprint["size"]
    require(type(size) is int and size >= 0, "Invalid source size")
    number(fingerprint["mtime"], "source modification time")
    return {**data, "fingerprint": fingerprint}


def _index(items, decode, name):
    require(type(items) is list, f"{name} must be an array")
    result = {}
    for raw in items:
        item = decode(raw)
        key = item["id"]
        string(key, f"{name} ID", nonempty=True)
        require(key not in result, f"Duplicate {name} ID: {key}", "ID_DUPLICATE")
        result[key] = item
    return result


def _manual_data(data):
    require(type(data) is dict, "Manual data must be an object")
    for symbol, value in data.items():
        choice(symbol, _SYMBOLS, "element symbol", "ELEMENT_UNKNOWN")
        if type(value) is not str:
            number(value, "manual value")
    return dict(data)


def _validate_cell(cell, sources, source_id=None):
    require(cell["kind"] != "error", "Error cells cannot be stored", "IMPORT_BLOCKED")
    ref = cell["source"]
    if ref is not None:
        _reference(ref["source_id"], sources, "cell source ID")
        require(source_id is None or ref["source_id"] == source_id,
                "Cell source differs from dataset mapping source", "REFERENCE_INVALID")


class DatasetCollection:
    """Own the active selection, original DTOs and one optional edit buffer per group.

    Snapshots use ordered DTO arrays and a manual_data object keyed by dataset ID.
    The editor buffer replaces a group's render data so deletions can be preserved.
    """

    def __init__(self):
        self._items = {name: {} for name in _COLLECTIONS}
        self._active_dataset_id = None
        self._manual_data = {}

    @property
    def active_dataset_id(self) -> str | None:
        return self._active_dataset_id

    def snapshot(self) -> dict:
        return deepcopy({
            **{name: list(items.values()) for name, items in self._items.items()},
            "active_dataset_id": self._active_dataset_id,
            "manual_data": self._manual_data,
        })

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> DatasetCollection:
        raw = fields(snapshot, _SNAPSHOT_FIELDS, name="DatasetCollection snapshot")
        items = cls._decode_items(raw)
        cls._validate_references(items)
        active = raw["active_dataset_id"]
        if items["datasets"] or active is not None:
            _reference(active, items["datasets"], "active dataset ID")
        require(type(raw["manual_data"]) is dict, "manual_data must be an object")
        edits = {}
        for key, data in raw["manual_data"].items():
            _reference(key, items["datasets"], "edited dataset ID")
            edits[key] = _manual_data(data)

        collection = cls()
        collection._items = items
        collection._active_dataset_id = active
        collection._manual_data = edits
        return collection

    @staticmethod
    def _decode_items(raw):
        return {
            "datasets": _index(raw["datasets"], lambda d: Dataset.from_dict(d).to_dict(), "dataset"),
            "conditions": _index(raw["conditions"], _condition, "condition"),
            "metrics": _index(raw["metrics"], _metric, "metric"),
            "sources": _index(raw["sources"], _source, "source"),
            "mappings": _index(raw["mappings"], lambda d: ImportMapping.from_dict(d).to_dict(), "mapping"),
        }

    @staticmethod
    def _validate_references(items):
        sources = items["sources"]
        for mapping in items["mappings"].values():
            _reference(mapping["source_id"], sources, "mapping source ID")
        for condition in items["conditions"].values():
            for cell in condition["attributes"].values():
                _validate_cell(cell, sources)

        for dataset in items["datasets"].values():
            metric = _reference(dataset["metric_id"], items["metrics"], "metric ID")
            condition = _reference(dataset["condition_id"], items["conditions"], "condition ID")
            provenance = dataset["provenance"]
            mapping = _reference(provenance["mapping_id"], items["mappings"], "dataset mapping ID")
            source_id = mapping["source_id"]
            require(provenance["source_hash"] == sources[source_id]["fingerprint"]["sha256"],
                    "Dataset hash differs from mapping source hash", "REFERENCE_INVALID")
            for cell in condition["attributes"].values():
                _validate_cell(cell, sources, source_id)
            expected = _METRIC_KINDS[metric["value_kind"]]
            for record in dataset["records"].values():
                value = record["value"]
                _validate_cell(value, sources, source_id)
                require(value["kind"] in (expected, "missing"),
                        "Record value kind differs from metric kind", "VALUE_KIND_MISMATCH")
                for cell in record["attributes"].values():
                    _validate_cell(cell, sources, source_id)

    def append(self, preview: dict, activate_dataset_id: str | None = None) -> list[str]:
        """Append a ready ExcelImportService preview and return its new dataset IDs.

        The first append selects its first group. Subsequent appends keep the
        selection unless the caller requests activation of a newly appended group.
        """
        require(type(preview) is dict, "Preview must be an object")
        require(preview.get("status") == "ready", "Preview is not ready", "IMPORT_BLOCKED")
        diagnostics = preview.get("diagnostics")
        require(type(diagnostics) is list, "Preview diagnostics must be an array")
        for raw in diagnostics:
            require(Diagnostic.from_dict(raw).severity != "error",
                    "Preview contains errors", "IMPORT_BLOCKED")

        incoming = self._decode_items({
            **{name: preview.get(name) for name in _COLLECTIONS if name != "mappings"},
            "mappings": [preview.get("mapping")],
        })
        require(bool(incoming["datasets"]), "Preview has no datasets", "EMPTY_DATASET")
        mapping_id = next(iter(incoming["mappings"]))
        for dataset in incoming["datasets"].values():
            provenance = dataset["provenance"]
            require(provenance["mapping_id"] == mapping_id and
                    provenance["source_hash"] == preview.get("source_hash"),
                    "Dataset provenance differs from preview", "REFERENCE_INVALID")

        candidate = {name: dict(items) for name, items in self._items.items()}
        for name, items in incoming.items():
            for key, item in items.items():
                if key in candidate[name]:
                    # One ExcelImportService may preview several sheets of the
                    # same source. Reuse only the identical source descriptor.
                    require(name == "sources" and item == candidate[name][key],
                            f"Duplicate {name} ID: {key}", "ID_DUPLICATE")
                else:
                    candidate[name][key] = item

        self._validate_references(candidate)
        added = list(incoming["datasets"])
        if activate_dataset_id is not None:
            _reference(activate_dataset_id, incoming["datasets"], "new active dataset ID")
        active = activate_dataset_id or self._active_dataset_id or added[0]
        self._items = candidate
        self._active_dataset_id = active
        return added

    def select(self, dataset_id: str) -> None:
        _reference(dataset_id, self._items["datasets"], "dataset ID")
        self._active_dataset_id = dataset_id

    def effective_data(self, dataset_id: str | None = None) -> dict:
        key = self._active_dataset_id if dataset_id is None else dataset_id
        if key is None:
            return {}
        dataset = _reference(key, self._items["datasets"], "dataset ID")
        if key in self._manual_data:
            return dict(self._manual_data[key])
        return legacy_data(dataset)

    def set_manual_data(self, data: dict | None, dataset_id: str | None = None) -> None:
        """Save a group's full editor data. None restores the original source."""
        key = self._active_dataset_id if dataset_id is None else dataset_id
        _reference(key, self._items["datasets"], "dataset ID")
        if data is None:
            self._manual_data.pop(key, None)
        else:
            self._manual_data[key] = _manual_data(data)
