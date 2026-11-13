from typing import assert_never
from uuid import UUID, uuid4

from warmpass.agents.models import AgentType
from warmpass.scheduling.base import OSJobScheduler, SchedulerError
from warmpass.scheduling.models import (
    DailyTrigger,
    ScheduledTrigger,
    ScheduleTrigger,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)
from warmpass.scheduling.store import WarmupScheduleStore


class SchedulerService:
    def __init__(
        self,
        *,
        store: WarmupScheduleStore,
        scheduler: OSJobScheduler,
    ) -> None:
        self._store = store
        self._scheduler = scheduler

    def add(self, agent: AgentType, trigger: ScheduleTrigger) -> WarmupSchedule:
        schedule = WarmupSchedule(
            id=uuid4(),
            agent=agent,
            trigger=trigger,
        )

        triggers = expand_triggers(schedule.trigger)
        arguments = build_warmup_arguments(schedule.agent)

        self._store.write(schedule, overwrite=False)
        self._scheduler.register_job(
            schedule.id, arguments=arguments, triggers=triggers
        )
        return schedule

    def remove(self, schedule_id: UUID) -> None:
        if self.get(schedule_id) is None:
            raise SchedulerError(f"Schedule {schedule_id} does not exist.")

        self._scheduler.unregister_job(schedule_id)
        self._store.remove(schedule_id)

    def clear(self) -> None:
        self._scheduler.clear_jobs()
        self._store.clear()

    def get(self, schedule_id: UUID) -> WarmupSchedule | None:
        schedule = self._store.read(schedule_id)
        job = self._scheduler.get_job(schedule_id)

        if schedule is None and job is None:
            return None
        elif schedule is None:
            raise SchedulerError(
                f"Schedule {schedule_id} has an OS job but no saved schedule record."
            )
        elif job is None:
            raise SchedulerError(
                f"Schedule {schedule_id} has a saved record, "
                "but its OS job is missing or not loaded."
            )

        expected_triggers = expand_triggers(schedule.trigger)
        if job.triggers != expected_triggers:
            raise SchedulerError(
                f"Schedule {schedule_id} in the OS has different triggers than its saved record. "
                "Remove and re-add the schedule."
            )

        expected_arguments = build_warmup_arguments(schedule.agent)
        if job.command[1:] != expected_arguments:
            raise SchedulerError(
                f"Schedule {schedule_id} in the OS has different command arguments than its saved record. "
                "Remove and re-add the schedule."
            )

        return schedule

    def get_list(self) -> list[WarmupSchedule]:
        ids = self._store.list_ids() | self._scheduler.list_job_ids()

        schedules: list[WarmupSchedule] = []
        for schedule_id in sorted(ids):
            schedule = self.get(schedule_id)
            if schedule is not None:
                schedules.append(schedule)

        return schedules


def build_warmup_arguments(agent: AgentType) -> list[str]:
    return ["warmup", "--agent", agent.value]


def expand_triggers(trigger: ScheduleTrigger) -> list[ScheduledTrigger]:
    match trigger:
        case DailyTrigger(window=window):
            days: list[WeekDay] | None = None
        case WeeklyTrigger(window=window, days=weekly_days):
            days = weekly_days
        case _:
            assert_never(trigger)

    minutes_per_day = 24 * 60
    start = (
        window.from_.hour * 60 + window.from_.minute if window.from_ is not None else 0
    )
    end = (
        window.until.hour * 60 + window.until.minute
        if window.until is not None
        else minutes_per_day
    )

    if end < start:
        end += minutes_per_day

    expanded: list[ScheduledTrigger] = []
    for minute in range(start, end, window.every * 60):
        minute_of_day = minute % minutes_per_day
        hour, minute_of_hour = divmod(minute_of_day, 60)
        if days is None:
            expanded.append(ScheduledTrigger(hour=hour, minute=minute_of_hour))
        else:
            for day in days:
                expanded.append(
                    ScheduledTrigger(hour=hour, minute=minute_of_hour, weekday=day)
                )

    return expanded
