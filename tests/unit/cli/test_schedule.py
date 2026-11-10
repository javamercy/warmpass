from datetime import time
from unittest.mock import Mock
from uuid import uuid4

import pytest
from typer.testing import CliRunner

import warmpass.cli.schedule as schedule_module
from warmpass.agents.models import AgentType
from warmpass.cli.main import app
from warmpass.scheduling.base import WarmupSchedulerError
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)


def test_add_daily_schedule_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(from_=time(23, 23), every=2)),
    )
    service = Mock()
    service.add.return_value = schedule

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        [
            "schedule",
            "add",
            "--agent",
            "codex",
            "--trigger",
            "daily",
            "--from",
            "23:23",
            "--every",
            "2h",
        ],
    )

    assert result.exit_code == 0
    service.add.assert_called_once_with(
        AgentType.CODEX,
        DailyTrigger(window=HourlyWindow(from_=time(23, 23), every=2)),
    )


def test_add_weekly_schedule_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger = WeeklyTrigger(
        window=HourlyWindow(from_=time(23, 23), every=2),
        days=[WeekDay.MONDAY, WeekDay.FRIDAY],
    )
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=trigger,
    )
    service = Mock()
    service.add.return_value = schedule

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        [
            "schedule",
            "add",
            "--agent",
            "codex",
            "--trigger",
            "weekly",
            "--from",
            "23:23",
            "--every",
            "2h",
            "--day",
            "monday",
            "--day",
            "friday",
        ],
    )

    assert result.exit_code == 0, result.output
    service.add.assert_called_once_with(AgentType.CODEX, trigger)


def test_add_schedule_rejects_invalid_time(monkeypatch: pytest.MonkeyPatch) -> None:
    service = Mock()
    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        [
            "schedule",
            "add",
            "--agent",
            "codex",
            "--trigger",
            "daily",
            "--from",
            "25:00",
            "--every",
            "2h",
        ],
    )

    assert result.exit_code != 0
    service.add.assert_not_called()


@pytest.mark.parametrize(
    ("trigger", "day_options"),
    [
        pytest.param("weekly", [], id="weekly-without-day"),
        pytest.param(
            "weekly",
            ["--day", "monday", "--day", "monday"],
            id="weekly-with-duplicate-day",
        ),
        pytest.param(
            "daily",
            ["--day", "monday"],
            id="daily-with-day",
        ),
    ],
)
def test_add_schedule_rejects_invalid_day_options(
    monkeypatch: pytest.MonkeyPatch,
    trigger: str,
    day_options: list[str],
) -> None:
    create_service = Mock()
    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        create_service,
    )

    result = CliRunner().invoke(
        app,
        [
            "schedule",
            "add",
            "--agent",
            "codex",
            "--trigger",
            trigger,
            "--from",
            "23:23",
            "--every",
            "2h",
            *day_options,
        ],
    )

    assert result.exit_code != 0
    create_service.assert_not_called()


def test_remove_schedule_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule_id = uuid4()
    service = Mock()

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        ["schedule", "remove", str(schedule_id)],
    )

    assert result.exit_code == 0, result.output
    service.remove.assert_called_once_with(schedule_id)


def test_get_missing_schedule_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule_id = uuid4()
    service = Mock()
    service.get.return_value = None

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        ["schedule", "get", str(schedule_id)],
    )

    assert result.exit_code != 0
    service.get.assert_called_once_with(schedule_id)


def test_get_existing_schedule_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(from_=time(23, 23), every=2)),
    )
    service = Mock()
    service.get.return_value = schedule

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        ["schedule", "get", str(schedule.id)],
    )

    assert result.exit_code == 0, result.output
    service.get.assert_called_once_with(schedule.id)
    assert str(schedule.id) in result.stdout


def test_list_schedules_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedules = [
        WarmupSchedule(
            id=uuid4(),
            agent=AgentType.CODEX,
            trigger=DailyTrigger(window=HourlyWindow(from_=time(23, 23), every=2)),
        ),
        WarmupSchedule(
            id=uuid4(),
            agent=AgentType.ANTIGRAVITY,
            trigger=DailyTrigger(window=HourlyWindow(from_=time(22, 22), every=2)),
        ),
    ]
    service = Mock()
    service.get_list.return_value = schedules

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(app, ["schedule", "list"])

    assert result.exit_code == 0, result.output
    service.get_list.assert_called_once_with()
    for schedule in schedules:
        assert str(schedule.id) in result.stdout


@pytest.mark.parametrize("command", ["get", "remove"])
def test_schedule_command_rejects_invalid_id(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    create_service = Mock()
    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        create_service,
    )

    result = CliRunner().invoke(
        app,
        ["schedule", command, "not-a-uuid"],
    )

    assert result.exit_code != 0
    create_service.assert_not_called()


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--every", "6h"],
        ["--every", "2h", "--from", "09:00", "--until", "09:00"],
        ["--every", "1h", "--from", "9:00"],
        ["--every", "1h", "--until", "00:00"],
        ["--every", "1h", "--at", "09:00"],
    ],
)
def test_add_rejects_invalid_window_options(
    monkeypatch: pytest.MonkeyPatch, options: list[str]
) -> None:
    create_service = Mock()
    monkeypatch.setattr(
        schedule_module, "create_warmup_scheduler_service", create_service
    )
    result = CliRunner().invoke(
        app, ["schedule", "add", "--agent", "codex", "--trigger", "daily", *options]
    )
    assert result.exit_code != 0
    create_service.assert_not_called()


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("add", ["add", "--agent", "codex", "--trigger", "daily", "--every", "1h"]),
        ("get", ["get", str(uuid4())]),
        ("get_list", ["list"]),
        ("remove", ["remove", str(uuid4())]),
        ("clear", ["clear", "--yes"]),
    ],
)
def test_scheduler_errors_are_reported(
    monkeypatch: pytest.MonkeyPatch, method: str, args: list[str]
) -> None:
    service = Mock()
    getattr(service, method).side_effect = WarmupSchedulerError("invalid schedule")
    monkeypatch.setattr(
        schedule_module, "create_warmup_scheduler_service", Mock(return_value=service)
    )
    result = CliRunner().invoke(app, ["schedule", *args])
    assert result.exit_code == 1
    assert "invalid schedule" in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("args", "answer", "clears"),
    [
        ([], "n\n", False),
        ([], "y\n", True),
        (["--yes"], "", True),
        (["-y"], "", True),
    ],
)
def test_clear_confirmation(
    monkeypatch: pytest.MonkeyPatch, args: list[str], answer: str, clears: bool
) -> None:
    service = Mock()
    factory = Mock(return_value=service)
    monkeypatch.setattr(schedule_module, "create_warmup_scheduler_service", factory)
    result = CliRunner().invoke(app, ["schedule", "clear", *args], input=answer)
    assert result.exit_code == 0, result.output
    if clears:
        service.clear.assert_called_once_with()
        service.get_list.assert_not_called()
        assert "cleared" in result.output
    else:
        factory.assert_not_called()
        assert "cancelled" in result.output
