from subprocess import DEVNULL, TimeoutExpired, run
from tempfile import TemporaryDirectory

from warmpass.agents.base import WarmupAgent
from warmpass.agents.models import WarmupAgentType, WarmupResult, WarmupStatus
from warmpass.agents.prompts import WARMUP_PROMPT


class AntigravityWarmupAgent(WarmupAgent):
    def __init__(self, executable: str = "agy", timeout_seconds: int = 60) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds

    def warmup(self) -> WarmupResult:
        command = [
            self._executable,
            "--prompt",
            WARMUP_PROMPT,
            "--model",
            "gemini-3.8-flash-low",
            "--output-format",
            "json",
            "--print-timeout",
            f"{self._timeout_seconds}s",
            "--disable-slash-commands",
        ]

        status: WarmupStatus
        message: str
        exit_code: int | None = None

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
                exit_code = completed.returncode

        except FileNotFoundError:
            status = WarmupStatus.FAILED
            message = f"Executable '{self._executable}' not found."

        except TimeoutExpired:
            status = WarmupStatus.TIMEOUT
            message = f"Warmup timed out after {self._timeout_seconds} seconds."

        except OSError as error:
            status = WarmupStatus.FAILED
            message = f"Error during warmup: {error}"

        else:
            if exit_code != 0:
                status = WarmupStatus.FAILED
                message = f"Warmup failed with exit code {completed.returncode}."
            else:
                status = WarmupStatus.SUCCESS
                message = "Warmup completed successfully."

        return WarmupResult(
            agent=WarmupAgentType.ANTIGRAVITY,
            status=status,
            message=message,
            exit_code=exit_code,
        )
