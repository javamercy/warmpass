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
def test_successful_warmup_exits_zero_and_logs_to_stdout(
    agent_process: FakeAgentProcess, agent: str, executable: str
) -> None:
    result = runner.invoke(app, ["warmup", "--agent", agent])

    assert result.exit_code == 0
    assert f"INFO Warmup started: agent={agent}" in result.stdout
    assert f"INFO Warmup completed: agent={agent} duration=" in result.stdout
    assert result.stderr == ""
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
    assert result.stderr == ""
    (call,) = agent_process.calls
    assert WARMUP_PROMPT in call.command
    assert call.command[-2:] == ["--model", "custom-model"]


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "error", "message"),
    [
        pytest.param(7, "", "quota exhausted", None, "exit code 7", id="agent-failed"),
        pytest.param(0, "", "", None, "empty response", id="empty-reply"),
        pytest.param(0, "", "", TimeoutExpired("codex", 60), "timed out", id="timeout"),
        pytest.param(0, "", "", FileNotFoundError(), "not found", id="not-installed"),
    ],
)
def test_failed_warmup_exits_one_with_message_on_stderr(
    agent_process: FakeAgentProcess,
    returncode: int,
    stdout: str,
    stderr: str,
    error: BaseException | None,
    message: str,
) -> None:
    agent_process.returncode = returncode
    agent_process.stdout = stdout
    agent_process.stderr = stderr
    agent_process.error = error

    result = runner.invoke(app, ["warmup", "--agent", "codex"])

    assert result.exit_code == 1
    assert "Warmup started" in result.stdout
    assert "Warmup completed" not in result.stdout
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
