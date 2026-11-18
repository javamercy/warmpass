from warmpass.agents.warmup_process import run_agent_warmup_process
from warmpass.warmup.base import WarmupAgent


class AntigravityWarmupAgent(WarmupAgent):
    def __init__(
        self,
        *,
        executable: str = "agy",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str, model: str | None = None) -> None:
        command = [
            self._executable,
            "--prompt",
            prompt,
            "--output-format",
            "json",
            "--print-timeout",
            f"{self._timeout_seconds}s",
            "--disable-slash-commands",
        ]
        if model is not None:
            command.extend(("--model", model))

        run_agent_warmup_process(
            command,
            executable=self._executable,
            timeout_seconds=self._timeout_seconds,
        )
