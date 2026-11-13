"""Test doubles for the two boundaries Warmpass crosses: agent processes and the
OS scheduler. They are shared by CLI, service, and contract tests."""

from dataclasses import dataclass, field
from subprocess import CompletedProcess
from uuid import UUID

from warmpass.scheduling.models import OSJob, ScheduledTrigger

FAKE_WARMPASS_EXECUTABLE = "/fake/bin/warmpass"


@dataclass(frozen=True)
class AgentCall:
    command: list[str]
    options: dict[str, object]


@dataclass
class FakeAgentProcess:
    """Replaces `subprocess.run` as the agent adapters call it.

    Returns the configured result, or raises `error` when one is set. Every call
    is recorded so tests can assert the command line and process options.
    """

    returncode: int = 0
    stdout: str = "OK\n"
    stderr: str = ""
    error: BaseException | None = None
    calls: list[AgentCall] = field(default_factory=list)

    def __call__(self, command: list[str], **options: object) -> CompletedProcess[str]:
        self.calls.append(AgentCall(command=command, options=options))
        if self.error is not None:
            raise self.error
        return CompletedProcess(command, self.returncode, self.stdout, self.stderr)


class FakeOSJobScheduler:
    """In-memory `OSJobScheduler`.

    `calls` records method names in order. `failures` maps a method name to the
    exception that method raises instead of acting.
    """

    def __init__(self) -> None:
        self.jobs: dict[UUID, OSJob] = {}
        self.calls: list[str] = []
        self.failures: dict[str, Exception] = {}

    def register_job(
        self,
        schedule_id: UUID,
        *,
        arguments: list[str],
        triggers: list[ScheduledTrigger],
    ) -> None:
        self._enter("register_job")
        self.jobs[schedule_id] = OSJob(
            schedule_id=schedule_id,
            command=[FAKE_WARMPASS_EXECUTABLE, *arguments],
            triggers=triggers,
        )

    def unregister_job(self, schedule_id: UUID) -> None:
        self._enter("unregister_job")
        self.jobs.pop(schedule_id, None)

    def get_job(self, schedule_id: UUID) -> OSJob | None:
        self._enter("get_job")
        return self.jobs.get(schedule_id)

    def list_job_ids(self) -> set[UUID]:
        self._enter("list_job_ids")
        return set(self.jobs)

    def clear_jobs(self) -> None:
        self._enter("clear_jobs")
        self.jobs.clear()

    def _enter(self, method: str) -> None:
        self.calls.append(method)
        error = self.failures.get(method)
        if error is not None:
            raise error
