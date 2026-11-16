from warmpass.agents.base import WarmupAgent, run_agent_warmup_process


class ClaudeWarmupAgent(WarmupAgent):
    def __init__(
        self,
        *,
        executable: str = "claude",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str, model: str | None = None) -> None:
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
