from datetime import time
from unittest.mock import Mock
from uuid import uuid4

import pytest
from typer.testing import CliRunner

import warmpass.cli.schedule as schedule_module
from warmpass.agents.models import WarmupAgentType
from warmpass.cli.main import app
from warmpass.scheduling.models import (
    DailyTrigger,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)


def test_add_daily_schedule_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(at=time(23, 23)),
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
            "--at",
            "23:23",
        ],
    )

    assert result.exit_code == 0
    service.add.assert_called_once_with(
        WarmupAgentType.CODEX,
        DailyTrigger(at=time(23, 23)),
    )


def test_add_weekly_schedule_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trigger = WeeklyTrigger(
        at=time(23, 23),
        days=[WeekDay.MONDAY, WeekDay.FRIDAY],
    )
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
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
            "--at",
            "23:23",
            "--day",
            "monday",
            "--day",
            "friday",
        ],
    )

    assert result.exit_code == 0, result.output
    service.add.assert_called_once_with(WarmupAgentType.CODEX, trigger)


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
            "--at",
            "25:00",
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
            "--at",
            "23:23",
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
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(at=time(23, 23)),
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
            agent=WarmupAgentType.CODEX,
            trigger=DailyTrigger(at=time(23, 23)),
        ),
        WarmupSchedule(
            id=uuid4(),
            agent=WarmupAgentType.ANTIGRAVITY,
            trigger=DailyTrigger(at=time(22, 22)),
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
