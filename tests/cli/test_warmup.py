"""`warmpass warmup` through the Typer runner, with the agent process faked."""

from subprocess import TimeoutExpired

import pytest
from typer.testing import CliRunner

from tests.support.fakes import FakeAgentProcess
from warmpass.cli.main import app
from warmpass.warmup.service import WARMUP_PROMPT

runner = CliRunner()


@pytest.mark.parametrize(
    ("agent", "executable"),
    [
        pytest.param("codex", "codex", id="codex"),
        pytest.param("antigravity", "agy", id="antigravity"),
        pytest.param("claude", "claude", id="claude"),
    ],
)
def test_successful_warmup_without_agent_output_exits_zero_and_logs_to_stdout(
    agent_process: FakeAgentProcess, agent: str, executable: str
) -> None:
    agent_process.stdout = ""

    result = runner.invoke(app, ["warmup", "--agent", agent])

    assert result.exit_code == 0
    (completion,) = result.stdout.splitlines()
    (attempt,) = result.stderr.splitlines()
    assert f"INFO Warmup completed: agent={agent} duration=" in completion
    assert attempt.endswith(f"INFO Attempting warmup: agent={agent}")
    (call,) = agent_process.calls
    assert call.command[0] == executable
    assert WARMUP_PROMPT in call.command
    assert "--model" not in call.command


@pytest.mark.parametrize("agent", ["codex", "antigravity", "claude"])
def test_selected_model_is_passed_to_the_agent(
    agent_process: FakeAgentProcess, agent: str
) -> None:
    result = runner.invoke(
        app, ["warmup", "--agent", agent, "--model", "custom-model"], input=""
    )

    assert result.exit_code == 0, result.output
    (call,) = agent_process.calls
    assert WARMUP_PROMPT in call.command
    assert call.command[-2:] == ["--model", "custom-model"]


@pytest.mark.parametrize(
    ("returncode", "error", "message"),
    [
        pytest.param(7, None, "exit code 7", id="agent-failed"),
        pytest.param(0, TimeoutExpired("codex", 60), "timed out", id="timeout"),
        pytest.param(0, FileNotFoundError(), "not found", id="not-installed"),
    ],
)
def test_failed_warmup_exits_one_with_message_on_stderr(
    agent_process: FakeAgentProcess,
    returncode: int,
    error: BaseException | None,
    message: str,
) -> None:
    agent_process.returncode = returncode
    agent_process.error = error

    result = runner.invoke(app, ["warmup", "--agent", "codex"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "INFO Attempting warmup: agent=codex" in result.stderr
    assert "ERROR Warmup failed: agent=codex" in result.stderr
    assert message in result.stderr
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(["warmup"], id="missing-agent"),
        pytest.param(["warmup", "--agent", "unknown"], id="unknown-agent"),
    ],
)
def test_usage_errors_exit_two_without_running_an_agent(
    agent_process: FakeAgentProcess, args: list[str]
) -> None:
    result = runner.invoke(app, args)

    assert result.exit_code == 2
    assert agent_process.calls == []
