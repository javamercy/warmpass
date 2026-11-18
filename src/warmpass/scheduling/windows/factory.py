"""Factory and Win32 helpers for the Windows Task Scheduler adapter."""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from warmpass.scheduling.base import OSJobScheduler, SchedulingError
from warmpass.scheduling.executable import (
    find_warmpass_executable,
    get_warmpass_executable_search_path,
)
from warmpass.scheduling.windows.scheduler import WindowsTaskScheduler

_NAME_SAM_COMPATIBLE = 2
_ERROR_MORE_DATA = 234


def _get_current_user_id() -> str:
    """Return the current Windows user in SAM-compatible DOMAIN\\user format via Secur32 GetUserNameExW."""
    if sys.platform != "win32":
        raise SchedulingError("Windows Task Scheduler is only supported on Windows.")

    secur32 = ctypes.WinDLL("secur32", use_last_error=True)
    get_user_name = secur32.GetUserNameExW
    get_user_name.argtypes = [
        ctypes.c_int,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.ULONG),
    ]

    get_user_name.restype = wintypes.BOOLEAN

    size = wintypes.ULONG(0)

    try:
        if not get_user_name(_NAME_SAM_COMPATIBLE, None, ctypes.byref(size)):
            error = ctypes.get_last_error()
            if error != _ERROR_MORE_DATA:
                raise ctypes.WinError(error)

        buffer = ctypes.create_unicode_buffer(size.value)

        if not get_user_name(_NAME_SAM_COMPATIBLE, buffer, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())

        return str(buffer.value)
    except OSError as exc:
        raise SchedulingError(
            f"Could not determine current Windows user ID: {exc}"
        ) from exc


def _get_system_directory() -> Path:
    """Return the Windows system directory via Kernel32 GetSystemDirectoryW so schtasks.exe is resolved outside PATH."""
    if sys.platform != "win32":
        raise SchedulingError("Windows Task Scheduler is only supported on Windows.")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_system_directory.restype = wintypes.UINT

    buffer = ctypes.create_unicode_buffer(32768)
    length = get_system_directory(buffer, len(buffer))

    if length == 0:
        error = ctypes.WinError(ctypes.get_last_error())
        raise SchedulingError(
            f"Could not determine Windows system directory: {error}"
        ) from error

    if length >= len(buffer):
        raise SchedulingError("Windows system directory path is too long.")

    return Path(buffer.value)


def create_windows_warmup_scheduler() -> OSJobScheduler:
    """Resolve warmpass, schtasks.exe, and the current user ID to construct the Windows Task Scheduler adapter."""
    search_path = get_warmpass_executable_search_path()
    warmpass_executable = find_warmpass_executable(search_path=search_path)

    schtasks_executable = _get_system_directory() / "schtasks.exe"
    if not schtasks_executable.is_file():
        raise SchedulingError(f"Cannot find schtasks.exe: {schtasks_executable}")

    return WindowsTaskScheduler(
        warmpass_executable=warmpass_executable,
        schtasks_executable=schtasks_executable,
        user_id=_get_current_user_id(),
    )
