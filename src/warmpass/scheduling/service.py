from uuid import UUID, uuid4

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.base import WarmupScheduler
from warmpass.scheduling.models import WarmupSchedule, WarmupScheduleTrigger


class WarmupSchedulerService:
    def __init__(self, warmup_scheduler: WarmupScheduler):
        self._warmup_scheduler = warmup_scheduler

    def add(
        self, agent: WarmupAgentType, trigger: WarmupScheduleTrigger
    ) -> WarmupSchedule:
        schedule = WarmupSchedule(
            id=uuid4(),
            agent=agent,
            trigger=trigger,
        )
        self._warmup_scheduler.add(schedule)
        return schedule

    def remove(self, schedule_id: UUID) -> None:
        self._warmup_scheduler.remove(schedule_id)

    def clear(self) -> None:
        self._warmup_scheduler.clear()

    def get(self, schedule_id: UUID) -> WarmupSchedule | None:
        return self._warmup_scheduler.get(schedule_id)

    def get_list(self) -> list[WarmupSchedule]:
        return self._warmup_scheduler.get_list()
