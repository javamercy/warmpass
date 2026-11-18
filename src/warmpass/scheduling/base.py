"""Protocol and base error for OS-native job scheduler backends."""

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
    ) -> None:
        """Register a new OS job for the schedule that invokes warmpass with the given arguments and triggers, or raise SchedulingError."""
        ...

    def unregister_job(self, schedule_id: UUID) -> None:
        """Remove the OS job for the given schedule ID, or raise SchedulingError."""
        ...

    def get_job(self, schedule_id: UUID) -> OSJob | None:
        """Return the installed OS job for the schedule ID, None if absent, or raise SchedulingError if invalid or not loaded."""
        ...

    def list_job_ids(self) -> set[UUID]:
        """Return the schedule IDs of all Warmpass jobs known to the OS scheduler, or raise SchedulingError."""
        ...

    def clear_jobs(self) -> None:
        """Remove all Warmpass jobs from the OS scheduler, or raise SchedulingError."""
        ...
