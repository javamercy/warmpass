"""Smoke-test built Warmpass wheel and sdist artifacts in isolated venvs."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

_DIST_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "dist"

_IMPORT_CHECK: Final[str] = """
import sys
from pathlib import Path

import warmpass
from warmpass.models import AgentType
from warmpass.wiring import create_warmup_service

assert Path(warmpass.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
for agent in AgentType:
    create_warmup_service(agent)

if sys.platform == "darwin":
    import warmpass.scheduling.macos.factory  # noqa: F401
elif sys.platform == "win32":
    import warmpass.scheduling.windows.factory  # noqa: F401
"""


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    expected_code: int = 0,
    stdout_contains: str | None = None,
    stderr_contains: str | None = None,
    timeout: int = 180,
) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    ok = (
        result.returncode == expected_code
        and (stdout_contains is None or stdout_contains in result.stdout)
        and (stderr_contains is None or stderr_contains in result.stderr)
    )
    if not ok:
        raise RuntimeError(
            f"Check failed for {command!r} (expected exit {expected_code}, got {result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _isolated_env(home_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for var in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(var, None)
    env["HOME"] = str(home_dir)
    env["USERPROFILE"] = str(home_dir)
    env["XDG_DATA_HOME"] = str(home_dir / ".local" / "share")
    env["LOCALAPPDATA"] = str(home_dir / "AppData" / "Local")
    env["APPDATA"] = str(home_dir / "AppData" / "Roaming")
    env["NO_COLOR"] = "1"
    return env


def smoke_test(artifact: Path) -> None:
    """Install a built artifact into a clean venv and verify imports and CLI entry points."""
    print(f"Smoke testing {artifact.name} ...")
    with TemporaryDirectory(prefix="warmpass-smoke-") as temp_name:
        root = Path(temp_name)
        venv_dir = root / "venv"
        work_dir = root / "work"
        home_dir = root / "home"
        empty_path_dir = root / "empty-path"
        work_dir.mkdir()
        home_dir.mkdir()
        empty_path_dir.mkdir()

        scripts_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
        venv_python = scripts_dir / (
            "python.exe" if sys.platform == "win32" else "python"
        )
        warmpass_exe = scripts_dir / (
            "warmpass.exe" if sys.platform == "win32" else "warmpass"
        )

        host_env = os.environ.copy()
        _run(
            ["uv", "venv", "--python", sys.executable, str(venv_dir)],
            cwd=work_dir,
            env=host_env,
        )
        _run(
            ["uv", "pip", "install", "--python", str(venv_python), str(artifact)],
            cwd=work_dir,
            env=host_env,
        )

        env = _isolated_env(home_dir)
        _run(
            [str(venv_python), "-c", _IMPORT_CHECK, str(venv_dir)],
            cwd=work_dir,
            env=env,
        )
        _run(
            [str(warmpass_exe), "--help"],
            cwd=work_dir,
            env=env,
            stdout_contains="Usage:",
        )

        # Empty PATH directory prevents resolving any real agent or POSIX os.defpath.
        no_agent_env = {**env, "PATH": str(empty_path_dir)}
        _run(
            [str(warmpass_exe), "warmup", "--agent", "codex"],
            cwd=work_dir,
            env=no_agent_env,
            expected_code=1,
            stderr_contains="Executable 'codex' not found.",
        )

    print(f"Passed: {artifact.name}")


def main() -> None:
    """Smoke-test the wheel and sdist in dist/."""
    wheels = sorted(_DIST_DIR.glob("*.whl"))
    sdists = sorted(_DIST_DIR.glob("*.tar.gz"))
    if not wheels or not sdists:
        raise RuntimeError(
            f"Expected .whl and .tar.gz in {_DIST_DIR}. Run `uv build` first."
        )

    for artifact in (*wheels, *sdists):
        smoke_test(artifact.resolve())


if __name__ == "__main__":
    main()
