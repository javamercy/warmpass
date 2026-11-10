import os
import plistlib
import subprocess
import tempfile
from pathlib import Path
from pyexpat import ExpatError
from uuid import UUID

from warmpass.scheduling.base import WarmupScheduler, WarmupSchedulerError
from warmpass.scheduling.macos.plist import (
    LABEL_PREFIX,
    PLIST_SUFFIX,
    PlistConfiguration,
    build_label,
    build_plist_path,
)
from warmpass.scheduling.models import WarmupSchedule
from warmpass.scheduling.store import WarmupScheduleStore


class MacOSLaunchdWarmupScheduler(WarmupScheduler):
    def __init__(
        self,
        *,
        executable: Path,
        executable_search_path: str,
    ) -> None:
        executable = executable.expanduser()
        if not executable.is_absolute():
            raise ValueError(f"Executable path must be absolute: {executable}")
        if not executable.is_file():
            raise ValueError(f"Executable is not a file: {executable}")
        if not os.access(executable, os.X_OK):
            raise ValueError(f"File is not executable: {executable}")

        self._executable = executable
        self._executable_search_path = executable_search_path
        self._home = Path.home()
        self._launch_agents_directory = self._home / "Library" / "LaunchAgents"
        self._log_directory = self._home / "Library" / "Logs" / "Warmup"

        self._store_directory = (
            self._home / "Library" / "Application Support" / "Warmup"
        )
        self._store = WarmupScheduleStore(self._store_directory)

    def add(self, schedule: WarmupSchedule) -> None:
        plist_path = build_plist_path(self._launch_agents_directory, schedule.id)
        if plist_path.exists():
            raise WarmupSchedulerError(
                f"Schedule with ID {schedule.id} already exists in launchd."
            )

        configuration = PlistConfiguration.from_schedule(
            schedule,
            program_arguments=["warmup", "--agent", schedule.agent.value],
            executable=self._executable,
            home=self._home,
            log_directory=self._log_directory,
            executable_search_path=self._executable_search_path,
        )

        data = plistlib.dumps(configuration.model_dump(), fmt=plistlib.FMT_XML)

        self._log_directory.mkdir(parents=True, exist_ok=True)
        plist_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._store.write(schedule)
        except FileExistsError as exc:
            raise WarmupSchedulerError(
                f"Schedule with ID {schedule.id} already exists in the store."
            ) from exc

        try:
            self._write_new_plist(plist_path, data)
        except OSError as exc:
            raise WarmupSchedulerError(
                f"Could not create plist for schedule {schedule.id}. "
                f"The schedule record was saved; inspect it before retrying."
            ) from exc

        try:
            self._bootstrap(plist_path)
        except subprocess.TimeoutExpired as exc:
            raise WarmupSchedulerError(
                f"Registration of schedule {schedule.id} timed out. "
                f"The job may have loaded. The record and plist were retained."
            ) from exc

        except (subprocess.CalledProcessError, OSError) as exc:
            raise WarmupSchedulerError(
                f"Could not register schedule {schedule.id} with launchd. "
                f"The record and plist were retained; inspect the job before retrying."
            ) from exc

    def _write_new_plist(self, path: Path, data: bytes) -> None:
        temp_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.stem}-",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(data)

            os.link(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _run_launchctl(self, *args: str) -> str:
        result = subprocess.run(
            ["/bin/launchctl", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.stdout

    def _bootstrap(self, plist_path: Path) -> None:
        self._run_launchctl("bootstrap", f"gui/{os.getuid()}", str(plist_path))

    def remove(self, schedule_id: UUID) -> None:
        if self.get(schedule_id) is None:
            raise WarmupSchedulerError(f"Schedule {schedule_id} does not exist.")

        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)
        target = f"gui/{os.getuid()}/{build_label(schedule_id)}"

        try:
            self._run_launchctl("bootout", target)
        except subprocess.TimeoutExpired as exc:
            raise WarmupSchedulerError(
                f"Removing schedule {schedule_id} timed out; its loaded status is "
                "unknown. The record and plist were retained."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise WarmupSchedulerError(
                f"Could not unload schedule {schedule_id}: {exc.stderr or exc}. "
                "The record and plist were retained."
            ) from exc
        except OSError as exc:
            raise WarmupSchedulerError(
                f"Could not run launchctl for schedule {schedule_id}: {exc}. "
                "The record and plist were retained."
            ) from exc

        try:
            plist_path.unlink()
        except OSError as exc:
            raise WarmupSchedulerError(
                f"Schedule {schedule_id} was unloaded, but its plist could not be "
                f"removed: {exc}. The record was retained."
            ) from exc

        try:
            self._store.remove(schedule_id)
        except OSError as exc:
            raise WarmupSchedulerError(
                f"Schedule {schedule_id} was unloaded and its plist removed, but "
                f"its record could not be removed: {exc}."
            ) from exc

    def clear(self) -> None:
        paths: list[Path] = []
        labels: set[str] = set()

        for directory, prefix, suffix in (
            (self._store_directory, "", ".json"),
            (self._launch_agents_directory, LABEL_PREFIX, PLIST_SUFFIX),
        ):
            try:
                entries = list(directory.iterdir())
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise WarmupSchedulerError(
                    f"Cannot list schedule files in {directory}: {exc}"
                ) from exc

            for entry in entries:
                if not entry.name.startswith(prefix) or not entry.name.endswith(suffix):
                    continue
                paths.append(entry)
                name = entry.name[len(prefix) : -len(suffix)]
                if name:
                    labels.add(f"{LABEL_PREFIX}{name}")

        domain = f"gui/{os.getuid()}"
        try:
            self._run_launchctl("print", domain)
            output = self._run_launchctl("list")
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            OSError,
        ) as exc:
            raise WarmupSchedulerError(
                f"Cannot discover loaded schedules; no files were removed: {exc}"
            ) from exc

        lines = output.splitlines()
        if not lines or lines[0].split() != ["PID", "Status", "Label"]:
            raise WarmupSchedulerError(
                "Unexpected launchctl list output; no schedule files were removed."
            )
        for line in lines[1:]:
            parts = line.split(maxsplit=2)
            if len(parts) != 3:
                raise WarmupSchedulerError(
                    "Unexpected launchctl list output; no schedule files were removed."
                )
            label = parts[2]
            if label.startswith(LABEL_PREFIX) and label != LABEL_PREFIX:
                labels.add(label)

        failures: list[str] = []
        for label in sorted(labels):
            target = f"{domain}/{label}"
            try:
                self._run_launchctl("print", target)
            except subprocess.CalledProcessError as exc:
                if exc.returncode in (3, 113):
                    continue
                failures.append(f"Cannot check {label}: {exc.stderr or exc}")
                continue
            except (subprocess.TimeoutExpired, OSError) as exc:
                failures.append(
                    f"Cannot check {label}; loaded status is unknown: {exc}"
                )
                continue

            try:
                self._run_launchctl("bootout", target)
            except subprocess.CalledProcessError as exc:
                failures.append(f"Cannot unload {label}: {exc.stderr or exc}")
            except (subprocess.TimeoutExpired, OSError) as exc:
                failures.append(f"Cannot unload {label}; outcome may be unknown: {exc}")

        if failures:
            raise WarmupSchedulerError(
                "Could not clear all launchd jobs; no schedule files were removed. "
                "Some jobs may already have been unloaded: " + "; ".join(failures)
            )

        for path in sorted(paths):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f"Cannot remove {path}: {exc}")

        if failures:
            raise WarmupSchedulerError(
                "Some schedule files could not be removed; other jobs and files "
                "may already have been cleared: " + "; ".join(failures)
            )

    def get(self, schedule_id: UUID) -> WarmupSchedule | None:
        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)

        try:
            schedule = self._store.read(schedule_id)
        except (ValueError, OSError) as exc:
            raise WarmupSchedulerError(
                f"Cannot read saved schedule {schedule_id}: {exc}"
            ) from exc

        try:
            data = plist_path.read_bytes()
        except FileNotFoundError as exc:
            if schedule is None:
                return None
            raise WarmupSchedulerError(
                f"Schedule {schedule_id} has a saved record but its plist is missing: "
                f"{plist_path}"
            ) from exc
        except OSError as exc:
            raise WarmupSchedulerError(
                f"Cannot read plist for schedule {schedule_id}: {exc}"
            ) from exc

        if schedule is None:
            raise WarmupSchedulerError(
                f"Schedule {schedule_id} has a plist but no saved schedule record."
            )

        try:
            raw = plistlib.loads(data)
            configuration = PlistConfiguration.model_validate(raw, strict=True)
        except (
            plistlib.InvalidFileException,
            ExpatError,
            ValueError,
            TypeError,
            OverflowError,
        ) as exc:
            raise WarmupSchedulerError(
                f"Invalid plist for schedule {schedule_id}: {exc}"
            ) from exc

        if configuration.Label != build_label(schedule_id):
            raise WarmupSchedulerError(
                f"Plist label for schedule {schedule_id} does not match its filename: "
                f"{configuration.Label!r}"
            )
        if not configuration.ProgramArguments or not configuration.ProgramArguments[0]:
            raise WarmupSchedulerError(
                f"Plist for schedule {schedule_id} has no executable."
            )

        target = f"gui/{os.getuid()}/{build_label(schedule_id)}"
        try:
            self._run_launchctl("print", target)
        except subprocess.TimeoutExpired as exc:
            raise WarmupSchedulerError(
                f"Checking launchd for schedule {schedule_id} timed out; "
                "its loaded status is unknown."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise WarmupSchedulerError(
                f"Cannot verify that schedule {schedule_id} is loaded in launchd: "
                f"{exc.stderr or exc}"
            ) from exc
        except OSError as exc:
            raise WarmupSchedulerError(
                f"Cannot run launchctl to check schedule {schedule_id}: {exc}"
            ) from exc

        return schedule

    def get_list(self) -> list[WarmupSchedule]:
        ids: set[UUID] = set()
        for directory, prefix, suffix in (
            (self._store_directory, "", ".json"),
            (self._launch_agents_directory, LABEL_PREFIX, PLIST_SUFFIX),
        ):
            try:
                entries = list(directory.iterdir())
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise WarmupSchedulerError(
                    f"Cannot list schedule files in {directory}: {exc}"
                ) from exc

            for entry in entries:
                if not entry.name.startswith(prefix) or not entry.name.endswith(suffix):
                    continue
                name = entry.name[len(prefix) : -len(suffix)]
                try:
                    schedule_id = UUID(name)
                except ValueError as exc:
                    raise WarmupSchedulerError(
                        f"Invalid schedule filename: {entry}"
                    ) from exc
                if name != str(schedule_id):
                    raise WarmupSchedulerError(f"Invalid schedule filename: {entry}")
                ids.add(schedule_id)

        schedules: list[WarmupSchedule] = []
        for schedule_id in sorted(ids):
            schedule = self.get(schedule_id)
            if schedule is None:
                raise WarmupSchedulerError(
                    f"Schedule {schedule_id} disappeared while listing schedules."
                )
            schedules.append(schedule)

        return schedules
