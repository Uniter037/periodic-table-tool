from copy import deepcopy
import json

import pytest

from application.dataset_collection import DatasetCollection
from application.excel_import import ExcelImportService
from domain import ContractError, Diagnostic
from test_xlsx_reader import MAIN, fixture_zip


@pytest.fixture
def service(tmp_path):
    sheet = f"""<worksheet xmlns="{MAIN}"><sheetData>
        <row r="1"><c r="B1" t="inlineStr"><is><t>H</t></is></c>
                   <c r="C1" t="inlineStr"><is><t>He</t></is></c></row>
        <row r="2"><c r="A2"><v>0</v></c><c r="B2"><v>0</v></c></row>
        <row r="3"><c r="A3"><v>5</v></c><c r="B3"><v>2</v></c><c r="C3"><v>3</v></c></row>
        </sheetData></worksheet>"""
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(fixture_zip(**{"sheets/value sheet.xml": sheet, "sheets/empty.xml": sheet}))
    return ExcelImportService(path)


def _preview(service, sheet="Values"):
    return service.preview(sheet, "B1:C1", "A2:A3", "B2:C3", "matrix_rows")


def test_select_and_edit_each_group_without_changing_source(service):
    collection = DatasetCollection()
    assert collection.active_dataset_id is None
    assert collection.effective_data() == {}
    preview = _preview(service)
    first, second = collection.append(preview)
    assert collection.active_dataset_id == first
    assert collection.effective_data() == {"H": 0}
    edit = {"H": "001", "Li": 7}
    collection.set_manual_data(edit)
    edit["H"] = "changed by caller"
    assert collection.effective_data() == {"H": "001", "Li": 7}

    collection.select(second)
    assert collection.effective_data() == {"H": 2, "He": 3}
    collection.set_manual_data({})
    assert collection.effective_data() == {}
    collection.select(first)
    assert collection.effective_data() == {"H": "001", "Li": 7}
    assert collection.snapshot()["datasets"] == preview["datasets"]
    collection.set_manual_data(None)
    assert collection.effective_data() == {"H": 0}
    assert collection.effective_data(second) == {}


def test_round_trip_preserves_all_objects_and_detaches_mutable_data(service):
    collection = DatasetCollection()
    preview = _preview(service)
    _, second = collection.append(preview)
    collection.select(second)
    collection.set_manual_data({"He": 9})
    saved = json.loads(json.dumps(collection.snapshot(), allow_nan=False))
    assert saved["mappings"] == [preview["mapping"]]
    for name in ("datasets", "conditions", "metrics", "sources"):
        assert saved[name] == preview[name]
    restored = DatasetCollection.from_snapshot(saved)
    assert restored.snapshot() == saved
    assert restored.active_dataset_id == second
    assert restored.effective_data() == {"He": 9}

    preview["conditions"][0]["attributes"].clear()
    saved["datasets"][0]["records"].clear()
    saved["manual_data"][second].clear()
    detached = restored.snapshot()
    detached["sources"][0]["fingerprint"].clear()
    returned_data = restored.effective_data()
    returned_data.clear()
    assert restored.snapshot() == collection.snapshot()
    assert restored.effective_data() == {"He": 9}
    assert DatasetCollection.from_snapshot(DatasetCollection().snapshot()).effective_data() == {}


def test_append_second_sheet_reuses_only_identical_source(service):
    collection = DatasetCollection()
    first, _ = collection.append(_preview(service))
    hidden = _preview(service, "Hidden")
    new_ids = collection.append(hidden)
    assert collection.active_dataset_id == first
    assert len(collection.snapshot()["sources"]) == 1
    assert len(collection.snapshot()["datasets"]) == 4
    collection.select(new_ids[-1])
    assert collection.effective_data() == {"H": 2, "He": 3}


@pytest.mark.parametrize(("damage", "code"), [
    ("duplicate_dataset", "ID_DUPLICATE"),
    ("duplicate_source", "ID_DUPLICATE"),
    ("conflicting_source", "ID_DUPLICATE"),
    ("bad_condition", "REFERENCE_INVALID"),
    ("bad_metric", "REFERENCE_INVALID"),
    ("bad_source", "REFERENCE_INVALID"),
    ("bad_hash", "REFERENCE_INVALID"),
    ("bad_activation", "REFERENCE_INVALID"),
    ("error_diagnostic", "IMPORT_BLOCKED"),
])
def test_rejected_append_is_atomic(service, damage, code):
    collection = DatasetCollection()
    collection.append(_preview(service))
    collection.set_manual_data({"H": 4})
    before = collection.snapshot()
    incoming = _preview(service, "Hidden")
    activate = None
    dataset = incoming["datasets"][0]
    if damage == "duplicate_dataset":
        dataset["id"] = before["datasets"][0]["id"]
    elif damage == "duplicate_source":
        incoming["sources"].append(deepcopy(incoming["sources"][0]))
    elif damage == "conflicting_source":
        incoming["sources"][0]["locator"] = None
    elif damage in ("bad_condition", "bad_metric"):
        dataset[damage.removeprefix("bad_") + "_id"] = "missing"
    elif damage == "bad_source":
        incoming["mapping"]["source_id"] = "missing"
    elif damage == "bad_hash":
        incoming["sources"] = []
        incoming["source_hash"] = "f" * 64
        for item in incoming["datasets"]:
            item["provenance"]["source_hash"] = incoming["source_hash"]
    elif damage == "bad_activation":
        activate = before["active_dataset_id"]
    else:
        incoming["diagnostics"].append(Diagnostic("CELL_ERROR", "error", "Bad cell").to_dict())

    with pytest.raises(ContractError) as error:
        collection.append(incoming, activate)
    assert error.value.code == code
    assert collection.snapshot() == before


def test_explicit_activation_and_invalid_selection(service):
    collection = DatasetCollection()
    preview = _preview(service)
    second = preview["datasets"][1]["id"]
    collection.append(preview, activate_dataset_id=second)
    for action in (lambda: collection.select("missing"),
                   lambda: collection.effective_data("missing"),
                   lambda: collection.set_manual_data({"H": float("nan")})):
        with pytest.raises(ContractError):
            action()
    assert collection.active_dataset_id == second
    assert collection.effective_data() == {"H": 2, "He": 3}


@pytest.mark.parametrize("damage", ["unknown_field", "duplicate", "active", "edit", "cell_source", "error_cell"])
def test_from_snapshot_rejects_malformed_data(service, damage):
    collection = DatasetCollection()
    collection.append(_preview(service))
    snapshot = collection.snapshot()
    value = snapshot["datasets"][0]["records"]["H"]["value"]
    if damage == "unknown_field":
        snapshot["extra"] = True
    elif damage == "duplicate":
        snapshot["conditions"].append(snapshot["conditions"][0])
    elif damage == "active":
        snapshot["active_dataset_id"] = None
    elif damage == "edit":
        snapshot["manual_data"]["missing"] = {"H": 1}
    elif damage == "cell_source":
        value["source"]["source_id"] = "missing"
    else:
        value.update(kind="error", numeric=None)
    with pytest.raises(ContractError):
        DatasetCollection.from_snapshot(snapshot)
