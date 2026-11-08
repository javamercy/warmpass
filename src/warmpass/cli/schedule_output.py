from typing import assert_never

from rich.console import Console
from rich.table import Table
from rich.text import Text

from warmpass.scheduling.models import (
    DailyTrigger,
    WarmupSchedule,
    WarmupScheduleTrigger,
    WeeklyTrigger,
)


def format_trigger(trigger: WarmupScheduleTrigger) -> str:
    at = trigger.at.strftime("%H:%M")

    match trigger:
        case DailyTrigger():
            return f"Daily at {at}"

        case WeeklyTrigger(days=days):
            day_names = ", ".join(day.name.title()[:3] for day in sorted(days))
            return f"{day_names} at {at}"

        case _:
            assert_never(trigger)


def print_schedule(schedule: WarmupSchedule, console: Console) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()

    table.add_row("ID", Text(str(schedule.id)))
    table.add_row("Agent", schedule.agent.value)
    table.add_row("Trigger", format_trigger(schedule.trigger))

    console.print(table)


def print_schedules(schedules: list[WarmupSchedule], console: Console) -> None:
    if not schedules:
        console.print("No warmup schedules found.")
        return

    table = Table(title="Warmup Schedules", show_lines=True)

    table.add_column("ID", no_wrap=True)
    table.add_column("Agent")
    table.add_column("Schedule")

    for schedule in schedules:
        table.add_row(
            Text(str(schedule.id)),
            schedule.agent.value,
            format_trigger(schedule.trigger),
        )

    console.print(table)
