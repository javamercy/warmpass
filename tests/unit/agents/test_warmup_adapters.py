from pathlib import Path
from subprocess import DEVNULL, CompletedProcess, TimeoutExpired
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
from warmpass.agents.prompts import WARMUP_PROMPT

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


def test_codex_uses_read_only_ephemeral_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(
        return_value=CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
    )
    monkeypatch.setattr(codex_module, "run", run)

    CodexWarmupAgent().warmup()

    run.assert_called_once()
    command = run.call_args.args[0]
    options = run.call_args.kwargs

    assert command == [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
        WARMUP_PROMPT,
    ]
    assert options["stdin"] == DEVNULL
    assert options["timeout"] == 60


def test_antigravity_uses_configured_executable_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(
        return_value=CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )
    )
    monkeypatch.setattr(antigravity_module, "run", run)

    AntigravityWarmupAgent(
        executable="test-agy",
        timeout_seconds=30,
    ).warmup()

    run.assert_called_once()
    command = run.call_args.args[0]
    options = run.call_args.kwargs

    assert command == [
        "test-agy",
        "--prompt",
        WARMUP_PROMPT,
        "--model",
        "gemini-3.8-flash-low",
        "--output-format",
        "json",
        "--print-timeout",
        "30s",
        "--disable-slash-commands",
    ]
    assert options["stdin"] == DEVNULL
    assert options["timeout"] == 30


def test_warmup_cleans_up_temporary_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module, _ = agent_case
    working_directories: list[Path] = []

    def fake_run(*args: object, **kwargs: object) -> CompletedProcess[str]:
        working_dir = Path(str(kwargs["cwd"]))

        assert working_dir.is_dir()
        working_directories.append(working_dir)

        return CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(agent_module, "run", fake_run)

    agent_class().warmup()

    assert len(working_directories) == 1
    assert not working_directories[0].exists()
