"""Reusable settings sections and locally scoped search navigation."""
import tkinter as tk
from tkinter import ttk


class CollapsibleSection(ttk.Frame):
    """Pack controls into ``body``; folding never recreates their widgets."""

    def __init__(self, master, title, expanded=True, **kwargs):
        super().__init__(master, **kwargs)
        self.title = title
        self.expanded = bool(expanded)
        self.toggle_button = ttk.Button(self, style='Section.TButton', command=self.toggle)
        self.toggle_button.pack(fill='x')
        self.body = ttk.Frame(self)
        self._render()

    def _render(self):
        self.toggle_button.configure(text=f"{'▾' if self.expanded else '▸'} {self.title}")
        if self.expanded:
            self.body.pack(fill='x', expand=True)
        else:
            self.body.pack_forget()

    def toggle(self):
        self.expanded = not self.expanded
        self._render()

    def expand(self):
        self.expanded = True
        self._render()


class SettingsSearch(ttk.Frame):
    """Register settings, then select a hit to reveal and focus its control.

    ``page`` is a notebook tab widget or tab identifier. Existing FocusIn
    handlers on scrollable pages perform scrolling after navigation.
    """

    def __init__(self, master, notebook, **kwargs):
        super().__init__(master, **kwargs)
        self.notebook = notebook
        self._settings = {}
        self._hits = []
        self.query_var = tk.StringVar(self)
        ttk.Label(self, text='搜索设置', style='Muted.TLabel').pack(anchor='w')
        self.no_results = ttk.Label(self, text='未找到匹配设置', style='Muted.TLabel')
        self.entry = ttk.Entry(self, textvariable=self.query_var)
        self.entry.pack(fill='x')
        self.results = tk.Listbox(self, height=5, exportselection=False)
        self.entry.bind('<Down>', self._next_hit)
        self.entry.bind('<Return>', self._activate)
        self.results.bind('<ButtonRelease-1>', self._activate)
        self.results.bind('<Return>', self._activate)
        self._trace = self.query_var.trace_add('write', self._refresh)
        self.bind('<Destroy>', self._cleanup, add='+')

    def register(self, key, label, widget, page, section=None):
        self._settings[key] = (label, widget, page, section)
        self._refresh()

    def _refresh(self, *_):
        query = self.query_var.get().strip().casefold()
        self.results.delete(0, 'end')
        self._hits = []
        if query:
            for key, (label, widget, page, section) in self._settings.items():
                if widget.winfo_exists() and query in f'{key} {label}'.casefold():
                    self._hits.append(key)
                    self.results.insert('end', label)
        self.no_results.pack_forget()
        if self._hits:
            self.results.pack(fill='x')
        else:
            self.results.pack_forget()
            if query:
                self.no_results.pack(anchor='w')

    def _next_hit(self, event=None):
        if self._hits:
            self.results.selection_set(0)
            self.results.activate(0)
            self.results.focus_set()
        return 'break'

    def _activate(self, event=None):
        selection = self.results.curselection()
        if self._hits:
            self.select(self._hits[selection[0] if selection else 0])
        return 'break'

    def select(self, key):
        """Navigate to a registered key; return False for a stale widget."""
        setting = self._settings.get(key)
        if setting is None or not setting[1].winfo_exists():
            return False
        label, widget, page, section = setting
        if section is not None:
            section.expand()
        self.notebook.select(page)
        self.update_idletasks()
        self.query_var.set('')
        self.update_idletasks()
        widget.focus_set()
        return True

    def _cleanup(self, event):
        if event.widget is self and self._trace is not None:
            self.query_var.trace_remove('write', self._trace)
            self._trace = None
            self._settings.clear()
            self._hits.clear()
