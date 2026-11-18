"""Resolution of the Warmpass executable and PATH for scheduled OS jobs."""

import os
import shutil
import sys
from pathlib import Path

from warmpass.scheduling.base import SchedulingError


def get_warmpass_executable_search_path(additional_paths: tuple[str, ...] = ()) -> str:
    """Build a deduplicated PATH string of absolute directories from the current PATH followed by additional_paths."""
    inherited_paths = [
        entry
        for entry in os.getenv("PATH", "").split(os.pathsep)
        if entry and Path(entry).is_absolute()
    ]

    paths = dict.fromkeys([*inherited_paths, *additional_paths])

    return os.pathsep.join(paths.keys())


def find_warmpass_executable(search_path: str) -> Path:
    """Resolve the absolute path to the warmpass binary within search_path, or raise SchedulingError if not found."""
    executable_name = "warmpass.exe" if sys.platform == "win32" else "warmpass"

    for directory in search_path.split(os.pathsep):
        if not directory or not Path(directory).is_absolute():
            continue

        candidate = Path(directory) / executable_name

        if sys.platform == "win32":
            if candidate.is_file():
                return candidate
        else:
            executable = shutil.which(str(candidate))
            if executable is not None:
                return Path(executable)

    raise SchedulingError(
        f"Could not find '{executable_name}' in PATH. "
        "Install Warmpass or add its executable directory to PATH."
    )
