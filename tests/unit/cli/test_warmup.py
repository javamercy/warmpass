from unittest.mock import MagicMock, Mock

import pytest
from typer.testing import CliRunner

import warmpass.cli.warmup as warmup_module
from warmpass.agents.base import WarmupError
from warmpass.agents.models import AgentType
from warmpass.cli.main import app


@pytest.mark.parametrize("is_terminal", [False, True])
def test_warmup_command_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    is_terminal: bool,
) -> None:
    service = Mock()
    service.warmup.return_value = None
    console = Mock(is_terminal=is_terminal)
    console.status.return_value = MagicMock()
    monkeypatch.setattr(warmup_module, "Console", Mock(return_value=console))

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
    assert "Warmup completed" in result.stdout
    assert "agent=codex" in result.stdout
    create_service.assert_called_once_with(AgentType.CODEX)
    service.warmup.assert_called_once()
    assert console.status.called is is_terminal


@pytest.mark.parametrize("is_terminal", [False, True])
def test_warmup_command_fails(
    monkeypatch: pytest.MonkeyPatch,
    is_terminal: bool,
) -> None:
    service = Mock()
    service.warmup.side_effect = WarmupError("Agent unavailable.")
    console = Mock(is_terminal=is_terminal)
    console.status.return_value = MagicMock()
    monkeypatch.setattr(warmup_module, "Console", Mock(return_value=console))

    monkeypatch.setattr(
        warmup_module,
        "create_warmup_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(app, ["warmup", "--agent", "codex"])

    assert result.exit_code == 1
    assert "Warmup started" in result.stdout
    assert "Warmup completed" not in result.stdout
    assert "Warmup failed" in result.stderr
    assert "agent=codex" in result.stderr
    assert "Agent unavailable." in result.stderr
    assert "Traceback" not in result.output
    service.warmup.assert_called_once()
    assert console.status.called is is_terminal
