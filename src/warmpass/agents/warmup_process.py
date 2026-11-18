from subprocess import DEVNULL, CompletedProcess, TimeoutExpired, run
from tempfile import TemporaryDirectory

from warmpass.warmup.base import WarmupError


def run_agent_warmup_process(
    command: list[str],
    *,
    executable: str,
    timeout_seconds: int,
) -> CompletedProcess[str]:
    try:
        with TemporaryDirectory(prefix="warmpass-warmup-") as working_dir:
            completed = run(
                command,
                cwd=working_dir,
                stdin=DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_seconds,
                errors="replace",
                check=False,
            )
    except FileNotFoundError as exc:
        raise WarmupError(f"Executable '{executable}' not found.") from exc
    except TimeoutExpired as exc:
        raise WarmupError(
            f"Warmup timed out after {timeout_seconds} seconds; "
            "the usage window may have started anyway."
        ) from exc
    except OSError as exc:
        raise WarmupError(f"Error during warmup: {exc}") from exc

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {details[:200]}" if details else "."
        raise WarmupError(
            f"Warmup failed with exit code {completed.returncode}{suffix}"
        )

    if not completed.stdout or not completed.stdout.strip():
        raise WarmupError("Warmup failed: agent returned an empty response.")

    return completed
