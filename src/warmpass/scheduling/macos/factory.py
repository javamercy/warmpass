import os
import shutil
from pathlib import Path
from typing import Final

from warmpass.scheduling.base import WarmupScheduler
from warmpass.scheduling.macos.scheduler import MacOSLaunchdWarmupScheduler

_MACOS_SYSTEM_PATHS: Final[tuple[str, ...]] = (
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)


def _get_executable_search_path() -> str:
    inherited_path = os.getenv("PATH", "")
    inherited_directories = [
        entry
        for entry in inherited_path.split(os.pathsep)
        if entry and Path(entry).is_absolute()
    ]
    directories = dict.fromkeys([*inherited_directories, *_MACOS_SYSTEM_PATHS])

    return os.pathsep.join(directories.keys())


def _find_warmpass_executable(search_path: str) -> Path:
    executable = shutil.which("warmpass", path=search_path)
    if executable is None:
        raise RuntimeError(
            "Could not find the warmpass executable in PATH. Install Warmpass or add its executable directory to PATH."
        )

    return Path(executable)


def create_macos_warmup_scheduler() -> WarmupScheduler:
    search_path = _get_executable_search_path()
    executable = _find_warmpass_executable(search_path)

    return MacOSLaunchdWarmupScheduler(
        executable=executable,
        executable_search_path=search_path,
    )
