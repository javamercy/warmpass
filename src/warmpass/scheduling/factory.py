import sys

from warmpass.scheduling.base import WarmupScheduler
from warmpass.scheduling.service import WarmupSchedulerService


def create_warmup_scheduler() -> WarmupScheduler:
    match sys.platform:
        case "darwin":
            from warmpass.scheduling.macos.factory import create_macos_warmup_scheduler

            return create_macos_warmup_scheduler()

        case "win32":
            from warmpass.scheduling.windows.factory import (
                create_windows_warmup_scheduler,
            )

            return create_windows_warmup_scheduler()

        case _:
            raise RuntimeError(
                f"Scheduling is not supported on this platform: {sys.platform}"
            )


def create_warmup_scheduler_service() -> WarmupSchedulerService:
    return WarmupSchedulerService(create_warmup_scheduler())
