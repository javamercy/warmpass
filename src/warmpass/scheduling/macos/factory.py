import shutil
from pathlib import Path
from typing import Final

from warmpass.paths import get_log_directory
from warmpass.scheduling.base import OSJobScheduler, SchedulingError
from warmpass.scheduling.executable import (
    find_warmpass_executable,
    get_warmpass_executable_search_path,
)
from warmpass.scheduling.macos.scheduler import MacOSLaunchdScheduler

_MACOS_SYSTEM_PATHS: Final[tuple[str, ...]] = (
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)


def _find_launchctl_executable(search_path: str) -> Path:
    launchctl_executable = shutil.which("launchctl", path=search_path)
    if launchctl_executable is None:
        raise SchedulingError(
            "Could not find 'launchctl' in PATH. "
            "Ensure that you are running on macOS and that 'launchctl' is available."
        )
    return Path(launchctl_executable)


def create_macos_warmup_scheduler() -> OSJobScheduler:
    search_path = get_warmpass_executable_search_path(
        additional_paths=_MACOS_SYSTEM_PATHS
    )

    return MacOSLaunchdScheduler(
        warmpass_executable_search_path=search_path,
        warmpass_executable=find_warmpass_executable(search_path=search_path),
        launchctl_executable=_find_launchctl_executable(search_path=search_path),
        log_directory=get_log_directory(),
    )
