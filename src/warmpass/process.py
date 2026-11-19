import subprocess


def run_subprocess(
    command: list[str],
    *,
    timeout: int,
    check: bool,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        timeout=timeout,
        check=check,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
