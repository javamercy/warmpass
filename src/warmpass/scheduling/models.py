from datetime import time
from enum import IntEnum
from typing import Annotated

from pydantic import BaseModel, Field

from warmpass.agents.models import WarmupAgentType


class WeekDay(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class DailyTrigger(BaseModel):
    at: time


class WeeklyTrigger(BaseModel):
    at: time
    days: Annotated[list[WeekDay], Field(min_length=1)]


type WarmupScheduleTrigger = DailyTrigger | WeeklyTrigger


class WarmupSchedule(BaseModel):
    id: str
    agent: WarmupAgentType
    trigger: WarmupScheduleTrigger
