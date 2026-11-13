from pathlib import Path
from typing import Annotated, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from warmpass.scheduling.models import (
    ScheduledTrigger,
    WeekDay,
)

LABEL_PREFIX: Final[str] = "dev.warmpass.schedule."
PLIST_SUFFIX: Final[str] = ".plist"


class PlistConfiguration(BaseModel):
    model_config = ConfigDict(validate_by_alias=True, validate_by_name=True)

    label: Annotated[str, Field(alias="Label")]
    program_arguments: Annotated[list[str], Field(alias="ProgramArguments")]
    start_calendar_interval: Annotated[
        list[dict[str, int]], Field(alias="StartCalendarInterval")
    ]
    run_at_load: Annotated[bool, Field(alias="RunAtLoad")]
    keep_alive: Annotated[bool, Field(alias="KeepAlive")]
    working_directory: Annotated[str, Field(alias="WorkingDirectory")]
    environment_variables: Annotated[
        dict[str, str], Field(alias="EnvironmentVariables")
    ]
    standard_out_path: Annotated[str, Field(alias="StandardOutPath")]
    standard_error_path: Annotated[str, Field(alias="StandardErrorPath")]

    @model_validator(mode="before")
    @classmethod
    def _normalize_single_interval(cls, data: object) -> object:
        if isinstance(data, dict):
            interval = data.get("StartCalendarInterval")
            if isinstance(interval, dict):
                return {**data, "StartCalendarInterval": [interval]}
        return data

    @classmethod
    def from_job(
        cls,
        schedule_id: UUID,
        *,
        warmpass_executable: Path,
        arguments: list[str],
        triggers: list[ScheduledTrigger],
        home: Path,
        log_directory: Path,
        warmpass_executable_search_path: str,
    ) -> PlistConfiguration:
        return cls(
            label=build_label(schedule_id),
            program_arguments=[str(warmpass_executable), *arguments],
            start_calendar_interval=[
                _to_launchd_interval(trigger) for trigger in triggers
            ],
            run_at_load=False,
            keep_alive=False,
            working_directory=str(home),
            environment_variables={
                "HOME": str(home),
                "PATH": warmpass_executable_search_path,
            },
            standard_out_path=str(log_directory / f"{schedule_id}.out.log"),
            standard_error_path=str(log_directory / f"{schedule_id}.err.log"),
        )

    def to_plist_dict(self) -> dict[str, object]:
        return self.model_dump(by_alias=True)

    def to_scheduled_triggers(self) -> list[ScheduledTrigger]:
        triggers: list[ScheduledTrigger] = []
        for interval in self.start_calendar_interval:
            if "Hour" not in interval or "Minute" not in interval:
                raise ValueError(
                    "Launchd calendar interval must include 'Hour' and 'Minute'."
                )

            allowed_keys = {"Hour", "Minute", "Weekday"}
            if set(interval.keys()) - allowed_keys:
                raise ValueError(
                    f"Unsupported keys in launchd calendar interval: {set(interval.keys()) - allowed_keys}"
                )

            raw_weekday = interval.get("Weekday")
            if raw_weekday is not None and not (0 <= raw_weekday <= 7):
                raise ValueError(f"Invalid launchd Weekday: {raw_weekday}")

            weekday = (
                WeekDay((raw_weekday - 1) % 7) if raw_weekday is not None else None
            )
            triggers.append(
                ScheduledTrigger(
                    hour=interval["Hour"],
                    minute=interval["Minute"],
                    weekday=weekday,
                )
            )
        return triggers


def _to_launchd_interval(trigger: ScheduledTrigger) -> dict[str, int]:
    interval: dict[str, int] = {
        "Hour": trigger.hour,
        "Minute": trigger.minute,
    }
    if trigger.weekday is not None:
        interval["Weekday"] = (int(trigger.weekday) + 1) % 7
    return interval


def build_label(schedule_id: UUID | str) -> str:
    return f"{LABEL_PREFIX}{schedule_id}"


def build_plist_path(launch_agents_directory: Path, schedule_id: UUID) -> Path:
    return launch_agents_directory / f"{LABEL_PREFIX}{schedule_id}{PLIST_SUFFIX}"
