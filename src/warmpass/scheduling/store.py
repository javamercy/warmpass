"""Filesystem store for persisted warmup schedule JSON records."""

import os
import tempfile
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from warmpass.scheduling.base import SchedulingError
from warmpass.scheduling.models import WarmupSchedule


class WarmupScheduleStore:
    """Read and write per-schedule JSON record files in a local directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def read(self, schedule_id: UUID) -> WarmupSchedule | None:
        """Read and validate the schedule record for schedule_id, return None if missing, or raise SchedulingError if unreadable or corrupt."""
        schedule_path = self._schedule_file_path(schedule_id)

        try:
            data = schedule_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SchedulingError(
                f"Cannot read saved schedule {schedule_id}: {exc}"
            ) from exc

        try:
            schedule = WarmupSchedule.model_validate_json(data)
        except ValidationError as exc:
            raise SchedulingError(
                f"Cannot read saved schedule {schedule_id}: invalid JSON record at {schedule_path}."
            ) from exc

        if schedule.id != schedule_id:
            raise SchedulingError(
                f"Cannot read saved schedule {schedule_id}: "
                f"record ID mismatch (expected {schedule_id}, got {schedule.id})."
            )

        return schedule

    def list_ids(self) -> set[UUID]:
        """Return the schedule IDs for all JSON records in the store directory, or raise SchedulingError on malformed filenames."""
        try:
            entries = list(self._directory.iterdir())
        except FileNotFoundError:
            return set()
        except OSError as exc:
            raise SchedulingError(
                f"Cannot list schedule files in {self._directory}: {exc}"
            ) from exc

        ids: set[UUID] = set()
        for entry in entries:
            if entry.name.startswith(".") or entry.suffix != ".json":
                continue

            try:
                schedule_id = UUID(entry.stem)
            except ValueError as exc:
                raise SchedulingError(f"Invalid schedule filename: {entry}") from exc
            if entry.name != f"{schedule_id}.json":
                raise SchedulingError(f"Invalid schedule filename: {entry}")

            ids.add(schedule_id)

        return ids

    def write(
        self,
        schedule: WarmupSchedule,
        *,
        overwrite: bool = True,
    ) -> None:
        """Atomically write a schedule JSON record via a temporary file, raising SchedulingError if overwrite is False and the file exists."""
        schedule_path = self._schedule_file_path(schedule.id)
        if not overwrite and schedule_path.exists():
            raise SchedulingError(
                f"Schedule {schedule.id} already exists in the store."
            )

        data = schedule.model_dump_json(indent=4)

        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SchedulingError(
                f"Could not create schedule store directory {self._directory}: {exc}"
            ) from exc

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

            os.replace(temp_path, schedule_path)
        except OSError as exc:
            raise SchedulingError(
                f"Could not save schedule {schedule.id}: {exc}"
            ) from exc

        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def remove(self, schedule_id: UUID) -> None:
        """Delete the schedule JSON record for schedule_id if present, or raise SchedulingError on OS failure."""
        schedule_path = self._schedule_file_path(schedule_id)
        try:
            schedule_path.unlink(missing_ok=True)
        except OSError as exc:
            raise SchedulingError(
                f"Could not remove schedule record {schedule_id}: {exc}"
            ) from exc

    def clear(self) -> None:
        """Delete all schedule JSON records in the store directory, or raise SchedulingError if any record cannot be removed."""
        try:
            entries = list(self._directory.iterdir())
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SchedulingError(
                f"Cannot list schedule files in {self._directory}: {exc}"
            ) from exc

        failures: list[str] = []
        for entry in sorted(entries):
            if entry.name.startswith(".") or entry.suffix != ".json":
                continue

            try:
                entry.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f"Cannot remove {entry}: {exc}")

        if failures:
            raise SchedulingError(
                "Some schedule record files could not be removed: "
                + "; ".join(failures)
            )

    def _schedule_file_path(self, schedule_id: UUID) -> Path:
        return self._directory / f"{schedule_id}.json"
