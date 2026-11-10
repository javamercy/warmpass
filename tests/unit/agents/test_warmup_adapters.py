from pathlib import Path
from subprocess import DEVNULL, CompletedProcess, TimeoutExpired
from types import ModuleType
from typing import cast
from unittest.mock import Mock

import pytest

import warmpass.agents.antigravity as antigravity_module
import warmpass.agents.codex as codex_module
from warmpass.agents.antigravity import AntigravityWarmupAgent
from warmpass.agents.base import WarmupAgent, WarmupError
from warmpass.agents.codex import CodexWarmupAgent
from warmpass.agents.prompts import WARMUP_PROMPT

type AgentCase = tuple[type[WarmupAgent], ModuleType]


@pytest.fixture(
    params=[
        pytest.param(
            (AntigravityWarmupAgent, antigravity_module),
            id="antigravity",
        ),
        pytest.param(
            (CodexWarmupAgent, codex_module),
            id="codex",
        ),
    ]
)
def agent_case(request: pytest.FixtureRequest) -> AgentCase:
    return cast(AgentCase, request.param)


def test_warmup_returns_none_when_agent_exits_successfully(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module = agent_case

    completed = CompletedProcess(
        args=[],
        returncode=0,
        stdout="",
        stderr="",
    )

    run = Mock(return_value=completed)
    monkeypatch.setattr(agent_module, "run", run)

    assert agent_class().warmup() is None
    run.assert_called_once()


def test_warmup_raises_when_agent_exits_with_error(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module = agent_case

    completed = CompletedProcess(
        args=[],
        returncode=7,
        stdout="",
        stderr="",
    )

    run = Mock(return_value=completed)
    monkeypatch.setattr(agent_module, "run", run)

    with pytest.raises(WarmupError, match="exit code 7"):
        agent_class().warmup()
    run.assert_called_once()


def test_warmup_raises_when_executable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module = agent_case

    run = Mock(side_effect=FileNotFoundError)
    monkeypatch.setattr(agent_module, "run", run)

    with pytest.raises(WarmupError, match="not found") as exc_info:
        agent_class().warmup()
    assert isinstance(exc_info.value.__cause__, FileNotFoundError)
    run.assert_called_once()


def test_warmup_raises_when_agent_takes_too_long(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module = agent_case

    run = Mock(side_effect=TimeoutExpired(cmd="agent", timeout=60))
    monkeypatch.setattr(agent_module, "run", run)

    with pytest.raises(WarmupError, match="timed out after 60 seconds") as exc_info:
        agent_class().warmup()
    assert isinstance(exc_info.value.__cause__, TimeoutExpired)
    run.assert_called_once()


def test_warmup_raises_when_process_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
) -> None:
    agent_class, agent_module = agent_case

    run = Mock(side_effect=OSError("Permission denied"))
    monkeypatch.setattr(agent_module, "run", run)

    with pytest.raises(WarmupError, match="Permission denied") as exc_info:
        agent_class().warmup()
    assert isinstance(exc_info.value.__cause__, OSError)
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
    agent_class, agent_module = agent_case
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


@pytest.mark.parametrize("failure", ["nonzero", "timeout"])
def test_warmup_cleans_up_temporary_directory_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    agent_case: AgentCase,
    failure: str,
) -> None:
    agent_class, agent_module = agent_case
    working_directories: list[Path] = []

    def fake_run(*args: object, **kwargs: object) -> CompletedProcess[str]:
        working_dir = Path(str(kwargs["cwd"]))
        assert working_dir.is_dir()
        working_directories.append(working_dir)
        if failure == "timeout":
            raise TimeoutExpired(cmd="agent", timeout=60)
        return CompletedProcess(args=[], returncode=7, stdout="", stderr="")

    monkeypatch.setattr(agent_module, "run", fake_run)

    with pytest.raises(WarmupError):
        agent_class().warmup()

    assert len(working_directories) == 1
    assert not working_directories[0].exists()
