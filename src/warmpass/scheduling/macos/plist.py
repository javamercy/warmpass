from __future__ import annotations

from pathlib import Path
from typing import Final, assert_never
from uuid import UUID

from pydantic import BaseModel

from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    WarmupSchedule,
    WarmupScheduleTrigger,
    WeekDay,
    WeeklyTrigger,
)

LABEL_PREFIX: Final[str] = "dev.warmpass.schedule."
PLIST_SUFFIX: Final[str] = ".plist"


class PlistConfiguration(BaseModel):
    Label: str
    ProgramArguments: list[str]
    StartCalendarInterval: dict[str, int] | list[dict[str, int]]
    RunAtLoad: bool
    KeepAlive: bool
    WorkingDirectory: str
    EnvironmentVariables: dict[str, str]
    StandardOutPath: str
    StandardErrorPath: str

    @classmethod
    def from_schedule(
        cls,
        schedule: WarmupSchedule,
        *,
        program_arguments: list[str],
        executable: Path,
        home: Path,
        log_directory: Path,
        executable_search_path: str,
    ) -> PlistConfiguration:
        return cls(
            Label=build_label(schedule.id),
            ProgramArguments=[str(executable), *program_arguments],
            StartCalendarInterval=_build_calendar_interval(schedule.trigger),
            RunAtLoad=False,
            KeepAlive=False,
            WorkingDirectory=str(home),
            EnvironmentVariables={
                "HOME": str(home),
                "PATH": executable_search_path,
            },
            StandardOutPath=str(log_directory / f"{schedule.id}.out.log"),
            StandardErrorPath=str(log_directory / f"{schedule.id}.err.log"),
        )


def _build_calendar_interval(
    trigger: WarmupScheduleTrigger,
) -> list[dict[str, int]]:
    match trigger:
        case DailyTrigger(window=window):
            return _build_hourly_intervals(window)

        case WeeklyTrigger(window=window, days=days):
            return _build_hourly_intervals(window, days)

        case _:
            assert_never(trigger)


def _build_hourly_intervals(
    window: HourlyWindow,
    days: list[WeekDay] | None = None,
) -> list[dict[str, int]]:
    minutes_per_day = 24 * 60
    start = (
        window.from_.hour * 60 + window.from_.minute if window.from_ is not None else 0
    )
    end = (
        window.until.hour * 60 + window.until.minute
        if window.until is not None
        else minutes_per_day
    )

    if end < start:
        end += minutes_per_day

    intervals: list[dict[str, int]] = []

    for minute in range(start, end, window.every * 60):
        minute_of_day = minute % minutes_per_day
        hour, minute_of_hour = divmod(minute_of_day, 60)

        if days is None:
            intervals.append(
                {
                    "Hour": hour,
                    "Minute": minute_of_hour,
                }
            )
        else:
            for day in days:
                intervals.append(
                    {
                        "Hour": hour,
                        "Minute": minute_of_hour,
                        "Weekday": (int(day) + 1) % 7,
                    }
                )

    return intervals


def build_label(schedule_id: UUID) -> str:
    return f"{LABEL_PREFIX}{schedule_id}"


def build_plist_path(launch_agents_directory: Path, schedule_id: UUID) -> Path:
    return launch_agents_directory / f"{LABEL_PREFIX}{schedule_id}{PLIST_SUFFIX}"
