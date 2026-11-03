"""固定画幅的预览：缩放栅格，不改变 Figure 的尺寸或布局。"""
from __future__ import annotations

import tkinter as tk

from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image, ImageTk


class PreviewCanvas(tk.Frame):
    def __init__(self, master, on_click=None, **kw):
        super().__init__(master, **kw)
        self.on_click = on_click
        self.fig = self.canvas = None
        self.hit_map = {}
        self._source = self._photo = None
        self._display_box = None
        self._surface = tk.Canvas(self, highlightthickness=0, background="#e4e8ee",
                                  width=100, height=100)
        self._surface.pack(fill="both", expand=True)
        self._paper = self._surface.create_rectangle(0, 0, 0, 0, fill="white", outline="#c7cdd6")
        self._item = self._surface.create_image(0, 0, anchor="nw")
        self._stale = tk.Label(self, text="旧预览 · 当前设置或数据无效，请查看底部提示", bg="#fff1d6", fg="#8a3b12")
        self._surface.bind("<Configure>", self.resize)
        self._surface.bind("<Button-1>", self._on_surface_click)

    def set_stale(self, stale):
        if stale:
            self._stale.place(x=6, y=6, relwidth=.96)
        else:
            self._stale.place_forget()

    def show(self, fig, hit_map):
        """成功渲染后替换预览；失败时释放新 Figure 并保留旧图。"""
        import matplotlib.pyplot as plt
        try:
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            source = Image.frombuffer("RGBA", canvas.get_width_height(),
                                      canvas.buffer_rgba(), "raw", "RGBA", 0, 1).copy()
        except Exception:
            if fig is not self.fig:
                plt.close(fig)
            raise
        old = (self.fig, self.canvas, self.hit_map, self._source, self._display_box)
        self.fig, self.canvas = fig, canvas
        self.hit_map = hit_map or {}
        self._source = source
        self._display_box = None
        try:
            self.resize()
        except Exception:
            self.fig, self.canvas, self.hit_map, self._source, self._display_box = old
            if fig is not self.fig:
                plt.close(fig)
            raise
        if old[0] is not None and old[0] is not fig:
            plt.close(old[0])

    def resize(self, event=None):
        if self._source is None:
            return
        width, height = self._surface.winfo_width(), self._surface.winfo_height()
        sw, sh = self._source.size
        scale = min(width / sw, height / sh)
        dw, dh = max(1, round(sw * scale)), max(1, round(sh * scale))
        box = ((width - dw) // 2, (height - dh) // 2, dw, dh)
        if box == self._display_box:
            return
        photo = ImageTk.PhotoImage(self._source.resize((dw, dh), Image.Resampling.LANCZOS),
                                   master=self._surface)
        self._surface.coords(self._paper, box[0], box[1], box[0] + dw, box[1] + dh)
        self._surface.coords(self._item, box[0], box[1])
        self._surface.itemconfigure(self._item, image=photo)
        self._photo, self._display_box = photo, box

    def _on_surface_click(self, event):
        if self.fig is None or self._display_box is None or not self.fig.axes:
            return
        left, top, width, height = self._display_box
        if not (left <= event.x < left + width and top <= event.y < top + height):
            return
        sw, sh = self._source.size
        point = ((event.x - left) * sw / width,
                 sh - (event.y - top) * sh / height)
        # 周期表在主 axes；颜色条点击不得误命中元素。
        ax = self.fig.axes[0]
        if not ax.bbox.contains(*point):
            return
        x, y = ax.transData.inverted().transform(point)
        symbol = self.hit_test(x, y)
        if symbol and self.on_click:
            self.on_click(symbol)

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
        self.fig = self.canvas = self._source = self._photo = None
        self.hit_map = {}
        super().destroy()
