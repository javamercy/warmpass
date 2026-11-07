from warmpass.scheduling.base import WarmupScheduler
from warmpass.scheduling.models import WarmupSchedule


class WarmupSchedulerService:
    def __init__(self, warmup_scheduler: WarmupScheduler):
        self._warmup_scheduler = warmup_scheduler

    def add(self, schedule: WarmupSchedule) -> None:
        self._warmup_scheduler.add(schedule)

    def remove(self, schedule_id: str) -> None:
        self._warmup_scheduler.remove(schedule_id)

    def get(self, schedule_id: str) -> WarmupSchedule | None:
        return self._warmup_scheduler.get(schedule_id)

    def get_list(self) -> list[WarmupSchedule]:
        return self._warmup_scheduler.get_list()
