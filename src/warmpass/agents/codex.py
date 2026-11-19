"""Warmup adapter for the Codex CLI."""

from warmpass.agents.warmup_process import run_agent_warmup_process
from warmpass.warmup.base import WarmupAgent


class CodexWarmupAgent(WarmupAgent):
    """Run ephemeral, read-only warmups through the Codex CLI outside any Git repository check."""

    def __init__(
        self,
        *,
        executable: str = "codex",
        timeout_seconds: int = 60,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self, prompt: str, model: str | None = None) -> None:
        """Invoke the Codex CLI with the given prompt and optional model, or raise WarmupError."""
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
            timeout=self._timeout_seconds,
        )
