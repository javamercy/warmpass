"""Task Scheduler XML generation and parsing. Pure logic, so it runs on every OS."""

from datetime import date
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET

import pytest

from warmpass.scheduling.models import ScheduledTrigger, WeekDay
from warmpass.scheduling.windows.task_xml import (
    TaskConfiguration,
    build_task_name,
    build_task_xml,
    parse_task_xml,
)

SCHEDULE_ID = UUID("e44215ce-26c9-41c4-96d7-67f0940496e4")
EXECUTABLE = Path("/opt/warmpass/warmpass")
HOME = Path("/Users/test")
ARGUMENTS = ["warmup", "--agent", "codex"]
ACTIVATION_DATE = date(2026, 1, 5)
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}

MON, FRI = WeekDay.MONDAY, WeekDay.FRIDAY


def build_xml(
    triggers: list[ScheduledTrigger], *, arguments: list[str] | None = None
) -> bytes:
    configuration = TaskConfiguration.from_job(
        SCHEDULE_ID,
        warmpass_executable=EXECUTABLE,
        arguments=ARGUMENTS if arguments is None else arguments,
        triggers=triggers,
        home=HOME,
        user_id="DOMAIN\\user",
        activation_date=ACTIVATION_DATE,
    )
    return build_task_xml(configuration)


def text(root: ET.Element, path: str) -> str | None:
    element = root.find(path, NS)
    return None if element is None else element.text


def test_generated_task_is_one_task_running_the_command_in_the_users_context() -> None:
    root = ET.fromstring(build_xml([ScheduledTrigger(hour=9, minute=30)]))

    assert text(root, "t:Actions/t:Exec/t:Command") == str(EXECUTABLE)
    assert text(root, "t:Actions/t:Exec/t:Arguments") == "warmup --agent codex"
    assert text(root, "t:Actions/t:Exec/t:WorkingDirectory") == str(HOME)
    assert text(root, "t:Principals/t:Principal/t:UserId") == "DOMAIN\\user"
    assert text(root, "t:Principals/t:Principal/t:LogonType") == "InteractiveToken"


def test_task_does_not_run_missed_starts_late() -> None:
    root = ET.fromstring(build_xml([ScheduledTrigger(hour=9, minute=30)]))

    assert text(root, "t:Settings/t:StartWhenAvailable") == "false"


def test_daily_triggers_become_one_daily_calendar_trigger_each() -> None:
    root = ET.fromstring(
        build_xml(
            [ScheduledTrigger(hour=9, minute=30), ScheduledTrigger(hour=11, minute=30)]
        )
    )

    triggers = root.findall("t:Triggers/t:CalendarTrigger", NS)
    assert [text(t, "t:StartBoundary") for t in triggers] == [
        "2026-01-05T09:30:00",
        "2026-01-05T11:30:00",
    ]
    assert all(text(t, "t:ScheduleByDay/t:DaysInterval") == "1" for t in triggers)


def test_weekly_triggers_with_the_same_time_share_one_calendar_trigger() -> None:
    root = ET.fromstring(
        build_xml(
            [
                ScheduledTrigger(hour=9, minute=0, weekday=MON),
                ScheduledTrigger(hour=9, minute=0, weekday=FRI),
                ScheduledTrigger(hour=11, minute=0, weekday=MON),
            ]
        )
    )

    triggers = root.findall("t:Triggers/t:CalendarTrigger", NS)
    days = [
        [
            day.tag.rsplit("}", 1)[-1]
            for day in t.findall("t:ScheduleByWeek/t:DaysOfWeek/*", NS)
        ]
        for t in triggers
    ]
    assert days == [["Monday", "Friday"], ["Monday"]]


def test_daily_and_weekly_triggers_cannot_be_mixed() -> None:
    with pytest.raises(ValueError, match="Cannot mix daily and weekly"):
        build_xml(
            [
                ScheduledTrigger(hour=9, minute=0),
                ScheduledTrigger(hour=9, minute=0, weekday=MON),
            ]
        )


@pytest.mark.parametrize(
    "triggers",
    [
        pytest.param(
            [ScheduledTrigger(hour=9, minute=30), ScheduledTrigger(hour=23, minute=5)],
            id="daily",
        ),
        pytest.param(
            [
                ScheduledTrigger(hour=9, minute=0, weekday=MON),
                ScheduledTrigger(hour=9, minute=0, weekday=FRI),
                ScheduledTrigger(hour=11, minute=0, weekday=MON),
                ScheduledTrigger(hour=11, minute=0, weekday=FRI),
            ],
            id="weekly",
        ),
    ],
)
def test_task_xml_round_trips_command_and_triggers(
    triggers: list[ScheduledTrigger],
) -> None:
    job = parse_task_xml(SCHEDULE_ID, build_xml(triggers))

    assert job.schedule_id == SCHEDULE_ID
    assert job.command == [str(EXECUTABLE), *ARGUMENTS]
    assert job.triggers == triggers


@pytest.mark.parametrize(
    "model",
    [
        pytest.param("custom model", id="space"),
        pytest.param("", id="empty"),
        pytest.param(r"custom\"model", id="backslash-before-quote"),
        pytest.param("custom model\\", id="trailing-backslash-in-quoted-argument"),
        pytest.param("custom/model\n", id="trailing-line-feed"),
    ],
)
def test_task_xml_preserves_model_argument_on_read_back(model: str) -> None:
    arguments = ["warmup", "--agent", "codex", "--model", model]
    xml = build_xml([ScheduledTrigger(hour=9, minute=30)], arguments=arguments)

    job = parse_task_xml(SCHEDULE_ID, xml)

    assert job.command == [str(EXECUTABLE), *arguments]


def wrap(body: str) -> str:
    return f'<Task xmlns="{NS["t"]}">{body}</Task>'


EXEC = "<Actions><Exec><Command>warmpass.exe</Command></Exec></Actions>"


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        pytest.param(wrap("<Triggers/>"), "missing an Exec Command", id="no-command"),
        pytest.param(
            wrap(f"<Triggers><CalendarTrigger/></Triggers>{EXEC}"),
            "missing StartBoundary",
            id="no-start-boundary",
        ),
        pytest.param(
            wrap(
                "<Triggers><CalendarTrigger><StartBoundary>2026-01-05T09:00:00"
                f"</StartBoundary></CalendarTrigger></Triggers>{EXEC}"
            ),
            "ScheduleByDay or ScheduleByWeek",
            id="no-schedule-kind",
        ),
        pytest.param(
            wrap(
                "<Triggers><CalendarTrigger><StartBoundary>2026-01-05T09:00:00"
                "</StartBoundary><ScheduleByWeek><DaysOfWeek><Funday/></DaysOfWeek>"
                f"</ScheduleByWeek></CalendarTrigger></Triggers>{EXEC}"
            ),
            "Unsupported weekday",
            id="unknown-weekday",
        ),
        pytest.param(
            wrap(
                "<Triggers><CalendarTrigger><StartBoundary>2026-01-05T09:00:00"
                "</StartBoundary><ScheduleByWeek><DaysOfWeek/></ScheduleByWeek>"
                f"</CalendarTrigger></Triggers>{EXEC}"
            ),
            "missing DaysOfWeek",
            id="no-weekdays",
        ),
    ],
)
def test_parse_rejects_tasks_it_did_not_generate(xml: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_task_xml(SCHEDULE_ID, xml)


def test_task_name_carries_the_warmpass_prefix() -> None:
    assert (
        build_task_name(SCHEDULE_ID)
        == "dev.warmpass.schedule.e44215ce-26c9-41c4-96d7-67f0940496e4"
    )
