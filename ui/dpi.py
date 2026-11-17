"""Enable native Windows text rendering before creating any Tk window.

System awareness is deliberate: the bundled Tk 8.6 interface does not handle
per-monitor WM_DPICHANGED layout transitions. Never force a thread override
when a host or executable manifest has already selected an awareness mode.
"""
import ctypes
import sys


def enable_high_dpi():
    """Return startup status; unsupported platforms remain unchanged."""
    if sys.platform != 'win32':
        return 'not-windows'
    try:
        shcore = ctypes.WinDLL('shcore', use_last_error=True)
        setter = shcore.SetProcessDpiAwareness
        setter.argtypes = [ctypes.c_int]
        setter.restype = ctypes.c_long
        result = setter(1)  # PROCESS_SYSTEM_DPI_AWARE
        if result == 0:
            return 'system-aware'
        if result & 0xffffffff == 0x80070005:  # already set by host/manifest
            return 'already-configured'
    except (AttributeError, OSError):
        pass
    try:
        setter = ctypes.WinDLL('user32', use_last_error=True).SetProcessDPIAware
        setter.argtypes = []
        setter.restype = ctypes.c_bool
        return 'system-aware' if setter() else 'unavailable'
    except (AttributeError, OSError):
        return 'unavailable'
