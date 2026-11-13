import os
import sys
from pathlib import Path

import pytest

from warmpass.scheduling.base import SchedulerError
from warmpass.scheduling.executable import (
    find_warmpass_executable,
    get_warmpass_executable_search_path,
)

EXECUTABLE_NAME = "warmpass.exe" if sys.platform == "win32" else "warmpass"


def make_executable(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / EXECUTABLE_NAME
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def search_path(*entries: Path | str) -> str:
    return os.pathsep.join(str(entry) for entry in entries)


def test_search_path_keeps_only_absolute_inherited_entries_without_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    monkeypatch.setenv("PATH", search_path(first, "relative/bin", "", second, first))

    assert get_warmpass_executable_search_path() == search_path(first, second)


def test_search_path_appends_additional_entries_after_inherited_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inherited, extra = tmp_path / "inherited", tmp_path / "extra"
    monkeypatch.setenv("PATH", search_path(inherited))

    result = get_warmpass_executable_search_path(
        additional_paths=(str(extra), str(inherited))
    )

    assert result == search_path(inherited, extra)


def test_find_returns_the_executable_from_the_first_directory_that_has_one(
    tmp_path: Path,
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    expected = make_executable(tmp_path / "bin")
    make_executable(tmp_path / "later")

    found = find_warmpass_executable(
        search_path(empty, tmp_path / "bin", tmp_path / "later")
    )

    assert found == expected


def test_find_ignores_relative_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_executable(tmp_path / "bin")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SchedulerError, match="Could not find"):
        find_warmpass_executable("bin")


def test_find_reports_the_executable_name_when_it_is_missing(tmp_path: Path) -> None:
    with pytest.raises(SchedulerError, match=f"'{EXECUTABLE_NAME}' in PATH"):
        find_warmpass_executable(search_path(tmp_path))


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no executable permission bit"
)
def test_find_skips_a_file_that_is_not_executable(tmp_path: Path) -> None:
    make_executable(tmp_path).chmod(0o644)

    with pytest.raises(SchedulerError, match="Could not find"):
        find_warmpass_executable(search_path(tmp_path))
