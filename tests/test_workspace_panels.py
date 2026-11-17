"""Behavioral coverage for the standalone workspace panels."""
import tkinter as tk
from tkinter import ttk

import pytest

from ui.settings_panel import CollapsibleSection, SettingsSearch
from ui.layout_issues import LayoutIssuesPanel


@pytest.fixture(scope="module")
def panel_root(_application):
    return _application


@pytest.fixture
def window(panel_root):
    root = tk.Toplevel(panel_root)
    root.geometry('500x400')
    yield root
    root.destroy()


def test_folding_preserves_entry_and_widget(window):
    section = CollapsibleSection(window, 'Appearance')
    section.pack(fill='x')
    entry = ttk.Entry(section.body)
    entry.pack()
    entry.insert(0, 'retained value')
    window.update()
    assert section.body.winfo_ismapped()
    section.toggle_button.invoke()
    window.update()
    assert not section.expanded
    assert not section.body.winfo_ismapped()
    assert entry.get() == 'retained value'
    section.expand()
    section.expand()
    window.update()
    assert section.expanded and entry.winfo_ismapped()
    assert entry.get() == 'retained value'


def test_search_selection_reveals_tab_section_and_focus(window):
    notebook = ttk.Notebook(window)
    notebook.pack(fill='both', expand=True)
    first, second = ttk.Frame(notebook), ttk.Frame(notebook)
    notebook.add(first, text='First')
    notebook.add(second, text='Second')
    section = CollapsibleSection(second, 'Labels', expanded=False)
    section.pack(fill='x')
    entry = ttk.Entry(section.body)
    entry.pack()
    search = SettingsSearch(window, notebook)
    search.pack(fill='x')
    search.register('font_size', 'Label font size', entry, second, section)
    window.update()
    window.focus_force()
    search.query_var.set('FONT')
    assert search.results.get(0, 'end') == ('Label font size',)
    search.results.selection_set(0)
    search.results.focus_set()
    window.update()
    search.results.event_generate('<Return>')
    window.update()
    assert notebook.select() == str(second)
    assert section.expanded and entry.winfo_ismapped()
    assert window.focus_get() is entry
    assert search.query_var.get() == ''
    assert not search.results.winfo_ismapped()
    entry.destroy()
    assert search.select('font_size') is False
    search.query_var.set('font')
    assert search.results.size() == 0
    window.update()
    assert search.no_results.winfo_ismapped()


def test_search_trace_removed_on_parent_destroy(window):
    host = ttk.Frame(window)
    notebook = ttk.Notebook(host)
    search = SettingsSearch(host, notebook)
    variable = search.query_var
    assert variable.trace_info()
    host.destroy()
    assert variable.trace_info() == []
    variable.set('safe after destruction')


def test_issue_selection_filters_markers_and_clears_stale_rows(window):
    selected = []
    panel = LayoutIssuesPanel(window, selected.append)
    panel.pack(fill='both', expand=True)
    panel.set_issues([
        {'code': 'TEXT_OUTSIDE_CELL', 'text': {'element': 'Fe', 'role': 'value'},
         'suggestion': '缩小字号或调整位置'},
        {'code': 'TEXT_OVERLAP', 'text': {'element': ('marker', 1, 2)}},
        {'code': 'TEXT_OVERLAP', 'text': {'element': 'Unknown'}},
    ])
    rows = panel.tree.get_children()
    assert len(rows) == 3
    assert panel.title.cget('text').endswith('(3)')
    panel.tree.selection_set(rows[0])
    window.update()
    assert selected == ['Fe']
    assert '数值' in panel.tree.item(rows[0], 'values')[1]
    assert panel.detail.cget('text') == '缩小字号或调整位置'
    assert panel.tree.column('issue', 'minwidth') == 80
    for row in rows[1:]:
        panel.tree.selection_set(row)
        window.update()
    assert selected == ['Fe']
    panel.set_issues([])
    window.update()
    panel._select()
    assert not panel.tree.get_children()
    assert not panel._targets
    assert panel.detail.cget('text') == ''
    assert panel.title.cget('text').endswith('(0)')
    assert selected == ['Fe']
    panel.set_issues([{'code': 'TEXT_OVERLAP', 'text': {'element': 'O'}}])
    panel.tree.selection_set(panel.tree.get_children()[0])
    window.update()
    assert selected == ['Fe', 'O']
    panel.set_issues(None)
    assert not panel.tree.get_children()
