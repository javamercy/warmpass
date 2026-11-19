"""Rich console formatting for displaying single and listed warmup schedules."""

from typing import assert_never

from rich.console import Console
from rich.table import Table
from rich.text import Text

from warmpass.scheduling.models import (
    DailyTrigger,
    ScheduleTrigger,
    WarmupSchedule,
    WeeklyTrigger,
)


def format_trigger(trigger: ScheduleTrigger) -> str:
    """Format a daily or weekly trigger and its local-time window for terminal display."""
    window = trigger.window

    start = window.from_.strftime("%H:%M") if window.from_ is not None else "00:00"
    end = window.until.strftime("%H:%M") if window.until is not None else "24:00"

    if (
        window.from_ is not None
        and window.until is not None
        and window.until < window.from_
    ):
        end += " next day"

    frequency = "every hour" if window.every == 1 else f"every {window.every} hours"

    match trigger:
        case DailyTrigger():
            days = "Daily"

        case WeeklyTrigger(days=weekdays):
            days = ", ".join(day.name.title()[:3] for day in sorted(weekdays))

        case _:
            assert_never(trigger)

    return f"{days}, {frequency}, [{start}–{end}) (local time)"


def print_schedule(schedule: WarmupSchedule, console: Console) -> None:
    """Render a single warmup schedule as a key-value grid on the given console."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()

    table.add_row("ID", Text(str(schedule.id)))
    table.add_row("Agent", schedule.agent.value)

    model = schedule.model if schedule.model is not None else "Default"

    table.add_row("Model", Text(model))
    table.add_row("Trigger", format_trigger(schedule.trigger))

    console.print(table)


def print_schedules(schedules: list[WarmupSchedule], console: Console) -> None:
    """Render a table of warmup schedules, or an empty-state message when the list is empty."""
    if not schedules:
        console.print("No warmup schedules found.")
        return

    table = Table(title="Warmup Schedules", show_lines=True)

    table.add_column("ID", no_wrap=True)
    table.add_column("Agent")
    table.add_column("Model")
    table.add_column("Schedule")

    for schedule in schedules:
        model = schedule.model if schedule.model is not None else "Default"
        table.add_row(
            Text(str(schedule.id)),
            schedule.agent.value,
            Text(model),
            format_trigger(schedule.trigger),
        )

    console.print(table)
