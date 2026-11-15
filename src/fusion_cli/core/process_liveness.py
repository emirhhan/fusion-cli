"""Platforma uygun, yan etkisiz süreç yoklaması."""

from __future__ import annotations

import os
import sys

_SYNCHRONIZE = 0x00100000
_ERROR_INVALID_PARAMETER = 87
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258


def process_alive(pid: int) -> bool | None:
    """Süreci yan etkisiz yokla; durum doğrulanamazsa None döndür."""
    if not 0 < pid <= 0x7FFF_FFFF:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return False if ctypes.get_last_error() == _ERROR_INVALID_PARAMETER else None
        try:
            outcome = int(kernel.WaitForSingleObject(handle, 0))
            if outcome == _WAIT_OBJECT_0:
                return False
            return True if outcome == _WAIT_TIMEOUT else None
        finally:
            kernel.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return None
        return True
