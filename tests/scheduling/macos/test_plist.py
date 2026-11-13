"""launchd plist generation and parsing. Pure logic, so it runs on every OS."""

import plistlib
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from warmpass.scheduling.macos.plist import (
    PlistConfiguration,
    build_label,
    build_plist_path,
)
from warmpass.scheduling.models import ScheduledTrigger, WeekDay

SCHEDULE_ID = UUID("e44215ce-26c9-41c4-96d7-67f0940496e4")
EXECUTABLE = Path("/opt/warmpass/bin/warmpass")
HOME = Path("/Users/test")
LOG_DIRECTORY = Path("/Users/test/logs")


def make_configuration(triggers: list[ScheduledTrigger]) -> PlistConfiguration:
    return PlistConfiguration.from_job(
        SCHEDULE_ID,
        warmpass_executable=EXECUTABLE,
        arguments=["warmup", "--agent", "codex"],
        triggers=triggers,
        home=HOME,
        log_directory=LOG_DIRECTORY,
        warmpass_executable_search_path="/opt/warmpass/bin:/usr/bin",
    )


def generated_plist(triggers: list[ScheduledTrigger]) -> dict[str, object]:
    """Parse what would be written to disk, as launchd would read it."""
    data = plistlib.dumps(make_configuration(triggers).to_plist_dict())
    return cast(dict[str, object], plistlib.loads(data))


def test_generated_job_is_one_job_with_all_triggers() -> None:
    plist = generated_plist(
        [
            ScheduledTrigger(hour=9, minute=30),
            ScheduledTrigger(hour=11, minute=30),
        ]
    )

    assert plist == {
        "Label": f"dev.warmpass.schedule.{SCHEDULE_ID}",
        "ProgramArguments": [str(EXECUTABLE), "warmup", "--agent", "codex"],
        "StartCalendarInterval": [
            {"Hour": 9, "Minute": 30},
            {"Hour": 11, "Minute": 30},
        ],
        "RunAtLoad": False,
        "KeepAlive": False,
        "WorkingDirectory": str(HOME),
        "EnvironmentVariables": {
            "HOME": str(HOME),
            "PATH": "/opt/warmpass/bin:/usr/bin",
        },
        "StandardOutPath": str(LOG_DIRECTORY / f"{SCHEDULE_ID}.out.log"),
        "StandardErrorPath": str(LOG_DIRECTORY / f"{SCHEDULE_ID}.err.log"),
    }


@pytest.mark.parametrize(
    ("day", "launchd_weekday"),
    [
        pytest.param(WeekDay.MONDAY, 1, id="monday"),
        pytest.param(WeekDay.TUESDAY, 2, id="tuesday"),
        pytest.param(WeekDay.WEDNESDAY, 3, id="wednesday"),
        pytest.param(WeekDay.THURSDAY, 4, id="thursday"),
        pytest.param(WeekDay.FRIDAY, 5, id="friday"),
        pytest.param(WeekDay.SATURDAY, 6, id="saturday"),
        pytest.param(WeekDay.SUNDAY, 0, id="sunday"),
    ],
)
def test_weekdays_are_translated_to_launchd_numbering(
    day: WeekDay, launchd_weekday: int
) -> None:
    plist = generated_plist([ScheduledTrigger(hour=9, minute=0, weekday=day)])

    assert plist["StartCalendarInterval"] == [
        {"Hour": 9, "Minute": 0, "Weekday": launchd_weekday}
    ]


@pytest.mark.parametrize(
    ("triggers"),
    [
        pytest.param([ScheduledTrigger(hour=0, minute=5)], id="daily"),
        pytest.param(
            [
                ScheduledTrigger(hour=9, minute=0, weekday=WeekDay.SUNDAY),
                ScheduledTrigger(hour=9, minute=0, weekday=WeekDay.MONDAY),
                ScheduledTrigger(hour=23, minute=59, weekday=WeekDay.SATURDAY),
            ],
            id="weekly",
        ),
    ],
)
def test_triggers_survive_a_write_and_read_round_trip(
    triggers: list[ScheduledTrigger],
) -> None:
    configuration = PlistConfiguration.model_validate(
        generated_plist(triggers), strict=True
    )

    assert configuration.to_scheduled_triggers() == triggers


def test_launchd_weekday_seven_means_sunday() -> None:
    configuration = make_configuration([])
    configuration.start_calendar_interval = [{"Hour": 9, "Minute": 0, "Weekday": 7}]

    assert configuration.to_scheduled_triggers() == [
        ScheduledTrigger(hour=9, minute=0, weekday=WeekDay.SUNDAY)
    ]


def test_a_single_calendar_interval_dict_is_read_as_a_list() -> None:
    plist = generated_plist([ScheduledTrigger(hour=9, minute=0)])
    plist["StartCalendarInterval"] = {"Hour": 9, "Minute": 0}

    configuration = PlistConfiguration.model_validate(plist, strict=True)

    assert configuration.start_calendar_interval == [{"Hour": 9, "Minute": 0}]


@pytest.mark.parametrize(
    ("interval", "message"),
    [
        pytest.param({"Hour": 9}, "must include 'Hour' and 'Minute'", id="no-minute"),
        pytest.param({"Minute": 0}, "must include 'Hour' and 'Minute'", id="no-hour"),
        pytest.param(
            {"Hour": 9, "Minute": 0, "Day": 1}, "Unsupported keys", id="extra-key"
        ),
        pytest.param(
            {"Hour": 9, "Minute": 0, "Weekday": 8},
            "Invalid launchd Weekday",
            id="weekday-8",
        ),
        pytest.param(
            {"Hour": 24, "Minute": 0}, "less than or equal to 23", id="hour-24"
        ),
    ],
)
def test_unsupported_calendar_intervals_are_rejected(
    interval: dict[str, int], message: str
) -> None:
    configuration = make_configuration([])
    configuration.start_calendar_interval = [interval]

    with pytest.raises(ValueError, match=message):
        configuration.to_scheduled_triggers()


def test_label_and_filename_carry_the_warmpass_prefix() -> None:
    label = build_label(SCHEDULE_ID)
    path = build_plist_path(Path("/LaunchAgents"), SCHEDULE_ID)

    assert label == "dev.warmpass.schedule.e44215ce-26c9-41c4-96d7-67f0940496e4"
    assert path == Path("/LaunchAgents") / f"{label}.plist"
