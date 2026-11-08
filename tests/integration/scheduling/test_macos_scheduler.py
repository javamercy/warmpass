import os
import subprocess
import sys
from datetime import time
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from typer.testing import CliRunner

import warmpass.cli.schedule as schedule_module
from warmpass.agents.models import WarmupAgentType
from warmpass.cli.main import app
from warmpass.scheduling.base import (
    WarmupScheduleAlreadyExistsError,
    WarmupScheduleRegistrationError,
    WarmupScheduleRemovalError,
)
from warmpass.scheduling.macos.plist import build_label, build_plist_path
from warmpass.scheduling.macos.scheduler import MacOSLaunchdWarmupScheduler
from warmpass.scheduling.models import DailyTrigger, WarmupSchedule
from warmpass.scheduling.service import WarmupSchedulerService

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="Tests on macOS launchd scheduler"
)


@pytest.fixture
def scheduler_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[MacOSLaunchdWarmupScheduler, Mock]:
    def fake_home(cls: type[Path]) -> Path:
        return tmp_path

    monkeypatch.setattr(Path, "home", classmethod(fake_home))

    run_launchctl = Mock()
    monkeypatch.setattr(
        MacOSLaunchdWarmupScheduler,
        "_run_launchctl",
        run_launchctl,
    )

    scheduler = MacOSLaunchdWarmupScheduler(
        executable=Path(sys.executable).resolve(),
        executable_search_path="/usr/bin:/bin",
    )

    return scheduler, run_launchctl


@pytest.fixture
def daily_schedule() -> WarmupSchedule:
    return WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(at=time(23, 23)),
    )


def test_add_and_get_succeeds(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, run_launchctl = scheduler_setup
    scheduler.add(daily_schedule)

    plist_path = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)

    assert plist_path.is_file()
    assert scheduler.get(daily_schedule.id) == daily_schedule
    run_launchctl.assert_called_once_with(
        "bootstrap",
        f"gui/{os.getuid()}",
        str(plist_path),
    )


def test_remove_succeeds(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, run_launchctl = scheduler_setup

    scheduler.add(daily_schedule)

    plist_path = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)
    assert plist_path.is_file()

    run_launchctl.reset_mock()

    scheduler.remove(daily_schedule.id)

    assert not plist_path.exists()
    assert scheduler.get(daily_schedule.id) is None

    target = f"gui/{os.getuid()}/{build_label(daily_schedule.id)}"
    run_launchctl.assert_called_once_with(
        "bootout",
        target,
    )


def test_add_removes_plist_when_registration_fails(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, run_launchctl = scheduler_setup
    run_launchctl.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd="launchctl",
        stderr="Registration failed",
    )

    with pytest.raises(WarmupScheduleRegistrationError):
        scheduler.add(daily_schedule)

    plist_path = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)
    assert not plist_path.exists()
    assert scheduler.get(daily_schedule.id) is None


def test_remove_keeps_plist_when_launchctl_fails(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, run_launchctl = scheduler_setup
    scheduler.add(daily_schedule)

    plist_path = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)

    run_launchctl.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd="launchctl",
        stderr="Removal failed",
    )

    with pytest.raises(WarmupScheduleRemovalError):
        scheduler.remove(daily_schedule.id)

    assert plist_path.is_file()
    assert scheduler.get(daily_schedule.id) == daily_schedule


def test_add_rejects_existing_schedule(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, run_launchctl = scheduler_setup
    scheduler.add(daily_schedule)

    with pytest.raises(WarmupScheduleAlreadyExistsError):
        scheduler.add(daily_schedule)

    assert scheduler.get(daily_schedule.id) == daily_schedule
    run_launchctl.assert_called_once()


def test_list_schedules_succeeds(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
) -> None:
    scheduler, _ = scheduler_setup

    assert scheduler.get_list() == []

    first = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(at=time(23, 23)),
    )
    second = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.ANTIGRAVITY,
        trigger=DailyTrigger(at=time(22, 22)),
    )

    scheduler.add(first)
    scheduler.add(second)

    unrelated_file = scheduler._launch_agents_directory / "unrelated.plist"
    unrelated_file.write_text("Not a Warmpass schedule")

    schedules = scheduler.get_list()

    assert {schedule.id: schedule for schedule in schedules} == {
        first.id: first,
        second.id: second,
    }


def test_cli_add_creates_schedule(
    monkeypatch: pytest.MonkeyPatch,
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
) -> None:
    scheduler, _ = scheduler_setup
    service = WarmupSchedulerService(scheduler)

    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=service),
    )

    result = CliRunner().invoke(
        app,
        [
            "schedule",
            "add",
            "--agent",
            "codex",
            "--trigger",
            "daily",
            "--at",
            "23:23",
        ],
    )

    assert result.exit_code == 0, result.output

    schedules = scheduler.get_list()
    assert len(schedules) == 1
    assert schedules[0].agent == WarmupAgentType.CODEX
    assert schedules[0].trigger == DailyTrigger(at=time(23, 23))


@pytest.mark.parametrize("returncode", [3, 113])
def test_remove_cleans_up_when_service_is_already_missing(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
    returncode: int,
) -> None:
    scheduler, run_launchctl = scheduler_setup
    scheduler.add(daily_schedule)

    run_launchctl.side_effect = subprocess.CalledProcessError(
        returncode=returncode,
        cmd="launchctl",
    )

    scheduler.remove(daily_schedule.id)

    assert scheduler.get(daily_schedule.id) is None
