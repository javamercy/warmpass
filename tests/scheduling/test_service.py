"""Schedule service: record-to-triggers expansion and record/OS coordination."""

from datetime import time
from uuid import UUID

import pytest

from tests.support.fakes import FakeOSJobScheduler
from warmpass.agents.models import AgentType
from warmpass.scheduling.base import SchedulerError
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    ScheduleTrigger,
    WeekDay,
    WeeklyTrigger,
)
from warmpass.scheduling.service import SchedulerService, expand_triggers
from warmpass.scheduling.store import WarmupScheduleStore

MON, FRI = WeekDay.MONDAY, WeekDay.FRIDAY


def daily(
    *, from_: time | None = None, until: time | None = None, every: int
) -> DailyTrigger:
    return DailyTrigger(window=HourlyWindow(from_=from_, until=until, every=every))


def expanded(trigger: ScheduleTrigger) -> list[tuple[int, int, WeekDay | None]]:
    return [(t.hour, t.minute, t.weekday) for t in expand_triggers(trigger)]


# --- expand_triggers: expected values are written out by hand ----------------


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        pytest.param(
            daily(every=5),
            [(0, 0), (5, 0), (10, 0), (15, 0), (20, 0)],
            id="all-day-every-5h",
        ),
        pytest.param(
            daily(every=1),
            [(hour, 0) for hour in range(24)],
            id="all-day-hourly",
        ),
        pytest.param(
            daily(from_=time(9), until=time(17), every=2),
            [(9, 0), (11, 0), (13, 0), (15, 0)],
            id="interval-divides-range-evenly",
        ),
        pytest.param(
            daily(from_=time(9, 30), until=time(14), every=2),
            [(9, 30), (11, 30), (13, 30)],
            id="interval-does-not-divide-range",
        ),
        pytest.param(
            daily(from_=time(9), until=time(13), every=2),
            [(9, 0), (11, 0)],
            id="end-equal-to-a-trigger-is-excluded",
        ),
        pytest.param(
            daily(from_=time(9), until=time(10), every=5),
            [(9, 0)],
            id="single-trigger",
        ),
        pytest.param(
            daily(from_=time(21, 30), every=2),
            [(21, 30), (23, 30)],
            id="from-only-runs-to-midnight",
        ),
        pytest.param(
            daily(until=time(3), every=2),
            [(0, 0), (2, 0)],
            id="until-only-starts-at-midnight",
        ),
        pytest.param(
            daily(from_=time(22), until=time(3), every=2),
            [(22, 0), (0, 0), (2, 0)],
            id="crosses-midnight",
        ),
        pytest.param(
            daily(from_=time(23, 45), until=time(0, 30), every=2),
            [(23, 45)],
            id="crosses-midnight-by-minutes",
        ),
        pytest.param(
            daily(from_=time(22), until=time(0), every=1),
            [(22, 0), (23, 0)],
            id="until-midnight-excludes-midnight",
        ),
    ],
)
def test_daily_trigger_expands_to_run_times(
    trigger: DailyTrigger, expected: list[tuple[int, int]]
) -> None:
    assert expanded(trigger) == [(hour, minute, None) for hour, minute in expected]


def test_weekly_trigger_repeats_each_run_time_on_every_day_in_given_order() -> None:
    trigger = WeeklyTrigger(
        days=[FRI, MON],
        window=HourlyWindow(from_=time(9), until=time(13), every=2),
    )

    assert expanded(trigger) == [
        (9, 0, FRI),
        (9, 0, MON),
        (11, 0, FRI),
        (11, 0, MON),
    ]


# --- SchedulerService --------------------------------------------------------


def make_trigger() -> DailyTrigger:
    return daily(from_=time(9), until=time(13), every=2)


def test_add_registers_one_job_with_all_triggers_and_saves_the_record(
    scheduler_service: SchedulerService,
    fake_scheduler: FakeOSJobScheduler,
    schedule_store: WarmupScheduleStore,
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())

    assert schedule.id.version == 4
    assert schedule_store.read(schedule.id) == schedule
    (job,) = fake_scheduler.jobs.values()
    assert job.schedule_id == schedule.id
    assert job.command[1:] == ["warmup", "--agent", "codex"]
    assert [(t.hour, t.minute) for t in job.triggers] == [(9, 0), (11, 0)]


def test_add_failed_registration_raises_and_registers_nothing(
    scheduler_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
) -> None:
    fake_scheduler.failures["register_job"] = SchedulerError("launchd refused")

    with pytest.raises(SchedulerError, match="launchd refused"):
        scheduler_service.add(AgentType.CODEX, make_trigger())

    assert fake_scheduler.jobs == {}


def test_remove_deletes_the_job_and_the_record(
    scheduler_service: SchedulerService,
    fake_scheduler: FakeOSJobScheduler,
    schedule_store: WarmupScheduleStore,
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())

    scheduler_service.remove(schedule.id)

    assert fake_scheduler.jobs == {}
    assert schedule_store.read(schedule.id) is None


def test_remove_unknown_schedule_raises_before_touching_the_os(
    scheduler_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
) -> None:
    with pytest.raises(SchedulerError, match="does not exist"):
        scheduler_service.remove(UUID(int=1))

    assert "unregister_job" not in fake_scheduler.calls


def test_remove_keeps_the_record_when_the_job_cannot_be_unregistered(
    scheduler_service: SchedulerService,
    fake_scheduler: FakeOSJobScheduler,
    schedule_store: WarmupScheduleStore,
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())
    fake_scheduler.failures["unregister_job"] = SchedulerError("bootout failed")

    with pytest.raises(SchedulerError, match="bootout failed"):
        scheduler_service.remove(schedule.id)

    assert schedule_store.read(schedule.id) == schedule


def test_clear_removes_all_jobs_and_records(
    scheduler_service: SchedulerService,
    fake_scheduler: FakeOSJobScheduler,
    schedule_store: WarmupScheduleStore,
) -> None:
    scheduler_service.add(AgentType.CODEX, make_trigger())
    scheduler_service.add(AgentType.ANTIGRAVITY, make_trigger())

    scheduler_service.clear()

    assert fake_scheduler.jobs == {}
    assert schedule_store.list_ids() == set()


def test_clear_keeps_records_when_jobs_cannot_be_cleared(
    scheduler_service: SchedulerService,
    fake_scheduler: FakeOSJobScheduler,
    schedule_store: WarmupScheduleStore,
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())
    fake_scheduler.failures["clear_jobs"] = SchedulerError("launchctl failed")

    with pytest.raises(SchedulerError, match="launchctl failed"):
        scheduler_service.clear()

    assert schedule_store.list_ids() == {schedule.id}


# --- reconciliation of the record with the OS job -----------------------------


def test_get_returns_none_when_neither_record_nor_job_exists(
    scheduler_service: SchedulerService,
) -> None:
    assert scheduler_service.get(UUID(int=1)) is None


def test_get_returns_the_schedule_when_record_and_job_match(
    scheduler_service: SchedulerService,
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())

    assert scheduler_service.get(schedule.id) == schedule


def test_get_reports_a_record_whose_job_is_missing(
    scheduler_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())
    del fake_scheduler.jobs[schedule.id]

    with pytest.raises(SchedulerError, match="OS job is missing"):
        scheduler_service.get(schedule.id)


def test_get_reports_a_job_without_a_record(
    scheduler_service: SchedulerService, schedule_store: WarmupScheduleStore
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())
    schedule_store.remove(schedule.id)

    with pytest.raises(SchedulerError, match="no saved schedule record"):
        scheduler_service.get(schedule.id)


def test_get_reports_a_job_whose_triggers_differ_from_the_record(
    scheduler_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())
    job = fake_scheduler.jobs[schedule.id]
    fake_scheduler.jobs[schedule.id] = job.model_copy(
        update={"triggers": job.triggers[:1]}
    )

    with pytest.raises(SchedulerError, match="different triggers"):
        scheduler_service.get(schedule.id)


def test_get_reports_a_job_whose_command_differs_from_the_record(
    scheduler_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
) -> None:
    schedule = scheduler_service.add(AgentType.CODEX, make_trigger())
    job = fake_scheduler.jobs[schedule.id]
    fake_scheduler.jobs[schedule.id] = job.model_copy(
        update={"command": [job.command[0], "warmup", "--agent", "antigravity"]}
    )

    with pytest.raises(SchedulerError, match="different command arguments"):
        scheduler_service.get(schedule.id)


def test_get_list_returns_consistent_schedules_sorted_by_id(
    scheduler_service: SchedulerService,
) -> None:
    first = scheduler_service.add(AgentType.CODEX, make_trigger())
    second = scheduler_service.add(AgentType.ANTIGRAVITY, make_trigger())

    schedules = scheduler_service.get_list()

    assert [schedule.id for schedule in schedules] == sorted([first.id, second.id])
    assert {schedule.id: schedule for schedule in schedules} == {
        first.id: first,
        second.id: second,
    }


def test_get_list_is_empty_without_records_or_jobs(
    scheduler_service: SchedulerService,
) -> None:
    assert scheduler_service.get_list() == []


def test_get_list_fails_when_any_schedule_is_inconsistent(
    scheduler_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
) -> None:
    scheduler_service.add(AgentType.CODEX, make_trigger())
    broken = scheduler_service.add(AgentType.CODEX, make_trigger())
    del fake_scheduler.jobs[broken.id]

    with pytest.raises(SchedulerError, match=str(broken.id)):
        scheduler_service.get_list()
