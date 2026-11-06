from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from infrastructure.readers import ReaderLimits, Region, XlsxReadError, XlsxReader

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"


def relationships(*entries):
    return f'<Relationships xmlns="{PACKAGE}">' + "".join(
        f'<Relationship Id="{key}" Type="{OFFICE}/{kind}" Target="{target}"/>'
        for key, kind, target in entries
    ) + "</Relationships>"


def fixture_zip(**replacements):
    parts = {
        "_rels/.rels": relationships(("workbook", "officeDocument", "books/book.xml")),
        "books/book.xml": f"""
          <workbook xmlns="{MAIN}" xmlns:r="{OFFICE}"><sheets>
            <sheet name="Values" sheetId="1" r:id="r2"/>
            <sheet name="Hidden" sheetId="2" state="veryHidden" r:id="r1"/>
          </sheets></workbook>""",
        "books/_rels/book.xml.rels": relationships(
            ("r1", "worksheet", "/sheets/empty.xml"),
            ("r2", "worksheet", "../sheets/value%20sheet.xml"),
            ("r3", "sharedStrings", "strings.xml"),
            ("r4", "styles", "styles.xml"),
        ),
        "books/strings.xml": f"""
          <sst xmlns="{MAIN}"><si><r><t xml:space="preserve"> Na</t></r>
          <r><t>Cl </t></r><rPh sb="0" eb="1"><t>phonetic</t></rPh></si>
          <si><t/></si></sst>""",
        "books/styles.xml": f"""
          <styleSheet xmlns="{MAIN}">
            <numFmts><numFmt numFmtId="164" formatCode="0.000 &quot;mg&quot;"/></numFmts>
            <cellStyleXfs><xf numFmtId="0"/><xf numFmtId="9"/></cellStyleXfs>
            <cellXfs><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="14"/>
            <xf xfId="1" numFmtId="0" applyNumberFormat="0"/><xf numFmtId="27"/></cellXfs>
          </styleSheet>""",
        "sheets/empty.xml": f'<worksheet xmlns="{MAIN}"><sheetData/></worksheet>',
        "sheets/value sheet.xml": f"""
          <worksheet xmlns="{MAIN}">
            <dimension ref="A1:GR205"/>
            <cols><col min="2" max="4" hidden="1"/><col min="8" max="8" hidden="1"/></cols>
            <sheetData>
              <row r="1" hidden="true">
                <c r="A1" s="1"><v>001.2500</v></c>
                <c r="B1" t="s"><v>0</v></c>
                <c r="C1" t="inlineStr"><is><t/></is></c>
                <c r="D1" s="2"><v>45292</v></c>
                <c r="E1" t="b"><v>0</v></c>
                <c r="F1" t="s"><v>1</v></c>
              </row>
              <row r="2">
                <c r="A2" s="3"><f t="shared" si="4" ref="A2:A3">ROUND(A1,0)</f><v>0</v></c>
                <c r="B2" t="str"><f>IF(TRUE,"","x")</f><v/></c>
                <c r="C2"><f>1+1</f><v/></c>
                <c r="D2" t="e"><f>1/0</f><v>#DIV/0!</v></c>
                <c r="E2" t="b"><f>TRUE()</f><v>1</v></c>
                <c r="F2" s="4"><v>23</v></c>
              </row>
              <row r="3"><c r="A3"><f t="shared" si="4"/><v>5</v></c></row>
              <row r="5" hidden="1"/>
              <row r="200"><c r="GR200"><v>9</v></c><c r="GS200"><v>8</v></c></row>
              <row r="205"><c r="A205"><v>7</v></c></row>
            </sheetData>
            <mergeCells><mergeCell ref="F3:G4"/><mergeCell ref="H3:I4"/></mergeCells>
          </worksheet>""",
    }
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, xml in (parts | replacements).items():
            archive.writestr(name, xml.strip())
    return stream.getvalue()


@pytest.fixture
def xlsx(tmp_path):
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(fixture_zip())
    return path


def test_summary_and_dense_grid_from_same_snapshot(xlsx):
    reader = XlsxReader()
    summary = reader.inspect(xlsx, "src")
    grid = reader.read_region(xlsx, "Values", "a1:f5", "src")
    assert summary.source_hash == grid.source_hash == sha256(xlsx.read_bytes()).hexdigest()
    visible, hidden = summary.sheets
    assert (visible.name, visible.hidden_state, visible.physical_bounds) == (
        "Values", "visible", "A1:GR205",
    )
    assert visible.nonempty_candidates[-1] == "GR200"
    assert {"C1", "C2", "F1"}.issubset(visible.nonempty_candidates)
    assert (hidden.name, hidden.hidden_state, hidden.physical_bounds) == ("Hidden", "veryHidden", None)
    assert hidden.nonempty_candidates == ()
    assert grid.region == Region("Values", "A1:F5")
    assert [len(row) for row in grid.cells] == [6] * 5
    assert grid.hidden_rows == (1, 5)
    assert grid.hidden_columns == ((2, 4),)
    assert grid.merged_ranges == ("F3:G4",)
    assert grid.number_format_ids == (("A1", 164), ("D1", 14), ("A2", 9), ("F2", 27))
    a, b, c, d, e, f = grid.cells[0]
    assert (a.kind, a.numeric, a.raw_text, a.format_code) == ("number", 1.25, "001.2500", '0.000 "mg"')
    assert (b.raw_text, c.raw_text, f.raw_text) == (" NaCl ", "", "")
    assert (d.numeric, d.format_code, e.kind, e.raw_text) == (45292, "mm-dd-yy", "text", "FALSE")
    blank = grid.cells[3][5]
    assert blank.kind == "missing"
    assert (blank.source.source_id, blank.source.sheet, blank.source.address) == ("src", "Values", "F4")
    assert reader.read_region(xlsx, "Values", "XFD1048576", "src").cells[0][0].kind == "missing"
    assert reader.read_region(xlsx, "Values", "A205", "src").cells[0][0].numeric == 7
    assert reader.read_region(xlsx, "Values", "C2", "src").hidden_columns == ((3, 3),)
    assert reader.read_region(xlsx, "Values", "G4", "src").merged_ranges == ("F3:G4",)


def test_formula_cache_does_not_require_calculation(xlsx):
    grid = XlsxReader().read_region(xlsx, "Values", "A2:F3", "src")
    zero, empty, missing, error, boolean, local_fmt = grid.cells[0]
    assert (zero.formula, zero.cached, zero.numeric, zero.format_code) == ("=ROUND(A1,0)", 0, 0, "0%")
    assert (empty.kind, empty.cached) == ("text", "")
    assert (missing.kind, missing.formula, missing.cached) == ("error", "=1+1", None)
    assert (error.kind, error.cached) == ("error", "#DIV/0!")
    assert (boolean.kind, boolean.cached, boolean.raw_text) == ("text", True, "TRUE")
    assert local_fmt.format_code is None
    follower = grid.cells[1][0]
    assert (follower.formula, follower.cached) == ("=", 5)
    master, follower_metadata = grid.formula_metadata
    assert master.stored_text == "ROUND(A1,0)"
    assert (follower_metadata.address, dict(follower_metadata.attributes), follower_metadata.stored_text) == (
        "A3", {"t": "shared", "si": "4"}, None,
    )


@pytest.mark.parametrize("address", ["A0", "XFE1", "A1048577", "B2:A1", "$A$1", "A1:B2:C3", "A1:XFD1048576"])
def test_invalid_or_oversized_selection(xlsx, address):
    with pytest.raises(XlsxReadError):
        XlsxReader().read_region(xlsx, "Values", address, "src")


@pytest.mark.parametrize(("limits", "message"), [
    (ReaderLimits(max_file_bytes=1), "file size"),
    (ReaderLimits(max_uncompressed_bytes=1), "uncompressed size"),
    (ReaderLimits(max_zip_entries=1), "entry count"),
])
def test_zip_budgets(xlsx, limits, message):
    with pytest.raises(XlsxReadError, match=message):
        XlsxReader(limits).inspect(xlsx, "src")


def test_invalid_file_and_sheet(xlsx):
    reader = XlsxReader()
    with pytest.raises(XlsxReadError, match="Worksheet not found"):
        reader.read_region(xlsx, "Missing", "A1", "src")
    xlsx.write_bytes(b"not a ZIP")
    with pytest.raises(XlsxReadError, match="Invalid or unreadable"):
        reader.inspect(xlsx, "src")


@pytest.mark.parametrize("xml", [
    f'<worksheet xmlns="{MAIN}"><sheetData><row r="1"></sheetData></worksheet>',
    f'<!DOCTYPE worksheet [<!ENTITY data "123">]><worksheet xmlns="{MAIN}"/>',
    f'<worksheet xmlns="{MAIN}"><sheetData><row r="1"><c r="A1" t="s"><v>999</v></c></row></sheetData></worksheet>',
])
def test_invalid_xml_or_shared_index(xlsx, xml):
    xlsx.write_bytes(fixture_zip(**{"sheets/value sheet.xml": xml}))
    with pytest.raises(XlsxReadError):
        XlsxReader().read_region(xlsx, "Values", "A1", "src")
