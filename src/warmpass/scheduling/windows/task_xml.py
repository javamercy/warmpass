"""Windows Task Scheduler XML models, UTF-16 serialization, and parser."""

import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Final, Literal, Self, assert_never, cast
from uuid import UUID
from xml.etree import ElementTree as ET

from pydantic import BaseModel

from warmpass.scheduling.models import OSJob, ScheduledTrigger, WeekDay

TASK_NAME_PREFIX: Final[str] = "dev.warmpass.schedule."
_TASK_XML_NAMESPACE: Final[str] = (
    "http://schemas.microsoft.com/windows/2004/02/mit/task"
)
_NS: Final[dict[str, str]] = {"t": _TASK_XML_NAMESPACE}


class DailyCalendarTrigger(BaseModel):
    """Task Scheduler daily calendar trigger starting at a naive local activation datetime."""

    start_boundary: datetime


class WeeklyCalendarTrigger(BaseModel):
    """Task Scheduler weekly calendar trigger for one time of day across one or more weekdays."""

    start_boundary: datetime
    days: list[WeekDay]


type CalendarTrigger = DailyCalendarTrigger | WeeklyCalendarTrigger


class ExecAction(BaseModel):
    """Task Scheduler executable action with command path, argument list, and working directory."""

    executable: Path
    arguments: list[str]
    working_directory: Path


class TaskPrincipal(BaseModel):
    """Task Scheduler security principal configured to run only when the user is logged on interactively."""

    user_id: str
    logon_type: Literal["InteractiveToken"] = "InteractiveToken"


class TaskSettings(BaseModel):
    """Task Scheduler execution policy settings, including battery, wake, and 5-minute execution timeout rules."""

    execution_time_limit: timedelta = timedelta(seconds=300)
    allow_hard_terminate: bool = True
    multiple_instances_policy: Literal["IgnoreNew"] = "IgnoreNew"

    disallow_start_if_on_batteries: bool = False
    stop_if_going_on_batteries: bool = False
    wake_to_run: bool = True
    start_when_available: bool = False


class TaskConfiguration(BaseModel):
    """Complete Windows Task Scheduler task definition prior to XML serialization."""

    name: str
    triggers: list[CalendarTrigger]
    action: ExecAction
    principal: TaskPrincipal
    settings: TaskSettings

    @classmethod
    def from_job(
        cls,
        schedule_id: UUID,
        *,
        warmpass_executable: Path,
        arguments: list[str],
        triggers: list[ScheduledTrigger],
        home: Path,
        user_id: str,
        activation_date: date,
    ) -> Self:
        """Build a task configuration for a schedule using the given activation date, user principal, and home working directory."""
        return cls(
            name=build_task_name(schedule_id),
            triggers=_to_calendar_triggers(triggers, activation_date),
            action=ExecAction(
                executable=warmpass_executable,
                arguments=arguments,
                working_directory=home,
            ),
            principal=TaskPrincipal(user_id=user_id),
            settings=TaskSettings(),
        )


def _to_calendar_triggers(
    triggers: list[ScheduledTrigger],
    activation_date: date,
) -> list[CalendarTrigger]:
    """Convert expanded fire triggers into daily or time-grouped weekly Task Scheduler calendar triggers."""
    if not triggers:
        return []

    if all(trigger.weekday is None for trigger in triggers):
        return [
            DailyCalendarTrigger(
                start_boundary=datetime.combine(
                    activation_date,
                    time(hour=trigger.hour, minute=trigger.minute),
                )
            )
            for trigger in triggers
        ]

    weekly_by_time: dict[tuple[int, int], list[WeekDay]] = {}
    for trigger in triggers:
        if trigger.weekday is None:
            raise ValueError(
                "Cannot mix daily and weekly triggers in one task configuration."
            )
        key = (trigger.hour, trigger.minute)
        weekly_by_time.setdefault(key, []).append(trigger.weekday)

    return [
        WeeklyCalendarTrigger(
            start_boundary=datetime.combine(
                activation_date,
                time(hour=hour, minute=minute),
            ),
            days=days,
        )
        for (hour, minute), days in weekly_by_time.items()
    ]


def build_task_name(schedule_id: UUID | str) -> str:
    """Return the Windows Task Scheduler task name for a schedule ID."""
    return f"{TASK_NAME_PREFIX}{schedule_id}"


def build_task_xml(configuration: TaskConfiguration) -> bytes:
    """Serialize a TaskConfiguration to UTF-16 XML bytes expected by schtasks.exe."""
    task = ET.Element("Task", attrib={"xmlns": _TASK_XML_NAMESPACE})

    _build_triggers(task, configuration.triggers)
    _build_principal(task, configuration.principal)
    _build_settings(task, configuration.settings)
    _build_action(task, configuration.action)

    return cast(bytes, ET.tostring(task, encoding="utf-16", xml_declaration=True))


def parse_task_xml(schedule_id: UUID, xml_content: str | bytes) -> OSJob:
    """Parse schtasks /query XML output into an OSJob, raising ValueError on missing or unsupported elements."""
    root = ET.fromstring(xml_content)

    command_element = root.find("t:Actions/t:Exec/t:Command", _NS)
    if (
        command_element is None
        or command_element.text is None
        or not command_element.text.strip()
    ):
        raise ValueError("Task XML is missing an Exec Command.")

    arguments_element = root.find("t:Actions/t:Exec/t:Arguments", _NS)
    arguments_text = (
        arguments_element.text.strip()
        if arguments_element is not None and arguments_element.text is not None
        else ""
    )
    command = [
        command_element.text.strip(),
        *(arguments_text.split() if arguments_text else []),
    ]

    triggers: list[ScheduledTrigger] = []
    for calendar_trigger in root.findall("t:Triggers/t:CalendarTrigger", _NS):
        boundary_element = calendar_trigger.find("t:StartBoundary", _NS)
        if boundary_element is None or boundary_element.text is None:
            raise ValueError("CalendarTrigger is missing StartBoundary.")

        start_boundary = datetime.fromisoformat(boundary_element.text.strip())
        hour = start_boundary.hour
        minute = start_boundary.minute

        schedule_by_day = calendar_trigger.find("t:ScheduleByDay", _NS)
        schedule_by_week = calendar_trigger.find("t:ScheduleByWeek", _NS)

        if schedule_by_day is not None:
            triggers.append(ScheduledTrigger(hour=hour, minute=minute))
        elif schedule_by_week is not None:
            days_element = schedule_by_week.find("t:DaysOfWeek", _NS)
            if days_element is None or len(days_element) == 0:
                raise ValueError("ScheduleByWeek is missing DaysOfWeek entries.")

            for day_element in days_element:
                tag_name = day_element.tag.rsplit("}", 1)[-1].upper()
                try:
                    weekday = WeekDay[tag_name]
                except KeyError as exc:
                    raise ValueError(
                        f"Unsupported weekday in Task XML: {tag_name}"
                    ) from exc
                triggers.append(
                    ScheduledTrigger(hour=hour, minute=minute, weekday=weekday)
                )
        else:
            raise ValueError(
                "CalendarTrigger must contain ScheduleByDay or ScheduleByWeek."
            )

    return OSJob(
        schedule_id=schedule_id,
        command=command,
        triggers=triggers,
    )


def _build_triggers(task: ET.Element, triggers: list[CalendarTrigger]) -> None:
    triggers_element = ET.SubElement(task, "Triggers")

    for trigger in triggers:
        calendar_element = ET.SubElement(triggers_element, "CalendarTrigger")
        _add_text(
            calendar_element,
            "StartBoundary",
            trigger.start_boundary.isoformat(timespec="seconds"),
        )

        match trigger:
            case DailyCalendarTrigger():
                schedule_by_day_element = ET.SubElement(
                    calendar_element, "ScheduleByDay"
                )
                _add_text(schedule_by_day_element, "DaysInterval", "1")

            case WeeklyCalendarTrigger(days=days):
                schedule_by_week_element = ET.SubElement(
                    calendar_element, "ScheduleByWeek"
                )
                _add_text(schedule_by_week_element, "WeeksInterval", "1")

                days_of_week_element = ET.SubElement(
                    schedule_by_week_element, "DaysOfWeek"
                )
                for day in days:
                    ET.SubElement(days_of_week_element, day.name.title())

            case _:
                assert_never(trigger)


def _build_principal(task: ET.Element, principal: TaskPrincipal) -> None:
    principals_element = ET.SubElement(task, "Principals")
    principal_element = ET.SubElement(principals_element, "Principal")

    _add_text(principal_element, "UserId", principal.user_id)
    _add_text(principal_element, "LogonType", principal.logon_type)


def _build_settings(task: ET.Element, settings: TaskSettings) -> None:
    settings_element = ET.SubElement(task, "Settings")

    _add_text(
        settings_element,
        "MultipleInstancesPolicy",
        settings.multiple_instances_policy,
    )
    _add_text(
        settings_element,
        "DisallowStartIfOnBatteries",
        str(settings.disallow_start_if_on_batteries).lower(),
    )
    _add_text(
        settings_element,
        "StopIfGoingOnBatteries",
        str(settings.stop_if_going_on_batteries).lower(),
    )
    _add_text(
        settings_element,
        "AllowHardTerminate",
        str(settings.allow_hard_terminate).lower(),
    )
    _add_text(
        settings_element,
        "StartWhenAvailable",
        str(settings.start_when_available).lower(),
    )
    _add_text(
        settings_element,
        "WakeToRun",
        str(settings.wake_to_run).lower(),
    )
    _add_text(
        settings_element,
        "ExecutionTimeLimit",
        f"PT{int(settings.execution_time_limit.total_seconds())}S",
    )


def _build_action(task: ET.Element, action: ExecAction) -> None:
    actions_element = ET.SubElement(task, "Actions")
    exec_element = ET.SubElement(actions_element, "Exec")

    _add_text(exec_element, "Command", str(action.executable))
    _add_text(exec_element, "Arguments", subprocess.list2cmdline(action.arguments))
    _add_text(exec_element, "WorkingDirectory", str(action.working_directory))


def _add_text(parent: ET.Element, name: str, value: str) -> None:
    ET.SubElement(parent, name).text = value
