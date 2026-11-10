from typing import Protocol
from uuid import UUID

from warmpass.scheduling.models import WarmupSchedule


class WarmupSchedulerError(RuntimeError):
    """Error raised when a warmup scheduler operation fails."""


class WarmupScheduler(Protocol):
    def add(self, schedule: WarmupSchedule) -> None: ...

    def remove(self, schedule_id: UUID) -> None: ...

    def clear(self) -> None: ...

    def get(self, schedule_id: UUID) -> WarmupSchedule | None: ...

    def get_list(self) -> list[WarmupSchedule]: ...
