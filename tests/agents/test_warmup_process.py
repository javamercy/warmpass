"""Tests for the shared agent process runner.

Exit codes and the working directory use the Python interpreter as a stand-in.
Timeouts, start failures, and subprocess options use the faked process boundary.
"""

import sys
from pathlib import Path
from subprocess import DEVNULL, CalledProcessError, TimeoutExpired

import pytest

from tests.support.fakes import FakeAgentProcess
from warmpass.agents.warmup_process import run_agent_warmup_process
from warmpass.warmup.base import WarmupError


def python_agent(code: str) -> list[str]:
    return [sys.executable, "-c", code]


# --- stand-in agent process ----------------------------------------------------


def test_exit_zero_succeeds_without_output() -> None:
    run_agent_warmup_process(python_agent("pass"), timeout=30)


def test_nonzero_exit_reports_only_the_exit_code() -> None:
    code = "import sys; print('stdout'); print('stderr', file=sys.stderr); sys.exit(7)"

    with pytest.raises(WarmupError) as exc_info:
        run_agent_warmup_process(python_agent(code), timeout=30)

    assert str(exc_info.value) == "Warmup failed with exit code 7."
    assert isinstance(exc_info.value.__cause__, CalledProcessError)


def test_agent_runs_in_a_temporary_directory_that_is_removed_afterwards(
    tmp_path: Path,
) -> None:
    cwd_file = tmp_path / "cwd.txt"
    code = (
        "import os; from pathlib import Path; "
        f"Path({str(cwd_file)!r}).write_text(os.getcwd(), encoding='utf-8')"
    )

    run_agent_warmup_process(python_agent(code), timeout=30)

    working_directory = Path(cwd_file.read_text(encoding="utf-8"))
    assert working_directory != Path.cwd()
    assert not working_directory.exists()


# --- faked agent process -------------------------------------------------------


def test_run_is_unattended_and_bounded(agent_process: FakeAgentProcess) -> None:
    run_agent_warmup_process(["agent", "--flag"], timeout=45)

    (call,) = agent_process.calls
    assert call.command == ["agent", "--flag"]
    assert call.options["stdin"] is DEVNULL
    assert call.options["timeout"] == 45
    assert call.options["check"] is True


def test_missing_executable_names_the_executable(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = FileNotFoundError()

    with pytest.raises(WarmupError, match="'agent' not found") as exc_info:
        run_agent_warmup_process(["agent"], timeout=30)

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_timeout_is_reported_with_the_configured_duration(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = TimeoutExpired(cmd="agent", timeout=45)

    with pytest.raises(WarmupError) as exc_info:
        run_agent_warmup_process(["agent"], timeout=45)

    assert str(exc_info.value) == "Warmup timed out after 45 seconds."
    assert isinstance(exc_info.value.__cause__, TimeoutExpired)


def test_process_that_cannot_start_is_a_warmup_error(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = PermissionError("Permission denied")

    with pytest.raises(WarmupError, match="Permission denied") as exc_info:
        run_agent_warmup_process(["agent"], timeout=30)

    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_temporary_directory_is_removed_after_a_timeout(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = TimeoutExpired(cmd="agent", timeout=1)

    with pytest.raises(WarmupError):
        run_agent_warmup_process(["agent"], timeout=1)

    working_directory = Path(str(agent_process.calls[0].options["cwd"]))
    assert not working_directory.exists()
