# -*- coding: utf-8 -*-
"""生成可重复的源码 ZIP；不构建或发布 exe。"""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "1.6.0"
DIST_DIR = ROOT / "dist"
ZIP_NAME = f"periodic-table-tool-v{VERSION}.zip"
INCLUDE = ["main.py", "README.md", "requirements.txt", "pyproject.toml",
           "make_dist.py", "build_exe.py", "verify_exe.py"]


def source_files(root=ROOT):
    """动态发现运行时模块及测试基准，排除缓存与构建产物。"""
    root = Path(root)
    files = set(INCLUDE)
    for package in ("core", "ui", "tests"):
        files.update(p.relative_to(root).as_posix()
                     for p in (root / package).rglob("*.py")
                     if "__pycache__" not in p.parts)
    for folder in ("tests/fixtures",):
        files.update(p.relative_to(root).as_posix()
                     for p in (root / folder).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix != ".pyc")
    files.update(p.relative_to(root).as_posix()
                 for p in (root / "examples").rglob("*")
                 if p.is_file() and not p.is_symlink()
                 and p.suffix.lower() in {".txt", ".json", ".csv", ".tsv"}
                 and "__pycache__" not in p.parts)
    for rel in sorted(files):
        if not (root / rel).is_file():
            raise FileNotFoundError(f"缺少文件: {rel}")
        yield rel


def build_archive(root=ROOT, destination=None):
    root = Path(root)
    files = list(source_files(root))
    destination = Path(destination) if destination else root / "dist" / ZIP_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            info = zipfile.ZipInfo(f"periodic-table-tool/{rel}", (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            zf.writestr(info, (root / rel).read_bytes())
    return destination


def main():
    path = build_archive()
    print(f"已生成 {path} ({path.stat().st_size} 字节)")


if __name__ == "__main__":
    main()
