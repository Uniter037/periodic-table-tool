"""验证实际源码包内容、动态模块发现与隔离安装。"""
from pathlib import Path
import ast
import hashlib
import subprocess
import sys
import zipfile

import make_dist
import build_exe

ROOT = Path(__file__).resolve().parents[1]


def test_archive_contents_and_reproducibility(tmp_path):
    first = make_dist.build_archive(destination=tmp_path / "first.zip")
    second = make_dist.build_archive(destination=tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        files = {name.removeprefix("periodic-table-tool/") for name in archive.namelist()}
        assert set(make_dist.INCLUDE) <= files
        for package in ("core", "ui", "application", "infrastructure", "domain"):
            assert {p.relative_to(ROOT).as_posix() for p in (ROOT / package).rglob("*.py")} <= files
        assert len([p for p in files if p.startswith("tests/fixtures/originals/") and p.endswith(".py")]) == 12
        assert not any("__pycache__" in p for p in files)


def test_new_ui_module_is_discovered(tmp_path):
    for rel in make_dist.INCLUDE:
        (tmp_path / rel).write_text("", encoding="utf-8")
    module = tmp_path / "ui" / "nested" / "preview.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    assert "ui/nested/preview.py" in set(make_dist.source_files(tmp_path))


def test_version_consistent():
    import re
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert version.group(1) == make_dist.VERSION == "1.9.0"


def test_fixture_provenance():
    source = (ROOT / "tests/verify.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    mapping = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "FILE_STYLE" for t in n.targets))
    folder = ROOT / "tests/fixtures/originals"
    provenance = (folder / "README.md").read_text(encoding="utf-8")
    assert len(mapping) == 12
    for name in mapping:
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() in provenance
    assert 'os.path.join(PROJECT_ROOT, "tests", "fixtures", "originals")' in source


def test_wheel_install_from_source_archive(tmp_path):
    archive = make_dist.build_archive(destination=tmp_path / "source.zip")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(tmp_path / "src")
    source = tmp_path / "src/periodic-table-tool"
    wheels = tmp_path / "wheels"
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                    "--wheel-dir", str(wheels), str(source)], check=True, capture_output=True, text=True)
    wheel = next(wheels.glob("*.whl"))
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())
        assert "main.py" in names
        for package in ("core", "ui", "application", "infrastructure", "domain"):
            assert {p.relative_to(source).as_posix() for p in (source / package).rglob("*.py")} <= names
        assert not any(p.startswith("tests/") for p in names)
        zf.extractall(tmp_path / "installed")
    subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import core; import main; assert core.__file__.startswith(sys.argv[1]); assert main.__file__.startswith(sys.argv[1])",
                    str(tmp_path / "installed")], cwd=tmp_path, check=True, capture_output=True, text=True)


def test_exe_build_collects_packages():
    command = build_exe.pyinstaller_command(sys.executable)
    assert "--windowed" in command and "--noupx" in command
    assert "matplotlib.backends.backend_tkagg" in command
    assert "matplotlib.backends.backend_agg" in command
    assert "matplotlib.backends.backend_svg" in command
    assert "matplotlib.backends.backend_pdf" in command
    assert "PIL.ImageTk" in command and "PIL._imagingtk" in command
    for package in ("core", "ui", "application", "infrastructure", "domain"):
        if (ROOT / package).is_dir():
            assert package in command
    assert all("==" in dep for dep in build_exe.REQUIREMENTS)


def test_examples_allowlist(tmp_path):
    for rel in make_dist.INCLUDE:
        (tmp_path / rel).write_text("", encoding="utf-8")
    folder = tmp_path / "examples" / "nested"
    folder.mkdir(parents=True)
    for name in ("heatmap.txt", "labels.txt", "data.json", "data.csv", "data.tsv", "secret.env", "script.py", "photo.png"):
        (folder / name).write_text("", encoding="utf-8")
    with zipfile.ZipFile(make_dist.build_archive(tmp_path)) as archive:
        names = set(archive.namelist())
    assert {name for name in names if "/examples/" in name} == {
        "periodic-table-tool/examples/nested/" + name
        for name in ("heatmap.txt", "labels.txt", "data.json", "data.csv", "data.tsv")
    }
