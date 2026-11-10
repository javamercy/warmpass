from datetime import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from warmpass.agents.models import AgentType
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)
from warmpass.scheduling.store import WarmupScheduleStore


@pytest.mark.parametrize("weekly", [False, True])
def test_record_round_trips_original_window(tmp_path: Path, weekly: bool) -> None:
    window = HourlyWindow(from_=time(9), until=time(12, 30), every=2)
    trigger = (
        WeeklyTrigger(window=window, days=[WeekDay.MONDAY, WeekDay.FRIDAY])
        if weekly
        else DailyTrigger(window=window)
    )
    schedule = WarmupSchedule(id=uuid4(), agent=AgentType.CODEX, trigger=trigger)
    directory = tmp_path / "nested" / "schedules"
    store = WarmupScheduleStore(directory)

    store.write(schedule)

    assert store.read(schedule.id) == schedule
    assert store.get_list() == [schedule]
    kind = "weekly" if weekly else "daily"
    contents = (directory / f"{schedule.id}.json").read_text(encoding="utf-8")
    assert f'"kind": "{kind}"' in contents


def test_write_does_not_overwrite_existing_record(tmp_path: Path) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(every=2)),
    )
    store = WarmupScheduleStore(tmp_path)
    store.write(schedule)
    with pytest.raises(FileExistsError):
        store.write(schedule)
    assert store.read(schedule.id) == schedule
    assert sorted(path.name for path in tmp_path.iterdir()) == [f"{schedule.id}.json"]


def test_missing_and_removed_records(tmp_path: Path) -> None:
    schedule_id = uuid4()
    missing_store = WarmupScheduleStore(tmp_path / "missing")
    assert missing_store.read(schedule_id) is None
    assert missing_store.get_list() == []
    store = WarmupScheduleStore(tmp_path)
    store.remove(schedule_id)
    assert store.read(schedule_id) is None


def test_remove_existing_record(tmp_path: Path) -> None:
    store = WarmupScheduleStore(tmp_path)
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(every=2)),
    )
    store.write(schedule)

    store.remove(schedule.id)

    assert store.read(schedule.id) is None
    assert store.get_list() == []
    assert not (tmp_path / f"{schedule.id}.json").exists()


def test_corrupt_record_is_reported(tmp_path: Path) -> None:
    schedule_id = uuid4()
    (tmp_path / f"{schedule_id}.json").write_text("{", encoding="utf-8")
    store = WarmupScheduleStore(tmp_path)
    with pytest.raises(ValidationError):
        store.read(schedule_id)
    with pytest.raises(ValueError, match="Invalid schedule record"):
        store.get_list()


def test_record_id_must_match_filename(tmp_path: Path) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(every=2)),
    )
    filename_id = uuid4()
    (tmp_path / f"{filename_id}.json").write_text(
        schedule.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="ID mismatch"):
        WarmupScheduleStore(tmp_path).read(filename_id)


def test_list_reports_malformed_filename(tmp_path: Path) -> None:
    (tmp_path / "not-a-uuid.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid schedule filename"):
        WarmupScheduleStore(tmp_path).get_list()


def test_list_reports_noncanonical_filename(tmp_path: Path) -> None:
    (tmp_path / f"{uuid4().hex}.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid schedule filename"):
        WarmupScheduleStore(tmp_path).get_list()


def test_list_skips_record_removed_during_listing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_id = uuid4()
    (tmp_path / f"{schedule_id}.json").write_text("{}", encoding="utf-8")
    store = WarmupScheduleStore(tmp_path)

    def missing_record(_schedule_id: UUID) -> None:
        return None

    monkeypatch.setattr(store, "read", missing_record)

    assert store.get_list() == []
