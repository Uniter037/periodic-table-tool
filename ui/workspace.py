"""Scrollable settings pages for the plotting workspace."""
import tkinter as tk
from tkinter import ttk


class ScrollPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, width=300)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = ttk.Frame(self.canvas, padding=10)
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.body)
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind('<Destroy>', self._cleanup)
        self._wheel = self.bind_all('<MouseWheel>', self._scroll, add='+')

    def _scroll(self, event):
        widget = event.widget
        while widget is not None:
            if widget is self:
                self.canvas.yview_scroll(-int(event.delta / 120), 'units')
                return
            widget = getattr(widget, 'master', None)

    def _cleanup(self, event):
        if event.widget is self and self._wheel:
            self._unbind(('bind', 'all', '<MouseWheel>'), self._wheel)
            self._wheel = None
