import subprocess
import tempfile
from datetime import date
from pathlib import Path
from uuid import UUID

from warmpass.scheduling.base import WarmupScheduler, WarmupSchedulerError
from warmpass.scheduling.models import WarmupSchedule
from warmpass.scheduling.store import WarmupScheduleStore
from warmpass.scheduling.windows.task_xml import (
    TaskConfiguration,
    build_task_name,
    build_task_xml,
)


class WindowsTaskSchedulerWarmupScheduler(WarmupScheduler):
    def __init__(
        self,
        *,
        executable: Path,
        schtasks_executable: Path,
        home: Path,
        user_id: str,
        store_directory: Path,
    ):
        self._executable = executable
        self._schtasks_executable = schtasks_executable
        self._home = home
        self._user_id = user_id
        self._store = WarmupScheduleStore(store_directory)

    def add(self, schedule: WarmupSchedule) -> None:
        configuration = TaskConfiguration.from_schedule(
            schedule,
            executable=self._executable,
            home=self._home,
            user_id=self._user_id,
            activation_date=date.today(),
        )

        xml_data = build_task_xml(configuration)

        try:
            self._store.write(schedule)

        except FileExistsError as exc:
            raise WarmupSchedulerError(
                f"Schedule {schedule.id} already exists in the store."
            ) from exc

        except OSError as exc:
            raise WarmupSchedulerError(
                f"Could not save schedule {schedule.id}. "
                "No task registration was attempted; inspect the store "
                "before retrying."
            ) from exc

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
                raise WarmupSchedulerError(
                    f"Could not create task XML for schedule {schedule.id}. "
                    "The schedule record was retained; no task registration "
                    "was attempted."
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
                raise WarmupSchedulerError(
                    f"Registration of schedule {schedule.id} timed out. "
                    f"Task {configuration.name!r} may have been registered. "
                    "The schedule record was retained; inspect the task "
                    "before retrying."
                ) from exc

            except subprocess.CalledProcessError as exc:
                details = (exc.stderr or exc.stdout or "").strip()
                raise WarmupSchedulerError(
                    f"Could not register schedule {schedule.id} as task "
                    f"{configuration.name!r}: {details or exc}. "
                    "The schedule record was retained; inspect the task "
                    "before retrying."
                ) from exc

            except OSError as exc:
                raise WarmupSchedulerError(
                    f"Could not run schtasks for schedule {schedule.id}: {exc}. "
                    "The schedule record was retained."
                ) from exc

        finally:
            if xml_path is not None:
                xml_path.unlink(missing_ok=True)

    def remove(self, schedule_id: UUID) -> None:
        self._store.remove(schedule_id)

        task_name = build_task_name(schedule_id)

        try:
            self._run_schtasks("/delete", "/tn", task_name, "/f")

        except subprocess.TimeoutExpired as exc:
            raise WarmupSchedulerError(
                f"Removing Windows task {task_name!r} timed out. "
                "The task may have been deleted. "
                "The schedule record was deleted; inspect the task "
                "before retrying."
            ) from exc

        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise WarmupSchedulerError(
                f"Could not delete Windows task {task_name!r}: "
                f"{details or exc}. "
                "The schedule record was deleted; inspect the task "
                "before retrying."
            ) from exc

        except OSError as exc:
            raise WarmupSchedulerError(
                f"Could not run schtasks to remove schedule {schedule_id}: {exc}. "
                "The schedule record was deleted."
            ) from exc

    def clear(self) -> None:
        try:
            schedules = self._store.get_list()
        except (OSError, ValueError) as exc:
            raise WarmupSchedulerError(
                f"Cannot list saved schedules; no tasks were removed: {exc}"
            ) from exc

        failures: list[str] = []

        for schedule in schedules:
            try:
                self.remove(schedule.id)
            except WarmupSchedulerError as exc:
                failures.append(f"{schedule.id}: {exc}")

        if failures:
            raise WarmupSchedulerError(
                "Could not remove all schedules. "
                "Some tasks and records may already have been removed: "
                + "; ".join(failures)
            )

    def get(self, schedule_id: UUID) -> WarmupSchedule | None:
        try:
            schedule = self._store.read(schedule_id)

        except (ValueError, OSError) as exc:
            raise WarmupSchedulerError(
                f"Cannot read saved schedule {schedule_id}: {exc}"
            ) from exc

        if schedule is None:
            return None

        task_name = build_task_name(schedule_id)

        try:
            self._run_schtasks(
                "/query",
                "/tn",
                task_name,
            )

        except subprocess.TimeoutExpired as exc:
            raise WarmupSchedulerError(
                f"Checking Windows task {task_name!r} timed out. Its status is unknown."
            ) from exc

        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise WarmupSchedulerError(
                f"Cannot verify Windows task {task_name!r}: "
                f"{details or exc}. "
                "The schedule record exists, but the task may be missing "
                "or inaccessible."
            ) from exc

        except OSError as exc:
            raise WarmupSchedulerError(
                f"Could not run schtasks to check schedule {schedule_id}: {exc}"
            ) from exc

        return schedule

    def get_list(self) -> list[WarmupSchedule]:
        try:
            saved_schedules = self._store.get_list()

        except (ValueError, OSError) as exc:
            raise WarmupSchedulerError(f"Cannot list saved schedules: {exc}") from exc

        schedules: list[WarmupSchedule] = []

        for saved_schedule in saved_schedules:
            schedule = self.get(saved_schedule.id)

            if schedule is not None:
                schedules.append(schedule)

        return schedules

    def _run_schtasks(self, *args: str) -> None:
        subprocess.run(
            [str(self._schtasks_executable), *args],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=30,
        )
