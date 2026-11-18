"""CLI subcommands and option parsers for managing warmup schedules."""

import re
from datetime import time
from enum import StrEnum
from typing import Annotated
from uuid import UUID

import typer
from pydantic import ValidationError
from rich.console import Console

from warmpass.cli.schedule_output import print_schedule, print_schedules
from warmpass.models import AgentType
from warmpass.scheduling.base import SchedulingError
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    ScheduleTrigger,
    TriggerKind,
    WeekDay,
    WeeklyTrigger,
)
from warmpass.wiring import create_scheduler_service

app = typer.Typer(help="Manage warmup schedules.")


class DayOption(StrEnum):
    """Case-insensitive CLI option values for weekday selection."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    def to_weekday(self) -> WeekDay:
        """Convert the CLI day option to its corresponding domain WeekDay."""
        return WeekDay[self.name]


class EveryOption(StrEnum):
    """CLI option values for hourly schedule frequency (1h to 5h)."""

    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    THREE_HOURS = "3h"
    FOUR_HOURS = "4h"
    FIVE_HOURS = "5h"

    def to_hours(self) -> int:
        """Return the integer number of hours represented by the option."""
        return int(self.value[:-1])


def parse_schedule_time(value: str) -> time:
    """Parse a strict 24-hour HH:MM string into a naive time, or raise typer.BadParameter."""
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        raise typer.BadParameter("Use 24-hour time in HH:MM format, e.g. 09:30.")

    hour, minute = map(int, value.split(":"))

    try:
        return time(hour=hour, minute=minute)
    except ValueError as exc:
        raise typer.BadParameter("Enter a valid time between 00:00 and 23:59.") from exc


@app.command()
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
    model: Annotated[
        str | None,
        typer.Option(help="The model to use for warmup."),
    ] = None,
) -> None:
    """Add a new warmup schedule (e.g. warmpass schedule add --agent codex --trigger daily --from 09:00 --until 17:00 --every 2h)."""
    if trigger == TriggerKind.DAILY and day:
        raise typer.BadParameter(
            "--day can only be used with a weekly trigger.",
            param_hint="--day",
        )
    if trigger == TriggerKind.WEEKLY and not day:
        raise typer.BadParameter(
            "A weekly trigger requires at least one --day.",
            param_hint="--day",
        )

    try:
        window = HourlyWindow(
            from_=from_,
            until=until,
            every=every.to_hours(),
        )

        schedule_trigger: ScheduleTrigger = (
            DailyTrigger(window=window)
            if trigger == TriggerKind.DAILY
            else WeeklyTrigger(
                days=[item.to_weekday() for item in day or ()],
                window=window,
            )
        )
    except ValidationError as exc:
        message = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise typer.BadParameter(message) from exc

    try:
        service = create_scheduler_service()
        schedule = service.add(agent=agent, trigger=schedule_trigger, model=model)
    except SchedulingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Schedule added:")
    print_schedule(schedule, Console())


@app.command()
def remove(
    schedule_id: Annotated[
        UUID, typer.Argument(help="The ID of the schedule to remove.")
    ],
) -> None:
    """Remove an existing warmup schedule."""
    try:
        service = create_scheduler_service()
        service.remove(schedule_id)
    except SchedulingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Schedule '{schedule_id}' has been removed.")


@app.command()
def clear(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip the confirmation prompt."),
    ] = False,
) -> None:
    """Remove all warmup schedules."""
    if not yes and not typer.confirm("Remove all warmup schedules?", default=False):
        typer.echo("Clear cancelled.")
        return

    try:
        service = create_scheduler_service()
        service.clear()
    except SchedulingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Warmup schedules cleared.")


@app.command()
def get(
    schedule_id: Annotated[
        UUID, typer.Argument(help="The ID of the schedule to retrieve.")
    ],
) -> None:
    """Retrieve details of a specific warmup schedule."""
    try:
        service = create_scheduler_service()
        schedule = service.get(schedule_id)
    except SchedulingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if schedule is None:
        typer.echo(f"No schedule found with ID: {schedule_id}", err=True)
        raise typer.Exit(code=1)

    print_schedule(schedule, Console())


@app.command(name="list")
def get_list() -> None:
    """List all warmup schedules."""
    try:
        service = create_scheduler_service()
        schedules = service.get_list()
    except SchedulingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    print_schedules(schedules, Console())
