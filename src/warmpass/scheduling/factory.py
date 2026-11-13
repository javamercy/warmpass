import sys

from warmpass.paths import get_store_directory
from warmpass.scheduling.base import OSJobScheduler, SchedulerError
from warmpass.scheduling.service import SchedulerService
from warmpass.scheduling.store import WarmupScheduleStore


def create_os_job_scheduler(platform: str | None = None) -> OSJobScheduler:
    target_platform = sys.platform if platform is None else platform
    match target_platform:
        case "darwin":
            from warmpass.scheduling.macos.factory import create_macos_warmup_scheduler

            return create_macos_warmup_scheduler()
        case "win32":
            from warmpass.scheduling.windows.factory import (
                create_windows_warmup_scheduler,
            )

            return create_windows_warmup_scheduler()
        case _:
            raise SchedulerError(f"Unsupported platform '{target_platform}'. ")


def create_scheduler_service() -> SchedulerService:
    scheduler = create_os_job_scheduler()
    store = WarmupScheduleStore(directory=get_store_directory())
    return SchedulerService(store=store, scheduler=scheduler)
