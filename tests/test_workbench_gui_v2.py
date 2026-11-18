"""Real native Tk integration, isolated from the session's legacy Tk root.

Each scenario runs as a main-guarded script so RenderJob's spawn workers can
import their main module without constructing another desktop.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
import json
import multiprocessing
from pathlib import Path
import sys
import time
import traceback


FORBIDDEN = {'core.styles', 'core.options', 'core.scientific', 'core.ptable',
             'ui.legacy_workbench'}


def native_only():
    assert not FORBIDDEN.intersection(sys.modules), sorted(FORBIDDEN.intersection(sys.modules))


def main():
    root, scenario, directory = sys.argv[1:]
    sys.path.insert(0, root)
    import main as entry
    from ui import workbench_v2 as gui
    assert entry.App is gui.App
    native_only()
    directory = Path(directory)
    app = gui.App(user_dir=directory / 'user', start_preview=False, recover=False)
    callbacks = []
    app.report_callback_exception = lambda *exc: callbacks.append(''.join(traceback.format_exception(*exc)))

    def unexpected_dialog(*args, **kwargs):
        raise AssertionError('Unexpected modal dialog: ' + repr(args))

    for name in ('showerror', 'showwarning', 'showinfo', 'askyesno', 'askyesnocancel'):
        setattr(gui.messagebox, name, unexpected_dialog)

    def pump_until(predicate, description, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.update()
            assert not callbacks, '\n'.join(callbacks)
            assert not app.status.get().startswith(('绘图失败', '导出未完成')), app.status.get()
            if predicate():
                return
            time.sleep(.01)
        raise AssertionError(description + ' timed out; status=' + app.status.get())

    def preview():
        pump_until(lambda: app._preview_after is None and not app.preview_job.active
                   and app.preview._source is not None and not app.preview._is_stale,
                   'real preview worker')
        assert app.preview_job.process is not None and app.preview_job.process.is_alive()
        assert app.preview_job.process.pid != __import__('os').getpid()
        assert app.preview._source.width > 100 and app.preview._source.height > 100
        assert len(app.preview._pixel_hits) == 118
        assert set(app.preview._pixel_hits.values()) == set(gui.ALL_SYMBOLS)

    def change_controls(patch):
        # A real widget callback fires after its variables already changed.
        app.settings.set_plot({**app.session.plot, **patch})
        app._settings_changed(patch)
        assert all(app.session.plot[key] == value for key, value in patch.items())

    try:
        app.update()
        assert not callbacks, callbacks
        native_only()
        assert app.session.user_dir == (directory / 'user').resolve()
        assert app.preview_job.process is None and app.export_job.process is None
        assert len(app.table.get_children()) == 118
        assert app.session.data == {} and not app.session.dirty

        if scenario == 'startup_demo':
            button = next(b for b in app.buttons if b.cget('text') == '载入示例')
            button.invoke()
            assert app.session.data == {'H': 0, 'C': -.5, 'O': .5, 'Ti': -.8, 'Ni': .8}
            assert str(app.table.item('H', 'values')[2]) == '0'
            assert app.session.dirty and app.preview._is_stale
            assert app._preview_after is not None
            app.cancel()

        elif scenario == 'session_edit':
            app.demo()
            change_controls({'kind': 'labels', 'font': 'DejaVu Sans'})
            preview()
            app.select_element('H')
            assert app.selected_symbol.get() == 'H'
            assert app.mark_value.get() == '0'
            assert app.table.selection() == ('H',)
            assert app.tabs.select() == str(app.mark_tab)
            app.mark_value.set('edited annotation')
            app.apply_mark()
            assert app.session.data['H'] == 'edited annotation'
            assert app.table.item('H', 'values')[2] == 'edited annotation'
            app._history(-1)
            assert app.session.data['H'] == 0 and app.mark_value.get() == '0'
            app._history(1)
            assert app.session.data['H'] == 'edited annotation'
            app.clear_mark()
            assert 'H' not in app.session.data and app.mark_value.get() == ''
            app._history(-1)
            assert app.session.data['H'] == 'edited annotation'
            project = directory / 'roundtrip.ptproj'
            assert app.save(path=project), app.status.get()
            saved = app.session.document
            assert not app.session.dirty and app.session.path == project.resolve()
            raw = json.loads(project.read_text(encoding='utf-8'))
            assert raw['schema'] == 2 and raw['current']['plot']['kind'] == 'labels'
            assert raw['current']['data']['H'] == 'edited annotation'
            app.new()
            assert app.session.data == {} and app.selected_symbol.get() == ''
            assert app.open_project(project), app.status.get()
            assert app.session.document == saved and not app.session.dirty
            assert app.settings.get_plot() == saved['current']['plot']
            assert app.table.item('H', 'values')[2] == 'edited annotation'
            app.cancel()

        elif scenario == 'responsive':
            before = app.session.document
            app.preferences['scale'] = '1.25'
            app._resize()
            assert app._font_scale == 1.25
            for layout, orientation in [('wide', 'horizontal'), ('compact', 'vertical')]:
                app.preferences['layout'] = layout
                app._resize()
                app.update_idletasks()
                assert app._layout[0] == layout
                assert str(app.panes.cget('orient')) == orientation
                assert len(app.panes.panes()) == 2
                assert app.settings_area.winfo_manager() == ('grid' if layout == 'wide' else '')
            app.toggle_settings()
            app.update_idletasks()
            assert app._drawer and app.settings_area.winfo_manager() == 'place'
            app.toggle_settings()
            assert not app._drawer and app.settings_area.winfo_manager() == ''
            app.preferences['layout'] = 'auto'
            for width, expected in [(900, 'compact'), (1300, 'wide'), (900, 'compact')]:
                app.geometry(f'{width}x700')
                pump_until(lambda: app._layout[0] == expected, 'responsive ' + expected, timeout=10)
                assert len(app.panes.panes()) == 2
            assert app.session.document == before and not app.session.dirty

        elif scenario.startswith('export_'):
            fmt = scenario.removeprefix('export_')
            app.demo()
            change_controls({'font': 'DejaVu Sans', 'dpi': 72, 'figsize': [8, 5]})
            preview()
            assert app._colorbar_box is not None
            app.output_dir = str(directory / 'exports')
            app.output_base = 'gui-native'
            app.format_var.set(fmt)
            app.export()
            assert app.export_job.active
            pump_until(lambda: not app.export_job.active and app.last_output is not None,
                       'real ' + fmt + ' publication')
            path = Path(app.last_output)
            assert path.parent == directory / 'exports' and path.suffix == '.' + fmt
            assert path.name.startswith('gui-native_') and path.stat().st_size > 1000
            raw = path.read_bytes()
            if fmt == 'png':
                from PIL import Image
                assert raw.startswith(b'\x89PNG\r\n\x1a\n')
                with Image.open(path) as image:
                    assert image.format == 'PNG' and image.size == (576, 360), image.size
                    image.verify()
            elif fmt == 'pdf':
                assert raw.startswith(b'%PDF-') and b'%%EOF' in raw[-1024:]
            else:
                from xml.etree import ElementTree
                tree = ElementTree.parse(path)
                assert tree.getroot().tag == '{http://www.w3.org/2000/svg}svg'
            assert '已导出 1 张图片' in app.status.get()
            original = raw
            app.last_output = None
            app.export()
            pump_until(lambda: not app.export_job.active and app.last_output is not None,
                       'second publication')
            assert Path(app.last_output) != path and path.read_bytes() == original
            assert len(list(path.parent.glob('*.' + fmt))) == 2

        elif scenario == 'layout_diagnostics':
            change_controls({'kind': 'labels', 'font': 'DejaVu Sans', 'label_fs': 40,
                                   'check_label_overlap': True})
            app.perform(lambda: app.session.patch(data={'H': 'A long annotation crossing cell boundaries'}))
            preview()
            rows = app.issues.tree.get_children()
            assert rows and any(app.issues.tree.item(row, 'values')[0] == 'H' for row in rows)
            change_controls({'check_label_overlap': False})
            preview()
            assert not app.issues.tree.get_children()
            assert not app.preview._is_stale

        elif scenario == 'diagnostics_switch':
            app.log_enabled.set(False)
            app.configure_logs()
            count = len(app.diagnostics.query().entries)
            assert not app.diagnostics.record('ERROR', 'gui.disabled', 'Disabled event')
            assert len(app.diagnostics.query().entries) == count
            preferences = json.loads(app.preferences_path.read_text(encoding='utf-8'))
            assert preferences['log_enabled'] is False
            app.log_enabled.set(True)
            app.log_level.set('WARNING')
            app.configure_logs()
            assert not app.diagnostics.record('INFO', 'gui.filtered', 'Filtered event')
            assert app.diagnostics.record('ERROR', 'gui.enabled', 'Enabled event')
            assert any(row['event_code'] == 'gui.enabled' for row in app.diagnostics.query().entries)
            app.log_enabled.set(False)
            app.configure_logs()
            assert not app.diagnostics.record('ERROR', 'gui.stopped', 'Stopped event')
            app.diagnostics.start_session(1)
            assert app.diagnostics.record('DEBUG', 'gui.temporary', 'Temporary event')
            app.diagnostics.stop_session()
            assert not app.diagnostics.record('ERROR', 'gui.after_session', 'Disabled again')
            preferences = json.loads(app.preferences_path.read_text(encoding='utf-8'))
            assert preferences['log_enabled'] is False and preferences['log_level'] == 'WARNING'
            assert app._load_preferences()['log_enabled'] is False

        else:
            raise AssertionError('Unknown scenario: ' + scenario)
        assert not callbacks, '\n'.join(callbacks)
        native_only()
    finally:
        worker_pids = {job.process.pid for job in (app.preview_job, app.export_job) if job.process}
        app.destroy()
        assert app.preview_job.process is None and app.export_job.process is None
        assert not worker_pids.intersection(process.pid for process in multiprocessing.active_children())
    print('GUI_V2_OK:' + scenario)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
'''


@pytest.mark.parametrize('scenario', [
    'startup_demo', 'session_edit', 'responsive', 'export_svg', 'export_png',
    'export_pdf', 'layout_diagnostics', 'diagnostics_switch',
])
def test_native_workbench_in_isolated_process(tmp_path, scenario):
    script = tmp_path / 'native_gui_scenario.py'
    script.write_text(_SCRIPT, encoding='utf-8')
    env = dict(os.environ, PTT_USER_DIR=str(tmp_path / 'user'), PYTHONIOENCODING='utf-8')
    env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
    result = subprocess.run(
        [sys.executable, str(script), str(ROOT), scenario, str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=180,
    )
    assert result.returncode == 0, f'{scenario}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}'
    assert 'GUI_V2_OK:' + scenario in result.stdout
