"""Regression tests for the frozen workbench DTO wire contracts."""
from copy import deepcopy
import json
import subprocess
import sys

import pytest

from domain import CellRef, CellValue, ContractError, Dataset, Diagnostic, ImportMapping, Provenance


@pytest.mark.parametrize("payload", [
    {"kind": "missing"},
    {"kind": "number", "numeric": 0},
    {"kind": "number", "numeric": 1.0},
    {"kind": "text", "raw_text": "001"},
    {"kind": "text", "raw_text": ""},
    {"kind": "text", "raw_text": "0"},
    {"kind": "number", "numeric": 0, "formula": "=1-1", "cached": 0},
    {"kind": "text", "raw_text": "", "formula": '=""', "cached": ""},
    {"kind": "text", "raw_text": "FALSE", "formula": "=FALSE()", "cached": False},
    {"kind": "error", "formula": "=A1"},
])
def test_cell_value_round_trip(payload):
    expected = dict.fromkeys(("raw_text", "numeric", "formula", "cached", "format_code", "source"))
    expected.update(payload)
    actual = CellValue.from_dict(payload).to_dict()
    assert actual == expected
    for key in ("numeric", "cached"):
        assert type(actual[key]) is type(expected[key])
    assert CellValue.from_dict(json.loads(json.dumps(actual, allow_nan=False))).to_dict() == actual


@pytest.mark.parametrize("payload", [
    {},
    {"kind": "missing", "numeric": 0},
    {"kind": "text"},
    {"kind": "text", "raw_text": "0", "numeric": 0},
    {"kind": "number"},
    {"kind": "number", "numeric": True},
    {"kind": "number", "numeric": "0"},
    {"kind": "missing", "cached": 0},
    {"kind": "text", "raw_text": "=A1", "formula": "=A1"},
    {"kind": "missing", "formula": "A1"},
    {"kind": "missing", "unknown": None},
    {"kind": "missing", "source": {"source_id": "s", "sheet": "Data", "address": "A1", "row": 1}},
])
def test_cell_value_rejects_invalid_fields(payload):
    with pytest.raises(ValueError):
        CellValue.from_dict(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numbers_are_rejected(value):
    for payload in (
        {"kind": "number", "numeric": value},
        {"kind": "error", "formula": "=A1", "cached": value},
    ):
        with pytest.raises(ContractError) as error:
            CellValue.from_dict(payload)
        assert error.value.code == "NON_FINITE_NUMBER"
    with pytest.raises(ValueError):
        CellValue("number", numeric=value).to_dict()


@pytest.mark.parametrize("address", ["$A$1", "a1", "A01", "A0", "A1:B2", "Data!A1", "XFE1", "A1048577"])
def test_cell_ref_rejects_noncanonical_or_out_of_bounds_addresses(address):
    with pytest.raises(ValueError):
        CellRef.from_dict({"source_id": "src", "sheet": "Data", "address": address})


def _dataset():
    return {
        "id": "dataset-1", "metric_id": "metric-1", "condition_id": "condition-1",
        "records": {"H": {"element": "H", "value": {"kind": "missing"}}},
        "provenance": {
            "mapping_id": None, "source_hash": None, "transform_version": "manual-v1",
            "created_at": "2024-02-29T12:00:00.123456789Z",
        },
    }


def test_dataset_retains_missing_record_and_detaches_both_boundaries():
    payload = _dataset()
    first = Dataset.from_dict(payload)
    second = Dataset.from_dict(payload)
    payload["records"]["H"]["value"]["kind"] = "error"
    result = first.to_dict()
    assert result["records"]["H"]["value"]["kind"] == "missing"
    assert result["records"]["H"]["attributes"] == {}
    result["records"]["H"]["attributes"]["mass"] = {}
    assert first.records["H"].attributes == {}
    assert first.records["H"].attributes is not second.records["H"].attributes
    assert Dataset.from_dict(first.to_dict()) == first


@pytest.mark.parametrize("change", [
    {"records": {}},
    {"records": {"H": {"element": "He", "value": {"kind": "missing"}}}},
    {"records": {"h": {"element": "h", "value": {"kind": "missing"}}}},
    {"records": {"H": {"element": "H", "value": {"kind": "missing"},
                       "attributes": {"value": {"kind": "missing"}}}}},
    {"records": {"H": {"element": "H", "value": {"kind": "missing"},
                       "attributes": {"He": {"kind": "missing"}}}}},
    {"metric_id": ""},
    {"extra": []},
])
def test_invalid_datasets(change):
    with pytest.raises(ValueError):
        Dataset.from_dict({**_dataset(), **change})


def test_provenance_validates_sources_versions_and_calendar():
    manual = _dataset()["provenance"]
    imported = {**manual, "mapping_id": "map", "source_hash": "a" * 64,
                "transform_version": "import-v1"}
    assert Provenance.from_dict(imported).to_dict() == imported
    for change in ({"source_hash": None}, {"source_hash": "A" * 64},
                   {"transform_version": "manual-v1"}, {"created_at": "2023-02-29T12:00:00Z"},
                   {"created_at": "2024-02-29T12:00:00+00:00"}):
        with pytest.raises(ValueError):
            Provenance.from_dict({**imported, **change})
    with pytest.raises(ValueError):
        Provenance.from_dict({k: v for k, v in manual.items() if k != "mapping_id"})


def test_diagnostic_defaults_severity_and_pointer():
    payload = {"code": "FORMULA_CACHE_USED", "severity": "warning", "message": "Saved result",
               "target": {"kind": "mapping", "id": None, "path": "/regions/a~1b/~0"}}
    assert Diagnostic.from_dict(payload).to_dict() == {**payload, "locations": [], "remedy": None}
    for change in ({"severity": "error"}, {"code": "UNKNOWN"}, {"details": {}},
                   {"target": {**payload["target"], "path": "/bad~2escape"}},
                   {"target": {"kind": "mapping", "path": ""}}):
        with pytest.raises(ValueError):
            Diagnostic.from_dict({**payload, **change})


def _region(range_, sheet="Data"):
    return {"sheet": sheet, "range": range_}


def _mapping(layout):
    regions = {
        "matrix_rows": {"elements": _region("B1:D1"), "conditions": _region("A2:A3"),
                        "values": _region("B2:D3")},
        "matrix_columns": {"elements": _region("A2:A4"), "conditions": _region("B1:C1"),
                           "values": _region("B2:C4")},
        "records": {"sheet": "Data", "start_row": 1, "end_row": 1048576,
                    "columns": {"element": "A", "value": "XFD"}},
        "category_groups": {"groups": [{"category": _region("A1"), "elements": _region("B1:D1")},
                                       {"category": _region("A2"), "elements": _region("B2:B4")}]},
    }
    return {
        "id": "map", "source_id": "src", "schema_version": 1, "layout": layout,
        "metric": {"name": "Measurement", "value_kind": "category" if layout == "category_groups" else "numeric"},
        "condition": {"name": "Condition"}, "regions": regions[layout],
    }


@pytest.mark.parametrize("layout", ["matrix_rows", "matrix_columns", "records", "category_groups"])
def test_valid_layouts_and_defaults(layout):
    payload = _mapping(layout)
    mapping = ImportMapping.from_dict(payload)
    data = mapping.to_dict()
    assert data["metric"]["unit"] is None
    assert data["condition"] == {"name": "Condition", "unit": None, "interpretation": "literal"}
    assert data["policies"] == {"duplicate": "error", "missing": "keep", "hidden": "include",
                                "formula": "cached_only"}
    assert data["transforms"] == []
    if layout == "records":
        assert data["regions"]["columns"]["condition"] is None
        assert data["regions"]["columns"]["attributes"] == {}
    if layout == "category_groups":
        assert all(group["group_name"] is None for group in data["regions"]["groups"])
    assert ImportMapping.from_dict(data) == mapping
    payload["regions"].clear()
    data["regions"].clear()
    assert mapping.to_dict()["regions"]


@pytest.mark.parametrize("layout,region_patch,code", [
    ("matrix_rows", {"values": _region("B2:C3")}, "MAPPING_SHAPE_MISMATCH"),
    ("matrix_rows", {"elements": _region("B1:D2")}, "MAPPING_SHAPE_MISMATCH"),
    ("matrix_columns", {"values": _region("B2:C3")}, "MAPPING_SHAPE_MISMATCH"),
    ("matrix_columns", {"conditions": _region("B1:B2")}, "MAPPING_SHAPE_MISMATCH"),
    ("matrix_rows", {"values": _region("B2:D3", "Other")}, "MAPPING_INVALID"),
    ("matrix_rows", {"values": _region("D3:B2")}, "REGION_INVALID"),
    ("records", {"start_row": True}, "REGION_INVALID"),
    ("records", {"end_row": 1048577}, "REGION_INVALID"),
    ("records", {"start_row": 3, "end_row": 2}, "REGION_INVALID"),
    ("records", {"columns": {"element": "A", "value": "XFE"}}, "REGION_INVALID"),
    ("records", {"columns": {"element": "A", "value": "B", "attributes": {"mass": "B"}}},
     "MAPPING_INVALID"),
    ("category_groups", {"groups": []}, "MAPPING_INVALID"),
    ("category_groups", {"groups": [{"category": _region("A1:A2"), "elements": _region("B1")}]},
     "MAPPING_INVALID"),
    ("category_groups", {"groups": [{"category": _region("A1"), "elements": _region("B1:C2")}]},
     "MAPPING_INVALID"),
])
def test_invalid_layout_dimensions(layout, region_patch, code):
    payload = _mapping(layout)
    payload["regions"].update(region_patch)
    with pytest.raises(ContractError) as error:
        ImportMapping.from_dict(payload)
    assert error.value.code == code


@pytest.mark.parametrize("change,code", [
    ({"schema_version": 2}, "SCHEMA_UNSUPPORTED"),
    ({"schema_version": True}, "MAPPING_INVALID"),
    ({"policies": {"duplicate": "last"}}, "MAPPING_INVALID"),
    ({"metric": {"name": "X", "value_kind": "numeric", "metric_id": "x"}}, "MAPPING_INVALID"),
    ({"extra": None}, "MAPPING_INVALID"),
    ({"transforms": [{"op": "trim", "target": "value", "params": {}}]}, "TRANSFORM_INVALID"),
    ({"transforms": [{"op": "round", "target": "value", "params": {"digits": True}}]},
     "TRANSFORM_INVALID"),
    ({"transforms": [{"op": "percent_scale", "target": "value", "params": {"factor": float("inf")}}]},
     "TRANSFORM_INVALID"),
    ({"transforms": [{"op": "numeric_parse", "target": "attributes.mass", "params": {}}]},
     "TRANSFORM_INVALID"),
])
def test_mapping_rejects_invalid_options(change, code):
    with pytest.raises(ContractError) as error:
        ImportMapping.from_dict({**_mapping("records"), **change})
    assert error.value.code == code


def test_transform_order_and_declared_attribute():
    payload = _mapping("records")
    payload["regions"]["columns"]["attributes"] = {"mass": "B"}
    payload["transforms"] = [
        {"op": "trim", "target": "attributes.mass", "params": {}},
        {"op": "numeric_parse", "target": "attributes.mass", "params": {}},
        {"op": "aggregate", "target": "value", "params": {"method": "mean"}},
    ]
    assert ImportMapping.from_dict(payload).to_dict()["transforms"] == payload["transforms"]
    invalid = deepcopy(payload)
    invalid["transforms"].insert(0, invalid["transforms"][-1])
    with pytest.raises(ValueError):
        ImportMapping.from_dict(invalid)


def test_domain_import_does_not_load_ui_or_workbook_dependencies():
    subprocess.run([sys.executable, "-c", """
import sys
import domain
assert not {"tkinter", "matplotlib", "openpyxl"} & sys.modules.keys()
"""], check=True)
