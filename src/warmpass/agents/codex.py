from warmpass.agents.warmup_process import run_agent_warmup_process
from warmpass.warmup.base import WarmupAgent


class CodexWarmupAgent(WarmupAgent):
    def __init__(
        self,
        *,
        executable: str = "codex",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str, model: str | None = None) -> None:
        command = [
            self._executable,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            prompt,
        ]
        if model is not None:
            command.extend(("--model", model))

        run_agent_warmup_process(
            command,
            executable=self._executable,
            timeout_seconds=self._timeout_seconds,
        )
