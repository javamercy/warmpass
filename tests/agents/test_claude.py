"""Test Claude's unattended invocation without running Claude Code."""

import json
import sys
from pathlib import Path
from subprocess import DEVNULL

from tests.support.fakes import FakeAgentProcess
from warmpass.agents.claude import ClaudeWarmupAgent


def test_claude_warmup_disables_tools_hooks_and_session_persistence(
    agent_process: FakeAgentProcess,
) -> None:
    ClaudeWarmupAgent().warmup("say OK")

    (call,) = agent_process.calls
    assert call.command == [
        "claude",
        "say OK",
        "--print",
        "--output-format",
        "json",
        "--tools",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--settings",
        '{"disableAllHooks":true}',
        "--no-session-persistence",
        "--max-turns",
        "1",
    ]
    assert call.options["stdin"] is DEVNULL
    assert call.options["timeout"] == 60


def test_claude_warmup_passes_the_selected_model(
    agent_process: FakeAgentProcess,
) -> None:
    ClaudeWarmupAgent().warmup("say OK", model="custom-model")

    (call,) = agent_process.calls
    assert call.command[-2:] == ["--model", "custom-model"]
    assert call.command.count("--model") == 1


def test_claude_warmup_uses_configured_executable_and_timeout(
    agent_process: FakeAgentProcess,
) -> None:
    ClaudeWarmupAgent(executable="/opt/bin/claude", timeout_seconds=5).warmup("say OK")

    (call,) = agent_process.calls
    assert call.command[0] == "/opt/bin/claude"
    assert call.options["timeout"] == 5


def test_claude_warmup_preserves_empty_tool_argument_and_closes_stdin(
    tmp_path: Path,
) -> None:
    # The adapter puts the prompt first, so Python can execute it as a script.
    script = tmp_path / "claude stand-in.py"
    script.write_text(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "received = {'arguments': sys.argv[1:], 'stdin': sys.stdin.read()}\n"
        "Path(__file__).with_suffix('.json').write_text("
        "json.dumps(received), encoding='utf-8')\n"
        "print(json.dumps({'result': 'OK'}))\n",
        encoding="utf-8",
    )

    ClaudeWarmupAgent(executable=sys.executable).warmup(str(script))

    received = json.loads(script.with_suffix(".json").read_text(encoding="utf-8"))
    arguments = received["arguments"]
    assert arguments[arguments.index("--tools") + 1] == ""
    assert json.loads(arguments[arguments.index("--settings") + 1]) == {
        "disableAllHooks": True
    }
    assert received["stdin"] == ""
