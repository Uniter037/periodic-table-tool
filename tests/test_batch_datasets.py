from copy import deepcopy

import pytest

from application.batch_datasets import group_ranges, plan_dataset_batch
from application.dataset_collection import DatasetCollection
from domain import ContractError
from test_dataset_collection import _preview, service


@pytest.fixture
def snapshot(service):
    collection = DatasetCollection()
    collection.append(_preview(service))
    return collection.snapshot()


def _ids(snapshot):
    return [dataset["id"] for dataset in snapshot["datasets"]]


def test_render_items_use_per_group_edits_and_selection_order(snapshot):
    first, second = _ids(snapshot)
    snapshot["manual_data"][second] = {"Li": -3, "He": "001"}
    original = deepcopy(snapshot)

    items = plan_dataset_batch(snapshot, [second, first])
    assert [data for _, data in items] == [{"Li": -3, "He": "001"}, {"H": 0}]
    assert plan_dataset_batch(snapshot) == items[::-1]
    items[0][1].clear()
    assert snapshot == original


@pytest.mark.parametrize("manual", [True, False])
def test_empty_group_is_rejected(snapshot, manual):
    first, second = _ids(snapshot)
    if manual:
        snapshot["manual_data"][first] = {}
    else:
        snapshot["datasets"][0]["records"].clear()
    with pytest.raises(ContractError, match="no render data"):
        plan_dataset_batch(snapshot, [first])
    assert plan_dataset_batch(snapshot, [second])[0][1] == {"H": 2, "He": 3}


@pytest.mark.parametrize("planner", [plan_dataset_batch, group_ranges])
def test_selection_validates_missing_duplicate_and_empty_ids(snapshot, planner):
    first, _ = _ids(snapshot)
    for ids, code in [(["unknown"], "REFERENCE_INVALID"),
                      ([first, first], "ID_DUPLICATE"), ([], "EMPTY_DATASET")]:
        with pytest.raises(ContractError) as error:
            planner(snapshot, ids)
        assert error.value.code == code

    snapshot["datasets"].append(deepcopy(snapshot["datasets"][0]))
    with pytest.raises(ContractError, match="Duplicate dataset ID"):
        planner(snapshot)


def test_names_are_readable_and_unique_with_unicode_and_case(snapshot):
    snapshot["metrics"][0]["name"] = "晶格/Å"
    snapshot["conditions"][0]["label"] = '室温: Café* .'
    snapshot["conditions"][1]["label"] = '室温: CAFE\u0301?'
    names = [name for name, _ in plan_dataset_batch(snapshot)]
    assert names == ["晶格_Å - 室温_ Café_", "晶格_Å - 室温_ CAFÉ_ (2)"]


@pytest.mark.parametrize("device", ["CON", "lPt9", "COM¹", "CONOUT$"])
def test_device_names_before_a_dot_are_prefixed(snapshot, device):
    snapshot["metrics"][0]["name"] = f"{device}.分组"
    assert all(name.startswith(f"_{device}.") for name, _ in plan_dataset_batch(snapshot))


def test_long_names_leave_room_for_extension_and_suffix(snapshot):
    snapshot["metrics"][0]["name"] = "🔬" * 300
    names = [name for name, _ in plan_dataset_batch(snapshot)]
    assert names[1].endswith(" (2)")
    assert all(len((name + ".png").encode("utf-16-le")) // 2 <= 255 for name in names)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True])
def test_ranges_skip_non_numeric_values_and_batch_rejects_invalid_values(snapshot, invalid):
    _, second = _ids(snapshot)
    metric = snapshot["metrics"][0]["id"]
    snapshot["manual_data"][second] = {"H": invalid, "He": -5, "Li": "200"}
    assert group_ranges(snapshot) == {metric: (-5, 0)}
    with pytest.raises(ContractError, match="invalid render value"):
        plan_dataset_batch(snapshot)


def test_constant_zero_range_keeps_exact_bounds_and_warns(snapshot):
    first, second = _ids(snapshot)
    metric = snapshot["metrics"][0]["id"]
    snapshot["manual_data"][second] = {"H": "200"}
    assert group_ranges(snapshot, [second]) == {}
    with pytest.warns(UserWarning, match="constant range"):
        assert group_ranges(snapshot, [first, second]) == {metric: (0, 0)}


def test_ranges_group_by_metric_id_and_reject_mixed_units(snapshot):
    first, second = _ids(snapshot)
    metric = snapshot["metrics"][0]
    metric["unit"] = "eV"
    other = {**metric, "id": "other"}
    snapshot["metrics"].append(other)
    snapshot["datasets"][1]["metric_id"] = other["id"]
    snapshot["manual_data"][first] = {"H": 0, "He": 1}

    assert group_ranges(snapshot) == {metric["id"]: (0, 1), "other": (2, 3)}
    other["unit"] = "K"
    with pytest.raises(ContractError, match="mixed units"):
        group_ranges(snapshot, [second, first])
    assert len(plan_dataset_batch(snapshot)) == 2
