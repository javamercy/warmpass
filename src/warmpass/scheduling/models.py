"""Pydantic models for persisted warmup schedules and expanded OS scheduler triggers."""

from datetime import time
from enum import IntEnum, StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from warmpass.models import AgentType


class WeekDay(IntEnum):
    """ISO-ordered weekday numbering (Monday is 0 through Sunday is 6)."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class HourlyWindow(BaseModel):
    """Local wall-clock time window [from_, until) and hourly interval (1 to 5 hours) for a schedule."""

    from_: time | None = None
    until: time | None = None
    every: Annotated[int, Field(strict=True, gt=0, le=5)]

    @field_validator("from_", "until")
    @classmethod
    def validate_time(cls, value: time | None) -> time | None:
        """Reject timezone-aware times and times finer than one minute."""
        if value is None:
            return None

        if value.tzinfo is not None:
            raise ValueError("Window times must not include a timezone")

        if value.second or value.microsecond:
            raise ValueError("Window times must have minute precision")

        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        """Reject empty windows where from_ and until would produce no runs."""
        if (
            self.from_ is not None
            and self.until is not None
            and self.from_ == self.until
        ):
            raise ValueError("The from and until times cannot be the same")

        if self.from_ is None and self.until == time.min:
            raise ValueError("A window ending at 00:00 would contain no runs")

        return self


class TriggerKind(StrEnum):
    """Schedule recurrence kind; values are the public CLI and JSON discriminator spellings."""

    DAILY = "daily"
    WEEKLY = "weekly"


class DailyTrigger(BaseModel):
    """Schedule trigger that runs every day within an hourly window, allowing windows that cross midnight."""

    kind: Literal[TriggerKind.DAILY] = TriggerKind.DAILY
    window: HourlyWindow


class WeeklyTrigger(BaseModel):
    """Schedule trigger that runs on selected weekdays within a same-day hourly window."""

    kind: Literal[TriggerKind.WEEKLY] = TriggerKind.WEEKLY
    days: Annotated[list[WeekDay], Field(min_length=1)]
    window: HourlyWindow

    @model_validator(mode="after")
    def validate_weekly_window(self) -> Self:
        """Reject duplicate weekdays and weekly windows that cross midnight."""
        if len(set(self.days)) != len(self.days):
            raise ValueError("Duplicate weekdays are not allowed")

        if (
            self.window.from_ is not None
            and self.window.until is not None
            and self.window.from_ > self.window.until
        ):
            raise ValueError("A weekly window cannot cross midnight")

        return self


type ScheduleTrigger = Annotated[
    DailyTrigger | WeeklyTrigger, Field(discriminator="kind")
]


class WarmupSchedule(BaseModel):
    """Persisted schedule record tying a schedule ID to an agent, optional model, and recurrence trigger."""

    id: UUID
    agent: AgentType
    model: str | None = None
    trigger: ScheduleTrigger


class ScheduledTrigger(BaseModel):
    """Single concrete fire time in 24-hour local wall-clock time, optionally scoped to one weekday."""

    hour: Annotated[int, Field(strict=True, ge=0, le=23)]
    minute: Annotated[int, Field(strict=True, ge=0, le=59)]
    weekday: WeekDay | None = None


class OSJob(BaseModel):
    """Inspectable representation of an installed OS scheduler job, its command argv, and its fire triggers."""

    schedule_id: UUID
    command: list[str]
    triggers: list[ScheduledTrigger]
