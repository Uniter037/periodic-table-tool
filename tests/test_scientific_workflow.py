"""Headless scientific workflow: text fidelity, real artists and export pixels."""
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
import numpy as np
from PIL import Image
import pytest

from core.dataio import convert_data, demo_data, parse_data
from core.scientific import colorbar_config, corrected_style, range_warnings
from core.styles import STYLES, render_table


@pytest.mark.parametrize("source", [
    'H,001\nHe,1.00\nLi,1e3\nBe,-0.00',
    'H\t001\nHe\t1.00\nLi\t1e3\nBe\t-0.00',
    '{"H":"001","He":1.00,"Li":1e3,"Be":-0.00}',
    "{'H': '001', 'He': 1.00, 'Li': 1e3, 'Be': -0.00}",
])
def test_preserved_annotation_and_numeric_render_boundary(source):
    original = {"H": "001", "He": "1.00", "Li": "1e3", "Be": "-0.00"}
    data = parse_data(source, preserve_text=True)
    assert data == original
    fig = render_table(dict(STYLES["custom"], kind="labels"), convert_data(data, "labels"))
    try:
        texts = [t.get_text() for t in fig.axes[0].texts]
        assert all(value in texts for value in original.values())
    finally:
        plt.close(fig)
    assert convert_data(data, "heatmap") == {"H": 1., "He": 1., "Li": 1000., "Be": -0.}
    assert data == original
    assert parse_data(source) == {"H": 1., "He": 1., "Li": 1000., "Be": -0.}


def test_quoted_annotation_whitespace_and_multiline_survive():
    text = 'H," 001 \nline two  "\nHe,1.00'
    data = parse_data(text, preserve_text=True)
    assert data == {"H": " 001 \nline two  ", "He": "1.00"}
    fig = render_table(dict(STYLES["custom"], kind="labels"), data)
    try:
        assert data["H"] in [t.get_text() for t in fig.axes[0].texts]
    finally:
        plt.close(fig)


@pytest.mark.parametrize("value", ["nan", "inf", "-Infinity", "1e999", "3c1"])
def test_labels_allow_text_that_heatmaps_reject(value):
    data = parse_data(f"H,{value}", preserve_text=True)
    assert convert_data(data, "labels") == {"H": value}
    with pytest.raises(ValueError):
        convert_data(data, "heatmap")


@pytest.mark.parametrize("source", ['H,001\nH,1.00', '{"H":1,"H":2}', "{'H':1,'H':2}"])
def test_preservation_still_rejects_duplicates(source):
    with pytest.raises(ValueError, match="重复"):
        parse_data(source, preserve_text=True)


@pytest.mark.parametrize("data,kind", [({"Xx": "1"}, "heatmap"),
    ({"H": True}, "labels"), ({"H": []}, "labels"),
    ({"H": float("inf")}, "labels"), ({"H": "1"}, "unknown")])
def test_conversion_rejects_invalid_input(data, kind):
    with pytest.raises(ValueError):
        convert_data(data, kind)


@pytest.mark.parametrize("sid", ["classic_ylorrd_orig", "classic_ylorrd", "classic_blues"])
def test_conversion_keeps_native_integer_script_pixels(sid):
    original = demo_data(sid)
    converted = convert_data(original, "heatmap")
    assert isinstance(converted["H"], int)
    figures = []
    try:
        for data in (original, converted):
            figures.append(render_table(STYLES[sid], data))
            figures[-1].canvas.draw()
        assert np.array_equal(np.asarray(figures[0].canvas.buffer_rgba()),
                              np.asarray(figures[1].canvas.buffer_rgba()))
    finally:
        for fig in figures:
            plt.close(fig)


@pytest.mark.parametrize("sid", [sid for sid, s in STYLES.items() if s["kind"] == "heatmap"])
def test_corrected_zero_has_visible_color_and_missing_cell_has_no_value(sid):
    before = deepcopy(STYLES[sid])
    style = corrected_style(STYLES[sid])
    fig = render_table(style, {"H": 0}, show_cbar=False)
    try:
        ax = fig.axes[0]
        hydrogen, helium = ax.patches[:2]
        assert hydrogen.get_facecolor()[3] == 1
        assert hydrogen.get_facecolor() != helium.get_facecolor()
        values = [t for t in ax.texts if t.get_position() ==
                  pytest.approx((hydrogen.get_x() + .5, hydrogen.get_y() + .12))]
        assert values and float(values[0].get_text().rstrip("%")) == 0
        assert not any(t.get_position() == pytest.approx((helium.get_x() + .5, helium.get_y() + .12))
                       for t in ax.texts)
    finally:
        plt.close(fig)
    assert STYLES[sid] == before


def test_corrected_coolwarm_preserves_center_and_distinguishes_values():
    style = corrected_style(STYLES["classic_coolwarm"])
    fig = render_table(style, {"H": .61, "He": .73, "Li": .77})
    try:
        cbar = fig.axes[1]._colorbar
        assert [cbar.norm(v) for v in (.61, .73, .77)] == pytest.approx([0, .5, 1])
        colors = [p.get_facecolor() for p in fig.axes[0].patches[:3]]
        assert colors == [cbar.cmap(x) for x in (0., .5, 1.)]
        assert len(set(colors)) == 3
        assert list(fig.axes[1].get_yticks()) == [.61, .73, .77]
        assert range_warnings(style, {"H": .61, "He": .77}) == []
        assert len(range_warnings(style, {"H": .8})) == 1
    finally:
        plt.close(fig)


def _custom_work(**overrides):
    import main
    params = dict(cmap="coolwarm", vmin="-1", vcenter="0", vmax="1",
        fmt="科学计数法", layout="镧锕三行块（重构）", kind="热力图",
        font="DejaVu Sans", edge="黑色细线", empty="浅灰", dpi="100",
        figsize="10x5", symbol_fs="9", number_fs="6", value_fs="8",
        edge_width="0", edge_color="#123456", value_dx=".2", value_dy="-.1",
        label_wrap="0", unit=" kg", color_nodes="1:#ff0000;0:#0000ff;0.2:#ffffff",
        cbar_orientation="vertical", cbar_location="top", cbar_fraction=".1",
        cbar_pad=".08", cbar_shrink=".7", cbar_label="Mass")
    params.update(overrides)
    fake = SimpleNamespace(param_vars={k: SimpleNamespace(get=lambda v=v: v) for k, v in params.items()},
                           bool_vars={}, custom_colors=[])
    base = deepcopy(STYLES["custom"])
    work = main.App._apply_custom_params(fake, base)
    assert base == STYLES["custom"]
    return work


def test_actual_main_field_contract_without_tk(monkeypatch):
    import main
    monkeypatch.setattr(main.tk, "Tk", lambda *a, **kw: pytest.fail("Tk must not be created"))
    work = _custom_work()
    fig = render_table(work, {"H": "0", "He": "-.6", "Li": "1"})
    try:
        ax = fig.axes[0]
        assert all(p.get_linewidth() == 0 for p in ax.patches)
        text = next(t for t in ax.texts if t.get_text() == "0.000e+00 kg")
        assert text.get_position() == pytest.approx((.7, 7.62))
        assert "Lanthanide" in [t.get_text() for t in ax.texts]
        assert not any("Lanthanide kg" in t.get_text() for t in ax.texts)
        assert fig.axes[1]._colorbar.orientation == "horizontal"
        assert fig.axes[1].get_xlabel() == "Mass"
        # A nonuniform node at .2 must be white (not the equally spaced midpoint).
        assert ax.patches[1].get_facecolor()[:3] == pytest.approx((1, 1, 1), abs=.012)
    finally:
        plt.close(fig)


def test_main_labels_ignore_invalid_heatmap_ranges_without_tk(monkeypatch):
    import main
    monkeypatch.setattr(main.tk, "Tk", lambda *a, **kw: pytest.fail("Tk must not be created"))
    work = _custom_work(kind="标注图（文本）", vmin="bad", vcenter="nan", vmax="inf")
    # Direct callers may also retain an invalid, currently unused heatmap range.
    work["norm"] = ("normalize", float("nan"), -1)
    fig = render_table(work, {"H": "001", "He": "1e3"})
    try:
        assert len(fig.axes) == 1
        assert {"001", "1e3"} <= {t.get_text() for t in fig.axes[0].texts}
    finally:
        plt.close(fig)


@pytest.mark.parametrize("kind,value,expected", [("labels", "abcdefghij", "abcd\nefgh\nij"),
    ("heatmap", .5, "0.50\nkg")])
def test_wrap_unit_offsets_and_edge_color(kind, value, expected):
    style = dict(STYLES["custom"], kind=kind, fmt="2f", norm=("normalize", 0, 1),
                 label_wrap=4, unit=" kg", value_dx=.25, value_dy=-.2,
                 edge_width=2.5, edge_color="#123456")
    fig = render_table(style, {"H": value}, show_cbar=False)
    try:
        ax = fig.axes[0]
        text = next(t for t in ax.texts if t.get_text() == expected)
        assert text.get_position() == pytest.approx((.75, 9.82))
        assert ax.patches[0].get_linewidth() == 2.5
        assert ax.patches[0].get_edgecolor() == to_rgba("#123456")
    finally:
        plt.close(fig)


@pytest.mark.parametrize("location", ["left", "right", "top", "bottom"])
def test_colorbar_location_ticks_label_and_size(location):
    style = dict(STYLES["custom"], norm=("normalize", 0, 1), cbar_location=location,
        cbar_orientation="vertical", cbar_fraction=.1, cbar_pad=.08, cbar_shrink=.6,
        cbar_label="Scale", cbar={"ticks": [1, 0, .5], "labels": ["max", "min", "hidden"],
                                 "visible": [True, True, False], "fontsize": 11})
    fig = render_table(style, {"H": .5})
    try:
        fig.canvas.draw()
        ax, bar = fig.axes
        horizontal = location in ("top", "bottom")
        axis = bar.xaxis if horizontal else bar.yaxis
        assert bar._colorbar.orientation == ("horizontal" if horizontal else "vertical")
        assert axis.label.get_text() == "Scale"
        assert [t.get_text() for t in axis.get_ticklabels()] == ["min", "max"]
        assert all(t.get_fontsize() == 11 for t in axis.get_ticklabels())
        a, b = ax.get_position(), bar.get_position()
        assert {"left": b.x1 < a.x0, "right": b.x0 > a.x1,
                "top": b.y0 > a.y1, "bottom": b.y1 < a.y0}[location]
    finally:
        plt.close(fig)


@pytest.mark.parametrize("orientation", ["horizontal", "vertical"])
def test_colorbar_dimensions_respond_to_each_control(orientation):
    def geometry(**options):
        style = dict(STYLES["custom"], cbar_orientation=orientation,
                     cbar_location="auto", cbar_fraction=.05, cbar_pad=.04, cbar_shrink=1)
        style.update(options)
        fig = render_table(style, {})
        try:
            fig.canvas.draw()
            a = fig.axes[0].get_position(original=True)
            b = fig.axes[1].get_position()
            return ((a.height, a.y0 - b.y1, b.width) if orientation == "horizontal"
                    else (a.width, b.x0 - a.x1, b.height))
        finally:
            plt.close(fig)
    base = geometry()
    assert geometry(cbar_fraction=.2)[0] < base[0]
    assert geometry(cbar_pad=.2)[1] > base[1]
    assert geometry(cbar_shrink=.5)[2] < .7 * base[2]


def test_nonuniform_color_nodes_reach_exported_png_pixels(tmp_path):
    style = dict(STYLES["custom"], norm=("normalize", 0, 1),
                 color_nodes="1:red；.2:white;0:blue", fmt="scientific", unit=" m")
    fig = render_table(style, {"H": 0, "He": .2, "Li": 1}, show_cbar=False)
    try:
        png = tmp_path / "nodes.png"
        fig.savefig(png, dpi=fig.dpi)
        with Image.open(png) as image:
            assert image.size == (1000, 500)
            for patch, expected in zip(fig.axes[0].patches[:3], ["blue", "white", "red"]):
                x, y = fig.axes[0].transData.transform((patch.get_x() + .8, patch.get_y() + .3))
                pixel = image.convert("RGBA").getpixel((int(x), image.height - 1 - int(y)))
                assert pixel == pytest.approx(np.array(to_rgba(expected)) * 255, abs=3)
        svg, pdf = BytesIO(), BytesIO()
        with matplotlib.rc_context({"svg.fonttype": "none"}):
            fig.savefig(svg, format="svg")
        fig.savefig(pdf, format="pdf")
        assert b"2.000e-01 m" in svg.getvalue()
        assert pdf.getvalue().startswith(b"%PDF")
    finally:
        plt.close(fig)


@pytest.mark.parametrize("key,value", [
    ("edge_width", -1), ("edge_width", 21), ("edge_width", True),
    ("edge_color", "bad-color"), ("edge", (1, "bad-color")), ("edge", (1,)),
    ("value_dx", float("nan")), ("value_dx", 2.01), ("value_dy", -2.01),
    ("label_wrap", 1.5), ("label_wrap", -1), ("label_wrap", 201), ("unit", 1),
    ("fmt", "unknown"),
    ("cbar_location", "diagonal"), ("cbar_orientation", "diagonal"),
    ("cbar_fraction", 0), ("cbar_fraction", .51), ("cbar_pad", -.01),
    ("cbar_pad", .51), ("cbar_shrink", .01), ("cbar_shrink", 1.01),
    ("cbar_shrink", float("inf")), ("label_fs", 0),
    ("norm", ("normalize", 1, 1)), ("norm", ("normalize", float("nan"), 1)),
    ("norm", ("twoslope", -1, 2, 1)), ("norm", ("normalize", 1)),
    ("color_nodes", "0:blue;.2:white;.2:red;1:red"),
    ("color_nodes", "0:blue;nan:white;1:red"), ("color_nodes", "0:blue;.9:red"),
    ("color_nodes", "0:blue;1:bad-color"), ("color_nodes", "broken"),
    ("cmap", ("custom", [(0, "blue"), (.5, "white"), (.5, "red"), (1, "red")])),
    ("cmap", ("custom", [(0, "blue"), (float("inf"), "red")])),
    ("cmap", ("custom", ["red"])),
])
@pytest.mark.parametrize("corrected", [False, True])
def test_invalid_advanced_fields_raise_without_figure_leaks(key, value, corrected):
    style = corrected_style(STYLES["classic_coolwarm"]) if corrected else dict(STYLES["custom"])
    style[key] = value
    other = plt.figure()
    before = plt.get_fignums()
    try:
        with pytest.raises(ValueError):
            render_table(style, {"H": .73}, show_cbar=False)
        assert plt.get_fignums() == before
    finally:
        plt.close(other)


@pytest.mark.parametrize("changes", [dict(ticks=[0, 0]), dict(ticks=[0, float("nan")]),
    dict(visible=[True]), dict(visible=[True, 1]), dict(fontsize=0), dict(fontsize=True),
    dict(labels=["one"]), dict(labels=["zero", 1]), dict(labels=["zero", None]),
    dict(labels="01"), dict(ticks=None), dict(fontsize=float("nan")), dict(fontsize=float("inf"))])
def test_all_colorbar_rows_validated_even_when_hidden(changes):
    config = dict(ticks=[0, 1], labels=["zero", "one"], visible=[True, False])
    config.update(changes)
    with pytest.raises(ValueError):
        colorbar_config(config)


def test_hidden_colorbar_rows_remain_in_source_and_restore_sorted():
    config = dict(ticks=[1, 0, .5], labels=["one", "zero", "half"], visible=[True, False, True])
    before = deepcopy(config)
    assert colorbar_config(config) == dict(ticks=[.5, 1], labels=["half", "one"], fontsize=8)
    assert config == before
    config["visible"][1] = True
    assert colorbar_config(config)["labels"] == ["zero", "half", "one"]
