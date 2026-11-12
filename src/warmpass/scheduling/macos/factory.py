from typing import Final

from warmpass.scheduling.base import WarmupScheduler
from warmpass.scheduling.executable import (
    find_warmpass_executable,
    get_executable_search_path,
)
from warmpass.scheduling.macos.scheduler import MacOSLaunchdWarmupScheduler

_MACOS_SYSTEM_PATHS: Final[tuple[str, ...]] = (
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)


def create_macos_warmup_scheduler() -> WarmupScheduler:
    search_path = get_executable_search_path(additional_paths=_MACOS_SYSTEM_PATHS)
    executable = find_warmpass_executable(search_path)

    return MacOSLaunchdWarmupScheduler(
        executable=executable,
        executable_search_path=search_path,
    )
