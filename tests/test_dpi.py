"""DPI setup must precede Tk and respect the host's existing configuration."""
import ctypes
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ui import dpi


@pytest.mark.parametrize('result,status', [(0, 'system-aware'),
                                         (-2147024891, 'already-configured')])
def test_modern_api_and_manifest_are_respected(monkeypatch, result, status):
    setter = Mock(return_value=result)
    loader = Mock(return_value=SimpleNamespace(SetProcessDpiAwareness=setter))
    monkeypatch.setattr(dpi.sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'WinDLL', loader, raising=False)
    assert dpi.enable_high_dpi() == status
    setter.assert_called_once_with(1)
    assert loader.call_count == 1  # no override after access-denied


def test_legacy_fallback(monkeypatch):
    setter = Mock(return_value=True)
    monkeypatch.setattr(dpi.sys, 'platform', 'win32')
    monkeypatch.setattr(ctypes, 'WinDLL', Mock(side_effect=[
        OSError('no shcore'), SimpleNamespace(SetProcessDPIAware=setter)]), raising=False)
    assert dpi.enable_high_dpi() == 'system-aware'
    setter.assert_called_once_with()


def test_unsupported_platform_does_not_load_windows_dll(monkeypatch):
    loader = Mock(side_effect=AssertionError('unexpected Windows DLL'))
    monkeypatch.setattr(dpi.sys, 'platform', 'linux')
    monkeypatch.setattr(ctypes, 'WinDLL', loader, raising=False)
    assert dpi.enable_high_dpi() == 'not-windows'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows native DPI verification')
def test_fresh_process_uses_native_dpi_before_tk():
    code = '''
import ctypes
from ui.dpi import enable_high_dpi
assert enable_high_dpi() in ('system-aware', 'already-configured')
awareness = ctypes.c_int()
assert ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(awareness)) == 0
assert awareness.value in (1, 2), awareness.value
import tkinter as tk
root = tk.Tk()
root.withdraw()
assert root.winfo_fpixels('1i') >= 96
root.destroy()
'''
    subprocess.run([sys.executable, '-c', code], check=True, timeout=30)
