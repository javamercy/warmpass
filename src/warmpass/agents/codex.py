from subprocess import DEVNULL, TimeoutExpired, run
from tempfile import TemporaryDirectory

from warmpass.agents.base import WarmupAgent, WarmupError
from warmpass.agents.prompts import WARMUP_PROMPT


class CodexWarmupAgent(WarmupAgent):
    def __init__(self, executable: str = "codex", timeout_seconds: int = 60) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self) -> None:
        command = [
            self._executable,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            WARMUP_PROMPT,
        ]

        try:
            with TemporaryDirectory(prefix="warmpass-warmup-") as working_dir:
                completed = run(
                    command,
                    cwd=working_dir,
                    stdin=DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self._timeout_seconds,
                    errors="replace",
                    check=False,
                )

        except FileNotFoundError as exc:
            raise WarmupError(f"Executable '{self._executable}' not found.") from exc

        except TimeoutExpired as exc:
            raise WarmupError(
                f"Warmup timed out after {self._timeout_seconds} seconds."
            ) from exc

        except OSError as exc:
            raise WarmupError(f"Error during warmup: {exc}") from exc

        if completed.returncode != 0:
            raise WarmupError(f"Warmup failed with exit code {completed.returncode}.")
