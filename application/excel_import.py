"""Preview explicit Excel matrix selections for the import dialog."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from os import fstat
from pathlib import Path
from uuid import uuid4

from domain import (
    CellRef, ContractError, Dataset, Diagnostic, DiagnosticTarget, ElementRecord,
    ImportMapping, Provenance,
)
from domain.data import _SYMBOLS
from infrastructure.readers import XlsxReader, XlsxReadError


_ROLES = ("elements", "conditions", "values")


def _id():
    return uuid4().hex


def _read_error_code(exc):
    # XlsxReadError has no structured code; use its specific reader messages
    # and the underlying I/O exception where the reader wraps one.
    message = str(exc)
    if "exceeds budget" in message or "exceeds cell budget" in message:
        return "READ_LIMIT_EXCEEDED"
    if message == "Non-finite XLSX numeric value":
        return "NON_FINITE_NUMBER"
    if message == "Worksheet not found":
        return "SHEET_NOT_FOUND"
    if message.startswith("XLSX source changed"):
        return "SOURCE_CHANGED"
    if isinstance(exc.__cause__, OSError):
        return "SOURCE_UNREADABLE"
    return "SOURCE_INVALID"


class ExcelImportService:
    """Read-only service for matrix previews; the caller owns any commit."""

    def __init__(self, path):
        self._path = Path(path).absolute()
        self._reader = XlsxReader()
        self._source_id = _id()
        summary = self._reader.inspect(self._path, self._source_id)
        self._sheets = tuple(sheet.name for sheet in summary.sheets)

    @property
    def sheets(self) -> list[str]:
        return list(self._sheets)

    def _fingerprint(self):
        digest = sha256()
        size = 0
        with self._path.open("rb") as stream:
            modified_at = fstat(stream.fileno()).st_mtime
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > self._reader.limits.max_file_bytes:
                    raise ContractError("Excel 文件超过读取上限。", "READ_LIMIT_EXCEEDED")
                digest.update(chunk)
        return digest.hexdigest(), size, modified_at

    def preview(self, sheet, elements_range, conditions_range, values_range, direction) -> dict:
        mapping_id = _id()
        diagnostics = []
        stats = dict.fromkeys((
            "dataset_count", "record_count", "number_count", "text_count",
            "missing_count", "error_count", "skipped_blank_count",
        ), 0)
        result = {
            "preview_id": _id(), "status": "invalid", "base_revision": 0,
            "source_hash": None, "mapping_hash": None, "mapping": None,
            "datasets": [], "conditions": [], "metrics": [], "sources": [],
            "diagnostics": diagnostics, "stats": stats,
        }

        def report(code, message, role=None, locations=(), severity="error", remedy=None):
            path = f"/regions/{role}" if role else "/regions"
            target = DiagnosticTarget("mapping", mapping_id, path)
            diagnostics.append(Diagnostic(
                code, severity, message, list(locations), target, remedy,
            ).to_dict())

        if direction not in ("matrix_rows", "matrix_columns"):
            report("MAPPING_INVALID", "请选择按行或按列导入。")
            return result
        if sheet not in self._sheets:
            report("SHEET_NOT_FOUND", "找不到所选工作表。")
            return result

        regions = {
            role: {"sheet": sheet, "range": area.strip().upper() if isinstance(area, str) else area}
            for role, area in zip(_ROLES, (elements_range, conditions_range, values_range))
        }
        try:
            mapping = ImportMapping.from_dict({
                "id": mapping_id, "source_id": self._source_id, "schema_version": 1,
                "layout": direction, "regions": regions,
                "metric": {"name": sheet, "value_kind": "numeric"},
                "condition": {"name": "条件"},
            })
        except ContractError as exc:
            report(exc.code, str(exc))
            return result

        # The public reader takes paths, not XLSX bytes. Each read hashes its
        # own immutable snapshot; bracket all three reads with independent hashes.
        role = None
        try:
            before, size, modified_at = self._fingerprint()
            grids = {}
            read_error = None
            for role, region in regions.items():
                try:
                    grid = self._reader.read_region(
                        self._path, sheet, region["range"], self._source_id,
                    )
                except XlsxReadError as exc:
                    read_error = exc
                    break
                if grid.source_hash != before:
                    raise ContractError("读取选区时 Excel 文件已变化，请重新预览。", "SOURCE_CHANGED")
                grids[role] = grid
            after, _, _ = self._fingerprint()
            if before != after:
                raise ContractError("读取选区时 Excel 文件已变化，请重新预览。", "SOURCE_CHANGED")
            if read_error is not None:
                raise read_error
        except ContractError as exc:
            report(exc.code, str(exc), role)
            return result
        except XlsxReadError as exc:
            report(_read_error_code(exc), "无法读取 Excel 选区，请检查文件和范围。", role)
            return result
        except OSError:
            report("SOURCE_UNREADABLE", "无法读取 Excel 文件，请重新选择文件。", role)
            return result

        result["source_hash"] = before
        result["sources"].append({
            "id": self._source_id, "kind": "xlsx", "display_name": self._path.name,
            "locator": str(self._path),
            "fingerprint": {"sha256": before, "size": size, "mtime": modified_at},
        })

        # Infer a text metric only when the selection has text and no numbers.
        # Mixed data is a numeric metric with explicit errors at text cells.
        kinds = {cell.kind for row in grids["values"].cells for cell in row}
        value_kind = "text" if "text" in kinds and "number" not in kinds else "numeric"
        mapping = replace(
            mapping, regions={
                role: {"sheet": sheet, "range": grid.region.range}
                for role, grid in grids.items()
            },
            metric={**mapping.metric, "value_kind": value_kind},
        )
        result["mapping"] = mapping.to_dict()
        result["mapping_hash"] = sha256(json.dumps(
            result["mapping"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()

        merged = False
        for role, grid in grids.items():
            if grid.merged_ranges:
                merged = True
                report("MERGED_REGION_UNSUPPORTED", "所选区域与合并单元格相交。", role,
                       (CellRef(self._source_id, sheet, area.split(":")[0])
                        for area in grid.merged_ranges))
            if grid.hidden_rows or grid.hidden_columns:
                report("HIDDEN_INCLUDED", "已包含选区中的隐藏行或列。", role, severity="info")
            cached = []
            for row in grid.cells:
                for cell in row:
                    if cell.kind == "error":
                        if cell.formula is not None and cell.cached is None:
                            report("FORMULA_CACHE_MISSING", "公式没有已保存的计算结果。", role,
                                   [cell.source], remedy="请在 Excel 中重新计算并保存。")
                        else:
                            report("CELL_ERROR", "单元格包含 Excel 错误。", role, [cell.source])
                    elif cell.formula is not None:
                        cached.append(cell.source)
            if cached:
                report("FORMULA_CACHE_USED", "使用已保存的公式结果，结果可能未刷新。",
                       role, cached, severity="warning")
        if merged:
            return result

        rows = direction == "matrix_rows"
        elements = grids["elements"].cells
        elements = elements[0] if rows else [row[0] for row in elements]
        conditions = grids["conditions"].cells
        conditions = [row[0] for row in conditions] if rows else conditions[0]
        values = grids["values"].cells
        groups = values if rows else list(zip(*values))

        element_indices = {}
        blank_indices = []
        for index, cell in enumerate(elements):
            if cell.kind == "error":
                continue
            if cell.kind == "missing":
                blank_indices.append(index)
            elif cell.kind != "text" or cell.raw_text not in _SYMBOLS:
                report("ELEMENT_UNKNOWN", "元素标签不是规范元素符号。", "elements", [cell.source])
            else:
                element_indices.setdefault(cell.raw_text, []).append(index)
        for indices in element_indices.values():
            if len(indices) > 1:
                report("ELEMENT_DUPLICATE", "同一组中出现重复的元素标签。", "elements",
                       [elements[index].source for index in indices])

        metric = {"id": _id(), **mapping.metric}
        result["metrics"].append(metric)
        provenance = Provenance(
            mapping_id, before, "import-v1",
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        expected = "number" if value_kind == "numeric" else "text"
        for condition_cell, group in zip(conditions, groups):
            label = condition_cell.raw_text
            if condition_cell.kind == "number":
                label = str(condition_cell.numeric)
            if condition_cell.kind in ("missing", "text") and (label is None or not label.strip()):
                report("CONDITION_MISSING", "条件标签为空。", "conditions", [condition_cell.source])
            condition = {
                "id": _id(), "label": label if label and label.strip() else condition_cell.source.address,
                "attributes": {mapping.condition["name"]: condition_cell.to_dict()},
            }
            result["conditions"].append(condition)

            checked = []
            for cell in group:
                if cell.kind not in (expected, "missing", "error"):
                    report("VALUE_KIND_MISMATCH", "单元格类型与指标类型不符。", "values", [cell.source])
                    cell = replace(cell, kind="error", numeric=None)
                checked.append(cell)
            for index in blank_indices:
                cell = checked[index]
                if cell.kind == "missing":
                    stats["skipped_blank_count"] += 1
                else:
                    report("ELEMENT_MISSING", "值存在，但缺少对应的元素标签。", "elements",
                           [elements[index].source, cell.source])

            # Invalid previews retain the first representable record for a
            # duplicate symbol; diagnostics point to every conflicting label.
            records = {
                symbol: ElementRecord(symbol, checked[indices[0]])
                for symbol, indices in element_indices.items()
            }
            if records:
                dataset = Dataset(_id(), metric["id"], condition["id"], records, provenance)
                result["datasets"].append(dataset.to_dict())
                stats["dataset_count"] += 1
                stats["record_count"] += len(records)
                for record in records.values():
                    stats[f"{record.value.kind}_count"] += 1

        if not result["datasets"]:
            report("EMPTY_DATASET", "选区中没有可导入的元素记录。")
        if not any(item["severity"] == "error" for item in diagnostics):
            result["status"] = "ready"
        return result


def legacy_data(dataset: dict | Dataset) -> dict:
    """Adapt a dataset for render_table, omitting missing cells."""
    if isinstance(dataset, Dataset):
        dataset = dataset.to_dict()
    data = {}
    for symbol, record in dataset["records"].items():
        value = record["value"]
        if value["kind"] == "number":
            data[symbol] = value["numeric"]
        elif value["kind"] == "text":
            data[symbol] = value["raw_text"]
        elif value["kind"] != "missing":
            raise ValueError("Cannot render a dataset containing error cells")
    return data
