"""固定画幅的预览：缩放栅格，不改变 Figure 的尺寸或布局。"""
from __future__ import annotations

import tkinter as tk

from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image, ImageTk
from core.imaging import rasterize


class PreviewCanvas(tk.Frame):
    def __init__(self, master, on_click=None, **kw):
        super().__init__(master, **kw)
        self.on_click = on_click
        self.fig = self.canvas = None
        self.hit_map = {}
        self._source = self._photo = None
        self._display_box = None
        self._pixel_hits = {}
        self.zoom = 1.0
        self.pan = [0, 0]
        self._surface = tk.Canvas(self, highlightthickness=0, background="#e4e8ee",
                                  width=100, height=100)
        self._surface.pack(fill="both", expand=True)
        self._paper = self._surface.create_rectangle(0, 0, 0, 0, fill="white", outline="#c7cdd6")
        self._item = self._surface.create_image(0, 0, anchor="nw")
        self._stale = tk.Label(self, text="旧预览 · 当前设置或数据无效，请查看底部提示", bg="#fff1d6", fg="#8a3b12")
        self._surface.bind("<Configure>", self.resize)
        self._surface.bind("<Button-1>", self._on_surface_click)
        self._surface.bind("<MouseWheel>", self._wheel)
        self._surface.bind("<ButtonPress-2>", self._pan_start)
        self._surface.bind("<B2-Motion>", self._pan_move)
        self._surface.bind("<ButtonPress-3>", self._pan_start)
        self._surface.bind("<B3-Motion>", self._pan_move)
        self._surface.bind("<Double-Button-3>", lambda e: self.fit())

    def fit(self):
        self.zoom, self.pan = 1.0, [0, 0]
        self._display_box = None
        self.resize()

    def _wheel(self, event):
        self.zoom = max(.25, min(8, self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
        self.resize()

    def _pan_start(self, event):
        self._pan_origin = (event.x, event.y, *self.pan)

    def _pan_move(self, event):
        if not hasattr(self, "_pan_origin"):
            return
        x, y, px, py = self._pan_origin
        self.pan = [px + event.x - x, py + event.y - y]
        self.resize()

    def set_stale(self, stale):
        if stale:
            self._stale.place(x=6, y=6, relwidth=.96)
        else:
            self._stale.place_forget()

    def show(self, fig, hit_map, tight=False):
        """成功渲染后替换预览；失败时释放新 Figure 并保留旧图。"""
        import matplotlib.pyplot as plt
        try:
            source, pixel_hits = rasterize(fig, hit_map, tight=tight)
            canvas = fig.canvas
        except Exception:
            if fig is not self.fig:
                plt.close(fig)
            raise
        try:
            self._replace_source(source, pixel_hits, fig, canvas, hit_map or {})
        except Exception:
            if fig is not self.fig:
                plt.close(fig)
            raise

    def show_packet(self, png, pixel_hits):
        """Decode before swapping; a failed display retains old pixels AND hits."""
        from io import BytesIO
        pixel_hits = dict(pixel_hits)
        with Image.open(BytesIO(png)) as image:
            source = image.convert("RGBA")
        self._replace_source(source, pixel_hits, None, None, {})

    def _replace_source(self, source, pixel_hits, fig, canvas, hit_map):
        import matplotlib.pyplot as plt
        attributes = ("fig", "canvas", "hit_map", "_source", "_pixel_hits",
                      "_display_box", "_photo")
        old = tuple(getattr(self, name) for name in attributes)
        self.fig, self.canvas, self.hit_map = fig, canvas, hit_map
        self._source, self._pixel_hits = source, pixel_hits
        self._display_box = None
        try:
            self.resize()
        except Exception:
            for name, value in zip(attributes, old):
                setattr(self, name, value)
            # resize may have moved the Tk items before its final operation failed.
            if self._display_box is not None:
                try:
                    self._position_image(self._display_box, self._photo)
                except tk.TclError:
                    pass
            source.close()
            raise
        if old[0] is not None and old[0] is not fig:
            plt.close(old[0])
        if old[3] is not None and old[3] is not source:
            old[3].close()

    def resize(self, event=None):
        if self._source is None:
            return
        width, height = self._surface.winfo_width(), self._surface.winfo_height()
        sw, sh = self._source.size
        scale = min(width / sw, height / sh) * self.zoom
        dw, dh = max(1, round(sw * scale)), max(1, round(sh * scale))
        box = ((width - dw) // 2 + self.pan[0], (height - dh) // 2 + self.pan[1], dw, dh)
        if box == self._display_box:
            return
        photo = ImageTk.PhotoImage(self._source.resize((dw, dh), Image.Resampling.LANCZOS),
                                   master=self._surface)
        self._position_image(box, photo)
        self._photo, self._display_box = photo, box

    def _position_image(self, box, photo):
        left, top, width, height = box
        self._surface.coords(self._paper, left, top, left + width, top + height)
        self._surface.coords(self._item, left, top)
        self._surface.itemconfigure(self._item, image=photo)

    def _on_surface_click(self, event):
        if self._display_box is None or self._source is None:
            return
        left, top, width, height = self._display_box
        if not (left <= event.x < left + width and top <= event.y < top + height):
            return
        sw, sh = self._source.size
        x, y = (event.x - left) * sw / width, (event.y - top) * sh / height
        for (x0, y0, x1, y1), symbol in self._pixel_hits.items():
            if x0 <= x <= x1 and y0 <= y <= y1 and self.on_click:
                self.on_click(symbol)
                break

    def _on_click(self, event):
        """兼容已有 Matplotlib 点击事件调用方。"""
        if (self.fig is None or not self.fig.axes or
                event.inaxes is not self.fig.axes[0] or event.button != 1):
            return
        symbol = self.hit_test(event.xdata, event.ydata)
        if symbol and self.on_click:
            self.on_click(symbol)

    def hit_test(self, x, y):
        if x is None or y is None:
            return None
        for (x0, y0, x1, y1), symbol in self.hit_map.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                return symbol
        return None

    def destroy(self):
        import matplotlib.pyplot as plt
        if self.fig is not None:
            plt.close(self.fig)
        if self._source is not None:
            self._source.close()
        self.fig = self.canvas = self._source = self._photo = None
        self.hit_map, self._pixel_hits, self._display_box = {}, {}, None
        super().destroy()
