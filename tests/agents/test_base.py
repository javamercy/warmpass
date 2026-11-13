"""Tests for the shared agent process runner.

Exit codes, output decoding, and the working directory use a real stand-in
process (the Python interpreter). Timeouts, start failures, and the options an
unattended run depends on use the faked process boundary.
"""

import sys
from pathlib import Path
from subprocess import DEVNULL, TimeoutExpired

import pytest

from tests.support.fakes import FakeAgentProcess
from warmpass.agents.base import WarmupError, run_agent_warmup_process


def python_agent(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def run(command: list[str], *, timeout_seconds: int = 30) -> str:
    completed = run_agent_warmup_process(
        command, executable="agent", timeout_seconds=timeout_seconds
    )
    return completed.stdout


def test_reply_is_returned_when_agent_exits_zero() -> None:
    assert run(python_agent("print('OK')")).strip() == "OK"


def test_non_utf8_output_is_replaced_instead_of_crashing() -> None:
    code = "import sys; sys.stdout.buffer.write(b'OK\\xff\\n')"

    assert run(python_agent(code)) == "OK\ufffd\n"


@pytest.mark.parametrize(
    "code",
    [
        pytest.param("pass", id="no-output"),
        pytest.param("print('   ')", id="whitespace-only"),
    ],
)
def test_exit_zero_with_empty_reply_is_a_failure(code: str) -> None:
    with pytest.raises(WarmupError, match="empty response"):
        run(python_agent(code))


def test_nonzero_exit_reports_code_and_prefers_stderr_detail() -> None:
    code = "import sys; print('out'); print('quota exhausted', file=sys.stderr); sys.exit(7)"

    with pytest.raises(WarmupError, match="exit code 7: quota exhausted"):
        run(python_agent(code))


def test_nonzero_exit_without_output_still_reports_code() -> None:
    with pytest.raises(WarmupError, match=r"exit code 3\.$"):
        run(python_agent("import sys; sys.exit(3)"))


def test_failure_detail_is_truncated() -> None:
    code = "import sys; print('x' * 500, file=sys.stderr); sys.exit(1)"

    with pytest.raises(WarmupError) as exc_info:
        run(python_agent(code))

    assert str(exc_info.value).endswith(": " + "x" * 200)


def test_agent_runs_in_a_temporary_directory_that_is_removed_afterwards() -> None:
    code = "import os; print(os.getcwd())"

    working_directory = Path(run(python_agent(code)).strip())

    assert working_directory != Path.cwd()
    assert not working_directory.exists()


def test_run_is_unattended_and_bounded(agent_process: FakeAgentProcess) -> None:
    run_agent_warmup_process(
        ["agent", "--flag"], executable="agent", timeout_seconds=45
    )

    (call,) = agent_process.calls
    assert call.command == ["agent", "--flag"]
    assert call.options["stdin"] is DEVNULL
    assert call.options["timeout"] == 45


def test_missing_executable_names_the_executable(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = FileNotFoundError()

    with pytest.raises(WarmupError, match="'agent' not found") as exc_info:
        run(["agent"])

    assert isinstance(exc_info.value.__cause__, FileNotFoundError)


def test_timeout_is_reported_as_unknown_outcome(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = TimeoutExpired(cmd="agent", timeout=45)

    with pytest.raises(
        WarmupError,
        match="timed out after 45 seconds; the usage window may have started",
    ) as exc_info:
        run(["agent"], timeout_seconds=45)

    assert isinstance(exc_info.value.__cause__, TimeoutExpired)


def test_process_that_cannot_start_is_a_warmup_error(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = PermissionError("Permission denied")

    with pytest.raises(WarmupError, match="Permission denied") as exc_info:
        run(["agent"])

    assert isinstance(exc_info.value.__cause__, PermissionError)


def test_temporary_directory_is_removed_after_a_timeout(
    agent_process: FakeAgentProcess,
) -> None:
    agent_process.error = TimeoutExpired(cmd="agent", timeout=1)

    with pytest.raises(WarmupError):
        run(["agent"])

    working_directory = Path(str(agent_process.calls[0].options["cwd"]))
    assert not working_directory.exists()
