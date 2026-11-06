"""Callback-driven Excel import dialog; workbook access belongs to the caller."""
from __future__ import annotations

from collections.abc import Callable, Mapping
import tkinter as tk
from tkinter import ttk

from .scrolling import ScrollableFrame


class _WizardScroll(ScrollableFrame):
    def nametowidget(self, name):
        # ScrollableFrame stores its toplevel in _root, shadowing Tk's _root().
        if str(name).startswith("."):
            return self.master.nametowidget(name)
        return super().nametowidget(name)

    _nametowidget = nametowidget

    def _wheel(self, event):
        # Tk has already routed the event. A screen hit test can find a
        # different window when the dialog is covered or loses focus.
        target = event.widget
        if not self.winfo_ismapped() or not self._contains(target):
            return
        if isinstance(target, (ttk.Treeview, tk.Text, ttk.Combobox)):
            return
        if self.canvas.yview() == (0.0, 1.0):
            return
        delta = -1 if getattr(event, "num", None) == 4 else 1
        if getattr(event, "delta", 0):
            delta = max(1, abs(event.delta) // 120) * (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(delta * 3, "units")
        return "break"


class ExcelImportDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        sheets: list[str],
        on_preview: Callable[[str, str, str, str, str], dict],
        on_commit: Callable[[dict], None],
    ):
        super().__init__(parent)
        self.title("Excel 导入向导")
        self.geometry("480x400")
        self.minsize(250, 160)
        owner = parent.winfo_toplevel()
        if owner.winfo_viewable():
            self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self._on_preview = on_preview
        self._on_commit = on_commit
        self._result = None
        self._revision = 0
        self._busy = False

        self.sheet = tk.StringVar(self, value=sheets[0] if sheets else "")
        self.elements_range = tk.StringVar(self, value="B1:AG1")
        self.conditions_range = tk.StringVar(self, value="A2:A6")
        self.values_range = tk.StringVar(self, value="B2:AG6")
        self.direction = tk.StringVar(self, value="matrix_rows")
        self._inputs = (
            self.sheet, self.elements_range, self.conditions_range,
            self.values_range, self.direction,
        )
        self.status = tk.StringVar(self)

        footer = ttk.Frame(self, padding=8)
        footer.pack(side="bottom", fill="x")
        self.preview_button = ttk.Button(footer, text="预览", command=self._preview)
        self.commit_button = ttk.Button(footer, text="确认导入", command=self._commit)
        self.cancel_button = ttk.Button(footer, text="取消", command=self.destroy)
        for column, button in enumerate(
            (self.preview_button, self.commit_button, self.cancel_button)
        ):
            footer.columnconfigure(column, weight=1, uniform="actions")
            button.grid(row=0, column=column, sticky="ew", padx=2)

        self.scroll = _WizardScroll(self)
        self.scroll.pack(fill="both", expand=True)
        form = self.scroll.content
        form.columnconfigure(1, weight=1)
        for row, (label, variable) in enumerate(zip(
            ("工作表", "元素区域", "条件区域", "数值区域", "矩阵方向"), self._inputs,
        )):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8))
            if variable is self.sheet or variable is self.direction:
                options = sheets if variable is self.sheet else ("matrix_rows", "matrix_columns")
                control = ttk.Combobox(
                    form, textvariable=variable, values=options, state="readonly", width=1,
                )
            else:
                control = ttk.Entry(form, textvariable=variable, width=1)
            control.grid(row=row, column=1, sticky="ew", pady=4)

        self._summary = ttk.Label(form, textvariable=self.status, justify="left")
        self._summary.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.scroll.canvas.bind(
            "<Configure>",
            lambda event: self._summary.configure(wraplength=max(1, event.width - 24)),
            add="+",
        )
        for variable in self._inputs:
            variable.trace_add("write", self._invalidate)
        self._invalidate()

    def _sync_actions(self):
        self.preview_button.state(
            ["!disabled"] if self.sheet.get() and not self._busy else ["disabled"]
        )
        self.commit_button.state(
            ["!disabled"] if self._result is not None and not self._busy else ["disabled"]
        )

    def _invalidate(self, *_args):
        self._revision += 1
        self._result = None
        self.status.set("请预览当前设置。" if self.sheet.get() else "没有可用的工作表。")
        self._sync_actions()

    @staticmethod
    def _diagnostic_field(diagnostic, field):
        if isinstance(diagnostic, Mapping):
            return diagnostic.get(field, "")
        return getattr(diagnostic, field, "")

    def _show_status(self, message):
        self.status.set(message)
        self.update_idletasks()
        if self.winfo_exists():
            top = self._summary.winfo_y()
            height = self.scroll.content.winfo_height()
            self.scroll.canvas.yview_moveto(max(0, top - 8) / max(1, height))

    def _preview(self):
        if self._busy or not self.sheet.get():
            return
        self._invalidate()
        revision = self._revision
        self._busy = True
        self._sync_actions()
        try:
            result = self._on_preview(*(variable.get() for variable in self._inputs))
            datasets, diagnostics = result["datasets"], result["diagnostics"]
            if not isinstance(datasets, list) or not isinstance(diagnostics, list):
                raise ValueError("预览结果中的 datasets 和 diagnostics 必须是列表。")
            lines = [f"数据集：{len(datasets)}；诊断：{len(diagnostics)}"]
            has_error = False
            for diagnostic in diagnostics:
                severity = self._diagnostic_field(diagnostic, "severity")
                code = self._diagnostic_field(diagnostic, "code")
                message = self._diagnostic_field(diagnostic, "message")
                has_error |= str(severity).lower() == "error"
                lines.append(" ".join(str(part) for part in (severity, code, message) if part))
            can_commit = bool(datasets) and not has_error
            if not can_commit:
                lines.append("预览含有错误，无法导入。" if has_error else "没有可导入的数据集。")
            if self.winfo_exists() and revision == self._revision:
                self._result = result if can_commit else None
                self._show_status("\n".join(lines))
        except Exception as exc:
            if self.winfo_exists() and revision == self._revision:
                self._result = None
                self._show_status(f"预览失败：{exc}")
        finally:
            self._busy = False
            if self.winfo_exists():
                self._sync_actions()

    def _commit(self):
        if self._busy or self._result is None:
            return
        self._busy = True
        self._sync_actions()
        try:
            self._on_commit(self._result)
        except Exception as exc:
            if self.winfo_exists():
                self._result = None
                self._show_status(f"导入失败：{exc}\n请重新预览后再确认。")
        else:
            if self.winfo_exists():
                self.destroy()
        finally:
            self._busy = False
            if self.winfo_exists():
                self._sync_actions()
