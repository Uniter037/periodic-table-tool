# -*- coding: utf-8 -*-
"""元素周期表绘图工具 - 图形化入口。

运行: python main.py

功能：
- 14 种绘图模式（13 种与原脚本输出一致 + 1 种自定义扩展）
- 图形化数据输入：表格逐格编辑 / 文件导入 / 一键载入示例
- 输出自动改名，绝不覆盖已有文件
"""
from __future__ import annotations

import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 注意：不强制 matplotlib 后端。GUI 仅用于参数/数据输入，图片保存为文件，
# 与后端无关；强制 TkAgg 会与测试/无头环境冲突。

from core import (STYLES, parse_data, validate_data, demo_data,
                  known_symbols, render_table, render_cmap_preview,
                  save_figure, auto_name)
from core.elements_data import ALL_SYMBOLS

SYMBOLS = set(ALL_SYMBOLS)
FORMATS = ["svg", "png", "pdf"]


class DataTable(tk.Frame):
    """元素数据表格：118 行，双击编辑值列。"""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._edit_entry = None
        self._edit_item = None

        self.tree = ttk.Treeview(self, columns=("num", "symbol", "value"),
                                 show="headings", height=24)
        self.tree.heading("num", text="原子序数")
        self.tree.heading("symbol", text="符号")
        self.tree.heading("value", text="数值 / 标注")
        self.tree.column("num", width=70, anchor="center", stretch=False)
        self.tree.column("symbol", width=60, anchor="center", stretch=False)
        self.tree.column("value", width=140, anchor="center")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._start_edit)
        self._fill_rows()

    def _fill_rows(self):
        self.tree.delete(*self.tree.get_children())
        for i in range(1, 119):
            self.tree.insert("", "end",
                             values=(i, ALL_SYMBOLS[i - 1], ""))

    def _start_edit(self, event):
        if self._edit_entry is not None:
            # 双击其他行时，先提交当前正在编辑的内容
            self._commit_edit(self._edit_item, self._edit_entry)
        col = self.tree.identify_column(event.x)
        if col != "#3":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        x, y, w, h = self.tree.bbox(item, "#3")
        entry = tk.Entry(self.tree)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, self.tree.set(item, "value"))
        entry.focus_set()
        entry.bind("<Return>", lambda e: self._commit_edit(item, entry))
        entry.bind("<Escape>", lambda e: self._cancel_edit(entry))
        entry.bind("<FocusOut>", lambda e: self._commit_edit(item, entry))
        self._edit_entry = entry
        self._edit_item = item

    def _cancel_edit(self, entry):
        """取消编辑：销毁输入框并重置状态，不写回任何值。"""
        entry.destroy()
        if self._edit_entry is entry:
            self._edit_entry = None
            self._edit_item = None

    def _commit_edit(self, item, entry):
        if self._edit_entry is not entry:
            # 输入框已被取消/销毁，忽略
            return
        value = entry.get().strip()
        entry.destroy()
        self._edit_entry = None
        self._edit_item = None
        self.tree.set(item, "value", value)

    def set_data(self, data: dict):
        """用字典数据填充表格。"""
        self._fill_rows()
        for child in self.tree.get_children():
            sym = self.tree.set(child, "symbol")
            if sym in data:
                self.tree.set(child, "value", str(data[sym]))

    def get_data(self) -> dict:
        """读取表格数据为 {符号: 值}。"""
        data = {}
        for child in self.tree.get_children():
            val = self.tree.set(child, "value").strip()
            if val:
                data[self.tree.set(child, "symbol")] = val
        return data

    def clear(self):
        self._fill_rows()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("元素周期表绘图工具")
        self.geometry("1080x640")
        self.minsize(960, 560)

        # 输出目录：默认项目 output/
        self.out_dir = os.path.join(PROJECT_ROOT, "output")
        self.last_output = None

        self._build_ui()
        self._on_style_change()

    # ------------------------------------------------------------------
    def _build_ui(self):
        main = ttk.Frame(self, padding=8)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        # ---- 左侧控制面板 ----
        left = ttk.LabelFrame(main, text="绘图设置", padding=8)
        left.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 8))

        ttk.Label(left, text="绘图模式").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar()
        self.mode_combo = ttk.Combobox(left, textvariable=self.mode_var,
                                       state="readonly", width=34)
        names = [s["name"] for s in STYLES.values()]
        self.mode_combo["values"] = names
        self.mode_combo.grid(row=0, column=1, columnspan=3, sticky="we", pady=(2, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_style_change())
        self.mode_combo.current(0)

        # 对应原文件说明
        self.file_label = ttk.Label(left, text="", foreground="#666666", wraplength=300)
        self.file_label.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))

        # 参数（自定义模式可编辑；其他模式只读显示默认值）
        params = [
            ("cmap", "颜色映射"),
            ("vmin", "最小值 vmin"),
            ("vcenter", "中心值 vcenter"),
            ("vmax", "最大值 vmax"),
            ("fmt", "数值格式"),
            ("title", "图标题"),
        ]
        self.param_vars = {}
        self.param_entries = {}
        for r, (key, label) in enumerate(params, start=2):
            ttk.Label(left, text=label).grid(row=r, column=0, sticky="w")
            var = tk.StringVar()
            entry = ttk.Entry(left, textvariable=var, width=26)
            entry.grid(row=r, column=1, columnspan=3, sticky="we", pady=2)
            self.param_vars[key] = var
            self.param_entries[key] = entry

        # 输出设置
        out_row = 8
        ttk.Label(left, text="输出格式").grid(row=out_row, column=0, sticky="w", pady=(10, 0))
        self.fmt_var = tk.StringVar(value="svg")
        fmt_combo = ttk.Combobox(left, textvariable=self.fmt_var, state="readonly",
                                 values=FORMATS, width=8)
        fmt_combo.grid(row=out_row, column=1, sticky="w", pady=(10, 0))

        ttk.Label(left, text="输出目录").grid(row=out_row + 1, column=0, sticky="w", pady=(6, 0))
        self.out_var = tk.StringVar(value=self.out_dir)
        out_entry = ttk.Entry(left, textvariable=self.out_var, width=20)
        out_entry.grid(row=out_row + 1, column=1, columnspan=2, sticky="we", pady=(6, 0))
        ttk.Button(left, text="浏览", width=5,
                   command=self._choose_out_dir).grid(row=out_row + 1, column=3, pady=(6, 0))

        ttk.Button(left, text="生成图片", command=self.generate).grid(
            row=out_row + 2, column=0, columnspan=4, sticky="we", pady=(12, 4))
        ttk.Button(left, text="打开输出目录", command=self._open_out_dir).grid(
            row=out_row + 3, column=0, columnspan=4, sticky="we", pady=4)

        self.hint_label = ttk.Label(left, text="", foreground="#888888",
                                    wraplength=310, justify="left")
        self.hint_label.grid(row=out_row + 4, column=0, columnspan=4, sticky="w", pady=(10, 0))

        # ---- 右侧数据面板 ----
        right = ttk.LabelFrame(main, text="元素数据（双击「数值 / 标注」列可直接编辑）", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.table = DataTable(right)
        self.table.grid(row=0, column=0, sticky="nsew")

        btns = ttk.Frame(right)
        btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="载入示例数据", command=self._load_demo).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="导入数据文件", command=self._import_file).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="清空数据", command=self.table.clear).pack(side="left")

        # ---- 状态栏 ----
        status = ttk.Frame(main)
        status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var, foreground="#333333").pack(side="left")

    # ------------------------------------------------------------------
    def _current_style_id(self) -> str:
        return list(STYLES.keys())[self.mode_combo.current()]

    def _on_style_change(self):
        style_id = self._current_style_id()
        style = STYLES[style_id]
        self.file_label.config(text=f"对应原脚本：{style['file']}")

        # 参数回填
        norm = style.get("norm")
        self.param_vars["cmap"].set(_cmap_name(style))
        self.param_vars["vmin"].set(str(norm[1]) if norm else "")
        self.param_vars["vcenter"].set(str(norm[2]) if norm and norm[0] == "twoslope" else "")
        self.param_vars["vmax"].set(str(norm[-1]) if norm else "")
        self.param_vars["fmt"].set(style.get("fmt", ""))
        self.param_vars["title"].set("")

        # 只读（非自定义模式参数不可改，保证与原脚本一致）
        editable = style.get("customizable", False)
        for key in ("cmap", "vmin", "vcenter", "vmax", "fmt"):
            self.param_entries[key].config(state="normal" if editable else "readonly")

        # 模式提示
        if style_id == "cmap_preview":
            self.hint_label.config(text="本模式生成所有 matplotlib 颜色映射的预览图，无需数据。")
        elif style.get("kind") == "labels":
            self.hint_label.config(text="标注模式：数值列填文本标注（如 3c1、1b）。")
        else:
            self.hint_label.config(text="热力图模式：数值列填数字，缺失元素显示为空/灰格。")

    # ------------------------------------------------------------------
    def _load_demo(self):
        style_id = self._current_style_id()
        data = demo_data(style_id)
        if not data:
            messagebox.showinfo("提示", "该模式没有内置示例数据，请手动输入或导入文件。")
            return
        self.table.set_data(data)
        self.status_var.set(f"已载入示例数据（{len(data)} 个元素）")

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="选择数据文件",
            filetypes=[("数据文件", "*.txt *.csv *.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            data = parse_data(text)
            if not data:
                raise ValueError("文件中没有可解析的数据")
            self.table.set_data(data)
            self.status_var.set(f"已从 {os.path.basename(path)} 导入 {len(data)} 条数据")
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    # ------------------------------------------------------------------
    def generate(self):
        style_id = self._current_style_id()
        style = STYLES[style_id]
        out_dir = self.out_var.get().strip() or self.out_dir

        try:
            if style_id == "cmap_preview":
                self._generate_cmap_preview(out_dir)
                return

            # 读取并校验数据
            raw = self.table.get_data()
            if not raw:
                messagebox.showwarning("提示", "请先输入数据：表格编辑、导入文件或载入示例。")
                return

            if style.get("kind") == "labels":
                data = raw
                unknown = [s for s in data if s not in known_symbols()]
                if unknown:
                    messagebox.showwarning("未知元素", f"以下符号不在周期表中，将被忽略：{', '.join(unknown)}")
                    data = {s: v for s, v in data.items() if s in known_symbols()}
            else:
                data, unknown, bad = validate_data(raw)
                if unknown:
                    messagebox.showwarning("未知元素", f"以下符号不在周期表中，将被忽略：{', '.join(unknown)}")
                # 无法转成数字的字符串不能用于热力图，提示并过滤
                bad = bad + [(s, v) for s, v in data.items() if isinstance(v, str)]
                data = {s: v for s, v in data.items() if not isinstance(v, str)}
                if bad:
                    messagebox.showwarning("非法值", f"以下数据不是有效数字，将被忽略：{bad}")

            # 自定义模式：应用面板参数（含标题）；其他模式保持与原脚本一致（无标题）
            work_style = style
            if style.get("customizable"):
                work_style = self._apply_custom_params(style)

            fmt = self.fmt_var.get()
            title = (self.param_vars["title"].get().strip()
                     if style.get("customizable") else "")
            fig = render_table(work_style, data, title=title or None)
            path = save_figure(fig, out_dir, "periodic_table", fmt,
                               bbox_inches="tight" if work_style.get("bbox_tight", True) else None)
            import matplotlib.pyplot as plt
            plt.close(fig)

            self.last_output = path
            self.status_var.set(f"已生成：{path}")
            if messagebox.askyesno("完成", f"图片已保存到：\n{path}\n\n是否打开查看？"):
                webbrowser.open(path)
        except Exception as exc:
            messagebox.showerror("生成失败", str(exc))

    def _generate_cmap_preview(self, out_dir):
        paths = render_cmap_preview(out_dir)
        self.last_output = out_dir
        self.status_var.set(f"已生成 {len(paths)} 张颜色映射预览图 → {out_dir}")
        messagebox.showinfo("完成", f"已生成 {len(paths)} 张预览图：\n{out_dir}")

    def _apply_custom_params(self, style):
        import copy
        from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
        work = copy.deepcopy(style)
        cmap_name = self.param_vars["cmap"].get().strip()
        try:
            vmin = float(self.param_vars["vmin"].get())
            vmax = float(self.param_vars["vmax"].get())
        except ValueError as exc:
            raise ValueError("vmin / vmax 必须是数字") from exc
        center_text = self.param_vars["vcenter"].get().strip()
        work["norm"] = ("twoslope", vmin, float(center_text), vmax) if center_text else ("normalize", vmin, vmax)
        work["fmt"] = self.param_vars["fmt"].get().strip() or "3f"
        work["cmap"] = cmap_name if cmap_name else "coolwarm"
        return work

    # ------------------------------------------------------------------
    def _choose_out_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_var.set(path)

    def _open_out_dir(self):
        path = self.out_var.get().strip() or self.out_dir
        try:
            os.makedirs(path, exist_ok=True)
            webbrowser.open(path)
        except OSError as exc:
            messagebox.showerror("打开失败", f"无法打开输出目录：{exc}")


def _cmap_name(style):
    spec = style.get("cmap")
    if isinstance(spec, tuple) and spec[0] == "custom":
        return "自定义(蓝-白-红)"
    return spec or ""


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
