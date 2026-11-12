import subprocess
import sys
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

_DARWIN_EXCLUDE_PATHS: Final[tuple[str, ...]] = (
    "src/warmpass/scheduling/windows/factory.py",
)
_LINUX_EXCLUDE_PATHS: Final[tuple[str, ...]] = (
    "src/warmpass/scheduling/windows/factory.py",
)


def run(*command: str) -> None:
    subprocess.run(command, cwd=_PROJECT_ROOT, check=True)


def main() -> None:
    run("ruff", "check")

    if sys.platform == "darwin":
        run("pyrefly", "check", "--project-excludes", *_DARWIN_EXCLUDE_PATHS)

    elif sys.platform == "linux":
        run("pyrefly", "check", "--project-excludes", *_LINUX_EXCLUDE_PATHS)

    elif sys.platform == "win32":
        run("pyrefly", "check")

    run("ruff", "format")


if __name__ == "__main__":
    main()
