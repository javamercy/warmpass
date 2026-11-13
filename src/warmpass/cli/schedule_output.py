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
