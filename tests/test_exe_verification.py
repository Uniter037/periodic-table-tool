"""Release verification must reject stale/failing runs and broken artifacts."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
import pytest

from verify_exe import inspect_outputs


@pytest.fixture
def exported_run(tmp_path):
    figure = Figure(figsize=(2, 1), dpi=50)
    figure.subplots().plot([0, 1], [0, 1])
    for fmt in ("svg", "png", "pdf"):
        figure.savefig(tmp_path / f"chart.{fmt}")
    marker = tmp_path / "smoke_progress.txt"
    marker.write_text("app_created\npreview:passed\nexport:svg\nexport:png\nexport:pdf\n"
                      "smoke:passed\nafter_mainloop\n", encoding="utf-8")
    return tmp_path, marker


def test_verifies_real_export_files(exported_run):
    folder, marker = exported_run
    result = inspect_outputs(folder, marker)
    assert result["png"]["pixels"] == [100, 50]
    assert all(result[fmt]["bytes"] > 100 for fmt in ("png", "svg", "pdf"))


def test_failed_or_incomplete_run_cannot_pass(exported_run):
    folder, marker = exported_run
    with marker.open("a", encoding="utf-8") as stream:
        stream.write("smoke:failed:export error\n")
    with pytest.raises(RuntimeError, match="export error"):
        inspect_outputs(folder, marker)
    marker.write_text("app_created\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="missing="):
        inspect_outputs(folder, marker)


def test_truncated_pdf_is_rejected(exported_run):
    folder, marker = exported_run
    path = folder / "chart.pdf"
    path.write_bytes(path.read_bytes()[:50])
    with pytest.raises(RuntimeError, match="incomplete PDF"):
        inspect_outputs(folder, marker)
