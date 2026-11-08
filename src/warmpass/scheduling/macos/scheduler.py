import os
import plistlib
import subprocess
import tempfile
from pathlib import Path
from pyexpat import ExpatError
from uuid import UUID

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.base import (
    WarmupScheduleAlreadyExistsError,
    WarmupScheduler,
    WarmupScheduleRegistrationError,
    WarmupScheduleRemovalError,
)
from warmpass.scheduling.macos.plist import (
    LABEL_PREFIX,
    PLIST_SUFFIX,
    PlistConfiguration,
    build_label,
    build_plist_path,
    parse_calendar_interval,
)
from warmpass.scheduling.models import (
    WarmupSchedule,
)

_SERVICE_NOT_FOUND_CODES: frozenset[int] = frozenset({3, 113})


class MacOSLaunchdWarmupScheduler(WarmupScheduler):
    def __init__(self, executable: Path, executable_search_path: str) -> None:
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

    def add(self, schedule: WarmupSchedule) -> None:
        plist_path = build_plist_path(self._launch_agents_directory, schedule.id)
        if plist_path.exists():
            raise WarmupScheduleAlreadyExistsError(schedule.id)

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
            self._write_new_plist(plist_path, data)
        except FileExistsError as exc:
            raise WarmupScheduleAlreadyExistsError(schedule.id) from exc

        try:
            self._bootstrap(plist_path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            plist_path.unlink(missing_ok=True)
            raise WarmupScheduleRegistrationError(
                f"Failed to register schedule {schedule.id}: {exc.stderr or exc}"
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

    def _run_launchctl(self, *args: str) -> None:
        subprocess.run(
            ["/bin/launchctl", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def _bootstrap(self, plist_path: Path) -> None:
        self._run_launchctl("bootstrap", f"gui/{os.getuid()}", str(plist_path))

    def remove(self, schedule_id: UUID) -> None:
        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)

        label = build_label(schedule_id)
        target = f"gui/{os.getuid()}/{label}"

        try:
            self._run_launchctl("bootout", target)
        except subprocess.CalledProcessError as exc:
            if exc.returncode not in _SERVICE_NOT_FOUND_CODES:
                raise WarmupScheduleRemovalError(
                    f"Failed to remove schedule `{schedule_id}`: {exc.stderr or exc}"
                ) from exc

        try:
            plist_path.unlink(missing_ok=True)
        except OSError as exc:
            raise WarmupScheduleRemovalError(
                f"Failed to remove schedule `{schedule_id}`: {exc}"
            ) from exc

    def get(self, schedule_id: UUID) -> WarmupSchedule | None:
        plist_path = build_plist_path(self._launch_agents_directory, schedule_id)

        try:
            data = plist_path.read_bytes()
        except FileNotFoundError:
            return None

        try:
            configuration = plistlib.loads(data, fmt=plistlib.PlistFormat.FMT_XML)
        except (plistlib.InvalidFileException, ExpatError, ValueError) as exc:
            raise WarmupScheduleRegistrationError(
                f"Invalid schedule plist `{schedule_id}`"
            ) from exc

        configuration = PlistConfiguration.model_validate(configuration)

        return WarmupSchedule(
            id=schedule_id,
            # TODO: Update parsing and validate the argument structure rather than relying only on an index.
            agent=WarmupAgentType(configuration.ProgramArguments[3]),
            trigger=parse_calendar_interval(configuration.StartCalendarInterval),
        )

    def get_list(self) -> list[WarmupSchedule]:
        try:
            filenames = sorted(
                entry.name
                for entry in self._launch_agents_directory.iterdir()
                if entry.name.startswith(LABEL_PREFIX)
                and entry.name.endswith(PLIST_SUFFIX)
            )
        except FileNotFoundError:
            return []

        schedules: list[WarmupSchedule] = []
        for filename in filenames:
            schedule_id = UUID(filename[len(LABEL_PREFIX) : -len(PLIST_SUFFIX)])
            schedule = self.get(schedule_id)

            if schedule is not None:
                schedules.append(schedule)

        return schedules
