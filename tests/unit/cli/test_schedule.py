from datetime import time
from unittest.mock import Mock
from uuid import uuid4

import pytest
from typer.testing import CliRunner

import warmpass.cli.schedule as schedule_module
from warmpass.agents.models import WarmupAgentType
from warmpass.cli.main import app
from warmpass.scheduling.models import DailyTrigger, WarmupSchedule


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
