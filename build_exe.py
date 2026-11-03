"""Windows exe 构建：用 CPython 3.14.2 x64 运行 python build_exe.py。

创建独立 .venv-build-exe，固定全部构建依赖，输出 dist/PeriodicTableTool.exe。
需要网络安装依赖；不发布。固定工具链便于复现构建流程，不承诺 PE 字节完全相同。
"""
from pathlib import Path
import os
import platform
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
REQUIREMENTS = (
    "pip==25.3", "setuptools==83.0.0", "pyinstaller==6.21.0",
    "pyinstaller-hooks-contrib==2026.6", "altgraph==0.17.5",
    "packaging==26.2", "pefile==2024.8.26", "pywin32-ctypes==0.2.3",
    "matplotlib==3.11.1", "numpy==2.5.1", "contourpy==1.3.3",
    "cycler==0.12.1", "fonttools==4.63.0", "kiwisolver==1.5.0",
    "pillow==12.3.0", "pyparsing==3.3.2", "python-dateutil==2.9.0.post0",
    "six==1.17.0",
)


def pyinstaller_command(python):
    command = [str(python), "-m", "PyInstaller", "--noconfirm", "--clean",
               "--onefile", "--windowed", "--noupx", "--name", "PeriodicTableTool",
               "--distpath", str(ROOT / "dist"),
               "--workpath", str(ROOT / "build" / "exe"),
               "--specpath", str(ROOT / "build"),
               "--paths", str(ROOT),
               "--hidden-import", "matplotlib.backends.backend_tkagg",
               "--hidden-import", "matplotlib.backends.backend_agg",
               "--hidden-import", "matplotlib.backends.backend_svg",
               "--hidden-import", "matplotlib.backends.backend_pdf",
               "--hidden-import", "PIL.ImageTk",
               "--hidden-import", "PIL._imagingtk"]
    for package in ("core", "ui"):
        if (ROOT / package).is_dir():
            command.extend(["--collect-submodules", package])
    command.append(str(ROOT / "main.py"))
    return command


def main():
    if (sys.platform != "win32" or platform.python_implementation() != "CPython"
            or sys.version_info[:3] != (3, 14, 2) or platform.machine().lower() not in ("amd64", "x86_64")):
        raise SystemExit("请使用 Windows CPython 3.14.2 x64（含 tkinter）运行此脚本。")
    import tkinter  # 在安装依赖前检查 GUI 标准库。
    environment = ROOT / ".venv-build-exe"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "Scripts" / "python.exe"
    env = dict(os.environ, PYTHONHASHSEED="0", SOURCE_DATE_EPOCH="1577836800",
               PYINSTALLER_CONFIG_DIR=str(ROOT / "build" / "pyinstaller-cache"))
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                    "--only-binary=:all:", *REQUIREMENTS], cwd=ROOT, env=env, check=True)
    subprocess.run([str(python), "-m", "pip", "check"], cwd=ROOT, env=env, check=True)
    subprocess.run(pyinstaller_command(python), cwd=ROOT, env=env, check=True)
    print(ROOT / "dist" / "PeriodicTableTool.exe")


if __name__ == "__main__":
    main()
