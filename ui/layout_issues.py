"""Compact, replaceable layout diagnostics with safe element navigation."""
from tkinter import ttk

from core.elements_data import ALL_SYMBOLS


class LayoutIssuesPanel(ttk.Frame):
    def __init__(self, master, on_select, **kwargs):
        super().__init__(master, **kwargs)
        self.on_select = on_select
        self._symbols = set(ALL_SYMBOLS)
        self._targets = {}
        self._details = {}
        self.title = ttk.Label(self, text='排版问题 (0)', style='Muted.TLabel')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.title.grid(row=0, column=0, sticky='w')
        self.tree = ttk.Treeview(self, columns=('element', 'issue'), show='headings',
                                 height=5, selectmode='browse')
        self.tree.heading('element', text='元素')
        self.tree.heading('issue', text='问题')
        self.tree.column('element', width=75, minwidth=50, stretch=False)
        self.tree.column('issue', width=140, minwidth=80, stretch=True)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky='ns')
        self.tree.grid(row=1, column=0, sticky='nsew')
        self.detail = ttk.Label(self, text='', wraplength=220,
                                justify='left', style='Muted.TLabel')
        self.detail.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(4, 0))
        self.bind('<Configure>', self._resize_detail)
        self.tree.bind('<<TreeviewSelect>>', self._select)

    def set_issues(self, issues):
        """Replace all rows, including callbacks; None clears the panel."""
        self._targets.clear()
        self._details.clear()
        self.detail.configure(text='')
        for row in self.tree.get_children():
            self.tree.delete(row)
        count = 0
        for issue in issues or ():
            text = issue.get('text') or {}
            element = text.get('element')
            valid = isinstance(element, str) and element in self._symbols
            display = element if isinstance(element, str) else str(element or '—')
            code = issue.get('code', '')
            description = {'TEXT_OUTSIDE_CELL': '文字超出单元格',
                           'TEXT_OVERLAP': '文字重叠'}.get(code, str(code))
            role = text.get('role')
            if role:
                role = {'value': '数值', 'symbol': '元素符号',
                        'number': '原子序数'}.get(role, role)
                description += f' · {role}'
            suggestion = issue.get('suggestion')
            row = self.tree.insert('', 'end', values=(display, description))
            self._details[row] = str(suggestion or '')
            if valid:
                self._targets[row] = element
            count += 1
        self.title.configure(text=f'排版问题 ({count})')

    def _resize_detail(self, event):
        self.detail.configure(wraplength=max(80, event.width - 12))

    def _select(self, event=None):
        selection = self.tree.selection()
        self.detail.configure(text=self._details.get(selection[0], '') if selection else '')
        symbol = self._targets.get(selection[0]) if selection else None
        if symbol is not None:
            self.on_select(symbol)
