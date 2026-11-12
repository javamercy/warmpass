import subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Final, Literal, assert_never, cast
from uuid import UUID
from xml.etree import ElementTree as ET

from pydantic import BaseModel

from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    WarmupSchedule,
    WarmupScheduleTrigger,
    WeekDay,
    WeeklyTrigger,
)

_TASK_XML_NAMESPACE: Final[str] = (
    "http://schemas.microsoft.com/windows/2004/02/mit/task"
)


class DailyCalendarTrigger(BaseModel):
    start_boundary: datetime


class WeeklyCalendarTrigger(BaseModel):
    start_boundary: datetime
    days: list[WeekDay]


type CalendarTrigger = DailyCalendarTrigger | WeeklyCalendarTrigger


class ExecAction(BaseModel):
    executable: Path
    arguments: list[str]
    working_directory: Path


class TaskPrincipal(BaseModel):
    user_id: str
    logon_type: Literal["InteractiveToken"] = "InteractiveToken"


class TaskSettings(BaseModel):
    execution_time_limit: timedelta = timedelta(seconds=300)
    allow_hard_terminate: bool = True
    multiple_instances_policy: Literal["IgnoreNew"] = "IgnoreNew"

    disallow_start_if_on_batteries: bool = False
    stop_if_going_on_batteries: bool = False
    wake_to_run: bool = True
    start_when_available: bool = False


class TaskConfiguration(BaseModel):
    name: str
    triggers: list[CalendarTrigger]
    action: ExecAction
    principal: TaskPrincipal
    settings: TaskSettings

    @classmethod
    def from_schedule(
        cls,
        schedule: WarmupSchedule,
        *,
        executable: Path,
        home: Path,
        user_id: str,
        activation_date: date,
    ) -> TaskConfiguration:
        return cls(
            name=build_task_name(schedule.id),
            triggers=TaskConfiguration._build_calendar_triggers(
                schedule.trigger, activation_date
            ),
            action=ExecAction(
                executable=executable,
                arguments=["warmup", "--agent", schedule.agent.value],
                working_directory=home,
            ),
            principal=TaskPrincipal(user_id=user_id),
            settings=TaskSettings(),
        )

    @staticmethod
    def _build_calendar_triggers(
        trigger: WarmupScheduleTrigger,
        activation_date: date,
    ) -> list[CalendarTrigger]:
        times = TaskConfiguration._build_window_times(trigger.window)

        match trigger:
            case DailyTrigger():
                return [
                    DailyCalendarTrigger(
                        start_boundary=datetime.combine(activation_date, run_time),
                    )
                    for run_time in times
                ]

            case WeeklyTrigger(days=days):
                return [
                    WeeklyCalendarTrigger(
                        start_boundary=datetime.combine(activation_date, run_time),
                        days=days,
                    )
                    for run_time in times
                ]

            case _:
                assert_never(trigger)

    @staticmethod
    def _build_window_times(
        window: HourlyWindow,
    ) -> list[time]:
        minutes_per_day = 24 * 60
        start = (
            window.from_.hour * 60 + window.from_.minute
            if window.from_ is not None
            else 0
        )
        end = (
            window.until.hour * 60 + window.until.minute
            if window.until is not None
            else minutes_per_day
        )

        if end < start:
            end += minutes_per_day

        times: list[time] = []

        for minute in range(start, end, window.every * 60):
            minute_of_day = minute % minutes_per_day
            hour, minute_of_hour = divmod(minute_of_day, 60)
            times.append(time(hour=hour, minute=minute_of_hour))

        return times


def build_task_name(schedule_id: UUID) -> str:
    return f"dev.warmpass.schedule.{schedule_id}"


def build_task_xml(configuration: TaskConfiguration) -> bytes:
    task = ET.Element("Task", attrib={"xmlns": _TASK_XML_NAMESPACE})

    _build_triggers(task, configuration.triggers)
    _build_principal(task, configuration.principal)
    _build_settings(task, configuration.settings)
    _build_action(task, configuration.action)

    return cast(bytes, ET.tostring(task, encoding="utf-16", xml_declaration=True))


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
