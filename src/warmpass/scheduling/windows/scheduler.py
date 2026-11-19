"""Windows Task Scheduler implementation of the OSJobScheduler protocol."""

import csv
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET

from pydantic import ValidationError

from warmpass.process import run_subprocess
from warmpass.scheduling.base import OSJobScheduler, SchedulingError
from warmpass.scheduling.models import OSJob, ScheduledTrigger
from warmpass.scheduling.windows.task_xml import (
    TASK_NAME_PREFIX,
    TaskConfiguration,
    build_task_name,
    build_task_xml,
    parse_task_xml,
)


class WindowsTaskScheduler(OSJobScheduler):
    """Manage scheduled Warmpass jobs as Windows Scheduled Tasks via schtasks.exe."""

    def __init__(
        self,
        *,
        warmpass_executable: Path,
        schtasks_executable: Path,
        user_id: str,
        home: Path | None = None,
    ) -> None:
        self._warmpass_executable = warmpass_executable
        self._schtasks_executable = schtasks_executable
        self._user_id = user_id
        self._home = home if home is not None else Path.home()

    def register_job(
        self,
        schedule_id: UUID,
        *,
        arguments: list[str],
        triggers: list[ScheduledTrigger],
    ) -> None:
        """Write a temporary task XML file and register the task via schtasks /create, or raise SchedulingError."""
        configuration = TaskConfiguration.from_job(
            schedule_id,
            warmpass_executable=self._warmpass_executable,
            arguments=arguments,
            triggers=triggers,
            home=self._home,
            user_id=self._user_id,
            activation_date=date.today(),
        )

        xml_data = build_task_xml(configuration)
        xml_path: Path | None = None

        try:
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix="warmpass-task-",
                    suffix=".xml",
                    delete=False,
                ) as temp_file:
                    xml_path = Path(temp_file.name)
                    temp_file.write(xml_data)
            except OSError as exc:
                raise SchedulingError(
                    f"Could not create task XML for schedule {schedule_id}: {exc}."
                ) from exc

            try:
                self._run_schtasks(
                    "/create",
                    "/tn",
                    configuration.name,
                    "/xml",
                    str(xml_path),
                )
            except subprocess.TimeoutExpired as exc:
                raise SchedulingError(
                    f"Registration of schedule {schedule_id} timed out."
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise SchedulingError(
                    f"Could not register schedule {schedule_id} with Task Scheduler: {exc.stderr or exc}"
                ) from exc
            except OSError as exc:
                raise SchedulingError(
                    f"Could not run schtasks for schedule {schedule_id}: {exc}."
                ) from exc
        finally:
            if xml_path is not None:
                xml_path.unlink(missing_ok=True)

    def unregister_job(self, schedule_id: UUID) -> None:
        """Delete the scheduled task for schedule_id via schtasks /delete, or raise SchedulingError."""
        task_name = build_task_name(schedule_id)

        try:
            self._run_schtasks("/delete", "/tn", task_name, "/f")
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Removing Windows task {task_name!r} timed out."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise SchedulingError(
                f"Could not delete Windows task {task_name!r}: {exc.stderr or exc}."
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Could not run schtasks to remove schedule {schedule_id}: {exc}."
            ) from exc

    def get_job(self, schedule_id: UUID) -> OSJob | None:
        """Query and parse the scheduled task XML for schedule_id, returning None if the task does not exist."""
        task_name = build_task_name(schedule_id)

        try:
            output = self._run_schtasks("/query", "/tn", task_name, "/xml")
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Checking Windows task {task_name!r} timed out."
            ) from exc
        except subprocess.CalledProcessError as exc:
            if schedule_id not in self.list_job_ids():
                return None

            raise SchedulingError(
                f"Cannot verify Windows task {task_name!r}: {exc.stderr or exc}."
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Could not run schtasks to check schedule {schedule_id}: {exc}"
            ) from exc

        try:
            return parse_task_xml(schedule_id, output)
        except (ET.ParseError, ValidationError, ValueError) as exc:
            raise SchedulingError(
                f"Invalid task XML for schedule {schedule_id}: {exc}"
            ) from exc

    def list_job_ids(self) -> set[UUID]:
        """Return schedule IDs for all Warmpass tasks returned by schtasks /query, or raise SchedulingError."""
        try:
            output = self._run_schtasks("/query", "/fo", "csv", "/nh")
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError("Listing Windows tasks timed out.") from exc
        except subprocess.CalledProcessError as exc:
            raise SchedulingError(
                f"Cannot list Windows tasks: {exc.stderr or exc}"
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Could not run schtasks to list schedules: {exc}"
            ) from exc

        ids: set[UUID] = set()
        for row in csv.reader(output.splitlines()):
            if not row:
                continue

            task_name = row[0].lstrip("\\")
            if not task_name.startswith(TASK_NAME_PREFIX):
                continue

            name = task_name[len(TASK_NAME_PREFIX) :]
            try:
                schedule_id = UUID(name)
            except ValueError as exc:
                raise SchedulingError(f"Invalid Windows task name: {row[0]!r}") from exc

            if name != str(schedule_id):
                raise SchedulingError(f"Invalid Windows task name: {row[0]!r}")

            ids.add(schedule_id)

        return ids

    def clear_jobs(self) -> None:
        """Delete all Warmpass tasks from Windows Task Scheduler, or raise SchedulingError if any deletion fails."""
        ids = self.list_job_ids()

        failures: list[str] = []
        for schedule_id in sorted(ids):
            task_name = build_task_name(schedule_id)
            try:
                self._run_schtasks("/delete", "/tn", task_name, "/f")
            except subprocess.CalledProcessError as exc:
                failures.append(f"Cannot delete {task_name}: {exc.stderr or exc}")
            except (subprocess.TimeoutExpired, OSError) as exc:
                failures.append(f"Cannot delete {task_name}: {exc}")

        if failures:
            raise SchedulingError(
                "Could not clear all Windows scheduled tasks: " + "; ".join(failures)
            )

    def _run_schtasks(self, *args: str) -> str:
        return run_subprocess(
            [str(self._schtasks_executable), *args], timeout=30, check=True
        ).stdout
