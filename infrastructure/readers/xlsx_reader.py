"""Read XLSX parts from one immutable byte snapshot, without evaluating formulas."""
from __future__ import annotations

import hashlib
import io
import math
import os
import posixpath
import re
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from domain.data import CellRef, CellValue


class XlsxReadError(ValueError):
    """Invalid/unsupported workbook, range, or configured budget violation."""


@dataclass(frozen=True)
class ReaderLimits:
    max_file_bytes: int = 50 * 1024**2
    max_uncompressed_bytes: int = 500 * 1024**2
    max_zip_entries: int = 10_000
    max_region_cells: int = 1_000_000

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("XLSX reader limits must be positive integers")


@dataclass(frozen=True)
class Region:
    sheet: str
    range: str


@dataclass(frozen=True)
class FormulaMetadata:
    address: str
    attributes: tuple[tuple[str, str], ...]
    # None for a shared-formula follower without stored expression text.
    stored_text: str | None


@dataclass(frozen=True)
class CellGrid:
    """Dense row-major grid. All metadata uses absolute Excel coordinates.

    Hidden axes are clipped to the selection; merged ranges are full ranges
    intersecting it. Column intervals are inclusive, one-based column numbers.
    A formula marker of "=" means the cell stores no expression of its own;
    its OOXML formula attributes (e.g. shared index) are in formula_metadata.
    """
    region: Region
    source_hash: str
    cells: tuple[tuple[CellValue, ...], ...]
    hidden_rows: tuple[int, ...]
    hidden_columns: tuple[tuple[int, int], ...]
    merged_ranges: tuple[str, ...]
    formula_metadata: tuple[FormulaMetadata, ...]
    # Preserves IDs even for locale-dependent built-ins with no portable code.
    number_format_ids: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class SheetSummary:
    name: str
    physical_bounds: str | None
    nonempty_candidates: tuple[str, ...]
    hidden_state: str


@dataclass(frozen=True)
class WorkbookSummary:
    source_id: str
    source_hash: str
    sheets: tuple[SheetSummary, ...]


_MAX_ROW, _MAX_COL = 1_048_576, 16_384
_A1 = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})", re.ASCII)
_MAIN = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/spreadsheetml/main",
)
_OFFICE_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/",
    "http://purl.oclc.org/ooxml/officeDocument/relationships/",
)
_PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_BUILTIN_FORMATS = {
    0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00",
    5: '"$"#,##0_);("$"#,##0)', 6: '"$"#,##0_);[Red]("$"#,##0)',
    7: '"$"#,##0.00_);("$"#,##0.00)', 8: '"$"#,##0.00_);[Red]("$"#,##0.00)',
    9: "0%", 10: "0.00%", 11: "0.00E+00", 12: "# ?/?", 13: "# ??/??",
    14: "mm-dd-yy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy",
    18: "h:mm AM/PM", 19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss",
    22: "m/d/yy h:mm", 37: "#,##0 ;(#,##0)", 38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)",
    41: '_(* #,##0_);_(* (#,##0);_(* "-"_);_(@_)',
    42: '_("$"* #,##0_);_("$"* (#,##0);_("$"* "-"_);_(@_)',
    43: '_(* #,##0.00_);_(* (#,##0.00);_(* "-"??_);_(@_)',
    44: '_("$"* #,##0.00_);_("$"* (#,##0.00);_("$"* "-"??_);_(@_)',
    45: "mm:ss", 46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@",
}


def _coordinate(address):
    match = _A1.fullmatch(address)
    if not match:
        raise XlsxReadError("Expected an Excel A1 address")
    col = 0
    for letter in match[1]:
        col = col * 26 + ord(letter) - 64
    row = int(match[2])
    if row > _MAX_ROW or col > _MAX_COL:
        raise XlsxReadError("Address exceeds Excel worksheet bounds")
    return row, col


def _bounds(address):
    start, sep, end = address.partition(":")
    r1, c1 = _coordinate(start)
    r2, c2 = _coordinate(end) if sep else (r1, c1)
    if r2 < r1 or c2 < c1:
        raise XlsxReadError("Reversed A1 range")
    return r1, c1, r2, c2


def _column(col):
    name = ""
    while col:
        col, rem = divmod(col - 1, 26)
        name = chr(65 + rem) + name
    return name


def _range(r1, c1, r2, c2):
    first, last = f"{_column(c1)}{r1}", f"{_column(c2)}{r2}"
    return first if first == last else f"{first}:{last}"


class _SafeXml:
    """Reject DTDs before Expat sees them; XLSX XML parts use UTF-8 here."""

    def __init__(self, stream):
        self.stream = stream
        self.tail = b""

    def read(self, size):
        block = self.stream.read(size)
        window = self.tail + block
        if b"\x00" in block or b"<!DOCTYPE" in window:
            raise XlsxReadError("Unsupported XML encoding or DTD in XLSX")
        self.tail = window[-8:]
        return block


def _records(zip_file, part, root, paths, namespaces=_MAIN):
    """Yield selected subtrees, discarding completed siblings as we stream."""
    with zip_file.open(part) as stream:
        stack = []
        namespace = None
        keep_depth = None
        for event, element in ET.iterparse(_SafeXml(stream), events=("start", "end")):
            if event == "start":
                if not stack:
                    namespace = next((ns for ns in namespaces
                                      if element.tag == f"{{{ns}}}{root}"), None)
                    if namespace is None:
                        raise XlsxReadError(f"Unexpected XML root; expected {root}")
                stack.append(element)
                if keep_depth is None and 1 < len(stack) <= 4:
                    prefix = f"{{{namespace}}}"
                    tags = tuple(node.tag[len(prefix):] if node.tag.startswith(prefix)
                                 else None for node in stack[1:])
                    if tags in paths:
                        keep_depth = len(stack)
                continue
            if keep_depth == len(stack):
                yield element, namespace
                keep_depth = None
            if keep_depth is None and len(stack) > 1:
                stack[-2].remove(element)
            stack.pop()


def _relationships(zip_file, rels_path):
    rels = {}
    for item, _ in _records(zip_file, rels_path, "Relationships",
                            {("Relationship",)}, (_PACKAGE_REL,)):
        rel_id = item.attrib["Id"]
        if not rel_id or rel_id in rels:
            raise XlsxReadError("Duplicate or empty XLSX relationship ID")
        rels[rel_id] = (item.attrib["Type"], item.attrib["Target"],
                        item.get("TargetMode", "Internal"))
    return rels


def _rel_type(value, name):
    return any(value == prefix + name for prefix in _OFFICE_REL)


def _part(base, relationship):
    _, target, mode = relationship
    uri = urlsplit(target)
    path = unquote(uri.path)
    if (mode != "Internal" or not path or uri.scheme or uri.netloc or uri.query
            or uri.fragment or "\\" in path or "\x00" in path):
        raise XlsxReadError("Invalid internal XLSX relationship target")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), path)).lstrip("/")
    if path in ("", ".", "..") or path.startswith("../"):
        raise XlsxReadError("XLSX relationship escapes the package")
    return path


def _rich_text(item, ns):
    text = f"{{{ns}}}t"
    run = f"{{{ns}}}r"
    plain = item.find(text)
    if plain is not None:
        return plain.text or ""
    return "".join(node.text or "" for child in item.iterfind(run)
                   for node in child.iterfind(text))


def _number(raw):
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", raw):
        raise XlsxReadError("Invalid XLSX numeric value")
    if len(raw) < 20 and raw.lstrip("+-").isdigit():
        return int(raw)
    value = float(raw)
    if not math.isfinite(value):
        raise XlsxReadError("Non-finite XLSX numeric value")
    return value


def _cell(item, ns, ref, format_code, shared):
    def find(tag):
        return item.find(f"{{{ns}}}{tag}")

    f, v, inline = find("f"), find("v"), find("is")
    raw = v.text if v is not None else None
    cell_type = item.get("t", "n")
    if cell_type not in ("n", "s", "inlineStr", "str", "b", "d", "e"):
        raise XlsxReadError("Unsupported XLSX cell type")
    numeric = cached = None
    if cell_type == "inlineStr" and inline is not None:
        kind, raw = "text", _rich_text(inline, ns)
        cached = raw
    elif cell_type == "str" and v is not None:
        kind, raw = "text", raw or ""
        cached = raw
    elif raw is None:
        kind = "error" if f is not None else "missing"
    elif cell_type == "n":
        kind, numeric = "number", _number(raw)
        cached = numeric
    elif cell_type == "s":
        kind, raw = "text", shared(raw)
        cached = raw
    elif cell_type == "b":
        if raw not in ("0", "1", "false", "true"):
            raise XlsxReadError("Invalid XLSX boolean")
        kind, cached = "text", raw in ("1", "true")
        raw = "TRUE" if cached else "FALSE"
    elif cell_type == "e":
        kind, cached = "error", raw
    else:
        kind, cached = "text", raw
    formula = None
    if f is not None:
        formula = f.text or "="
        if not formula.startswith("="):
            formula = "=" + formula
    else:
        cached = None
    return CellValue(kind, raw, numeric, formula, cached, format_code, ref), f


def _row_cells(row, ns, row_number):
    col = 0
    for item in row.iterfind(f"{{{ns}}}c"):
        address = item.get("r")
        if address is None:
            col += 1
            if col > _MAX_COL:
                raise XlsxReadError("Cell exceeds Excel worksheet bounds")
        else:
            actual_row, actual_col = _coordinate(address)
            if actual_row != row_number or actual_col <= col:
                raise XlsxReadError("Out-of-order or duplicate XLSX cell")
            col = actual_col
        yield col, item


def _row_number(item, previous):
    row = int(item.get("r", previous + 1))
    if not previous < row <= _MAX_ROW:
        raise XlsxReadError("Invalid or out-of-order XLSX row")
    return row


class _Workbook:
    def __init__(self, zip_file):
        self.zip = zip_file
        roots = [rel for rel in _relationships(zip_file, "_rels/.rels").values()
                 if _rel_type(rel[0], "officeDocument")]
        if len(roots) != 1:
            raise XlsxReadError("Expected one workbook part")
        part = _part("", roots[0])
        rels_path = posixpath.join(posixpath.dirname(part), "_rels",
                                   posixpath.basename(part) + ".rels")
        rels = _relationships(zip_file, rels_path)
        self.styles = self.strings = None
        for rel in rels.values():
            for name, attr in (("styles", "styles"), ("sharedStrings", "strings")):
                if _rel_type(rel[0], name):
                    if getattr(self, attr) is not None:
                        raise XlsxReadError(f"Duplicate XLSX {name} part")
                    setattr(self, attr, _part(part, rel))
        self.sheets = {}
        names = set()
        for sheet, _ in _records(zip_file, part, "workbook", {("sheets", "sheet")}):
            name = sheet.attrib["name"]
            rel_id = next((sheet.get(f"{{{prefix[:-1]}}}id") for prefix in _OFFICE_REL
                           if f"{{{prefix[:-1]}}}id" in sheet.attrib), None)
            rel = rels[rel_id]
            state = sheet.get("state", "visible")
            if not name or name.casefold() in names or state not in ("visible", "hidden", "veryHidden"):
                raise XlsxReadError("Invalid XLSX sheet name or state")
            names.add(name.casefold())
            if _rel_type(rel[0], "worksheet"):
                target = _part(part, rel)
                zip_file.getinfo(target)
                self.sheets[name] = (target, state)
        if not names:
            raise XlsxReadError("Workbook has no sheets")

    def formats(self):
        formats = dict(_BUILTIN_FORMATS)
        styles, parents, cells = [], [], []
        if self.styles:
            for group, ns in _records(self.zip, self.styles, "styleSheet", {
                ("numFmts",), ("cellStyleXfs",), ("cellXfs",),
            }):
                if group.tag == f"{{{ns}}}numFmts":
                    for element in group.iterfind(f"{{{ns}}}numFmt"):
                        formats[int(element.attrib["numFmtId"])] = element.attrib["formatCode"]
                elif group.tag == f"{{{ns}}}cellStyleXfs":
                    parents.extend(int(xf.get("numFmtId", "0")) for xf in group.iterfind(f"{{{ns}}}xf"))
                else:
                    cells.extend(xf.attrib for xf in group.iterfind(f"{{{ns}}}xf"))
            for xf in cells:
                fmt = int(xf.get("numFmtId", "0"))
                if xf.get("xfId") is not None and (
                    xf.get("applyNumberFormat") in ("0", "false") or "numFmtId" not in xf
                ):
                    index = int(xf["xfId"])
                    if not 0 <= index < len(parents):
                        raise XlsxReadError("Invalid XLSX parent style index")
                    fmt = parents[index]
                styles.append(fmt)
        return formats, styles or [0]

    def shared_strings(self):
        if self.strings is None:
            raise XlsxReadError("Missing XLSX shared strings part")
        return [_rich_text(item, ns) for item, ns in
                _records(self.zip, self.strings, "sst", {("si",)})]


def _signature(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


class XlsxReader:
    """Read worksheet summaries and explicit A1 selections from local XLSX files."""

    def __init__(self, limits: ReaderLimits | None = None):
        self.limits = limits or ReaderLimits()

    @contextmanager
    def _open(self, path):
        try:
            path_before = _signature(os.stat(path))
            with open(path, "rb") as stream:
                before = _signature(os.fstat(stream.fileno()))
                if before[2] > self.limits.max_file_bytes:
                    raise XlsxReadError("XLSX file size exceeds budget")
                snapshot = stream.read(before[2] + 1)
                if len(snapshot) > self.limits.max_file_bytes:
                    raise XlsxReadError("XLSX file size exceeds budget")
                if (len(snapshot) != before[2] or before != _signature(os.fstat(stream.fileno()))
                        or before[:2] != path_before[:2]
                        or path_before != _signature(os.stat(path))):
                    raise XlsxReadError("XLSX source changed during snapshot; retry")
            source_hash = hashlib.sha256(snapshot).hexdigest()
            with ZipFile(io.BytesIO(snapshot)) as archive:
                members = archive.infolist()
                if len(members) > self.limits.max_zip_entries:
                    raise XlsxReadError("XLSX ZIP entry count exceeds budget")
                if sum(member.file_size for member in members) > self.limits.max_uncompressed_bytes:
                    raise XlsxReadError("XLSX uncompressed size exceeds budget")
                if len({member.filename for member in members}) != len(members):
                    raise XlsxReadError("Duplicate XLSX ZIP entry")
                yield _Workbook(archive), source_hash
        except XlsxReadError:
            raise
        except (OSError, BadZipFile, ET.ParseError, KeyError, ValueError, RuntimeError,
                EOFError, zlib.error) as exc:
            raise XlsxReadError("Invalid or unreadable XLSX workbook") from exc

    @staticmethod
    def _validate_source(source_id):
        if not isinstance(source_id, str) or not source_id.strip():
            raise XlsxReadError("source_id must be a nonempty string")

    def inspect(self, path, source_id: str) -> WorkbookSummary:
        """Summarize worksheets in workbook order; candidates cover A1:GR200."""
        self._validate_source(source_id)
        summaries = []
        with self._open(path) as (book, source_hash):
            for name, (part, state) in book.sheets.items():
                dimension = None
                candidates = []
                row = 0
                r1, c1, r2, c2 = _MAX_ROW, _MAX_COL, 0, 0
                with _closing_records(book.zip, part, "worksheet", {
                    ("dimension",), ("sheetData", "row"),
                }) as records:
                    for item, ns in records:
                        if item.tag == f"{{{ns}}}dimension":
                            dimension = _range(*_bounds(item.attrib["ref"]))
                            continue
                        row = _row_number(item, row)
                        if row > 200 and dimension is not None:
                            continue
                        tags = {f"{{{ns}}}{tag}" for tag in ("f", "v", "is")}
                        for col, cell in _row_cells(item, ns, row):
                            r1, c1, r2, c2 = min(r1, row), min(c1, col), row, max(c2, col)
                            if row <= 200 and col <= 200 and any(
                                child.tag in tags and (child.text is not None or
                                child.tag != f"{{{ns}}}v" or cell.get("t") == "str")
                                for child in cell
                            ):
                                candidates.append(f"{_column(col)}{row}")
                physical = dimension or (_range(r1, c1, r2, c2) if r2 else None)
                summaries.append(SheetSummary(name, physical, tuple(candidates), state))
        return WorkbookSummary(source_id, source_hash, tuple(summaries))

    def read_region(self, path, sheet: str, range: str, source_id: str) -> CellGrid:
        """Return all cells of a bounded, closed A1 selection (including blanks)."""
        self._validate_source(source_id)
        if (not isinstance(sheet, str) or not sheet or not isinstance(range, str)
                or not range.isascii() or len(range) > 21):
            raise XlsxReadError("Expected a worksheet name and A1 range")
        r1, c1, r2, c2 = _bounds(range.upper())
        if (r2 - r1 + 1) * (c2 - c1 + 1) > self.limits.max_region_cells:
            raise XlsxReadError("XLSX selection exceeds cell budget")
        with self._open(path) as (book, source_hash):
            if sheet not in book.sheets:
                raise XlsxReadError("Worksheet not found")
            part, _ = book.sheets[sheet]
            return _read_grid(book, part, Region(sheet, _range(r1, c1, r2, c2)),
                              source_id, source_hash, (r1, c1, r2, c2))


@contextmanager
def _closing_records(*args):
    records = _records(*args)
    try:
        yield records
    finally:
        records.close()


def _read_grid(book, part, region, source_id, source_hash, bounds):
    r1, c1, r2, c2 = bounds
    hidden_rows, hidden_columns, merges, formulas, format_ids = [], [], [], [], []
    rows = []
    row = 0
    formats, styles = book.formats()
    strings = None
    columns = tuple((col, _column(col)) for col in range(c1, c2 + 1))

    def shared(raw):
        nonlocal strings
        if strings is None:
            strings = book.shared_strings()
        index = int(raw)
        if not 0 <= index < len(strings):
            raise XlsxReadError("Invalid XLSX shared string index")
        return strings[index]

    def complete(row_number, values):
        return tuple(values[col] if col in values else CellValue(
            "missing", source=CellRef(source_id, region.sheet, f"{label}{row_number}")
        ) for col, label in columns)

    # Read to the end: mergeCells usually follows sheetData.
    with _closing_records(book.zip, part, "worksheet", {
        ("cols", "col"), ("sheetData", "row"), ("mergeCells", "mergeCell"),
    }) as records:
        for item, ns in records:
            tag = item.tag[len(ns) + 2:]
            if tag == "col":
                start, end = int(item.attrib["min"]), int(item.attrib["max"])
                if not 1 <= start <= end <= _MAX_COL:
                    raise XlsxReadError("Invalid XLSX column span")
                if item.get("hidden") in ("1", "true") and start <= c2 and end >= c1:
                    hidden_columns.append((max(start, c1), min(end, c2)))
            elif tag == "mergeCell":
                a, b, c, d = _bounds(item.attrib["ref"])
                if a <= r2 and c >= r1 and b <= c2 and d >= c1:
                    merges.append(_range(a, b, c, d))
            else:
                row = _row_number(item, row)
                if not r1 <= row <= r2:
                    continue
                if item.get("hidden") in ("1", "true"):
                    hidden_rows.append(row)
                values = {}
                for col, cell in _row_cells(item, ns, row):
                    if not c1 <= col <= c2:
                        continue
                    address = f"{columns[col - c1][1]}{row}"
                    style = int(cell.get("s", "0"))
                    if not 0 <= style < len(styles):
                        raise XlsxReadError("Invalid XLSX cell style index")
                    fmt_id = styles[style]
                    value, formula = _cell(cell, ns, CellRef(source_id, region.sheet, address),
                                           formats.get(fmt_id), shared)
                    if fmt_id:
                        format_ids.append((address, fmt_id))
                    if formula is not None and (formula.attrib or not formula.text):
                        formulas.append(FormulaMetadata(address, tuple(sorted(formula.attrib.items())),
                                                        formula.text))
                    values[col] = value
                while r1 + len(rows) < row:
                    rows.append(complete(r1 + len(rows), {}))
                rows.append(complete(row, values))
    while r1 + len(rows) <= r2:
        rows.append(complete(r1 + len(rows), {}))
    return CellGrid(region, source_hash, tuple(rows), tuple(hidden_rows),
                    tuple(hidden_columns), tuple(merges), tuple(formulas), tuple(format_ids))
