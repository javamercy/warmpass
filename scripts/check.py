import subprocess
import sys
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def run(*command: str) -> None:
    subprocess.run(command, cwd=_PROJECT_ROOT, check=True)


def main() -> None:
    """Run lint, platform-specific type checking, and formatting."""
    run("ruff", "check")

    if sys.platform in {"darwin", "linux"}:
        run(
            "pyrefly",
            "check",
            "--project-excludes",
            "src/warmpass/scheduling/windows/factory.py",
        )

    elif sys.platform == "win32":
        run(
            "pyrefly",
            "check",
            "--project-excludes",
            "src/warmpass/scheduling/macos/scheduler.py",
            "--project-excludes",
            "tests/scheduling/macos/test_scheduler.py",
        )

    run("ruff", "format")


if __name__ == "__main__":
    main()
