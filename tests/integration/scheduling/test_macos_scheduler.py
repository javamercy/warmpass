import os
import plistlib
import subprocess
import sys
from datetime import time
from pathlib import Path
from unittest.mock import Mock, call
from uuid import uuid4

import pytest
from typer.testing import CliRunner

import warmpass.cli.schedule as schedule_module
from warmpass.agents.models import AgentType
from warmpass.cli.main import app
from warmpass.scheduling.base import WarmupSchedulerError
from warmpass.scheduling.macos.plist import LABEL_PREFIX, build_label, build_plist_path
from warmpass.scheduling.macos.scheduler import MacOSLaunchdWarmupScheduler
from warmpass.scheduling.models import DailyTrigger, HourlyWindow, WarmupSchedule
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
    run_launchctl = Mock(return_value="")
    monkeypatch.setattr(MacOSLaunchdWarmupScheduler, "_run_launchctl", run_launchctl)
    scheduler = MacOSLaunchdWarmupScheduler(
        executable=Path(sys.executable).resolve(),
        executable_search_path="/usr/bin:/bin",
    )
    return scheduler, run_launchctl


@pytest.fixture
def daily_schedule() -> WarmupSchedule:
    return WarmupSchedule(
        id=uuid4(),
        agent=AgentType.CODEX,
        trigger=DailyTrigger(
            window=HourlyWindow(from_=time(9), until=time(12, 30), every=2)
        ),
    )


def test_add_and_get_round_trip(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler.add(daily_schedule)
    plist = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)
    record = scheduler._store_directory / f"{daily_schedule.id}.json"
    assert plist.is_file() and record.is_file()
    assert scheduler.get(daily_schedule.id) == daily_schedule
    assert launchctl.call_args_list == [
        call("bootstrap", f"gui/{os.getuid()}", str(plist)),
        call("print", f"gui/{os.getuid()}/{build_label(daily_schedule.id)}"),
    ]


def test_remove_succeeds(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler.add(daily_schedule)
    launchctl.reset_mock()
    scheduler.remove(daily_schedule.id)
    assert scheduler.get(daily_schedule.id) is None
    assert not (scheduler._store_directory / f"{daily_schedule.id}.json").exists()
    target = f"gui/{os.getuid()}/{build_label(daily_schedule.id)}"
    assert launchctl.call_args_list == [call("print", target), call("bootout", target)]


@pytest.mark.parametrize("failure", ["timeout", "failed"])
def test_add_retains_files_when_bootstrap_fails(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
    failure: str,
) -> None:
    scheduler, launchctl = scheduler_setup
    launchctl.side_effect = (
        subprocess.TimeoutExpired("launchctl", 300)
        if failure == "timeout"
        else subprocess.CalledProcessError(1, "launchctl", stderr="failed")
    )
    with pytest.raises(WarmupSchedulerError, match="retained"):
        scheduler.add(daily_schedule)
    assert build_plist_path(
        scheduler._launch_agents_directory, daily_schedule.id
    ).exists()
    assert (scheduler._store_directory / f"{daily_schedule.id}.json").exists()


def test_add_rejects_existing_schedule(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler.add(daily_schedule)
    with pytest.raises(WarmupSchedulerError, match="already exists"):
        scheduler.add(daily_schedule)
    launchctl.assert_called_once()


@pytest.mark.parametrize("failure", ["timeout", "failed", "unloaded"])
def test_remove_retains_files_on_unload_failure(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
    failure: str,
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler.add(daily_schedule)
    error = (
        subprocess.TimeoutExpired("launchctl", 300)
        if failure == "timeout"
        else subprocess.CalledProcessError(113, "launchctl", stderr="not loaded")
    )
    launchctl.side_effect = [error] if failure == "unloaded" else ["", error]
    with pytest.raises(WarmupSchedulerError):
        scheduler.remove(daily_schedule.id)
    assert build_plist_path(
        scheduler._launch_agents_directory, daily_schedule.id
    ).exists()
    assert (scheduler._store_directory / f"{daily_schedule.id}.json").exists()


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("missing-record", "no saved schedule record"),
        ("invalid-record", "Cannot read saved schedule"),
        ("missing-plist", "plist is missing"),
        ("invalid-plist", "Invalid plist"),
        ("wrong-label", "does not match"),
        ("unloaded", "Cannot verify"),
    ],
)
def test_get_rejects_inconsistent_state(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
    damage: str,
    message: str,
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler.add(daily_schedule)
    record = scheduler._store_directory / f"{daily_schedule.id}.json"
    plist = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)
    if damage == "missing-record":
        record.unlink()
    elif damage == "invalid-record":
        record.write_text("not json", encoding="utf-8")
    elif damage == "missing-plist":
        plist.unlink()
    elif damage == "invalid-plist":
        plist.write_bytes(b"not a plist")
    elif damage == "wrong-label":
        data = plistlib.loads(plist.read_bytes())
        data["Label"] = "other.label"
        plist.write_bytes(plistlib.dumps(data))
    else:
        launchctl.side_effect = subprocess.CalledProcessError(113, "launchctl")
    with pytest.raises(WarmupSchedulerError, match=message):
        scheduler.get(daily_schedule.id)


def test_edited_plist_is_not_compared_to_record(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, _ = scheduler_setup
    scheduler.add(daily_schedule)
    plist = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)
    data = plistlib.loads(plist.read_bytes())
    data["StartCalendarInterval"] = [{"Hour": 17, "Minute": 0}]
    plist.write_bytes(plistlib.dumps(data))
    assert scheduler.get(daily_schedule.id) == daily_schedule


def test_list_schedules_and_orphans(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, _ = scheduler_setup
    assert scheduler.get_list() == []
    scheduler.add(daily_schedule)
    assert scheduler.get_list() == [daily_schedule]
    orphan = scheduler._store_directory / f"{uuid4()}.json"
    orphan.write_text(daily_schedule.model_dump_json(), encoding="utf-8")
    with pytest.raises(WarmupSchedulerError, match="mismatch"):
        scheduler.get_list()


def test_clear_invalid_unloaded_and_loaded_only_jobs(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler._store_directory.mkdir(parents=True)
    scheduler._launch_agents_directory.mkdir(parents=True)
    present, unloaded, orphan = (str(uuid4()) for _ in range(3))
    record = scheduler._store_directory / f"{present}.json"
    invalid = scheduler._store_directory / "invalid.json"
    plist = scheduler._launch_agents_directory / f"{LABEL_PREFIX}{present}.plist"
    unloaded_plist = (
        scheduler._launch_agents_directory / f"{LABEL_PREFIX}{unloaded}.plist"
    )
    unrelated = scheduler._launch_agents_directory / "unrelated.plist"
    for path in (record, invalid, plist, unloaded_plist, unrelated):
        path.write_text("invalid", encoding="utf-8")
    loaded = {f"{LABEL_PREFIX}{present}", f"{LABEL_PREFIX}{orphan}"}

    def run(*args: str) -> str:
        if args == ("list",):
            return "PID\tStatus\tLabel\n" + "".join(
                f"-\t0\t{label}\n" for label in sorted(loaded)
            )
        if (
            args[0] == "print"
            and args[1].count("/") == 2
            and args[1].rsplit("/", 1)[1] not in loaded
        ):
            raise subprocess.CalledProcessError(113, "launchctl")
        if args[0] == "bootout":
            loaded.remove(args[1].rsplit("/", 1)[1])
        return ""

    launchctl.side_effect = run
    scheduler.clear()
    assert not loaded
    assert not any(path.exists() for path in (record, invalid, plist, unloaded_plist))
    assert unrelated.exists()
    launchctl.assert_any_call("bootout", f"gui/{os.getuid()}/{LABEL_PREFIX}{orphan}")


def test_clear_preserves_files_if_unload_times_out(
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
    daily_schedule: WarmupSchedule,
) -> None:
    scheduler, launchctl = scheduler_setup
    scheduler.add(daily_schedule)
    record = scheduler._store_directory / f"{daily_schedule.id}.json"
    plist = build_plist_path(scheduler._launch_agents_directory, daily_schedule.id)

    def run(*args: str) -> str:
        if args == ("list",):
            return f"PID\tStatus\tLabel\n-\t0\t{build_label(daily_schedule.id)}\n"
        if args[0] == "bootout":
            raise subprocess.TimeoutExpired("launchctl", 300)
        return ""

    launchctl.side_effect = run
    with pytest.raises(WarmupSchedulerError, match="no schedule files were removed"):
        scheduler.clear()
    assert record.exists() and plist.exists()


def test_cli_add_creates_schedule(
    monkeypatch: pytest.MonkeyPatch,
    scheduler_setup: tuple[MacOSLaunchdWarmupScheduler, Mock],
) -> None:
    scheduler, _ = scheduler_setup
    monkeypatch.setattr(
        schedule_module,
        "create_warmup_scheduler_service",
        Mock(return_value=WarmupSchedulerService(scheduler)),
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
            "--from",
            "09:00",
            "--until",
            "12:30",
            "--every",
            "2h",
        ],
    )
    assert result.exit_code == 0, result.output
    schedules = scheduler.get_list()
    assert len(schedules) == 1
    assert schedules[0].trigger == DailyTrigger(
        window=HourlyWindow(from_=time(9), until=time(12, 30), every=2)
    )
