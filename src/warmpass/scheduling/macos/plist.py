from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Final, assert_never

from pydantic import BaseModel

from warmpass.scheduling.models import (
    DailyTrigger,
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
) -> dict[str, int] | list[dict[str, int]]:
    match trigger:
        case DailyTrigger(at=at):
            return {
                "Hour": at.hour,
                "Minute": at.minute,
            }

        case WeeklyTrigger(at=at, days=days):
            return [
                {
                    "Hour": at.hour,
                    "Minute": at.minute,
                    "Weekday": (int(day) + 1) % 7,
                }
                for day in days
            ]

        case _:
            assert_never(trigger)


def parse_calendar_interval(
    value: dict[str, int] | list[dict[str, int]],
) -> WarmupScheduleTrigger:
    if isinstance(value, dict):
        return DailyTrigger(at=time(hour=value["Hour"], minute=value["Minute"]))

    days: set[WeekDay] = set()
    at: time | None = None

    for interval in value:
        current_time = time(hour=interval["Hour"], minute=interval["Minute"])
        weekday = interval["Weekday"]
        if not (0 <= weekday <= 7):
            raise ValueError("Invalid weekday")

        if at is None:
            at = current_time
        elif at != current_time:
            raise ValueError("Weekly intervals must share the same time")

        days.add(WeekDay((weekday + 6) % 7))

    if len(days) != len(value):
        raise ValueError("Duplicate weekdays")

    if at is None:
        raise ValueError("Missing weekly time")

    return WeeklyTrigger(at=at, days=days)


def build_label(schedule_id: str) -> str:
    return f"{LABEL_PREFIX}{schedule_id}"


def build_plist_path(launch_agents_directory: Path, schedule_id: str) -> Path:
    return launch_agents_directory / f"{LABEL_PREFIX}{schedule_id}{PLIST_SUFFIX}"
