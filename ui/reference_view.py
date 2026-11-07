"""Nonmodal, read-only reference comparison with independently owned snapshots."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk

from core.reference_image import load_reference_image, snapshot_image


class _ImagePane(ttk.Frame):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.image = self.photo = None
        self.zoom = 1.0
        self.pan = [0, 0]
        self.origin = None
        ttk.Label(self, text=title).pack(anchor="w")
        tools = ttk.Frame(self)
        tools.pack(fill="x")
        for text, command in [("−", lambda: self.scale(1 / 1.2)),
                              ("+", lambda: self.scale(1.2)), ("适合窗口", self.fit)]:
            ttk.Button(tools, text=text, command=command).pack(side="left")
        self.canvas = tk.Canvas(self, background="#e4e8ee", highlightthickness=0,
                                width=320, height=320)
        self.canvas.pack(fill="both", expand=True)
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.empty = self.canvas.create_text(160, 160, text="暂无图像", fill="#555555")
        self.canvas.bind("<Configure>", self.draw)
        self.canvas.bind("<MouseWheel>", lambda e: self.scale(1.2 if e.delta > 0 else 1/1.2))
        self.canvas.bind("<Button-4>", lambda e: self.scale(1.2))
        self.canvas.bind("<Button-5>", lambda e: self.scale(1/1.2))
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.move_pan)

    def set_image(self, image):
        old = self.image
        self.image = image
        self.fit()
        if old is not None:
            old.close()

    def fit(self):
        self.zoom, self.pan = 1.0, [0, 0]
        self.draw()

    def scale(self, factor):
        self.zoom = max(.1, min(16, self.zoom * factor))
        self.draw()

    def start_pan(self, event):
        self.origin = event.x, event.y, *self.pan

    def move_pan(self, event):
        if self.origin:
            x, y, px, py = self.origin
            self.pan = [px + event.x - x, py + event.y - y]
            self.draw()

    def draw(self, event=None):
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        self.canvas.coords(self.empty, width // 2, height // 2)
        self.canvas.itemconfigure(self.empty, state="normal" if self.image is None else "hidden")
        if self.image is None:
            self.canvas.itemconfigure(self.item, image="")
            self.photo = None
            return
        sw, sh = self.image.size
        scale = min(width / sw, height / sh) * self.zoom
        left = (width - sw * scale) / 2 + self.pan[0]
        top = (height - sh * scale) / 2 + self.pan[1]
        # Render only the viewport, even at maximum zoom (no huge resized bitmap).
        with self.image.transform((width, height), Image.Transform.AFFINE,
                                  (1/scale, 0, -left/scale, 0, 1/scale, -top/scale),
                                  Image.Resampling.BICUBIC) as visible:
            self.photo = ImageTk.PhotoImage(visible, master=self.canvas)
        self.canvas.itemconfigure(self.item, image=self.photo)

    def destroy(self):
        if self.image is not None:
            self.image.close()
        self.image = self.photo = None
        super().destroy()


def open_reference_window(parent, path, current_image, refresh_callback=None) -> tk.Toplevel:
    """Open a nonmodal comparison; callback() may return a new PIL.Image or None.

    Ownership of supplied PIL copies transfers to this window; they are closed
    when replaced or destroyed. Independent display snapshots are also owned.
    Failures retain the previous image and appear
    inline. No grab_set/wait_window, automatic refresh, or style extraction.

    reference_loaded reports whether the latest non-cancelled load succeeded;
    reference_error is its readable error (None on success/no attempt).
    reference_path identifies the currently displayed reference, retained on error.
    """
    window = tk.Toplevel(parent)
    window.reference_loaded = False
    window.reference_error = None
    window.reference_path = None
    window.title("样图对照")
    window.geometry("1060x650")
    window.minsize(640, 400)
    owned = [current_image]
    def release_input(event):
        if event.widget is window:
            if isinstance(owned[0], Image.Image):
                owned[0].close()
            owned[0] = None
    window.bind("<Destroy>", release_input, add="+")
    status = tk.StringVar(window)
    toolbar = ttk.Frame(window, padding=8)
    toolbar.pack(fill="x")
    panes = ttk.Panedwindow(window, orient="horizontal")
    panes.pack(fill="both", expand=True, padx=8)
    reference = _ImagePane(panes, "左：参考原图（只读）")
    current = _ImagePane(panes, "右：当前预览快照（不会自动同步）")
    panes.add(reference, weight=1)
    panes.add(current, weight=1)

    def load(selected):
        if not selected:
            return
        window.reference_loaded = False
        window.reference_error = None
        try:
            reference.set_image(load_reference_image(selected))
            window.reference_loaded = True
            window.reference_path = str(selected)
            status.set(f"参考图：{selected}")
        except Exception as exc:
            window.reference_error = str(exc)
            status.set(f"参考图加载失败：{exc}")

    def choose():
        load(filedialog.askopenfilename(parent=window, title="选择参考图",
             filetypes=[("参考图", "*.png *.jpg *.jpeg *.svg")]))

    def refresh():
        incoming = None
        try:
            incoming = refresh_callback()
            current.set_image(snapshot_image(incoming))
            if isinstance(owned[0], Image.Image) and owned[0] is not incoming:
                owned[0].close()
            owned[0] = incoming
            status.set("当前预览快照已手动刷新。")
        except Exception as exc:
            if isinstance(incoming, Image.Image) and incoming is not owned[0]:
                incoming.close()
            status.set(f"刷新失败，保留原快照：{exc}")

    ttk.Button(toolbar, text="加载参考图…", command=choose).pack(side="left")
    ttk.Button(toolbar, text="手动刷新当前快照", command=refresh,
               state="normal" if refresh_callback else "disabled").pack(side="left", padx=8)
    ttk.Label(toolbar, text="滚轮或 ± 缩放；左键拖动平移").pack(side="left")
    ttk.Label(window, text="仅作视觉对照，不会自动提取样式；右侧为打开时/手动刷新时的快照。",
              padding=8).pack(fill="x")
    ttk.Label(window, textvariable=status, wraplength=1000, padding=8).pack(fill="x")
    if path:
        load(path)
    try:
        current.set_image(snapshot_image(current_image))
    except Exception as exc:
        status.set(f"当前快照加载失败：{exc}")
    return window
