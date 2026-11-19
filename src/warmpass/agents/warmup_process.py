"""Shared subprocess runner for unattended coding agent warmup invocations."""

from subprocess import CalledProcessError, TimeoutExpired
from tempfile import TemporaryDirectory

from warmpass.process import run_subprocess
from warmpass.warmup.base import WarmupError


def run_agent_warmup_process(
    command: list[str],
    *,
    timeout: int,
) -> None:
    """Run an agent CLI in a temporary directory and require a nonempty reply."""
    try:
        with TemporaryDirectory(prefix="warmpass-warmup-") as working_dir:
            run_subprocess(command, cwd=working_dir, check=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise WarmupError(f"Executable '{command[0]}' not found.") from exc
    except TimeoutExpired as exc:
        raise WarmupError(f"Warmup timed out after {timeout} seconds.") from exc
    except CalledProcessError as exc:
        raise WarmupError(f"Warmup failed with exit code {exc.returncode}.") from exc
    except OSError as exc:
        raise WarmupError(f"Could not run warmup: {exc}") from exc
