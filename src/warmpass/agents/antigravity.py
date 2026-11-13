from warmpass.agents.base import WarmupAgent, run_agent_warmup_process


class AntigravityWarmupAgent(WarmupAgent):
    def __init__(
        self,
        *,
        executable: str = "agy",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str) -> None:
        command = [
            self._executable,
            "--prompt",
            prompt,
            "--model",
            "gemini-3.8-flash-low",
            "--output-format",
            "json",
            "--print-timeout",
            f"{self._timeout_seconds}s",
            "--disable-slash-commands",
        ]
        run_agent_warmup_process(
            command,
            executable=self._executable,
            timeout_seconds=self._timeout_seconds,
        )
