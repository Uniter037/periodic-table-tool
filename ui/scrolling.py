"""A bounded settings page with scoped mouse wheel and keyboard scrolling."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, width=280, height=100, highlightthickness=0,
                                background='#f4f6f8')
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = ttk.Frame(self.canvas, padding=10)
        self._window = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.content.bind('<Configure>', self._sync_region)
        self.canvas.bind('<Configure>', self._sync_width)
        self._root = self.winfo_toplevel()
        self._bindings = []
        for sequence, callback in (('<MouseWheel>', self._wheel), ('<Button-4>', self._wheel),
                                   ('<Button-5>', self._wheel), ('<FocusIn>', self._focus)):
            self._bindings.append((sequence, self._root.bind(sequence, callback, add='+')))

    def _contains(self, widget):
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, 'master', None)
        return False

    def _sync_region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _sync_width(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync_region()

    def _wheel(self, event):
        if not self.winfo_ismapped():
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        if not self._contains(target):
            return
        # A tick table has its own scrollbar; do not scroll its page as well.
        if isinstance(target, (ttk.Treeview, tk.Text, ttk.Combobox)):
            return
        if self.canvas.yview() == (0.0, 1.0):
            return
        delta = -1 if getattr(event, 'num', None) == 4 else 1
        if getattr(event, 'delta', 0):
            delta = -max(1, abs(event.delta) // 120) * (1 if event.delta > 0 else -1)
        self.canvas.yview_scroll(delta * 3, 'units')
        return 'break'

    def _focus(self, event):
        widget = event.widget
        if not self.winfo_ismapped() or not self._contains(widget) or widget is self.canvas:
            return
        top = widget.winfo_rooty() - self.content.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible_top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        total = max(1, self.content.winfo_height())
        if top < visible_top:
            self.canvas.yview_moveto(max(0, top - 8) / total)
        elif bottom > visible_top + height:
            self.canvas.yview_moveto((bottom - height + 8) / total)

    def destroy(self):
        for sequence, binding in self._bindings:
            self._root.unbind(sequence, binding)
        super().destroy()
