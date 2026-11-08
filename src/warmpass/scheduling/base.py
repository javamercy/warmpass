from typing import Protocol
from uuid import UUID

from warmpass.scheduling.models import WarmupSchedule


class WarmupSchedulerError(RuntimeError):
    """Error raised when a warmup scheduler operation fails."""


class WarmupScheduleAlreadyExistsError(WarmupSchedulerError):
    """Error raised when a warmup schedule already exists."""


class WarmupScheduleRegistrationError(WarmupSchedulerError):
    """Error raised when a warmup schedule fails to register."""


class WarmupScheduleRemovalError(WarmupSchedulerError):
    """Error raised when a warmup schedule fails to remove."""


class WarmupScheduler(Protocol):
    def add(self, schedule: WarmupSchedule) -> None: ...

    def remove(self, schedule_id: UUID) -> None: ...

    def get(self, schedule_id: UUID) -> WarmupSchedule | None: ...

    def get_list(self) -> list[WarmupSchedule]: ...
