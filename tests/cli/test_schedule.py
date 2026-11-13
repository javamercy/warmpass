"""`warmpass schedule ...` through the Typer runner.

The real service and a real store (under tmp_path) sit behind the CLI. Only the
OS scheduler is faked, so state assertions look at the fake's jobs and the store.
"""

from datetime import time
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from tests.support.fakes import FakeOSJobScheduler
from warmpass.agents.models import AgentType
from warmpass.cli.main import app
from warmpass.scheduling.base import SchedulerError
from warmpass.scheduling.models import DailyTrigger, HourlyWindow, WarmupSchedule
from warmpass.scheduling.service import SchedulerService
from warmpass.scheduling.store import WarmupScheduleStore

runner = CliRunner()


def add_args(trigger: str, *extra: str, every: str = "2h") -> list[str]:
    return [
        "schedule",
        "add",
        "--agent",
        "codex",
        "--trigger",
        trigger,
        "--every",
        every,
        *extra,
    ]


def add_existing_schedule(service: SchedulerService) -> WarmupSchedule:
    window = HourlyWindow(from_=time(9), until=time(17), every=2)
    return service.add(AgentType.CODEX, DailyTrigger(window=window))


def hour_minute_weekday(
    scheduler: FakeOSJobScheduler,
) -> list[tuple[int, int, int | None]]:
    (job,) = scheduler.jobs.values()
    return [(t.hour, t.minute, t.weekday) for t in job.triggers]


@pytest.mark.usefixtures("cli_service")
class TestAdd:
    def test_daily_schedule_registers_one_job_and_saves_the_record(
        self, fake_scheduler: FakeOSJobScheduler, schedule_store: WarmupScheduleStore
    ) -> None:
        result = runner.invoke(
            app, add_args("daily", "--from", "09:00", "--until", "17:00")
        )

        assert result.exit_code == 0, result.output
        (schedule_id,) = fake_scheduler.jobs
        assert schedule_store.list_ids() == {schedule_id}
        assert "Schedule added:" in result.stdout
        assert str(schedule_id) in result.stdout
        (job,) = fake_scheduler.jobs.values()
        assert job.command[1:] == ["warmup", "--agent", "codex"]
        assert hour_minute_weekday(fake_scheduler) == [
            (9, 0, None),
            (11, 0, None),
            (13, 0, None),
            (15, 0, None),
        ]

    def test_weekly_schedule_accepts_repeated_days_in_any_case(
        self, fake_scheduler: FakeOSJobScheduler
    ) -> None:
        result = runner.invoke(
            app,
            add_args(
                "weekly", "--from", "09:00", "--until", "11:00",
                "--day", "monday", "--day", "Friday",
            ),
        )  # fmt: skip

        assert result.exit_code == 0, result.output
        assert hour_minute_weekday(fake_scheduler) == [(9, 0, 0), (9, 0, 4)]

    @pytest.mark.parametrize(
        ("args", "message"),
        [
            pytest.param(
                add_args("daily", "--from", "9:30"), "HH:MM format", id="time-format"
            ),
            pytest.param(
                add_args("daily", "--from", "25:00"), "valid time", id="time-range"
            ),
            pytest.param(
                add_args("daily", "--day", "monday"),
                "--day can only be used with a weekly trigger",
                id="daily-with-day",
            ),
            pytest.param(
                add_args("weekly"), "requires at least one --day", id="weekly-no-day"
            ),
            pytest.param(
                add_args("weekly", "--day", "monday", "--day", "monday"),
                "Duplicate weekdays",
                id="duplicate-day",
            ),
            pytest.param(
                add_args("daily", "--from", "09:00", "--until", "09:00"),
                "cannot be the same",
                id="empty-window",
            ),
            pytest.param(
                add_args("daily", "--until", "00:00"),
                "would contain no runs",
                id="ends-at-midnight-without-start",
            ),
            pytest.param(
                add_args(
                    "weekly", "--day", "monday", "--from", "22:00", "--until", "03:00"
                ),
                "cannot cross midnight",
                id="weekly-crosses-midnight",
            ),
            pytest.param(add_args("daily", every="6h"), "6h", id="interval-too-long"),
        ],
    )
    def test_invalid_options_exit_two_and_change_nothing(
        self,
        fake_scheduler: FakeOSJobScheduler,
        schedule_store: WarmupScheduleStore,
        args: list[str],
        message: str,
    ) -> None:
        result = runner.invoke(app, args)

        assert result.exit_code == 2
        assert message in result.stderr
        assert fake_scheduler.calls == []
        assert schedule_store.list_ids() == set()

    def test_scheduler_failure_exits_one_without_a_success_message(
        self, fake_scheduler: FakeOSJobScheduler
    ) -> None:
        fake_scheduler.failures["register_job"] = SchedulerError("launchd refused")

        result = runner.invoke(app, add_args("daily"))

        assert result.exit_code == 1
        assert "Error: launchd refused" in result.stderr
        assert "Schedule added" not in result.stdout


@pytest.mark.usefixtures("cli_service")
class TestRemove:
    def test_removes_the_job_and_the_record(
        self,
        cli_service: SchedulerService,
        fake_scheduler: FakeOSJobScheduler,
        schedule_store: WarmupScheduleStore,
    ) -> None:
        schedule = add_existing_schedule(cli_service)

        result = runner.invoke(app, ["schedule", "remove", str(schedule.id)])

        assert result.exit_code == 0, result.output
        assert f"'{schedule.id}' has been removed" in result.stdout
        assert fake_scheduler.jobs == {}
        assert schedule_store.list_ids() == set()

    def test_unknown_schedule_exits_one_and_touches_no_job(
        self, fake_scheduler: FakeOSJobScheduler
    ) -> None:
        result = runner.invoke(app, ["schedule", "remove", str(uuid4())])

        assert result.exit_code == 1
        assert "does not exist" in result.stderr
        assert "unregister_job" not in fake_scheduler.calls

    def test_malformed_id_exits_two(self) -> None:
        result = runner.invoke(app, ["schedule", "remove", "not-a-uuid"])

        assert result.exit_code == 2


@pytest.mark.usefixtures("cli_service")
class TestClear:
    @pytest.mark.parametrize(
        ("args", "answer"),
        [
            pytest.param(["--yes"], None, id="yes-flag"),
            pytest.param(["-y"], None, id="short-yes-flag"),
            pytest.param([], "y\n", id="confirmed"),
        ],
    )
    def test_clears_jobs_and_records(
        self,
        cli_service: SchedulerService,
        fake_scheduler: FakeOSJobScheduler,
        schedule_store: WarmupScheduleStore,
        args: list[str],
        answer: str | None,
    ) -> None:
        add_existing_schedule(cli_service)
        add_existing_schedule(cli_service)

        result = runner.invoke(app, ["schedule", "clear", *args], input=answer)

        assert result.exit_code == 0, result.output
        assert "Warmup schedules cleared." in result.stdout
        assert fake_scheduler.jobs == {}
        assert schedule_store.list_ids() == set()

    def test_declined_confirmation_cancels_without_touching_anything(
        self,
        cli_service: SchedulerService,
        fake_scheduler: FakeOSJobScheduler,
        schedule_store: WarmupScheduleStore,
    ) -> None:
        schedule = add_existing_schedule(cli_service)
        fake_scheduler.calls.clear()

        result = runner.invoke(app, ["schedule", "clear"], input="n\n")

        assert result.exit_code == 0
        assert "Clear cancelled." in result.stdout
        assert fake_scheduler.calls == []
        assert schedule_store.list_ids() == {schedule.id}

    def test_scheduler_failure_exits_one(
        self, fake_scheduler: FakeOSJobScheduler
    ) -> None:
        fake_scheduler.failures["clear_jobs"] = SchedulerError("launchctl failed")

        result = runner.invoke(app, ["schedule", "clear", "--yes"])

        assert result.exit_code == 1
        assert "Error: launchctl failed" in result.stderr
        assert "cleared" not in result.stdout


@pytest.mark.usefixtures("cli_service")
class TestGet:
    def test_prints_the_schedule(self, cli_service: SchedulerService) -> None:
        schedule = add_existing_schedule(cli_service)

        result = runner.invoke(app, ["schedule", "get", str(schedule.id)])

        assert result.exit_code == 0, result.output
        assert str(schedule.id) in result.stdout
        assert "codex" in result.stdout
        assert "Daily, every 2 hours, [09:00–17:00)" in result.stdout

    def test_unknown_schedule_exits_one(self) -> None:
        schedule_id = uuid4()

        result = runner.invoke(app, ["schedule", "get", str(schedule_id)])

        assert result.exit_code == 1
        assert f"No schedule found with ID: {schedule_id}" in result.stderr

    def test_record_without_os_job_exits_one_with_the_drift(
        self, cli_service: SchedulerService, fake_scheduler: FakeOSJobScheduler
    ) -> None:
        schedule = add_existing_schedule(cli_service)
        fake_scheduler.jobs.clear()

        result = runner.invoke(app, ["schedule", "get", str(schedule.id)])

        assert result.exit_code == 1
        assert "OS job is missing" in result.stderr


@pytest.mark.usefixtures("cli_service")
class TestList:
    def test_says_when_there_are_no_schedules(self) -> None:
        result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 0
        assert "No warmup schedules found." in result.stdout

    def test_prints_every_schedule(self, cli_service: SchedulerService) -> None:
        ids: list[UUID] = [
            add_existing_schedule(cli_service).id,
            add_existing_schedule(cli_service).id,
        ]

        result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 0, result.output
        assert all(str(schedule_id) in result.stdout for schedule_id in ids)

    def test_os_job_without_record_exits_one(
        self, cli_service: SchedulerService, schedule_store: WarmupScheduleStore
    ) -> None:
        schedule = add_existing_schedule(cli_service)
        schedule_store.remove(schedule.id)

        result = runner.invoke(app, ["schedule", "list"])

        assert result.exit_code == 1
        assert "no saved schedule record" in result.stderr
