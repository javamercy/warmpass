import csv
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET

from pydantic import ValidationError

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
                    f"Could not create task XML for schedule {schedule_id}: {exc}. "
                    "The schedule record was retained; no task registration was attempted."
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
                    f"Registration of schedule {schedule_id} timed out. "
                    f"Task {configuration.name!r} may have been registered. "
                    "The schedule record was retained; inspect the task before retrying."
                ) from exc
            except subprocess.CalledProcessError as exc:
                details = (exc.stderr or exc.stdout or "").strip()
                raise SchedulingError(
                    f"Could not register schedule {schedule_id} as task "
                    f"{configuration.name!r}: {details or exc}. "
                    "The schedule record was retained; inspect the task before retrying."
                ) from exc
            except OSError as exc:
                raise SchedulingError(
                    f"Could not run schtasks for schedule {schedule_id}: {exc}. "
                    "The schedule record was retained."
                ) from exc
        finally:
            if xml_path is not None:
                xml_path.unlink(missing_ok=True)

    def unregister_job(self, schedule_id: UUID) -> None:
        task_name = build_task_name(schedule_id)

        try:
            self._run_schtasks("/delete", "/tn", task_name, "/f")
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Removing Windows task {task_name!r} timed out; "
                "its status is unknown. The schedule record was retained."
            ) from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise SchedulingError(
                f"Could not delete Windows task {task_name!r}: {details or exc}. "
                "The schedule record was retained."
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Could not run schtasks to remove schedule {schedule_id}: {exc}. "
                "The schedule record was retained."
            ) from exc

    def get_job(self, schedule_id: UUID) -> OSJob | None:
        task_name = build_task_name(schedule_id)

        try:
            xml_output = self._run_schtasks("/query", "/tn", task_name, "/xml")
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Checking Windows task {task_name!r} timed out; its status is unknown."
            ) from exc
        except subprocess.CalledProcessError as exc:
            if schedule_id not in self.list_job_ids():
                return None

            details = (exc.stderr or exc.stdout or "").strip()
            raise SchedulingError(
                f"Cannot verify Windows task {task_name!r}: {details or exc}."
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Could not run schtasks to check schedule {schedule_id}: {exc}"
            ) from exc

        try:
            return parse_task_xml(schedule_id, xml_output)
        except (ET.ParseError, ValidationError, ValueError) as exc:
            raise SchedulingError(
                f"Invalid task XML for schedule {schedule_id}: {exc}"
            ) from exc

    def list_job_ids(self) -> set[UUID]:
        try:
            output = self._run_schtasks("/query", "/fo", "csv", "/nh")
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                "Listing Windows tasks timed out; task status is unknown."
            ) from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise SchedulingError(
                f"Cannot list Windows tasks: {details or exc}"
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
        ids = self.list_job_ids()

        failures: list[str] = []
        for schedule_id in sorted(ids):
            task_name = build_task_name(schedule_id)
            try:
                self._run_schtasks("/delete", "/tn", task_name, "/f")
            except subprocess.CalledProcessError as exc:
                details = (exc.stderr or exc.stdout or "").strip()
                failures.append(f"Cannot delete {task_name}: {details or exc}")
            except (subprocess.TimeoutExpired, OSError) as exc:
                failures.append(
                    f"Cannot delete {task_name}; outcome may be unknown: {exc}"
                )

        if failures:
            raise SchedulingError(
                "Could not clear all Windows scheduled tasks; no schedule files were removed. "
                "Some tasks may already have been deleted: " + "; ".join(failures)
            )

    def _run_schtasks(self, *args: str) -> str:
        result = subprocess.run(
            [str(self._schtasks_executable), *args],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=30,
        )
        return result.stdout
