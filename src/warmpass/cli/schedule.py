import re
from datetime import time
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

import typer
from rich.console import Console

from warmpass.agents.models import WarmupAgentType
from warmpass.cli.schedule_output import print_schedule, print_schedules
from warmpass.scheduling.factory import create_warmup_scheduler_service
from warmpass.scheduling.models import (
    DailyTrigger,
    WarmupSchedule,
    WeekDay,
    WeeklyTrigger,
)

app = typer.Typer(help="Manage warmup schedules.")


class TriggerKind(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class DayOption(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    def to_weekday(self) -> WeekDay:
        return WeekDay[self.name]


def parse_schedule_time(value: str) -> time:
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        raise typer.BadParameter("Use 24-hour time in HH:MM format, e.g. 09:30.")

    hour, minute = map(int, value.split(":"))

    try:
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise typer.BadParameter("Enter a valid time between 00:00 and 23:59.") from exc


@app.command(help="Add a new warmup schedule.")
def add(
    agent: Annotated[
        WarmupAgentType, typer.Option(help="The agent to schedule for warmup.")
    ],
    trigger: Annotated[TriggerKind, typer.Option(help="The type of trigger.")],
    at: Annotated[
        time,
        typer.Option(
            parser=parse_schedule_time, help="Time of day, for example '09:30'."
        ),
    ],
    day: Annotated[
        list[DayOption] | None,
        typer.Option(
            help="Weekday to run on; repeat for multiple days.", case_sensitive=False
        ),
    ] = None,
) -> None:
    if trigger == TriggerKind.DAILY:
        if day:
            raise typer.BadParameter(
                "--day can only be used with a weekly trigger.", param_hint="--day"
            )

        schedule_trigger = DailyTrigger.model_validate({"at": at})

    else:
        if not day:
            raise typer.BadParameter(
                "A weekly trigger requires at least one --day.", param_hint="--day"
            )

        if len(set(day)) != len(day):
            raise typer.BadParameter(
                "Duplicate days are not allowed.", param_hint="--day"
            )

        schedule_trigger = WeeklyTrigger.model_validate(
            {
                "at": at,
                "days": [d.to_weekday() for d in day],
            }
        )

    schedule = WarmupSchedule(
        id=str(uuid4()),
        agent=agent,
        trigger=schedule_trigger,
    )

    service = create_warmup_scheduler_service()
    service.add(schedule)

    typer.echo("Schedule added:")
    print_schedule(schedule, Console())


@app.command(help="Remove an existing warmup schedule.")
def remove(
    schedule_id: Annotated[
        str, typer.Argument(help="The ID of the schedule to remove.")
    ],
) -> None:
    service = create_warmup_scheduler_service()
    service.remove(schedule_id)

    typer.echo(f"Schedule '{schedule_id}' has been removed.")


@app.command(help="Retrieve details of a specific warmup schedule.")
def get(
    schedule_id: Annotated[
        str, typer.Argument(help="The ID of the schedule to retrieve.")
    ],
) -> None:
    service = create_warmup_scheduler_service()
    schedule = service.get(schedule_id)

    if schedule is None:
        typer.echo(f"No schedule found with ID: {schedule_id}", err=True)
        raise typer.Exit(code=1)

    print_schedule(schedule, Console())


@app.command(name="list", help="List all warmup schedules.")
def get_list() -> None:
    service = create_warmup_scheduler_service()
    schedules = service.get_list()

    print_schedules(schedules, Console())
