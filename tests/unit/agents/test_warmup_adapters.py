from subprocess import CompletedProcess, TimeoutExpired
from types import ModuleType
from typing import cast
from unittest.mock import Mock

import pytest

import warmpass.agents.antigravity as antigravity_module
import warmpass.agents.codex as codex_module
from warmpass.agents.antigravity import AntigravityWarmupAgent
from warmpass.agents.base import WarmupAgent
from warmpass.agents.codex import CodexWarmupAgent
from warmpass.agents.models import WarmupAgentType, WarmupStatus

type AgentCase = tuple[type[WarmupAgent], ModuleType, WarmupAgentType]


@pytest.fixture(
    params=[
        pytest.param(
            (AntigravityWarmupAgent, antigravity_module, WarmupAgentType.ANTIGRAVITY),
            id="antigravity",
        ),
        pytest.param(
            (CodexWarmupAgent, codex_module, WarmupAgentType.CODEX),
            id="codex",
        ),
    ]
)
def agent_case(request: pytest.FixtureRequest) -> AgentCase:
    return cast(AgentCase, request.param)


def test_warmup_returns_success_when_agent_exits_successfully(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module, expected_agent = agent_case

    completed = CompletedProcess(
        args=[],
        returncode=0,
        stdout="",
        stderr="",
    )

    run = Mock(return_value=completed)
    monkeypatch.setattr(agent_module, "run", run)

    result = agent_class().warmup()

    assert result.agent == expected_agent
    assert result.status == WarmupStatus.SUCCESS
    assert result.exit_code == 0
    run.assert_called_once()


def test_warmup_returns_failure_when_agent_exits_with_error(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module, expected_agent = agent_case

    completed = CompletedProcess(
        args=[],
        returncode=7,
        stdout="",
        stderr="",
    )

    run = Mock(return_value=completed)
    monkeypatch.setattr(agent_module, "run", run)

    result = agent_class().warmup()

    assert result.agent == expected_agent
    assert result.status == WarmupStatus.FAILED
    assert result.exit_code == 7
    run.assert_called_once()


def test_warmup_returns_failure_when_executable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module, expected_agent = agent_case

    run = Mock(side_effect=FileNotFoundError)
    monkeypatch.setattr(agent_module, "run", run)

    result = agent_class().warmup()

    assert result.agent == expected_agent
    assert result.status == WarmupStatus.FAILED
    assert result.exit_code is None
    run.assert_called_once()


def test_warmup_returns_timeout_when_agent_takes_too_long(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module, expected_agent = agent_case

    run = Mock(side_effect=TimeoutExpired(cmd="agent", timeout=60))
    monkeypatch.setattr(agent_module, "run", run)

    result = agent_class().warmup()

    assert result.agent == expected_agent
    assert result.status == WarmupStatus.TIMEOUT
    assert result.exit_code is None
    run.assert_called_once()


def test_warmup_returns_failure_when_process_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module, expected_agent = agent_case

    run = Mock(side_effect=OSError("Permission denied"))
    monkeypatch.setattr(agent_module, "run", run)

    result = agent_class().warmup()

    assert result.agent == expected_agent
    assert result.status == WarmupStatus.FAILED
    assert result.exit_code is None
    run.assert_called_once()
