"""Document-backed editing controls, physical layout and reference-view entry points."""
from __future__ import annotations

import copy
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def parse_figure_size(text):
    text = str(text).strip().lower().replace("×", "x")
    factor = 25.4 if text.endswith("mm") else 1.0
    if factor != 1:
        text = text[:-2].strip()
    try:
        width, height = (float(value.strip()) / factor for value in text.split("x"))
    except (ValueError, TypeError) as exc:
        raise ValueError("画幅请输入 10x5（英寸）或 254x127 mm") from exc
    if not (math.isfinite(width) and math.isfinite(height) and 2 <= width <= 40 and 1 <= height <= 40):
        raise ValueError("画幅宽度须为 50.8～1016 mm，高度须为 25.4～1016 mm")
    return width, height


def parse_box(text):
    try:
        values = [float(value.strip()) for value in text.replace("，", ",").split(",")]
    except (ValueError, AttributeError) as exc:
        raise ValueError("位置参数必须是四个逗号分隔的数字") from exc
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        raise ValueError("位置参数必须是四个有限数字")
    return values


def _box_text(values):
    return ",".join(format(value, ".12g") for value in values)


class EditControlsMixin:
    def _editable_figure(self):
        return self._current_style_id() != "cmap_preview" and (
            not self.compat_var.get() or self._current_style_id() == "custom")

    def _sync_mark_selection(self):
        if not hasattr(self, "mark_symbol_var"):
            return
        symbol = self.mark_symbol_var.get()
        self.mark_value_var.set(str(self.data.get(symbol, "")))
        self.preview.set_selected(symbol)

    def _update_preview_edit_mode(self):
        self.preview.set_edit_enabled(self.mark_mode_var.get())

    def _sync_preview_edit_controls(self, style, colorbar_box=None):
        self._update_preview_edit_mode()
        self.preview.set_selected(self.mark_symbol_var.get())
        box = colorbar_box or style.get("cbar_box")
        if box is None and self.preview.fig is not None and len(self.preview.fig.axes) == 2:
            box = list(self.preview.fig.axes[1].get_position().bounds)
        if (not self._editable_figure() or style.get("bbox_tight", True)
                or not self.show_cbar_var.get() or style.get("kind") != "heatmap"):
            box = None
        self._displayed_colorbar_box = box
        self.preview.set_colorbar_box(box)

    def _set_element_options(self, symbol, options):
        from core.scientific import validate_element_overrides
        if not self._editable_figure():
            raise ValueError("请关闭原脚本兼容模式后调整单元素显示")
        candidate = copy.deepcopy(self.element_overrides)
        if options:
            candidate[symbol] = dict(options)
        else:
            candidate.pop(symbol, None)
        self.element_overrides = validate_element_overrides(candidate)
        self._refresh_preview()

    def _move_element_label(self, symbol, dx, dy):
        if not self.mark_mode_var.get() or not self._editable_figure():
            return
        row = dict(self.element_overrides.get(symbol, {}))
        row["value_dx"] = row.get("value_dx", 0) + dx
        row["value_dy"] = row.get("value_dy", 0) + dy
        try:
            self._set_element_options(symbol, row)
            self.status_var.set(f"已移动 {symbol} 标注；Ctrl+Z 撤销，可在显示 / 位置中复位")
        except ValueError as exc:
            self.status_var.set(f"未移动标注：{exc}")

    def _move_colorbar(self, x, y):
        box = getattr(self, "_displayed_colorbar_box", None)
        if not self.mark_mode_var.get() or not self._editable_figure() or box is None:
            return
        self._apply_edit_params({"cbar_box": _box_text([x, y, box[2], box[3]])})
        self.status_var.set("已移动颜色条；Ctrl+Z 撤销，精确尺寸中可恢复自动位置")

    def _apply_edit_params(self, values):
        from core.scientific import validate_render_options
        if not self._editable_figure():
            raise ValueError("请关闭原脚本兼容模式后调整尺寸")
        before = {key: self.param_vars[key].get() for key in values}
        restoring = self._restoring
        self._restoring = True
        try:
            for key, value in values.items():
                self.param_vars[key].set(value)
            validate_render_options(self._current_work_style())
        except Exception:
            for key, value in before.items():
                self.param_vars[key].set(value)
            raise
        finally:
            self._restoring = restoring
        self._refresh_preview()

    def _show_element_options(self):
        from core.elements_data import ALL_SYMBOLS
        symbol = self.mark_symbol_var.get()
        if symbol not in ALL_SYMBOLS:
            self.status_var.set("请先在预览中点击一个元素")
            return
        if not self._editable_figure():
            self.status_var.set("请关闭原脚本兼容模式后调整单元素显示")
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"{symbol} · 显示与位置（保留原数据）")
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        row = self.element_overrides.get(symbol, {})
        toggles = {}
        for key, label in (("show_value", "显示该元素的数值 / 标注"),
                           ("show_color", "显示该元素的数据着色"),
                           ("include_in_range", "参与自动色标范围计算")):
            var = toggles[key] = tk.BooleanVar(dialog, value=row.get(key, True))
            ttk.Checkbutton(frame, text=label, variable=var).pack(anchor="w", pady=3)
        offsets = {}
        for key, label in (("value_dx", "额外水平偏移（格宽，右为正）"),
                           ("value_dy", "额外垂直偏移（格高，上为正）")):
            ttk.Label(frame, text=label).pack(anchor="w")
            var = offsets[key] = tk.StringVar(dialog, value=str(row.get(key, 0)))
            ttk.Entry(frame, textvariable=var).pack(fill="x", pady=3)
        error = tk.StringVar(dialog)
        ttk.Label(frame, textvariable=error, foreground="#a62a2a", wraplength=350).pack(fill="x")

        def apply(reset=False):
            try:
                values = {} if reset else {**{k: v.get() for k, v in toggles.items()},
                                            **{k: float(v.get()) for k, v in offsets.items()}}
                self._set_element_options(symbol, values)
            except ValueError as exc:
                error.set(str(exc))
                return
            self.status_var.set(f"已更新 {symbol} 的显示与位置，原数据保留；Ctrl+Z 撤销")
            dialog.destroy()

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="应用", command=apply).pack(side="left", padx=3)
        ttk.Button(actions, text="恢复默认", command=lambda: apply(True)).pack(side="left", padx=3)
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="left", padx=3)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.grab_set()

    def _show_geometry_dialog(self):
        try:
            width, height = (v * 25.4 for v in parse_figure_size(self.param_vars["figsize"].get()))
            margins = parse_box(self.param_vars["margins"].get()) if self.param_vars["margins"].get() else [.04, .1, .88, .9]
            box = parse_box(self.param_vars["cbar_box"].get()) if self.param_vars["cbar_box"].get() else (
                getattr(self, "_displayed_colorbar_box", None) or [.91, .1, .025, .8])
        except ValueError as exc:
            messagebox.showerror("尺寸设置", str(exc), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("精确尺寸与边距 · 毫米")
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        values = {}
        fields = [("width", "画幅宽度", width), ("height", "画幅高度", height),
                  ("left", "主图区左边距", margins[0]*width),
                  ("bottom", "主图区下边距", margins[1]*height),
                  ("right", "主图区右边距", (1-margins[2])*width),
                  ("top", "主图区上边距", (1-margins[3])*height),
                  ("cx", "色条距画幅左侧", box[0]*width), ("cy", "色条距画幅底部", box[1]*height),
                  ("cw", "色条宽度", box[2]*width), ("ch", "色条高度", box[3]*height)]
        for index, (key, label, value) in enumerate(fields):
            ttk.Label(frame, text=label + "（mm）").grid(row=index, column=0, sticky="w", pady=3)
            values[key] = tk.StringVar(dialog, value=f"{value:.6g}")
            ttk.Entry(frame, textvariable=values[key], width=16).grid(row=index, column=1, sticky="ew", pady=3)
        auto_margins = tk.BooleanVar(dialog, value=not self.param_vars["margins"].get())
        auto_cbar = tk.BooleanVar(dialog, value=not self.param_vars["cbar_box"].get())
        ttk.Checkbutton(frame, text="自动主图区边距（忽略上面四项边距）", variable=auto_margins).grid(row=10, columnspan=2, sticky="w")
        ttk.Checkbutton(frame, text="自动颜色条位置（忽略上面四项色条尺寸）", variable=auto_cbar).grid(row=11, columnspan=2, sticky="w")
        ttk.Label(frame, text="紧裁切会改变最终画幅尺寸；精确尺寸建议使用固定画幅。", wraplength=360).grid(row=12, columnspan=2, sticky="w", pady=5)
        error = tk.StringVar(dialog)
        ttk.Label(frame, textvariable=error, foreground="#a62a2a", wraplength=360).grid(row=13, columnspan=2)

        def apply():
            try:
                v = {k: float(var.get()) for k, var in values.items()}
                if not all(math.isfinite(x) for x in v.values()) or v['width'] <= 0 or v['height'] <= 0:
                    raise ValueError("尺寸须为有限数字，宽高须为正数")
                w, h = v['width'], v['height']
                changes = {"figsize": f"{w:.12g}x{h:.12g} mm",
                    "margins": "" if auto_margins.get() else _box_text([v['left']/w,v['bottom']/h,1-v['right']/w,1-v['top']/h]),
                    "cbar_box": "" if auto_cbar.get() else _box_text([v['cx']/w,v['cy']/h,v['cw']/w,v['ch']/h])}
                self._apply_edit_params(changes)
            except (ValueError, ZeroDivisionError) as exc:
                error.set(str(exc))
                return
            dialog.destroy()

        ttk.Button(frame, text="应用尺寸", command=apply).grid(row=14, column=0, pady=8)
        ttk.Button(frame, text="取消", command=dialog.destroy).grid(row=14, column=1, pady=8)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.grab_set()

    def _open_reference(self, path=None):
        path = path or filedialog.askopenfilename(title="选择样图", filetypes=[("图片", "*.svg *.png *.jpg *.jpeg"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            from ui.reference_view import open_reference_window
            return open_reference_window(self, path, self.preview.current_image(),
                                         refresh_callback=self.preview.current_image)
        except Exception as exc:
            messagebox.showerror("无法打开样图", str(exc), parent=self)
