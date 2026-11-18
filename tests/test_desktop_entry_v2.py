"""Entry dispatch checks without constructing a desktop or running smoke."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def isolated(code, *args):
    return subprocess.run([sys.executable, '-c', code, *map(str, args)], cwd=ROOT,
                          check=True, capture_output=True, text=True, timeout=60)


def test_import_main_uses_v2_without_legacy_engine():
    isolated('''
import sys
import main
from ui.workbench_v2 import App, main as desktop_main
assert main.App is App
assert main.main is desktop_main
assert not {'ui.legacy_workbench', 'core.styles', 'core.options',
            'core.scientific', 'core.ptable', 'application.project_codec'} & set(sys.modules)
''')


@pytest.mark.parametrize('equals', [False, True])
def test_agent_dispatch_precedes_gui_import(tmp_path, equals):
    request = tmp_path / 'request.json'
    request.write_text('{"api_version":2,"action":"describe"}', encoding='utf-8')
    isolated('''
import builtins, json, multiprocessing, runpy, sys
original = builtins.__import__
events = []
def guard(name, *args, **kwargs):
    if name == 'ui' or name.startswith(('ui.', 'tkinter')):
        raise AssertionError('Agent dispatch imported GUI: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
multiprocessing.freeze_support = lambda: events.append('freeze')
request, response, equals = sys.argv[1:]
sys.argv = ['main.py', '--agent-request=' + request] if equals == 'True' else ['main.py', '--agent-request', request]
sys.argv += ['--agent-response', response]
try:
    runpy.run_path('main.py', run_name='__main__')
except SystemExit as exc:
    assert exc.code == 0, exc.code
else:
    raise AssertionError('Agent dispatch did not exit')
assert events == ['freeze']
with open(response, encoding='utf-8') as stream:
    assert json.load(stream)['ok']
''', request, tmp_path / 'response.json', equals)


def test_frozen_worker_dispatch_stops_before_agent_or_gui():
    isolated('''
import builtins, multiprocessing, runpy, sys
original = builtins.__import__
def guard(name, *args, **kwargs):
    if name == 'ui' or name.startswith(('ui.', 'tkinter', 'application')):
        raise AssertionError('Worker imported app: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guard
sys.frozen = True
sys.argv = ['main.exe', '--multiprocessing-fork', '--agent-request=must-not-read']
def worker_dispatch():
    raise SystemExit(73)
multiprocessing.freeze_support = worker_dispatch
try:
    runpy.run_path('main.py', run_name='__main__')
except SystemExit as exc:
    assert exc.code == 73
else:
    raise AssertionError('Worker dispatch did not exit')
''')


def test_normal_start_calls_v2_after_freeze_support():
    isolated('''
import multiprocessing, runpy, sys, types
events = []
multiprocessing.freeze_support = lambda: events.append('freeze')
module = types.ModuleType('ui.workbench_v2')
module.App = object
module.main = lambda: events.append('v2')
sys.modules['ui.workbench_v2'] = module
sys.argv = ['main.py']
runpy.run_path('main.py', run_name='__main__')
assert events == ['freeze', 'v2'], events
''')


def test_legacy_source_root_is_repository():
    isolated('''
from pathlib import Path
from ui import legacy_workbench as legacy
assert Path(legacy.PROJECT_ROOT) == Path.cwd()
''')
