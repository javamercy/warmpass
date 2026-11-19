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
from warmpass import process, wiring
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
    monkeypatch.setattr("typer.rich_utils.FORCE_TERMINAL", False)

    def data_directory(appname: str, appauthor: bool) -> Path:
        return tmp_path / "warmpass-data"

    def log_directory(appname: str, appauthor: bool) -> Path:
        return tmp_path / "warmpass-logs"

    monkeypatch.setattr("warmpass.paths.user_data_path", data_directory)
    monkeypatch.setattr("warmpass.paths.user_log_path", log_directory)


@pytest.fixture(autouse=True)
def forbid_real_agents_and_schedulers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Allow only the Python interpreter and the test's scheduler stand-ins."""
    real_run = subprocess.run
    allowed_executables = {
        sys.executable,
        str(tmp_path / "launchctl"),
        str(tmp_path / "schtasks"),
        str(tmp_path / "schtasks.cmd"),
    }

    def run_only_stand_ins(
        command: list[str], **options: Any
    ) -> subprocess.CompletedProcess[str]:
        if command[0] not in allowed_executables:
            raise AssertionError(f"Test tried to run a real program: {command[0]!r}")
        return real_run(command, **options)

    def refuse_real_scheduler() -> None:
        raise AssertionError("Test tried to build a real OS job scheduler.")

    monkeypatch.setattr(process.subprocess, "run", run_only_stand_ins)
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
    monkeypatch.setattr(process.subprocess, "run", fake)
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
    fake_scheduler: FakeOSJobScheduler, monkeypatch: pytest.MonkeyPatch
) -> SchedulerService:
    """Build the CLI's real service with the in-memory OS scheduler."""
    monkeypatch.setattr(wiring, "create_os_job_scheduler", lambda: fake_scheduler)
    return wiring.create_scheduler_service()
