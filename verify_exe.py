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


def inspect_agent_interface(target, root, environment, options, timeout):
    """Exercise the same windowed binary using JSON files, without opening Tk."""
    counter = 0
    def call(request, expected_ok=True):
        nonlocal counter
        counter += 1
        source = root / f"agent-request-{counter}.json"
        response = root / f"agent-response-{counter}.json"
        source.write_text(json.dumps({"api_version":1, **request}), encoding="utf-8")
        process = subprocess.run([str(target), "--agent-request", str(source),
                                  "--agent-response", str(response)], cwd=root, env=environment,
                                 timeout=min(timeout, 60), **options)
        result = json.loads(response.read_text(encoding="utf-8"))
        if result.get("ok") is not expected_ok or process.returncode != (0 if expected_ok else 2):
            raise RuntimeError(f"Agent interface failed: {result}")
        return result
    description = call({"action":"describe"})["result"]
    if "update" not in description["actions"]:
        raise RuntimeError("Agent capability discovery incomplete")
    project = root / "agent-project.ptproj"
    created = call({"action":"create", "project":str(project), "patch":{
        "data":{"Y":.73925}, "params":{"vmin":"0.72","vcenter":"0.7318","vmax":"0.76",
        "fmt":"四位小数", "layout":"镧锕三行块（重构）"}}})["result"]
    changed = call({"action":"update", "project":str(project),
                    "expected_revision":created["revision"], "patch":{"data":{"Fe":.73},
                    "element_overrides":{"Y":{"show_value":False}}}})["result"]
    conflict = call({"action":"update", "project":str(project),
                     "expected_revision":created["revision"], "patch":{"data":{"Y":999}}}, False)
    if conflict['error']['code'] != 'REVISION_CONFLICT':
        raise RuntimeError("Stale writes were not rejected")
    checked = call({"action":"inspect", "project":str(project)})["result"]
    if checked['document']['current']['data'] != {'Y':.73925, 'Fe':.73}:
        raise RuntimeError("Agent edits lost measurements")
    exported = call({"action":"export", "project":str(project), "expected_revision":changed['revision'],
                     "output_dir":str(root/'agent_exports'),"formats":["png","svg","pdf"]})['result']
    if len(exported['files']) != 3 or any(not Path(f['path']).is_file() for f in exported['files']):
        raise RuntimeError("Agent export did not publish all requested formats")
    return {"passed":True,"commands":counter,"stale_write_rejected":True,"formats":["png","svg","pdf"]}


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
        agent = inspect_agent_interface(target, root, environment, options, timeout)
        return {"executable": str(executable),
                "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "exports": exports, "agent_interface": agent, "passed": True}


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
