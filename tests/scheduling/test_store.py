import os
from datetime import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from warmpass.models import AgentType
from warmpass.scheduling.base import SchedulingError
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    ScheduleTrigger,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)
from warmpass.scheduling.store import WarmupScheduleStore


def make_schedule(trigger: ScheduleTrigger | None = None) -> WarmupSchedule:
    return WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=trigger or DailyTrigger(window=HourlyWindow(every=2)),
    )


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    return tmp_path / "schedules"


@pytest.fixture
def store(directory: Path) -> WarmupScheduleStore:
    return WarmupScheduleStore(directory)


# --- reading -----------------------------------------------------------------


@pytest.mark.parametrize(
    "trigger",
    [
        pytest.param(
            DailyTrigger(
                window=HourlyWindow(from_=time(9), until=time(12, 30), every=2)
            ),
            id="daily",
        ),
        pytest.param(
            WeeklyTrigger(
                days=[WeekDay.MONDAY, WeekDay.FRIDAY],
                window=HourlyWindow(from_=time(9), until=time(12, 30), every=2),
            ),
            id="weekly",
        ),
    ],
)
def test_record_round_trips_with_its_original_window(
    store: WarmupScheduleStore, trigger: ScheduleTrigger
) -> None:
    schedule = make_schedule(trigger)

    store.write(schedule)

    assert store.read(schedule.id) == schedule


@pytest.mark.parametrize("directory_exists", [True, False])
def test_missing_record_reads_as_none(
    directory: Path, store: WarmupScheduleStore, directory_exists: bool
) -> None:
    if directory_exists:
        directory.mkdir()

    assert store.read(uuid4()) is None


def test_unreadable_record_is_an_error_not_a_missing_record(
    directory: Path, store: WarmupScheduleStore
) -> None:
    schedule_id = uuid4()
    (directory / f"{schedule_id}.json").mkdir(parents=True)

    with pytest.raises(SchedulingError, match="Cannot read saved schedule"):
        store.read(schedule_id)


def test_corrupt_record_is_reported_and_left_untouched(
    directory: Path, store: WarmupScheduleStore
) -> None:
    schedule_id = uuid4()
    record = directory / f"{schedule_id}.json"
    directory.mkdir()
    record.write_text("{", encoding="utf-8")

    with pytest.raises(SchedulingError, match="invalid JSON record"):
        store.read(schedule_id)

    assert record.read_text(encoding="utf-8") == "{"


def test_record_with_a_different_id_than_its_filename_is_rejected(
    directory: Path, store: WarmupScheduleStore
) -> None:
    schedule = make_schedule()
    other_id = uuid4()
    directory.mkdir()
    (directory / f"{other_id}.json").write_text(
        schedule.model_dump_json(), encoding="utf-8"
    )

    with pytest.raises(SchedulingError, match="ID mismatch"):
        store.read(other_id)


# --- writing -----------------------------------------------------------------


def test_write_without_overwrite_refuses_an_existing_record(
    directory: Path, store: WarmupScheduleStore
) -> None:
    schedule = make_schedule()
    store.write(schedule)

    with pytest.raises(SchedulingError, match="already exists"):
        store.write(schedule, overwrite=False)

    assert store.read(schedule.id) == schedule


def test_write_without_overwrite_does_not_replace_a_corrupt_record(
    directory: Path, store: WarmupScheduleStore
) -> None:
    schedule = make_schedule()
    directory.mkdir()
    record = directory / f"{schedule.id}.json"
    record.write_text("{", encoding="utf-8")

    with pytest.raises(SchedulingError, match="already exists"):
        store.write(schedule, overwrite=False)

    assert record.read_text(encoding="utf-8") == "{"


def test_write_replaces_an_existing_record_by_default(
    store: WarmupScheduleStore,
) -> None:
    schedule = make_schedule()
    store.write(schedule)
    replacement = schedule.model_copy(
        update={"trigger": DailyTrigger(window=HourlyWindow(every=5))}
    )

    store.write(replacement)

    assert store.read(schedule.id) == replacement


def test_failed_replace_keeps_the_old_record_and_leaves_no_temp_file(
    directory: Path, store: WarmupScheduleStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = make_schedule()
    store.write(schedule)
    record = directory / f"{schedule.id}.json"
    original = record.read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    replacement = schedule.model_copy(
        update={"trigger": DailyTrigger(window=HourlyWindow(every=5))}
    )

    with pytest.raises(SchedulingError, match="Could not save schedule"):
        store.write(replacement)

    assert record.read_bytes() == original
    assert [path.name for path in directory.iterdir()] == [record.name]


def test_write_reports_a_store_directory_that_cannot_be_created(
    tmp_path: Path,
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")

    with pytest.raises(SchedulingError, match="Could not create schedule store"):
        WarmupScheduleStore(blocker / "schedules").write(make_schedule())


# --- listing, removing, clearing ---------------------------------------------


def test_list_ids_returns_record_ids_and_ignores_other_files(
    directory: Path, store: WarmupScheduleStore
) -> None:
    schedule = make_schedule()
    store.write(schedule)
    (directory / f".{uuid4()}-abc.tmp").write_text("", encoding="utf-8")
    (directory / "notes.txt").write_text("", encoding="utf-8")

    assert store.list_ids() == {schedule.id}


def test_list_ids_is_empty_when_the_directory_does_not_exist(
    store: WarmupScheduleStore,
) -> None:
    assert store.list_ids() == set()


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("not-a-uuid.json", id="not-a-uuid"),
        pytest.param(f"{UUID(int=1).hex}.json", id="non-canonical-uuid"),
    ],
)
def test_list_ids_rejects_malformed_record_filenames(
    directory: Path, store: WarmupScheduleStore, filename: str
) -> None:
    directory.mkdir()
    (directory / filename).write_text("{}", encoding="utf-8")

    with pytest.raises(SchedulingError, match="Invalid schedule filename"):
        store.list_ids()


def test_remove_deletes_only_the_given_record(
    store: WarmupScheduleStore,
) -> None:
    removed, kept = make_schedule(), make_schedule()
    store.write(removed)
    store.write(kept)

    store.remove(removed.id)

    assert store.list_ids() == {kept.id}


def test_remove_of_a_missing_record_is_not_an_error(
    store: WarmupScheduleStore,
) -> None:
    store.remove(uuid4())


def test_clear_removes_records_but_not_other_files(
    directory: Path, store: WarmupScheduleStore
) -> None:
    store.write(make_schedule())
    store.write(make_schedule())
    temp_file = directory / f".{uuid4()}-abc.tmp"
    other_file = directory / "notes.txt"
    temp_file.write_text("", encoding="utf-8")
    other_file.write_text("", encoding="utf-8")

    store.clear()

    assert store.list_ids() == set()
    assert temp_file.exists()
    assert other_file.exists()


def test_clear_with_no_directory_is_not_an_error(store: WarmupScheduleStore) -> None:
    store.clear()
