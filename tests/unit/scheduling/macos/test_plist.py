from datetime import time
from pathlib import Path
from uuid import uuid4

import pytest

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.macos.plist import PlistConfiguration, build_label
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    WarmupSchedule,
    WarmupScheduleTrigger,
    WeekDay,
    WeeklyTrigger,
)


def make_configuration(trigger: WarmupScheduleTrigger) -> PlistConfiguration:
    schedule = WarmupSchedule(id=uuid4(), agent=WarmupAgentType.CODEX, trigger=trigger)
    return PlistConfiguration.from_schedule(
        schedule=schedule,
        program_arguments=["warmup", "--agent", "codex"],
        executable=Path("/usr/local/bin/warmpass"),
        home=Path("/home/test-user"),
        log_directory=Path("/home/test-user/logs"),
        executable_search_path="/usr/local/bin:/usr/bin",
    )


@pytest.mark.parametrize("every", [1, 2, 3, 4, 5])
def test_all_day_schedule_restarts_at_midnight(every: int) -> None:
    configuration = make_configuration(DailyTrigger(window=HourlyWindow(every=every)))

    assert configuration.StartCalendarInterval == [
        {"Hour": hour, "Minute": 0} for hour in range(0, 24, every)
    ]


@pytest.mark.parametrize(
    ("start", "until", "expected"),
    [
        (time(9, 30), time(13, 30), [(9, 30), (11, 30)]),
        (time(21, 30), None, [(21, 30), (23, 30)]),
        (None, time(3), [(0, 0), (2, 0)]),
        (time(22), time(3), [(22, 0), (0, 0), (2, 0)]),
        (time(23, 45), time(0, 30), [(23, 45)]),
    ],
)
def test_daily_window_bounds(
    start: time | None, until: time | None, expected: list[tuple[int, int]]
) -> None:
    configuration = make_configuration(
        DailyTrigger(window=HourlyWindow(from_=start, until=until, every=2))
    )

    assert configuration.StartCalendarInterval == [
        {"Hour": hour, "Minute": minute} for hour, minute in expected
    ]


@pytest.mark.parametrize(
    ("day", "launchd_weekday"),
    [(day, (day.value + 1) % 7) for day in WeekDay],
)
def test_weekly_schedule_maps_weekdays_to_launchd(
    day: WeekDay, launchd_weekday: int
) -> None:
    configuration = make_configuration(
        WeeklyTrigger(
            window=HourlyWindow(from_=time(9, 30), until=time(12), every=2),
            days=[day],
        )
    )

    assert configuration.StartCalendarInterval == [
        {"Hour": 9, "Minute": 30, "Weekday": launchd_weekday},
        {"Hour": 11, "Minute": 30, "Weekday": launchd_weekday},
    ]


def test_plist_contains_expected_command_environment_and_logs() -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(window=HourlyWindow(every=5)),
    )
    config = PlistConfiguration.from_schedule(
        schedule,
        program_arguments=["warmup", "--agent", "codex"],
        executable=Path("/bin/warmpass"),
        home=Path("/home/test"),
        log_directory=Path("/home/test/logs"),
        executable_search_path="/bin:/usr/bin",
    )
    assert config.Label == build_label(schedule.id)
    assert config.ProgramArguments == ["/bin/warmpass", "warmup", "--agent", "codex"]
    assert config.EnvironmentVariables == {
        "HOME": "/home/test",
        "PATH": "/bin:/usr/bin",
    }
    assert config.StandardOutPath == f"/home/test/logs/{schedule.id}.out.log"
    assert config.StandardErrorPath == f"/home/test/logs/{schedule.id}.err.log"
    assert not config.RunAtLoad and not config.KeepAlive
