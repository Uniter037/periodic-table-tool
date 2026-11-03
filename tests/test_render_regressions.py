"""Headless regressions for rendering ownership, finite data and text fonts."""
import csv
from io import StringIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
import pytest

from core.dataio import parse_data, validate_data
from core.styles import STYLES, render_table, render_cmap_preview
from core import fonts


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-Infinity", "1e999"])
def test_nonfinite_input(value):
    for source in (f"H, {value}", '{"H": "' + value + '"}'):
        with pytest.raises(ValueError, match="有限"):
            parse_data(source)
    for val in (value, float(value)):
        valid, unknown, bad = validate_data({"H": val, "He": 0, "Li": "标注"})
        assert valid == {"He": 0, "Li": "标注"}
        assert not unknown and bad[0][0] == "H"
        before = plt.get_fignums()
        with pytest.raises(ValueError):
            render_table(STYLES["custom"], {"H": val})
        assert plt.get_fignums() == before


@pytest.mark.parametrize("source", ['{"H": NaN}', '{"H": Infinity}', "{'H': 1e999}"])
def test_nonfinite_dict_literals(source):
    with pytest.raises(ValueError):
        parse_data(source)


@pytest.mark.parametrize("layout", ["classic", "reconstructed"])
def test_custom_zero_is_present(layout):
    style = dict(STYLES["custom"], layout=layout, norm=("normalize", -1, 1))
    fig = render_table(style, {"H": 0}, show_cbar=False)
    try:
        ax = fig.axes[0]
        assert any(t.get_text() == "0.000" for t in ax.texts)
        assert ax.patches[0].get_facecolor() != to_rgba(style["empty"])
        assert ax.patches[1].get_facecolor() == to_rgba(style["empty"])
    finally:
        plt.close(fig)


@pytest.mark.parametrize("sid", [key for key, style in STYLES.items()
                                if style["kind"] == "heatmap" and key != "custom"])
def test_legacy_zero_unchanged(sid):
    fig = render_table(STYLES[sid], {"H": 0}, show_cbar=False)
    try:
        values = [t.get_text() for t in fig.axes[0].texts]
        if sid == "classic_ylorrd_orig":
            assert "0" in values
        else:
            assert not any(value in values for value in ("0", "0.00", "0.000", "0.00%"))
            assert fig.axes[0].patches[0].get_facecolor() == to_rgba(STYLES[sid]["empty"])
    finally:
        plt.close(fig)


@pytest.mark.parametrize("stage", ["cmap", "layout", "save"])
def test_failure_closes_only_owned_figure(stage, monkeypatch, tmp_path):
    other = plt.figure()
    before = plt.get_fignums()
    def fail(*args, **kwargs):
        raise RuntimeError("injected failure")
    try:
        with pytest.raises((RuntimeError, ValueError)):
            if stage == "save":
                monkeypatch.setattr(matplotlib.figure.Figure, "savefig", fail)
                render_cmap_preview(str(tmp_path), ["viridis"])
            else:
                style = dict(STYLES["custom"])
                if stage == "cmap":
                    style["cmap"] = "invalid_cmap"
                else:
                    monkeypatch.setattr(plt, "tight_layout", fail)
                render_table(style, {"H": 0})
        assert plt.get_fignums() == before
    finally:
        plt.close(other)


def test_chinese_fallback_and_ascii_preserved(monkeypatch):
    monkeypatch.setattr(plt, "tight_layout", lambda: None)
    monkeypatch.setattr(fonts, "_fallback_fonts", lambda: [("DejaVu Sans", set(map(ord, "中文标题")))])
    fig = render_table(STYLES["labels_light"], {"H": "中文"}, title="标题", show_cbar=False)
    try:
        texts = {t.get_text(): t for t in fig.axes[0].texts}
        assert texts["H"].get_fontfamily() == ["Arial"]
        assert texts["中文"].get_fontfamily() == ["Arial", "DejaVu Sans"]
        assert "DejaVu Sans" in fig._suptitle.get_fontfamily()
    finally:
        plt.close(fig)


def test_installed_chinese_font_draws_without_missing_glyphs():
    import warnings
    required = set(map(ord, "中文标题"))
    if not any(required <= glyphs for _, glyphs in fonts._fallback_fonts()):
        pytest.skip("No installed font covers the Chinese sample")
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message="Glyph .* missing from font")
        fig = render_table(STYLES["labels_light"], {"H": "中文"}, title="标题")
        try:
            fig.canvas.draw()
        finally:
            plt.close(fig)


@pytest.mark.parametrize("layout", ["classic", "reconstructed"])
@pytest.mark.parametrize("kind", ["heatmap", "labels"])
def test_custom_text_controls(layout, kind):
    style = dict(STYLES["custom"], layout=layout, kind=kind,
                 symbol_fs=12, number_fs=7, value_fs=10, label_color="purple")
    fig = render_table(style, {"H": 0}, show_cbar=False)
    try:
        texts = {t.get_text(): t for t in fig.axes[0].texts}
        assert texts["H"].get_fontsize() == 12
        assert texts["1"].get_fontsize() == 7
        value = "0.000" if kind == "heatmap" else "0"
        assert texts[value].get_fontsize() == 10
        assert texts[value].get_color() == "purple"
        if layout == "reconstructed":
            assert texts["La~Lu"].get_fontsize() == 12
            assert texts["Lanthanide"].get_fontsize() == 10
    finally:
        plt.close(fig)
    for role, absent in (("symbol", "H"), ("number", "1"), ("value", value)):
        fig = render_table(dict(style, **{f"show_{role}": False}), {"H": 0}, show_cbar=False)
        try:
            assert absent not in [t.get_text() for t in fig.axes[0].texts]
            assert len(fig.axes[0].patches) > 80
        finally:
            plt.close(fig)


def test_label_colors_edges_and_transparent_export(tmp_path):
    from PIL import Image
    style = dict(STYLES["custom"], kind="labels", bg="beige", highlight_bg="navy",
                 highlight_fg="yellow", edge=(1.5, "red"), transparent=True)
    fig = render_table(style, {"H": "sample"}, show_cbar=False)
    try:
        ax = fig.axes[0]
        assert ax.patches[0].get_facecolor() == to_rgba("navy")
        assert ax.patches[1].get_facecolor() == to_rgba("beige")
        assert ax.patches[0].get_edgecolor() == to_rgba("red")
        assert ax.patches[0].get_linewidth() == 1.5
        assert next(t for t in ax.texts if t.get_text() == "sample").get_color() == "yellow"
        path = tmp_path / "transparent.png"
        fig.savefig(path)
        with Image.open(path) as image:
            assert image.getpixel((0, 0))[3] == 0
        assert fig.patch.get_alpha() == ax.patch.get_alpha() == 0
    finally:
        plt.close(fig)


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
@pytest.mark.parametrize("cbar_style", ["standard", "plain", "ax_plain"])
def test_custom_colorbar_options(orientation, cbar_style):
    style = dict(STYLES["custom"], cbar_orientation=orientation, cbar_label="Scale",
                 cbar_style=cbar_style, cbar={"ticks": [0.6, 0.78], "labels": ["low", "high"], "fontsize": 11},
                 transparent=True)
    fig = render_table(style, {"H": 0.7})
    try:
        ax = fig.axes[-1]
        axis = ax.xaxis if orientation == "horizontal" else ax.yaxis
        assert axis.label.get_text() == "Scale"
        assert [t.get_text() for t in axis.get_ticklabels()] == ["low", "high"]
        assert all(t.get_fontsize() == 11 for t in axis.get_ticklabels())
        assert ax.patch.get_alpha() == 0
    finally:
        plt.close(fig)
    fig = render_table(style, {"H": 0.7}, show_cbar=False)
    try:
        assert len(fig.axes) == 1
    finally:
        plt.close(fig)


@pytest.mark.parametrize("option,value", [("symbol_fs", 0), ("number_fs", float("nan")),
    ("value_fs", float("inf")), ("show_symbol", "false"), ("transparent", 1),
    ("cbar_orientation", "diagonal"), ("edge", (-1, "red"))])
def test_invalid_custom_options_do_not_leak(option, value):
    before = plt.get_fignums()
    with pytest.raises(ValueError):
        render_table(dict(STYLES["custom"], **{option: value}), {})
    assert plt.get_fignums() == before


@pytest.mark.parametrize("source", [
    "\ufeffelement,value\nH,0\nC,-1\nO,1\nHe,\n\n",
    "元素\t数值\nH\t0\nC\t-1\nO\t1\nHe\t\n\n",
    "H\t0\nC\t-1\nO\t1\nHe\t",
])
def test_spreadsheet_input(source):
    assert parse_data(source) == {"H": 0, "C": -1, "O": 1}


@pytest.mark.parametrize("delimiter", [",", "\t"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("label", [
    "line1\nline2",
    "line1\r\nline2",
    "alpha\tbeta",
    'first,"quoted"\n# continuation\n\nlast\tpart',
])
def test_csv_quoted_labels(delimiter, newline, label):
    source = StringIO(newline="")
    writer = csv.writer(source, delimiter=delimiter, lineterminator=newline,
                        quoting=csv.QUOTE_ALL)
    writer.writerows([("element", "value"), ("H", label), ("He", 2)])
    assert parse_data(source.getvalue()) == {"H": label, "He": 2}


def test_csv_tab_in_unquoted_value():
    assert parse_data("element,value\nH,alpha\tbeta\nHe,2") == {
        "H": "alpha\tbeta", "He": 2,
    }


def test_csv_multiline_with_comments_and_legacy_rows():
    source = ('# before header\nelement,value\nH,"first\n# inside label\n\nlast"\n'
              '# between records\nHe=3c1\nLi 2\nBe: alpha,beta\nB，text\n')
    assert parse_data(source) == {
        "H": "first\n# inside label\n\nlast", "He": "3c1", "Li": 2,
        "Be": "alpha,beta", "B": "text",
    }


@pytest.mark.parametrize("source", [
    "H=0\nHe: -1\nLi，2\nBe 3\nB,4\nC\t5\nN",
    '{"H": 0, "He": -1, "Li": 2, "Be": 3, "B": 4, "C": 5}',
    "{'H': 0, 'He': -1, 'Li': 2, 'Be': 3, 'B': 4, 'C': 5}",
])
def test_legacy_and_dictionary_input_preserved(source):
    assert parse_data(source) == {"H": 0, "He": -1, "Li": 2, "Be": 3, "B": 4, "C": 5}


@pytest.mark.parametrize("source", [
    'H,"line1\nline2"\nH,2',
    'H,"line1\nline2"\n" H ",2',
    'H,""\nH,"line1\nline2"',
])
def test_csv_multiline_duplicate_input_rejected(source):
    with pytest.raises(ValueError, match="重复元素: H"):
        parse_data(source)


@pytest.mark.parametrize("source, message", [
    ('H,"line1\nline2', "第 1 行 CSV/TSV 格式错误"),
    ('H,"line1\nline2"\nHe,"unclosed', "第 3 行 CSV/TSV 格式错误"),
    ('H,"line1\nline2",extra', "第 1 行需要两列"),
])
def test_csv_multiline_invalid_records_rejected(source, message):
    with pytest.raises(ValueError, match=message):
        parse_data(source)


@pytest.mark.parametrize("source", ["H,1\nH,2", '{"H": 1, "H": 2}',
    "{'H': 1, 'H': 2}", '{"H": 1, " H ": 2}', "H,\nH,2"])
def test_duplicate_input_rejected(source):
    with pytest.raises(ValueError, match="重复元素: H"):
        parse_data(source)


def test_labels_and_empty_dictionary_values():
    assert parse_data('element,value\nH,"alpha,beta"\nHe,中文') == {"H": "alpha,beta", "He": "中文"}
    assert parse_data("H: alpha,beta\nHe=3c1") == {"H": "alpha,beta", "He": "3c1"}
    assert parse_data('\ufeff{"H": "", "He": null, "Li": 0}') == {"Li": 0}


def test_custom_demo_has_signed_and_zero_values():
    from core.dataio import demo_data
    data = demo_data("custom")
    assert 0 in data.values() and min(data.values()) < 0 < max(data.values())
    assert validate_data(data) == (data, [], [])
    fig = render_table(STYLES["custom"], data)
    plt.close(fig)
