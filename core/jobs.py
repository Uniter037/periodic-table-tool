"""Persistent, spawn-only Agg renderer; no Tk objects cross the process boundary.

Only the latest queued request is kept. Invalidation suppresses all messages from
the running request without restarting the worker. Explicit cancellation stops
the process and removes its private staging tree. Export paths from ``done``
remain valid until the next request is dispatched or ``cancel()``.
Callers own publication of completed exports and must poll from one thread.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
from pathlib import Path
import shutil
import tempfile


def _run(request, directory, connection, request_id):
    plt = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from .styles import render_table, render_cmap_preview, CMAP_PREVIEW_LIST
        from .imaging import rasterize, save_options

        request = pickle.loads(request)
        mode = request["mode"]
        if mode == "cmap":
            paths = []
            for index, name in enumerate(CMAP_PREVIEW_LIST):
                paths.extend(render_cmap_preview(directory, [name]))
                connection.send((request_id, "progress", index + 1, len(CMAP_PREVIEW_LIST)))
            result = {"files": [(p, Path(p).stem) for p in paths]}
        else:
            if mode not in ("preview", "export", "batch"):
                raise ValueError(f"未知绘图任务: {mode}")
            items = request.get("items")
            if items is None:
                items = [("periodic_table", request["data"])]
            if not items or (mode == "preview" and len(items) != 1):
                raise ValueError("预览需要一组数据；导出需要至少一组数据")
            result = {"files": []}
            for index, (name, data) in enumerate(items):
                style = request["style"]
                fig = render_table(style, data, title=request.get("title") or None,
                                   show_cbar=request["show_cbar"], figsize=style.get("figsize", (10, 5)))
                try:
                    if mode == "preview":
                        # Keep physical layout, cap only the preview raster resolution.
                        fig.set_dpi(min(style.get("dpi", 100), 100,
                                        1600 / max(fig.get_size_inches())))
                        source, hits = rasterize(fig, request.get("hit_map"),
                                                 style.get("bbox_tight", True),
                                                 transparent=style.get("transparent", False))
                        from io import BytesIO
                        with BytesIO() as buffer:
                            source.save(buffer, format="PNG")
                            result = {"png": buffer.getvalue(), "hits": hits}
                        source.close()
                    else:
                        fmt = request["format"].lower()
                        if fmt not in ("png", "svg", "pdf"):
                            raise ValueError(f"不支持的输出格式: {fmt}")
                        path = str(Path(directory) / f"{index}.{fmt}")
                        fig.savefig(path, **save_options(style))
                        result["files"].append((path, name))
                finally:
                    plt.close(fig)
                connection.send((request_id, "progress", index + 1, len(items)))
        temporary = Path(directory) / "result.tmp"
        with temporary.open("wb") as stream:
            pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporary, Path(directory) / "result.pkl")
        connection.send((request_id, "done"))
    except BaseException as exc:
        connection.send((request_id, "error", f"{type(exc).__name__}: {exc}"))
    finally:
        if plt is not None:
            plt.close("all")


def _service(directory, connection):
    try:
        while True:
            request_id, request = connection.recv()
            _run(request, str(Path(directory) / str(request_id)), connection, request_id)
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class RenderJob:
    def __init__(self):
        self.process = self.connection = self.directory = None
        self.busy = False
        self.pending = None
        self._sequence = 0
        self._current = None
        self._obsolete = False
        self._staging = None

    @property
    def active(self):
        return self.busy

    def start(self, request):
        """Snapshot the request now; coalesce updates while the worker is busy."""
        snapshot = pickle.dumps(request, protocol=pickle.HIGHEST_PROTOCOL)
        if self.busy:
            self.pending = snapshot
            self._obsolete = True
        else:
            self._dispatch(snapshot)

    def _dispatch(self, snapshot):
        try:
            if self.process is not None and not self.process.is_alive():
                self.cancel()
            if self.process is None:
                self.directory = tempfile.TemporaryDirectory(prefix="ptable-render-")
                context = mp.get_context("spawn")
                self.connection, child = context.Pipe(duplex=True)
                self.process = context.Process(target=_service,
                                               args=(self.directory.name, child), daemon=True)
                try:
                    self.process.start()
                finally:
                    child.close()
            self._clear_staging()
            self._sequence += 1
            self._current = self._sequence
            self._staging = Path(self.directory.name) / str(self._current)
            self._staging.mkdir()
            self.connection.send((self._current, snapshot))
            self.busy, self._obsolete = True, False
        except BaseException:
            self.cancel()
            raise

    def invalidate(self):
        """Invalidate running AND queued results, including during UI debounce."""
        if self.busy:
            self._obsolete = True
            self.pending = None

    def _clear_staging(self):
        if self._staging is not None:
            shutil.rmtree(self._staging)
            self._staging = None

    def _worker_failed(self, reason):
        obsolete, pending = self._obsolete, self.pending
        self.cancel()
        if obsolete:
            return self._advance(pending)
        return ("error", reason)

    def _advance(self, pending):
        if pending is not None:
            try:
                self._dispatch(pending)
            except Exception as exc:
                return ("error", f"无法启动最新绘图请求: {exc}")
        return ("obsolete",)

    def poll(self):
        """Return progress/done/error/obsolete tuples, or None; errors fire once."""
        if self.connection is None:
            return None
        try:
            while self.connection.poll():
                request_id, kind, *payload = self.connection.recv()
                if request_id != self._current or not self.busy:
                    continue
                if kind == "progress":
                    if self._obsolete:
                        continue
                    return (kind, *payload)
                self.busy = False
                if self._obsolete:
                    pending, self.pending = self.pending, None
                    self._clear_staging()
                    self._obsolete = False
                    return self._advance(pending)
                if kind == "done":
                    try:
                        with (self._staging / "result.pkl").open("rb") as stream:
                            result = pickle.load(stream)
                    except Exception as exc:
                        self._clear_staging()
                        return ("error", f"无法读取绘图结果: {exc}")
                    if "png" in result:
                        self._clear_staging()
                    else:
                        (self._staging / "result.pkl").unlink()
                    return ("done", result)
                self._clear_staging()
                return ("error", payload[0] if payload else "未知绘图错误")
            if self.process is not None and not self.process.is_alive():
                return self._worker_failed(f"绘图进程退出（{self.process.exitcode}）")
        except (EOFError, OSError) as exc:
            return self._worker_failed(f"绘图进程异常退出: {exc}")
        return None

    def cancel(self):
        """Stop/join the worker and delete all unpublished output; reusable."""
        self.busy, self.pending, self._obsolete = False, None, False
        if self.process is not None:
            # A failed Process.start() has no PID and cannot be joined.
            if self.process.pid is not None:
                if self.process.is_alive():
                    self.process.terminate()
                self.process.join(timeout=1)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join()
            self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        if self.directory is not None:
            self.directory.cleanup()
            self.directory = None
        self._staging = self._current = None
