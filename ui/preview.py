"""固定画幅的预览：缩放栅格，不改变 Figure 的尺寸或布局。"""
from __future__ import annotations

import tkinter as tk

from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image, ImageTk
from core.imaging import rasterize


class PreviewCanvas(tk.Frame):
    def __init__(self, master, on_click=None, on_move=None, on_colorbar_move=None, **kw):
        super().__init__(master, **kw)
        self.on_click = on_click
        self.on_move = on_move
        self.on_colorbar_move = on_colorbar_move
        self._selected = self._colorbar_box = self._drag = None
        self._drag_target = None
        self._edit_enabled, self._is_stale = True, False
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
        self._surface.bind("<B1-Motion>", self._on_surface_drag)
        self._surface.bind("<ButtonRelease-1>", self._on_surface_release)
        self._surface.bind("<Escape>", self._cancel_drag)
        self._surface.bind("<MouseWheel>", self._wheel)
        self._surface.bind("<ButtonPress-2>", self._pan_start)
        self._surface.bind("<B2-Motion>", self._pan_move)
        self._surface.bind("<ButtonPress-3>", self._pan_start)
        self._surface.bind("<B3-Motion>", self._pan_move)
        self._surface.bind("<Double-Button-3>", lambda e: self.fit())

    def fit(self):
        self._cancel_drag()
        self.zoom, self.pan = 1.0, [0, 0]
        self._display_box = None
        self.resize()

    def _wheel(self, event):
        self._cancel_drag()
        self.zoom = max(.25, min(8, self.zoom * (1.15 if event.delta > 0 else 1 / 1.15)))
        self.resize()

    def _pan_start(self, event):
        self._cancel_drag()
        self._pan_origin = (event.x, event.y, *self.pan)

    def _pan_move(self, event):
        if not hasattr(self, "_pan_origin"):
            return
        x, y, px, py = self._pan_origin
        self.pan = [px + event.x - x, py + event.y - y]
        self.resize()

    def set_stale(self, stale):
        self._is_stale = bool(stale)
        if stale:
            self._cancel_drag()
        self._draw_overlays()
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
        self._cancel_drag()
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
                    self._draw_overlays()
                except tk.TclError:
                    pass
            source.close()
            raise
        self._drag = None
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
        self._cancel_drag()
        photo = ImageTk.PhotoImage(self._source.resize((dw, dh), Image.Resampling.LANCZOS),
                                   master=self._surface)
        self._position_image(box, photo)
        self._photo, self._display_box = photo, box
        self._draw_overlays()

    def _position_image(self, box, photo):
        left, top, width, height = box
        self._surface.coords(self._paper, left, top, left + width, top + height)
        self._surface.coords(self._item, left, top)
        self._surface.itemconfigure(self._item, image=photo)

    def current_image(self):
        """Return an independent snapshot without interaction overlays."""
        return self._source.copy() if self._source is not None else None

    def set_selected(self, symbol):
        self._selected = symbol
        self._draw_overlays()

    def set_edit_enabled(self, enabled):
        self._edit_enabled = bool(enabled)
        self._cancel_drag()
        self._draw_overlays()

    def set_colorbar_box(self, box):
        # Figure coordinates: normalized, origin at bottom left. None for tight crops.
        if box is not None:
            import math
            box = tuple(float(v) for v in box)
            if (len(box) != 4 or not all(math.isfinite(v) for v in box)
                    or box[2] <= 0 or box[3] <= 0
                    or min(box) < 0 or box[0] + box[2] > 1
                    or box[1] + box[3] > 1):
                raise ValueError("colorbar box must fit within the normalized figure")
        self._colorbar_box = box
        self._cancel_drag()
        self._draw_overlays()

    def _can_edit(self):
        return (self.__dict__.get('_edit_enabled', True)
                and not self.__dict__.get('_is_stale', False))

    def _source_point(self, event):
        if self._display_box is None or self._source is None:
            return None
        left, top, width, height = self._display_box
        sw, sh = self._source.size
        return ((event.x - left) * sw / width, (event.y - top) * sh / height)

    def _bar_pixels(self, box):
        x, y, w, h = box
        sw, sh = self._source.size
        return x * sw, (1 - y - h) * sh, (x + w) * sw, (1 - y) * sh

    def _draw_overlays(self):
        # Canvas-only rectangles never modify source pixels, Figure, or hit maps.
        if not (self.__dict__.get('_selected') or self.__dict__.get('_colorbar_box')
                or self.__dict__.get('_has_overlays')):
            return
        if not hasattr(self._surface, 'delete'):
            return  # Legacy lightweight surfaces support image positioning only.
        self._surface.delete('preview-controls')
        self._has_overlays = True
        if self._display_box is None or self._source is None:
            return
        boxes = []
        selected = self.__dict__.get('_selected')
        for rect, symbol in self._pixel_hits.items():
            if symbol == selected:
                boxes.append((rect, '#1875ef', {}))
        bar = self.__dict__.get('_colorbar_box')
        if bar is not None and self._can_edit():
            boxes.append((self._bar_pixels(bar), '#e08020', {}))
        target = self.__dict__.get('_drag_target')
        if target is not None and self._can_edit():
            boxes.append((target, '#1875ef', {'dash': (5, 3)}))
        left, top, width, height = self._display_box
        sw, sh = self._source.size
        for (x0, y0, x1, y1), color, options in boxes:
            self._surface.create_rectangle(
                left + x0 * width / sw, top + y0 * height / sh,
                left + x1 * width / sw, top + y1 * height / sh,
                outline=color, width=2, tags='preview-controls', **options)

    def _on_surface_click(self, event):
        self._cancel_drag()
        if hasattr(self._surface, "focus_set"):
            self._surface.focus_set()
        point = self._source_point(event)
        if point is None:
            return
        x, y = point
        sw, sh = self._source.size
        if not (0 <= x < sw and 0 <= y < sh):
            return
        bar = self.__dict__.get('_colorbar_box')
        if self._can_edit() and bar is not None:
            x0, y0, x1, y1 = self._bar_pixels(bar)
            if x0 <= x <= x1 and y0 <= y <= y1:
                self._drag = ('bar', event.x, event.y, point, bar)
                return
        for rect, symbol in self._pixel_hits.items():
            x0, y0, x1, y1 = rect
            if x0 <= x <= x1 and y0 <= y <= y1:
                if self._can_edit():
                    self.set_selected(symbol)
                    if x1 > x0 and y1 > y0:
                        self._drag = ('element', event.x, event.y, point, (symbol, rect))
                if self.on_click:
                    self.on_click(symbol)
                break

    def _cancel_drag(self, event=None):
        self._drag = self._drag_target = None
        self._draw_overlays()

    def _moved_bar(self, box, dx, dy):
        x, y, w, h = box
        sw, sh = self._source.size
        return (max(0., min(1 - w, x + dx / sw)),
                max(0., min(1 - h, y - dy / sh)), w, h)

    def _on_surface_drag(self, event):
        drag = self.__dict__.get('_drag')
        if drag is None or not self._can_edit():
            self._cancel_drag()
            return
        kind, start_x, start_y, origin, payload = drag
        point = self._source_point(event)
        self._drag_target = None
        if point is not None and (event.x - start_x) ** 2 + (event.y - start_y) ** 2 > 16:
            dx, dy = point[0] - origin[0], point[1] - origin[1]
            if kind == 'element':
                _, (x0, y0, x1, y1) = payload
                self._drag_target = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
            else:
                self._drag_target = self._bar_pixels(self._moved_bar(payload, dx, dy))
        self._draw_overlays()

    def _on_surface_release(self, event):
        drag = self.__dict__.get('_drag')
        self._cancel_drag()
        if drag is None or not self._can_edit():
            return
        kind, start_x, start_y, origin, payload = drag
        if (event.x - start_x) ** 2 + (event.y - start_y) ** 2 <= 16:
            return
        point = self._source_point(event)
        if point is None:
            return
        dx, dy = point[0] - origin[0], point[1] - origin[1]
        if kind == 'element':
            symbol, (x0, y0, x1, y1) = payload
            callback = self.__dict__.get('on_move')
            if callback is not None:
                callback(symbol, dx / (x1 - x0), -dy / (y1 - y0))
        else:
            x, y, _, _ = self._moved_bar(payload, dx, dy)
            callback = self.__dict__.get('on_colorbar_move')
            if callback is not None:
                callback(x, y)

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
