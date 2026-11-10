import os
import tempfile
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from warmpass.scheduling.models import WarmupSchedule


def _schedule_file_path(directory: Path, schedule_id: UUID) -> Path:
    return directory / f"{schedule_id}.json"


def read_schedule(directory: Path, schedule_id: UUID) -> WarmupSchedule | None:
    schedule_path = _schedule_file_path(directory, schedule_id)

    try:
        data = schedule_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    schedule = WarmupSchedule.model_validate_json(data)
    if schedule.id != schedule_id:
        raise ValueError(
            f"Schedule ID mismatch: expected {schedule_id}, got {schedule.id}"
        )

    return schedule


def write_schedule(directory: Path, schedule: WarmupSchedule) -> None:
    schedule_path = _schedule_file_path(directory, schedule.id)
    data = schedule.model_dump_json(indent=4)

    directory.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=f".{schedule.id}-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(data)

        os.link(temp_path, schedule_path)

    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def remove_schedule(directory: Path, schedule_id: UUID) -> None:
    _schedule_file_path(directory, schedule_id).unlink(missing_ok=True)


def list_schedules(directory: Path) -> list[WarmupSchedule]:
    schedules: list[WarmupSchedule] = []

    try:
        schedule_files = sorted(
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix == ".json"
        )

    except FileNotFoundError:
        return schedules

    for schedule_file in schedule_files:
        try:
            schedule_id = UUID(schedule_file.stem)
        except ValueError as exc:
            raise ValueError(f"Invalid schedule filename: {schedule_file}") from exc

        if schedule_file.name != f"{schedule_id}.json":
            raise ValueError(f"Invalid schedule filename: {schedule_file}")

        try:
            schedule = read_schedule(directory, schedule_id)
        except ValidationError as exc:
            raise ValueError(f"Invalid schedule record: {schedule_file}") from exc

        if schedule is not None:
            schedules.append(schedule)

    return schedules
