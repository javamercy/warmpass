"""Suite-wide safety rules and the fixtures shared across test modules.

The two autouse fixtures guarantee that no test can spend agent quota, register
an OS job, or touch the real home directory or Warmpass state, even by mistake.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.support.fakes import FakeAgentProcess, FakeOSJobScheduler
from warmpass.paths import get_store_directory
from warmpass.scheduling.service import SchedulerService
from warmpass.scheduling.store import WarmupScheduleStore


@pytest.fixture(autouse=True)
def isolated_user_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Send the home directory and Warmpass record and log locations to tmp_path."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    def data_directory(appname: str, appauthor: bool) -> Path:
        return tmp_path / "warmpass-data"

    def log_directory(appname: str, appauthor: bool) -> Path:
        return tmp_path / "warmpass-logs"

    monkeypatch.setattr("warmpass.paths.user_data_path", data_directory)
    monkeypatch.setattr("warmpass.paths.user_log_path", log_directory)


@pytest.fixture(autouse=True)
def forbid_real_agents_and_schedulers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test would run a real agent or build a real OS scheduler.

    Agent processes may only run the current Python interpreter, which is how
    stand-in agents are written. Tests that need a scheduler use the fakes.
    """
    real_run = subprocess.run

    def run_only_python(
        command: list[str], **options: Any
    ) -> subprocess.CompletedProcess[str]:
        if command[0] != sys.executable:
            raise AssertionError(f"Test tried to run a real program: {command[0]!r}")
        return real_run(command, **options)

    def refuse_real_scheduler() -> None:
        raise AssertionError("Test tried to build a real OS job scheduler.")

    monkeypatch.setattr("warmpass.agents.base.run", run_only_python)
    monkeypatch.setattr(
        "warmpass.scheduling.macos.factory.create_macos_warmup_scheduler",
        refuse_real_scheduler,
    )
    monkeypatch.setattr(
        "warmpass.scheduling.windows.factory.create_windows_warmup_scheduler",
        refuse_real_scheduler,
    )


@pytest.fixture
def agent_process(monkeypatch: pytest.MonkeyPatch) -> FakeAgentProcess:
    """The process boundary of every agent adapter, faked in one place."""
    fake = FakeAgentProcess()
    monkeypatch.setattr("warmpass.agents.base.run", fake)
    return fake


@pytest.fixture
def fake_scheduler() -> FakeOSJobScheduler:
    return FakeOSJobScheduler()


@pytest.fixture
def schedule_store() -> WarmupScheduleStore:
    """A real store in the redirected Warmpass data directory."""
    return WarmupScheduleStore(get_store_directory())


@pytest.fixture
def scheduler_service(
    schedule_store: WarmupScheduleStore, fake_scheduler: FakeOSJobScheduler
) -> SchedulerService:
    """The real service over a real store and a fake OS scheduler."""
    return SchedulerService(store=schedule_store, scheduler=fake_scheduler)


@pytest.fixture
def cli_service(
    scheduler_service: SchedulerService, monkeypatch: pytest.MonkeyPatch
) -> SchedulerService:
    """Make `warmpass schedule ...` use `scheduler_service`."""
    monkeypatch.setattr(
        "warmpass.cli.schedule.create_scheduler_service", lambda: scheduler_service
    )
    return scheduler_service
