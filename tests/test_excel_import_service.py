from dataclasses import replace
from hashlib import sha256
import json

import pytest

from application.excel_import import ExcelImportService, legacy_data
from domain import Dataset, Diagnostic, ImportMapping
from test_xlsx_reader import MAIN, fixture_zip


def _workbook(tmp_path, contents):
    path = tmp_path / "matrix.xlsx"
    path.write_bytes(fixture_zip(**{
        "sheets/value sheet.xml": f'<worksheet xmlns="{MAIN}">{contents}</worksheet>',
    }))
    return path


def _text(address, value):
    return f'<c r="{address}" t="inlineStr"><is><t>{value}</t></is></c>'


def _row(number, *cells):
    return f'<row r="{number}">{"".join(cells)}</row>'


def _sheet(*rows, before="", after=""):
    return f'{before}<sheetData>{"".join(rows)}</sheetData>{after}'


def _preview(service, elements="B1:C1", conditions="A2:A3", values="B2:C3",
             direction="matrix_rows"):
    return service.preview("Values", elements, conditions, values, direction)


def _codes(result):
    return {item["code"] for item in result["diagnostics"]}


@pytest.fixture
def matrix(tmp_path):
    return _workbook(tmp_path, _sheet(
        _row(1, _text("B1", "H"), _text("C1", "He")),
        _row(2, '<c r="A2"><v>0</v></c>', '<c r="B2"><f>1-1</f><v>0</v></c>'),
        _row(3, '<c r="A3"><v>0</v></c>', '<c r="B3"><v>3</v></c>', '<c r="C3"><v>-4</v></c>'),
        _row(4, '<c r="B4"><f>ROUND(B3,0)</f></c>'),
        before='<cols><col min="2" max="2" hidden="1"/></cols>',
    ))


def test_matrix_rows_json_references_missing_and_legacy(matrix):
    service = ExcelImportService(matrix)
    assert service.sheets == ["Values", "Hidden"]
    service.sheets.clear()
    result = _preview(service, elements=" b1:c1 ")
    assert result["status"] == "ready"
    assert result["source_hash"] == sha256(matrix.read_bytes()).hexdigest()
    assert _codes(result) == {"FORMULA_CACHE_USED", "HIDDEN_INCLUDED"}
    cache = next(item for item in result["diagnostics"] if item["code"] == "FORMULA_CACHE_USED")
    assert [ref["address"] for ref in cache["locations"]] == ["B2"]
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    mapping = ImportMapping.from_dict(result["mapping"])
    assert mapping.regions["elements"]["range"] == "B1:C1"
    assert result["sources"][0]["id"] == mapping.source_id
    assert len(result["metrics"]) == 1
    assert [item["label"] for item in result["conditions"]] == ["0", "0"]
    assert len({item["id"] for item in result["conditions"]}) == 2
    assert [item["condition_id"] for item in result["datasets"]] == [
        item["id"] for item in result["conditions"]
    ]
    for data in result["datasets"]:
        dataset = Dataset.from_dict(data)
        assert dataset.metric_id == result["metrics"][0]["id"]
        assert dataset.provenance.source_hash == result["source_hash"]
        assert dataset.provenance.mapping_id == mapping.id
        assert all(record.value.source.source_id == mapping.source_id
                   for record in dataset.records.values())
    first, second = result["datasets"]
    assert first["records"]["H"]["value"]["cached"] == 0
    assert first["records"]["He"]["value"]["kind"] == "missing"
    assert first["records"]["He"]["value"]["source"]["address"] == "C2"
    assert legacy_data(first) == {"H": 0}
    assert legacy_data(Dataset.from_dict(second)) == {"H": 3, "He": -4}
    assert result["stats"]["missing_count"] == 1


def test_matrix_columns_preserves_text_and_does_not_infer_numbers(tmp_path):
    path = _workbook(tmp_path, _sheet(
        _row(1, _text("B1", "first"), _text("C1", "second")),
        _row(2, _text("A2", "H"), _text("B2", "001"), _text("C2", "H site")),
        _row(3, _text("A3", "He"), '<c r="B3" t="str"><f>IF(TRUE,"","x")</f><v/></c>'),
    ))
    result = _preview(ExcelImportService(path), "A2:A3", "B1:C1", "B2:C3", "matrix_columns")
    assert result["status"] == "ready"
    assert result["metrics"][0]["value_kind"] == "text"
    assert [legacy_data(item) for item in result["datasets"]] == [
        {"H": "001", "He": ""}, {"H": "H site"},
    ]
    assert _codes(result) == {"FORMULA_CACHE_USED"}


@pytest.mark.parametrize(("overrides", "code"), [
    ({"elements": "B1:C2"}, "MAPPING_SHAPE_MISMATCH"),
    ({"values": "B2:B3"}, "MAPPING_SHAPE_MISMATCH"),
    ({"conditions": "A3:A2"}, "REGION_INVALID"),
    ({"values": "XFE1:XFE2"}, "REGION_INVALID"),
    ({"direction": "records"}, "MAPPING_INVALID"),
])
def test_bad_selection_returns_diagnostics(matrix, overrides, code):
    result = _preview(ExcelImportService(matrix), **overrides)
    assert result["status"] == "invalid"
    assert result["datasets"] == []
    assert _codes(result) == {code}


def test_bad_cells_are_locatable_and_cannot_commit(tmp_path):
    path = _workbook(tmp_path, _sheet(
        _row(1, _text("B1", "H"), _text("C1", "H"), _text("D1", "Xx"), _text("F1", "He")),
        _row(2, '<c r="B2"><f>1+1</f><v/></c>', '<c r="C2"><v>9</v></c>',
             '<c r="D2" t="e"><f>1/0</f><v>#DIV/0!</v></c>',
             '<c r="E2"><v>7</v></c>', _text("F2", "not a number")),
    ))
    result = _preview(ExcelImportService(path), "B1:G1", "A2", "B2:G2")
    assert result["status"] == "invalid"
    diagnostics = [Diagnostic.from_dict(item) for item in result["diagnostics"]]
    assert {diag.code: [ref.address for ref in diag.locations] for diag in diagnostics} == {
        "ELEMENT_DUPLICATE": ["B1", "C1"],
        "ELEMENT_UNKNOWN": ["D1"],
        "CONDITION_MISSING": ["A2"],
        "FORMULA_CACHE_MISSING": ["B2"],
        "CELL_ERROR": ["D2"],
        "ELEMENT_MISSING": ["E1", "E2"],
        "VALUE_KIND_MISMATCH": ["F2"],
    }
    records = result["datasets"][0]["records"]
    assert records["H"]["value"]["kind"] == "error"
    assert records["H"]["value"]["formula"] == "=1+1"
    assert records["He"]["value"]["kind"] == "error"
    assert records["He"]["value"]["raw_text"] == "not a number"
    assert result["stats"]["skipped_blank_count"] == 1
    with pytest.raises(ValueError):
        legacy_data(result["datasets"][0])


def test_merge_intersecting_selection_blocks_preview(tmp_path):
    path = _workbook(tmp_path, _sheet(
        _row(1, _text("B1", "H"), _text("C1", "He")),
        _row(2, _text("A2", "one")),
        after='<mergeCells><mergeCell ref="B2:C2"/></mergeCells>',
    ))
    result = _preview(ExcelImportService(path), conditions="A2", values="B2:C2")
    assert _codes(result) == {"MERGED_REGION_UNSUPPORTED"}
    assert result["datasets"] == []


@pytest.mark.parametrize("change", ["grid_hash", "file_after_last_grid"])
def test_source_changes_reject_entire_preview(matrix, monkeypatch, change):
    service = ExcelImportService(matrix)
    read_region = service._reader.read_region

    def read_then_change(path, sheet, area, source_id):
        grid = read_region(path, sheet, area, source_id)
        if area == "A2:A3" and change == "grid_hash":
            return replace(grid, source_hash="0" * 64)
        if area == "B2:C3" and change == "file_after_last_grid":
            path.write_bytes(fixture_zip())
        return grid

    monkeypatch.setattr(service._reader, "read_region", read_then_change)
    result = _preview(service)
    assert _codes(result) == {"SOURCE_CHANGED"}
    assert result["source_hash"] is None
    assert result["datasets"] == []
