import sys
from datetime import time
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.macos.store import (
    list_schedules,
    read_schedule,
    remove_schedule,
    write_schedule,
)
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="Tests macOS schedule record storage"
)


@pytest.mark.parametrize("weekly", [False, True])
def test_record_round_trips_original_window(tmp_path: Path, weekly: bool) -> None:
    window = HourlyWindow(from_=time(9), until=time(12, 30), every=2)
    trigger = (
        WeeklyTrigger(window=window, days=[WeekDay.MONDAY, WeekDay.FRIDAY])
        if weekly
        else DailyTrigger(window=window)
    )
    schedule = WarmupSchedule(id=uuid4(), agent=WarmupAgentType.CODEX, trigger=trigger)
    directory = tmp_path / "nested" / "schedules"

    write_schedule(directory, schedule)

    assert read_schedule(directory, schedule.id) == schedule
    assert list_schedules(directory) == [schedule]
    kind = "weekly" if weekly else "daily"
    contents = (directory / f"{schedule.id}.json").read_text(encoding="utf-8")
    assert f'"kind": "{kind}"' in contents


def test_write_does_not_overwrite_existing_record(tmp_path: Path) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(every=2)),
    )
    write_schedule(tmp_path, schedule)
    with pytest.raises(FileExistsError):
        write_schedule(tmp_path, schedule)
    assert read_schedule(tmp_path, schedule.id) == schedule
    assert sorted(path.name for path in tmp_path.iterdir()) == [f"{schedule.id}.json"]


def test_missing_and_removed_records(tmp_path: Path) -> None:
    schedule_id = uuid4()
    assert read_schedule(tmp_path / "missing", schedule_id) is None
    assert list_schedules(tmp_path / "missing") == []
    remove_schedule(tmp_path, schedule_id)
    assert read_schedule(tmp_path, schedule_id) is None


def test_corrupt_record_is_reported(tmp_path: Path) -> None:
    schedule_id = uuid4()
    (tmp_path / f"{schedule_id}.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError):
        read_schedule(tmp_path, schedule_id)
    with pytest.raises(ValueError, match="Invalid schedule record"):
        list_schedules(tmp_path)


def test_record_id_must_match_filename(tmp_path: Path) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(every=2)),
    )
    filename_id = uuid4()
    (tmp_path / f"{filename_id}.json").write_text(
        schedule.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="ID mismatch"):
        read_schedule(tmp_path, filename_id)


def test_list_reports_malformed_filename(tmp_path: Path) -> None:
    (tmp_path / "not-a-uuid.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid schedule filename"):
        list_schedules(tmp_path)
