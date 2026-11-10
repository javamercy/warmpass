import os
import tempfile
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from warmpass.scheduling.models import WarmupSchedule


class WarmupScheduleStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def read(self, schedule_id: UUID) -> WarmupSchedule | None:
        schedule_path = self._schedule_file_path(schedule_id)

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

    def write(self, schedule: WarmupSchedule) -> None:
        schedule_path = self._schedule_file_path(schedule.id)
        data = schedule.model_dump_json(indent=4)

        self._ensure_directory_exists()

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
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

    def remove(self, schedule_id: UUID) -> None:
        schedule_path = self._schedule_file_path(schedule_id)
        schedule_path.unlink(missing_ok=True)

    def get_list(self) -> list[WarmupSchedule]:
        schedules: list[WarmupSchedule] = []

        try:
            schedule_files = sorted(
                path
                for path in self._directory.iterdir()
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
                schedule = self.read(schedule_id)
            except ValidationError as exc:
                raise ValueError(f"Invalid schedule record: {schedule_file}") from exc

            if schedule is not None:
                schedules.append(schedule)

        return schedules

    def _schedule_file_path(self, schedule_id: UUID) -> Path:
        return self._directory / f"{schedule_id}.json"

    def _ensure_directory_exists(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
