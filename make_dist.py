# -*- coding: utf-8 -*-
"""打包发行包：生成 dist/periodic-table-tool-v1.0.0.zip。"""
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION = "1.1.0"
DIST_DIR = os.path.join(ROOT, "dist")
ZIP_NAME = f"periodic-table-tool-v{VERSION}.zip"

# 需要打包的文件（相对项目根）
INCLUDE = [
    "main.py",
    "README.md",
    "requirements.txt",
    "pyproject.toml",
    "core/__init__.py",
    "core/ptable.py",
    "core/elements_data.py",
    "core/styles.py",
    "core/dataio.py",
    "core/saver.py",
]
EXCLUDE_PARTS = ("__pycache__",)


def main():
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_path = os.path.join(DIST_DIR, ZIP_NAME)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            src = os.path.join(ROOT, rel)
            if not os.path.isfile(src):
                raise FileNotFoundError(f"缺少文件: {rel}")
            arc = os.path.join("periodic-table-tool", rel)
            zf.write(src, arc)
    size = os.path.getsize(zip_path)
    print(f"已生成 {zip_path} ({size} 字节)")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        print(f"包含 {len(names)} 个文件:")
        for n in names:
            print(f"  {n}")


if __name__ == "__main__":
    main()
