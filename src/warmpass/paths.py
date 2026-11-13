from pathlib import Path
from typing import Final

from platformdirs import user_data_path, user_log_path

_APP_NAME: Final[str] = "Warmpass"


def get_store_directory() -> Path:
    """Return the directory where schedule JSON records are stored."""

    return user_data_path(appname=_APP_NAME, appauthor=False)


def get_log_directory() -> Path:
    """Return the directory where warmup and scheduler logs are stored."""

    return user_log_path(appname=_APP_NAME, appauthor=False)
