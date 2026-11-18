"""Real GUI draft regressions, each using an independent Tk process.

Use the same App(user_dir=..., start_preview=False, recover=False) interface as
other native GUI tests. Rendering is outside these widget/session regressions.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_dataset_collection import service, _preview

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import json
import multiprocessing
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace


def main():
    root, scenario, directory = sys.argv[1:]
    sys.path.insert(0, root)
    import tkinter as tk
    from tkinter import ttk
    from ui import workbench_v2 as gui
    from main import App as GUIApp
    assert GUIApp is gui.App
    directory = Path(directory)
    app = GUIApp(user_dir=directory / 'user', start_preview=False, recover=False)
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
    def unexpected(*args, **kwargs):
        raise AssertionError('Unexpected dialog: ' + repr(args))
    for name in ('showerror', 'showwarning', 'showinfo', 'askyesno', 'askyesnocancel'):
        setattr(gui.messagebox, name, unexpected)
    # Exercise actual callbacks and widgets, without spawning render workers.
    app.schedule_preview = lambda: None

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    def button(window, text):
        return next(w for w in descendants(window)
                    if isinstance(w, ttk.Button) and w.cget('text') == text)

    def dialog(title):
        return next(w for w in app.winfo_children()
                    if isinstance(w, tk.Toplevel) and w.title() == title)

    def edit(symbol, value):
        app.table.see(symbol)
        app.update_idletasks()
        x, y, width, height = app.table.bbox(symbol, 'value')
        app._edit_table(SimpleNamespace(x=x + width // 2, y=y + height // 2))
        assert app._table_entry is not None
        entry = app._table_entry[1]
        entry.delete(0, 'end')
        entry.insert(0, value)
        return entry

    try:
        app.update()
        if scenario.startswith('table_'):
            app.session.patch(data={'H': 0})
            app._sync()
            before = app.session.document
            entry = edit('H', '001')
            if scenario == 'table_valid':
                app.settings._vars['title'].set('pending title')
                # Save immediately, before the settings debounce can run.
                target = directory / 'saved.ptproj'
                assert app.save(path=target), app.status.get()
                saved = json.loads(target.read_text(encoding='utf-8'))
                assert saved['current']['plot']['title'] == 'pending title'
                assert saved['current']['data']['H'] == '001'
                assert app._table_entry is None
                assert app.settings.get_plot() == app.session.plot
                assert app.session.undo()
                assert app.session.document == before, 'Both drafts must be one history transaction'
            else:
                app.settings._vars['dpi'].set('invalid dpi')
                target = directory / 'must-not-save.ptproj'
                assert app.save(path=target) is False
                assert not target.exists()
                assert app.session.document == before
                assert app._table_entry[1] is entry and entry.get() == '001'
                assert app.settings._vars['dpi'].get() == 'invalid dpi'
                assert app.session.path is None
                assert app.session.undo() and app.session.data == {}

        elif scenario.startswith('switch_'):
            preview = json.loads((directory / 'preview.json').read_text(encoding='utf-8'))
            ids = app.session.import_excel(preview)
            app._sync()
            before = app.session.document
            second = app.session.collection.effective_data(ids[1])
            edit('H', '001')
            app.settings._vars['title'].set('pending group title')
            if scenario == 'switch_invalid':
                app.settings._vars['dpi'].set('bad dpi')
            app.dataset_dialog()
            window = dialog('切换 Excel 数据组')
            choices = next(w for w in descendants(window) if isinstance(w, tk.Listbox))
            choices.selection_clear(0, 'end')
            choices.selection_set(1)
            button(window, '切换').invoke()
            if scenario == 'switch_invalid':
                assert app.session.document == before
                assert app.session.collection.active_dataset_id == ids[0]
                assert app._table_entry[1].get() == '001'
                assert window.winfo_exists()
            else:
                assert app.session.collection.active_dataset_id == ids[1]
                assert app._table_entry is None
                assert app.session.data == second
                assert app.session.collection.effective_data(ids[0]) == {'H': '001'}
                assert app.session.plot['title'] == 'pending group title'
                # A later validation must not transfer A's editor into B.
                assert app._valid_controls()
                assert app.session.data == second
                app.session.select_dataset(ids[0])
                assert app.session.data == {'H': '001'}

        elif scenario.startswith('text_'):
            app.session.patch(plot={'kind': 'labels'})
            app._sync()
            expected = {'Ni': '001', 'Fe': '123456789012345678901234567890', 'H': '1.2300'}
            text = '\n'.join(symbol + ',' + value for symbol, value in expected.items())
            if scenario == 'text_paste':
                app.clipboard_clear()
                app.clipboard_append(text)
                app.paste()
                window = dialog('粘贴元素数据')
                widget = next(w for w in descendants(window) if isinstance(w, tk.Text))
                assert widget.get('1.0', 'end-1c') == text
                button(window, '应用数据').invoke()
            else:
                suffix = '.json' if scenario == 'text_json' else '.csv'
                path = directory / ('annotations' + suffix)
                path.write_text(json.dumps(expected) if suffix == '.json' else text, encoding='utf-8')
                app.import_file(path)
            assert app.session.data == expected, app.session.data
            for symbol, value in expected.items():
                assert str(app.table.item(symbol, 'values')[2]) == value
            target = directory / 'annotations.ptproj'
            assert app.save(path=target)
            assert json.loads(target.read_text(encoding='utf-8'))['current']['data'] == expected
            from application.plot_service import prepare_plot
            assert prepare_plot(app.session.plot, app.session.data)[1] == expected
        else:
            raise AssertionError(scenario)
        assert not errors, '\n'.join(errors)
        assert app.preview_job.process is None and app.export_job.process is None
        assert not {'ui.legacy_workbench', 'core.styles', 'core.options',
                    'core.scientific', 'core.ptable'} & set(sys.modules)
    finally:
        app.destroy()
    print('DRAFT_V2_OK:' + scenario)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
'''


@pytest.mark.parametrize('scenario', [
    'table_valid', 'table_invalid', 'switch_valid', 'switch_invalid',
    'text_csv', 'text_json', 'text_paste',
])
def test_workbench_draft_regression_in_isolated_process(tmp_path, service, scenario):
    (tmp_path / 'preview.json').write_text(json.dumps(_preview(service)), encoding='utf-8')
    script = tmp_path / 'workbench_draft_scenario.py'
    script.write_text(_SCRIPT, encoding='utf-8')
    env = dict(os.environ, PTT_USER_DIR=str(tmp_path / 'user'), PYTHONIOENCODING='utf-8')
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, str(script), str(ROOT), scenario, str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=60,
    )
    assert result.returncode == 0, f'{scenario}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}'
    assert 'DRAFT_V2_OK:' + scenario in result.stdout
