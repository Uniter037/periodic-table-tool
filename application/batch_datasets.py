"""Prepare dataset collection snapshots for batch rendering."""
from __future__ import annotations

import re
from sys import float_info
from unicodedata import normalize
import warnings

from domain._validation import require, string

from .excel_import import legacy_data


_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\ud800-\udfff]')
_DEVICE_NAME = re.compile(r"CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³]", re.I)
# At most 240 UTF-16 code units, leaving room for the output extension.
_MAX_STEM = 120


def _selected_datasets(snapshot, dataset_ids):
    datasets = {}
    for dataset in snapshot["datasets"]:
        key = dataset["id"]
        string(key, "dataset ID", nonempty=True)
        require(key not in datasets, f"Duplicate dataset ID: {key}", "ID_DUPLICATE")
        datasets[key] = dataset

    require(not isinstance(dataset_ids, (str, bytes)), "Expected a sequence of dataset IDs")
    ids = list(datasets if dataset_ids is None else dataset_ids)
    require(bool(ids), "Select at least one dataset", "EMPTY_DATASET")
    seen = set()
    for key in ids:
        string(key, "selected dataset ID", nonempty=True, code="REFERENCE_INVALID")
        require(key in datasets, f"Unknown dataset ID: {key}", "REFERENCE_INVALID")
        require(key not in seen, f"Duplicate selected dataset ID: {key}", "ID_DUPLICATE")
        seen.add(key)
    return [datasets[key] for key in ids]


def _effective_data(snapshot, dataset):
    edits = snapshot["manual_data"]
    key = dataset["id"]
    return dict(edits[key]) if key in edits else legacy_data(dataset)


def _finite_number(value):
    return type(value) in (int, float) and -float_info.max <= value <= float_info.max


def _unique_name(metric, condition, used):
    parts = [_UNSAFE_NAME.sub("_", normalize("NFC", part)).strip(" .")
             for part in (metric, condition)]
    base = (" - ".join(filter(None, parts)) or "dataset")[:_MAX_STEM].rstrip(" .")
    if _DEVICE_NAME.fullmatch(base.split(".", 1)[0].rstrip(" ")):
        base = "_" + base
    name = base[:_MAX_STEM].rstrip(" .")
    index = 2
    while name.casefold() in used:
        suffix = f" ({index})"
        name = base[:_MAX_STEM - len(suffix)].rstrip(" .") + suffix
        index += 1
    used.add(name.casefold())
    return name


def plan_dataset_batch(collection_snapshot, dataset_ids=None) -> list[tuple[str, dict]]:
    """Return detached RenderJob items in selection order (snapshot order by default)."""
    datasets = _selected_datasets(collection_snapshot, dataset_ids)
    metrics = {metric["id"]: metric for metric in collection_snapshot["metrics"]}
    conditions = {condition["id"]: condition for condition in collection_snapshot["conditions"]}
    items = []
    used = set()
    for dataset in datasets:
        data = _effective_data(collection_snapshot, dataset)
        key = dataset["id"]
        require(bool(data), f"Dataset {key} has no render data", "EMPTY_DATASET")
        for symbol, value in data.items():
            require(type(value) is str or _finite_number(value),
                    f"Dataset {key} has an invalid render value for {symbol}", "VALUE_INVALID")
        metric = metrics[dataset["metric_id"]]["name"]
        condition = conditions[dataset["condition_id"]]["label"]
        items.append((_unique_name(metric, condition, used), data))
    return items


def group_ranges(collection_snapshot, dataset_ids=None) -> dict[str, tuple[float, float]]:
    """Return exact bounds per metric for a unit-compatible selection.

    Omit metrics without finite numbers. Constant metrics retain equal bounds
    and emit a warning so callers can choose how to display them.
    """
    datasets = _selected_datasets(collection_snapshot, dataset_ids)
    metrics = {metric["id"]: metric for metric in collection_snapshot["metrics"]}
    ranges = {}
    for dataset in datasets:
        values = [value for value in _effective_data(collection_snapshot, dataset).values()
                  if _finite_number(value)]
        if values:
            key = dataset["metric_id"]
            low, high = min(values), max(values)
            if key in ranges:
                old_low, old_high = ranges[key]
                low, high = min(old_low, low), max(old_high, high)
            ranges[key] = low, high

    units = {metrics[key].get("unit") for key in ranges}
    require(len(units) <= 1, "Cannot share a range across mixed units", "UNIT_MISMATCH")
    for key, (low, high) in ranges.items():
        if low == high:
            warnings.warn(f"Metric {key} has a constant range ({low})", stacklevel=2)
    return ranges
