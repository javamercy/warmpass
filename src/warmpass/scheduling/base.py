from typing import Protocol
from uuid import UUID

from warmpass.errors import WarmpassError
from warmpass.scheduling.models import OSJob, ScheduledTrigger


class SchedulingError(WarmpassError):
    """Base class for all scheduling errors."""


class OSJobScheduler(Protocol):
    """Protocol for an OS-native job scheduler (e.g., launchd, Task Scheduler, systemd/cron)."""

    def register_job(
        self,
        schedule_id: UUID,
        *,
        arguments: list[str],
        triggers: list[ScheduledTrigger],
    ) -> None: ...

    def unregister_job(self, schedule_id: UUID) -> None: ...

    def get_job(self, schedule_id: UUID) -> OSJob | None: ...

    def list_job_ids(self) -> set[UUID]: ...

    def clear_jobs(self) -> None: ...
