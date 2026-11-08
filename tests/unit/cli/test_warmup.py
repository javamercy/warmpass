from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

import warmpass.cli.warmup as warmup_module
from warmpass.agents.models import WarmupAgentType, WarmupResult, WarmupStatus
from warmpass.cli.main import app


def test_warmup_command_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    service.warmup.return_value = WarmupResult(
        agent=WarmupAgentType.CODEX,
        status=WarmupStatus.SUCCESS,
        message="Warmup completed successfully.",
        exit_code=0,
    )

    create_service = Mock(return_value=service)
    monkeypatch.setattr(
        warmup_module,
        "create_warmup_service",
        create_service,
    )

    result = CliRunner().invoke(
        app,
        [
            "warmup",
            "--agent",
            "codex",
        ],
    )

    assert result.exit_code == 0
    create_service.assert_called_once_with(WarmupAgentType.CODEX)
    service.warmup.assert_called_once()


def test_warmup_command_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = Mock()
    service.warmup.return_value = WarmupResult(
        agent=WarmupAgentType.CODEX,
        status=WarmupStatus.FAILED,
        message="Agent unavailable.",
        exit_code=1,
    )

    monkeypatch.setattr(
        warmup_module,
        "create_warmup_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(app, ["warmup", "--agent", "codex"])

    assert result.exit_code != 0
