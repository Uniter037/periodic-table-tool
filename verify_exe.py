"""Run the frozen application's real import/preview/export workflow in isolation.

Usage: python verify_exe.py [dist/PeriodicTableTool.exe] [--timeout 180]
The EXE is copied to a fresh directory, so old logs and outputs cannot pass a run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from PIL import Image


def inspect_outputs(folder: Path, marker: Path) -> dict:
    lines = marker.read_text(encoding="utf-8").splitlines()
    required = {"app_created", "preview:passed", "export:svg", "export:png", "export:pdf",
                "smoke:passed", "after_mainloop"}
    missing = required.difference(lines)
    failures = [line for line in lines if line.startswith("smoke:failed:")]
    if missing or failures:
        raise RuntimeError(f"EXE smoke failed: missing={sorted(missing)}, errors={failures}")
    result = {}
    for fmt in ("png", "svg", "pdf"):
        files = list(folder.glob(f"*.{fmt}"))
        if len(files) != 1:
            raise RuntimeError(f"Expected one {fmt} export, got {len(files)}")
        path = files[0]
        raw = path.read_bytes()
        if not raw:
            raise RuntimeError(f"Empty export: {path.name}")
        info = {"name": path.name, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
        if fmt == "png":
            with Image.open(path) as picture:
                picture.load()
                if min(picture.size) <= 1:
                    raise RuntimeError("PNG has no usable canvas")
                if all(low == high for low, high in picture.convert("RGB").getextrema()):
                    raise RuntimeError("PNG is a solid color instead of a chart")
                info["pixels"] = list(picture.size)
        elif fmt == "svg":
            root = ET.fromstring(raw)
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                raise RuntimeError("Invalid SVG root")
        elif not raw.startswith(b"%PDF-") or not raw.rstrip().endswith(b"%%EOF"):
            raise RuntimeError("Invalid or incomplete PDF")
        result[fmt] = info
    return result


def verify(executable: Path, timeout: float = 180) -> dict:
    executable = executable.resolve(strict=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="ptt-exe-acceptance-") as directory:
        root = Path(directory)
        target = root / "PeriodicTableTool.exe"
        shutil.copy2(executable, target)
        outputs = root / "exports"
        environment = dict(os.environ, PTT_SMOKE="1",
                           PTT_SMOKE_EXPORT_DIR=str(outputs),
                           PTT_USER_DIR=str(root / "user"))
        options = {}
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            options["startupinfo"] = startup
        process = subprocess.Popen([str(target)], cwd=root, env=environment, **options)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, check=False)
            else:
                process.kill()
            process.wait(timeout=15)
            raise RuntimeError(f"EXE acceptance timed out after {timeout:g} seconds") from None
        if code:
            raise RuntimeError(f"EXE exited with code {code}")
        exports = inspect_outputs(outputs, root / "smoke_progress.txt")
        return {"executable": str(executable),
                "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "exports": exports, "passed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", nargs="?", type=Path,
                        default=Path(__file__).resolve().parent / "dist/PeriodicTableTool.exe")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    result = verify(args.executable, args.timeout)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
