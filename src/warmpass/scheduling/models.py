from datetime import time
from enum import IntEnum, StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from warmpass.agents.models import AgentType


class WeekDay(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class HourlyWindow(BaseModel):
    from_: time | None = None
    until: time | None = None
    every: Annotated[int, Field(strict=True, gt=0, le=5)]

    @field_validator("from_", "until")
    @classmethod
    def validate_time(cls, value: time | None) -> time | None:
        if value is None:
            return None

        if value.tzinfo is not None:
            raise ValueError("Window times must not include a timezone")

        if value.second or value.microsecond:
            raise ValueError("Window times must have minute precision")

        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
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
    DAILY = "daily"
    WEEKLY = "weekly"


class DailyTrigger(BaseModel):
    kind: Literal[TriggerKind.DAILY] = TriggerKind.DAILY
    window: HourlyWindow


class WeeklyTrigger(BaseModel):
    kind: Literal[TriggerKind.WEEKLY] = TriggerKind.WEEKLY
    days: Annotated[list[WeekDay], Field(min_length=1)]
    window: HourlyWindow

    @model_validator(mode="after")
    def validate_weekly_window(self) -> Self:
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
    id: UUID
    agent: AgentType
    trigger: ScheduleTrigger


class ScheduledTrigger(BaseModel):
    hour: Annotated[int, Field(strict=True, ge=0, le=23)]
    minute: Annotated[int, Field(strict=True, ge=0, le=59)]
    weekday: WeekDay | None = None


class OSJob(BaseModel):
    schedule_id: UUID
    command: list[str]
    triggers: list[ScheduledTrigger]
