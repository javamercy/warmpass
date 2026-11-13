from warmpass.agents.base import WarmupAgent, run_agent_warmup_process


class CodexWarmupAgent(WarmupAgent):
    def __init__(
        self,
        *,
        executable: str = "codex",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str) -> None:
        command = [
            self._executable,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            prompt,
        ]
        run_agent_warmup_process(
            command,
            executable=self._executable,
            timeout_seconds=self._timeout_seconds,
        )
