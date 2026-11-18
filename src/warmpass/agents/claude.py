"""Warmup adapter for the Claude Code (claude) CLI."""

from warmpass.agents.warmup_process import run_agent_warmup_process
from warmpass.warmup.base import WarmupAgent


class ClaudeWarmupAgent(WarmupAgent):
    """Run single-turn, ephemeral warmups through the Claude Code CLI with tools, hooks, and MCP disabled."""

    def __init__(
        self,
        *,
        executable: str = "claude",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str, model: str | None = None) -> None:
        """Invoke the Claude Code CLI with the given prompt and optional model, or raise WarmupError."""
        command = [
            self._executable,
            prompt,
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
        if model is not None:
            command.extend(("--model", model))

        run_agent_warmup_process(
            command,
            executable=self._executable,
            timeout_seconds=self._timeout_seconds,
        )
