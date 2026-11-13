from subprocess import DEVNULL

from tests.support.fakes import FakeAgentProcess
from warmpass.agents.codex import CodexWarmupAgent


def test_codex_warmup_runs_read_only_and_ephemeral(
    agent_process: FakeAgentProcess,
) -> None:
    CodexWarmupAgent().warmup("say OK")

    (call,) = agent_process.calls
    assert call.command == [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "say OK",
    ]
    assert call.options["stdin"] is DEVNULL
    assert call.options["timeout"] == 60


def test_codex_warmup_uses_configured_executable_and_timeout(
    agent_process: FakeAgentProcess,
) -> None:
    CodexWarmupAgent(executable="/opt/bin/codex", timeout_seconds=5).warmup("say OK")

    (call,) = agent_process.calls
    assert call.command[0] == "/opt/bin/codex"
    assert call.options["timeout"] == 5
