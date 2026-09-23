"""Windows privilege detection."""
from __future__ import annotations

import ctypes
import sys


def is_administrator() -> bool:
    """Return whether the current Windows process has administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False

def relaunch_as_administrator() -> bool:
    """Request UAC elevation only after an explicit UI action; never invoked automatically."""
    try:
        parameters = " ".join(f'"{item}"' for item in sys.argv)
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, parameters, None, 1) > 32
    except (AttributeError, OSError):
        return False
