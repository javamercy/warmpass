"""macOS launchd implementation of the OSJobScheduler protocol."""

import os
import plistlib
import subprocess
import tempfile
from pathlib import Path
from pyexpat import ExpatError
from uuid import UUID

from pydantic import ValidationError

from warmpass.scheduling.base import OSJobScheduler, SchedulingError
from warmpass.scheduling.macos.plist import (
    LABEL_PREFIX,
    PLIST_SUFFIX,
    PlistConfiguration,
    build_label,
    build_plist_path,
)
from warmpass.scheduling.models import OSJob, ScheduledTrigger


class MacOSLaunchdScheduler(OSJobScheduler):
    """Manage scheduled Warmpass jobs as user LaunchAgents in ~/Library/LaunchAgents via launchctl."""

    def __init__(
        self,
        *,
        warmpass_executable: Path,
        launchctl_executable: Path,
        warmpass_executable_search_path: str,
        log_directory: Path,
        home: Path | None = None,
    ) -> None:
        self._warmpass_executable = warmpass_executable
        self._launchctl_executable = launchctl_executable
        self._warmpass_executable_search_path = warmpass_executable_search_path
        self._log_directory = log_directory
        self._home = home if home is not None else Path.home()
        self._launch_agents_directory = self._home / "Library" / "LaunchAgents"

    def register_job(
        self,
        schedule_id: UUID,
        *,
        arguments: list[str],
        triggers: list[ScheduledTrigger],
    ) -> None:
        """Write a LaunchAgent plist and bootstrap it into the user's GUI launchd domain, or raise SchedulingError."""
        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)
        if plist_path.exists():
            raise SchedulingError(f"Schedule {schedule_id} already exists in launchd.")

        configuration = PlistConfiguration.from_job(
            schedule_id,
            warmpass_executable=self._warmpass_executable,
            triggers=triggers,
            arguments=arguments,
            home=self._home,
            log_directory=self._log_directory,
            warmpass_executable_search_path=self._warmpass_executable_search_path,
        )

        data = plistlib.dumps(configuration.to_plist_dict(), fmt=plistlib.FMT_XML)

        try:
            self._log_directory.mkdir(parents=True, exist_ok=True)
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_plist(plist_path, data)
        except OSError as exc:
            raise SchedulingError(
                f"Could not create plist for schedule {schedule_id}: {exc}. "
                "The schedule record was saved; inspect it before retrying."
            ) from exc

        try:
            self._run_launchctl("bootstrap", f"gui/{os.getuid()}", str(plist_path))
        except (subprocess.CalledProcessError, OSError) as exc:
            raise SchedulingError(
                f"Could not register schedule {schedule_id} with launchd. "
                "The record and plist were retained; inspect the job before retrying."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Registration of schedule {schedule_id} timed out. "
                "The job may have loaded. The record and plist were retained."
            ) from exc

    def unregister_job(self, schedule_id: UUID) -> None:
        """Boot out the LaunchAgent from the user's GUI launchd domain and remove its plist file, or raise SchedulingError."""
        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)
        target = f"gui/{os.getuid()}/{build_label(schedule_id)}"

        try:
            self._run_launchctl("bootout", target)
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Removing schedule {schedule_id} timed out; its loaded status is "
                "unknown. The record and plist were retained."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise SchedulingError(
                f"Could not unload schedule {schedule_id}: {exc.stderr or exc}. "
                "The record and plist were retained."
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Could not run launchctl for schedule {schedule_id}: {exc}. "
                "The record and plist were retained."
            ) from exc

        try:
            plist_path.unlink(missing_ok=True)
        except OSError as exc:
            raise SchedulingError(
                f"Schedule {schedule_id} was unloaded, but its plist could not be "
                f"removed: {exc}. The record was retained."
            ) from exc

    def get_job(self, schedule_id: UUID) -> OSJob | None:
        """Read the schedule's plist and verify that the job is loaded in launchd, returning None if the plist is absent."""
        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)

        try:
            data = plist_path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SchedulingError(
                f"Cannot read plist for schedule {schedule_id}: {exc}"
            ) from exc

        try:
            raw = plistlib.loads(data)
            configuration = PlistConfiguration.model_validate(raw, strict=True)
            triggers = configuration.to_scheduled_triggers()
        except (
            plistlib.InvalidFileException,
            ExpatError,
            ValidationError,
            ValueError,
            TypeError,
            OverflowError,
        ) as exc:
            raise SchedulingError(
                f"Invalid plist for schedule {schedule_id}: {exc}"
            ) from exc

        if configuration.label != build_label(schedule_id):
            raise SchedulingError(
                f"Plist label for schedule {schedule_id} does not match its filename: "
                f"{configuration.label!r}"
            )

        if (
            not configuration.program_arguments
            or not configuration.program_arguments[0]
        ):
            raise SchedulingError(
                f"Plist for schedule {schedule_id} has no executable."
            )

        target = f"gui/{os.getuid()}/{build_label(schedule_id)}"
        try:
            self._run_launchctl("print", target)
        except subprocess.TimeoutExpired as exc:
            raise SchedulingError(
                f"Checking launchd for schedule {schedule_id} timed out; "
                "its loaded status is unknown."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise SchedulingError(
                f"Cannot verify that schedule {schedule_id} is loaded in launchd: "
                f"{exc.stderr or exc}"
            ) from exc
        except OSError as exc:
            raise SchedulingError(
                f"Cannot run launchctl to check schedule {schedule_id}: {exc}"
            ) from exc

        return OSJob(
            schedule_id=schedule_id,
            triggers=triggers,
            command=configuration.program_arguments,
        )

    def list_job_ids(self) -> set[UUID]:
        """Return schedule IDs for all Warmpass LaunchAgent plist files, or raise SchedulingError on invalid filenames."""
        try:
            entries = list(self._launch_agents_directory.iterdir())
        except FileNotFoundError:
            return set()
        except OSError as exc:
            raise SchedulingError(
                f"Cannot list plist files in {self._launch_agents_directory}: {exc}"
            ) from exc

        ids: set[UUID] = set()
        for entry in sorted(entries):
            if not entry.name.startswith(LABEL_PREFIX) or not entry.name.endswith(
                PLIST_SUFFIX
            ):
                continue

            name = entry.name[len(LABEL_PREFIX) : -len(PLIST_SUFFIX)]
            try:
                schedule_id = UUID(name)
            except ValueError as exc:
                raise SchedulingError(
                    f"Invalid schedule plist filename: {entry}"
                ) from exc

            if name != str(schedule_id):
                raise SchedulingError(f"Invalid schedule plist filename: {entry}")

            ids.add(schedule_id)

        return ids

    def clear_jobs(self) -> None:
        """Boot out all loaded Warmpass LaunchAgents and delete all Warmpass plist files, or raise SchedulingError."""
        plist_paths: list[Path] = []
        labels: set[str] = set()

        try:
            entries: list[Path] = list(self._launch_agents_directory.iterdir())
        except FileNotFoundError:
            entries: list[Path] = []
        except OSError as exc:
            raise SchedulingError(
                f"Cannot list schedule files in {self._launch_agents_directory}: {exc}"
            ) from exc

        for entry in entries:
            if not entry.name.startswith(LABEL_PREFIX) or not entry.name.endswith(
                PLIST_SUFFIX
            ):
                continue

            plist_paths.append(entry)

        domain = f"gui/{os.getuid()}"
        try:
            self._run_launchctl("print", domain)
            output = self._run_launchctl("list")
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            OSError,
        ) as exc:
            raise SchedulingError(
                f"Cannot discover loaded schedules; no files were removed: {exc}"
            ) from exc

        lines = output.splitlines()
        if not lines or lines[0].split() != ["PID", "Status", "Label"]:
            raise SchedulingError(
                "Unexpected launchctl list output; no schedule files were removed."
            )

        for line in lines[1:]:
            parts = line.split(maxsplit=2)
            if len(parts) != 3:
                raise SchedulingError(
                    "Unexpected launchctl list output; no schedule files were removed."
                )

            label = parts[2]
            if label.startswith(LABEL_PREFIX) and label != LABEL_PREFIX:
                labels.add(label)

        failures: list[str] = []
        for label in sorted(labels):
            target = f"{domain}/{label}"
            try:
                self._run_launchctl("bootout", target)
            except subprocess.CalledProcessError as exc:
                failures.append(f"Cannot unload {label}: {exc.stderr or exc}")
            except (subprocess.TimeoutExpired, OSError) as exc:
                failures.append(f"Cannot unload {label}; outcome may be unknown: {exc}")

        if failures:
            raise SchedulingError(
                "Could not clear all launchd jobs; no schedule files were removed. "
                "Some jobs may already have been unloaded: " + "; ".join(failures)
            )

        for plist_path in plist_paths:
            try:
                plist_path.unlink(missing_ok=True)
            except OSError as exc:
                failures.append(f"Cannot remove {plist_path}: {exc}")

        if failures:
            raise SchedulingError(
                "Some plist files could not be removed; other jobs and files "
                "may already have been cleared: " + "; ".join(failures)
            )

    def _write_plist(self, path: Path, data: bytes) -> None:
        """Atomically write plist bytes via a sibling temporary file so launchd never sees a partial file."""
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

            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _run_launchctl(self, *args: str) -> str:
        result = subprocess.run(
            [self._launchctl_executable, *args],
            check=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            text=True,
            timeout=30,
        )
        return result.stdout
