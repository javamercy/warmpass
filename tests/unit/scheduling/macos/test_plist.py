from datetime import time
from pathlib import Path
from uuid import uuid4

import pytest

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.macos.plist import PlistConfiguration, parse_calendar_interval
from warmpass.scheduling.models import (
    DailyTrigger,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)


def test_daily_schedule_creates_calender_interval() -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(at=time(23, 23)),
    )

    configuration = PlistConfiguration.from_schedule(
        schedule=schedule,
        program_arguments=["warmup", "--agent", "codex"],
        executable=Path("/usr/local/bin/warmpass"),
        home=Path("/home/test-user"),
        log_directory=Path("/home/test-user/logs"),
        executable_search_path="/usr/local/bin:/usr/bin",
    )

    assert configuration.StartCalendarInterval == {
        "Hour": 23,
        "Minute": 23,
    }


@pytest.mark.parametrize(
    ("day", "launchd_weekday"),
    [
        (WeekDay.MONDAY, 1),
        (WeekDay.TUESDAY, 2),
        (WeekDay.WEDNESDAY, 3),
        (WeekDay.THURSDAY, 4),
        (WeekDay.FRIDAY, 5),
        (WeekDay.SATURDAY, 6),
        (WeekDay.SUNDAY, 0),
    ],
)
def test_weekly_schedule_maps_weekdays_to_launchd(
    day: WeekDay,
    launchd_weekday: int,
) -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=WeeklyTrigger(at=time(23, 23), days=[day]),
    )

    configuration = PlistConfiguration.from_schedule(
        schedule=schedule,
        program_arguments=["warmup", "--agent", "codex"],
        executable=Path("/usr/local/bin/warmpass"),
        home=Path("/home/test-user"),
        log_directory=Path("/home/test-user/logs"),
        executable_search_path="/usr/local/bin:/usr/bin",
    )

    assert configuration.StartCalendarInterval == [
        {
            "Hour": 23,
            "Minute": 23,
            "Weekday": launchd_weekday,
        }
    ]


@pytest.mark.parametrize("launchd_weekday", [0, 7])
def test_parse_weekly_schedule_accepts_both_sunday_values(
    launchd_weekday: int,
) -> None:
    trigger = parse_calendar_interval(
        [{"Hour": 23, "Minute": 23, "Weekday": launchd_weekday}]
    )

    assert trigger == WeeklyTrigger(
        at=time(23, 23),
        days=[WeekDay.SUNDAY],
    )


def test_parse_weekly_schedule_rejects_different_times() -> None:
    intervals = [
        {"Hour": 23, "Minute": 23, "Weekday": 1},
        {"Hour": 22, "Minute": 22, "Weekday": 2},
    ]

    with pytest.raises(ValueError):
        parse_calendar_interval(intervals)


def test_parse_weekly_schedule_rejects_duplicate_sundays() -> None:
    intervals = [
        {"Hour": 9, "Minute": 30, "Weekday": 0},
        {"Hour": 9, "Minute": 30, "Weekday": 7},
    ]

    with pytest.raises(ValueError):
        parse_calendar_interval(intervals)
