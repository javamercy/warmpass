import re
from datetime import time
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import typer
from pydantic import ValidationError
from rich.console import Console

from warmpass.agents.models import AgentType
from warmpass.cli.schedule_output import print_schedule, print_schedules
from warmpass.scheduling.base import WarmupSchedulerError
from warmpass.scheduling.factory import create_warmup_scheduler_service
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    TriggerKind,
    WeekDay,
    WeeklyTrigger,
)

app = typer.Typer(help="Manage warmup schedules.")


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


class EveryOption(StrEnum):
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    THREE_HOURS = "3h"
    FOUR_HOURS = "4h"
    FIVE_HOURS = "5h"

    def to_hours(self) -> int:
        return int(self.value[:-1])


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
        AgentType,
        typer.Option(help="The agent to schedule for warmup."),
    ],
    trigger: Annotated[
        TriggerKind,
        typer.Option(help="The type of trigger."),
    ],
    every: Annotated[
        EveryOption,
        typer.Option(help="Frequency: 1h, 2h, 3h, 4h, or 5h."),
    ],
    from_: Annotated[
        time | None,
        typer.Option(
            "--from",
            parser=parse_schedule_time,
            help="Window start in local time, HH:MM.",
        ),
    ] = None,
    until: Annotated[
        time | None,
        typer.Option(
            parser=parse_schedule_time,
            help="Exclusive window end in local time, HH:MM.",
        ),
    ] = None,
    day: Annotated[
        list[DayOption] | None,
        typer.Option(
            help="Weekday to run on; repeat for multiple days.",
            case_sensitive=False,
        ),
    ] = None,
) -> None:
    if trigger == TriggerKind.DAILY and day:
        raise typer.BadParameter(
            "--day can only be used with a weekly trigger.",
            param_hint="--day",
        )

    try:
        window = HourlyWindow(
            from_=from_,
            until=until,
            every=every.to_hours(),
        )

        if trigger == TriggerKind.DAILY:
            schedule_trigger = DailyTrigger(window=window)
        else:
            if not day:
                raise typer.BadParameter(
                    "A weekly trigger requires at least one --day.",
                    param_hint="--day",
                )
            schedule_trigger = WeeklyTrigger(
                days=[item.to_weekday() for item in day],
                window=window,
            )
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        raise typer.BadParameter(message) from exc

    try:
        service = create_warmup_scheduler_service()
        schedule = service.add(agent, schedule_trigger)
    except WarmupSchedulerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Schedule added:")
    print_schedule(schedule, Console())


@app.command(help="Remove an existing warmup schedule.")
def remove(
    schedule_id: Annotated[
        UUID, typer.Argument(help="The ID of the schedule to remove.")
    ],
) -> None:
    try:
        service = create_warmup_scheduler_service()
        service.remove(schedule_id)
    except WarmupSchedulerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Schedule '{schedule_id}' has been removed.")


@app.command(help="Remove all warmup schedules")
def clear(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the confirmation prompt."),
    ] = False,
) -> None:
    if not yes and not typer.confirm("Remove all warmup schedules?", default=False):
        typer.echo("Clear cancelled.")
        return

    try:
        service = create_warmup_scheduler_service()
        service.clear()
    except WarmupSchedulerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Warmup schedules cleared.")


@app.command(help="Retrieve details of a specific warmup schedule.")
def get(
    schedule_id: Annotated[
        UUID, typer.Argument(help="The ID of the schedule to retrieve.")
    ],
) -> None:
    try:
        service = create_warmup_scheduler_service()
        schedule = service.get(schedule_id)
    except WarmupSchedulerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if schedule is None:
        typer.echo(f"No schedule found with ID: {schedule_id}", err=True)
        raise typer.Exit(code=1)

    print_schedule(schedule, Console())


@app.command(name="list", help="List all warmup schedules.")
def get_list() -> None:
    try:
        service = create_warmup_scheduler_service()
        schedules = service.get_list()
    except WarmupSchedulerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    print_schedules(schedules, Console())
