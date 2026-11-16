from subprocess import DEVNULL

from tests.support.fakes import FakeAgentProcess
from warmpass.agents.antigravity import AntigravityWarmupAgent


def test_antigravity_warmup_uses_json_output_and_no_slash_commands(
    agent_process: FakeAgentProcess,
) -> None:
    AntigravityWarmupAgent().warmup("say OK")

    (call,) = agent_process.calls
    assert call.command == [
        "agy",
        "--prompt",
        "say OK",
        "--output-format",
        "json",
        "--print-timeout",
        "60s",
        "--disable-slash-commands",
    ]
    assert call.options["stdin"] is DEVNULL
    assert call.options["timeout"] == 60


def test_antigravity_warmup_passes_the_selected_model(
    agent_process: FakeAgentProcess,
) -> None:
    AntigravityWarmupAgent().warmup("say OK", model="gemini-3.8-flash-low")

    (call,) = agent_process.calls
    assert call.command[-2:] == ["--model", "gemini-3.8-flash-low"]
    assert call.command.count("--model") == 1


def test_antigravity_warmup_keeps_agent_and_process_timeouts_in_step(
    agent_process: FakeAgentProcess,
) -> None:
    AntigravityWarmupAgent(executable="/opt/bin/agy", timeout_seconds=30).warmup(
        "say OK"
    )

    (call,) = agent_process.calls
    assert call.command[0] == "/opt/bin/agy"
    assert call.command[call.command.index("--print-timeout") + 1] == "30s"
    assert call.options["timeout"] == 30
