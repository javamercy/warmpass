import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from warmpass.scheduling.base import WarmupScheduler
from warmpass.scheduling.executable import (
    find_warmpass_executable,
    get_executable_search_path,
)
from warmpass.scheduling.windows.scheduler import WindowsTaskSchedulerWarmupScheduler

_NAME_SAM_COMPATIBLE = 2
_ERROR_MORE_DATA = 234


def _get_current_user_id() -> str:
    secur32 = ctypes.WinDLL("secur32", use_last_error=True)
    get_user_name = secur32.GetUserNameExW
    get_user_name.argtypes = [
        ctypes.c_int,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.ULONG),
    ]

    get_user_name.restype = wintypes.BOOLEAN

    size = wintypes.ULONG(0)

    if not get_user_name(_NAME_SAM_COMPATIBLE, None, ctypes.byref(size)):
        error = ctypes.get_last_error()
        if error != _ERROR_MORE_DATA:
            raise ctypes.WinError(error)

    buffer = ctypes.create_unicode_buffer(size.value)

    if not get_user_name(_NAME_SAM_COMPATIBLE, buffer, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())

    return str(buffer.value)


def _get_system_directory() -> Path:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_system_directory = kernel32.GetSystemDirectoryW
    get_system_directory.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    get_system_directory.restype = wintypes.UINT

    buffer = ctypes.create_unicode_buffer(32768)
    length = get_system_directory(buffer, len(buffer))

    if length == 0:
        raise ctypes.WinError(ctypes.get_last_error())

    if length >= len(buffer):
        raise RuntimeError("Windows system directory path is too long.")

    return Path(buffer.value)


def _get_store_directory() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")

    if not local_app_data or not Path(local_app_data).is_absolute():
        raise RuntimeError("LOCALAPPDATA is missing or is not an absolute path.")

    return Path(local_app_data) / "Warmup"


def create_windows_warmup_scheduler() -> WarmupScheduler:
    search_path = get_executable_search_path()
    executable = find_warmpass_executable(search_path)

    schtasks_executable = _get_system_directory() / "schtasks.exe"
    if not schtasks_executable.is_file():
        raise RuntimeError(f"Cannot find schtasks.exe: {schtasks_executable}")

    return WindowsTaskSchedulerWarmupScheduler(
        executable=executable,
        home=Path.home(),
        user_id=_get_current_user_id(),
        store_directory=_get_store_directory(),
        schtasks_executable=schtasks_executable,
    )
