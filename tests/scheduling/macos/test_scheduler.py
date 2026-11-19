"""launchd scheduler adapter.

Files live under tmp_path. `launchctl` is faked at the one method that runs it
(`_run_launchctl`), plus two tests that run a real stand-in executable so the
adapter's own process handling is covered.
"""

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from warmpass.scheduling.base import SchedulingError
from warmpass.scheduling.macos.plist import build_label, build_plist_path
from warmpass.scheduling.macos.scheduler import MacOSLaunchdScheduler
from warmpass.scheduling.models import ScheduledTrigger, WeekDay

if sys.platform == "win32":
    pytest.skip("The launchd adapter uses os.getuid()", allow_module_level=True)

SCHEDULE_ID = UUID("e44215ce-26c9-41c4-96d7-67f0940496e4")
OTHER_ID = UUID("0a6f1d0e-3b0c-4a53-9d63-2f5d6f9a7b11")
ARGUMENTS = ["warmup", "--agent", "codex"]
TRIGGERS = [
    ScheduledTrigger(hour=9, minute=0, weekday=WeekDay.MONDAY),
    ScheduledTrigger(hour=11, minute=0, weekday=WeekDay.MONDAY),
]
DOMAIN = f"gui/{os.getuid()}"


def launchctl_list_output(*labels: str) -> str:
    rows = [
        "PID\tStatus\tLabel",
        "-\t0\tcom.apple.Finder",
        *(f"-\t0\t{label}" for label in labels),
    ]
    return "\n".join(rows) + "\n"


class FakeLaunchctl:
    """Records launchctl invocations; failures and output are keyed by subcommand."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failures: dict[str, BaseException] = {}
        self.outputs = {"list": launchctl_list_output()}

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        failure = self.failures.get(args[0])
        if failure is not None:
            raise failure
        return self.outputs.get(args[0], "")

    def targets(self, subcommand: str) -> list[str]:
        return [call[1] for call in self.calls if call[0] == subcommand]


def build_scheduler(
    tmp_path: Path, launchctl_executable: Path = Path("launchctl-is-faked")
) -> MacOSLaunchdScheduler:
    return MacOSLaunchdScheduler(
        warmpass_executable=Path("/opt/warmpass/bin/warmpass"),
        launchctl_executable=launchctl_executable,
        warmpass_executable_search_path="/opt/warmpass/bin:/usr/bin",
        log_directory=tmp_path / "logs",
        home=tmp_path / "home",
    )


@pytest.fixture
def launch_agents(tmp_path: Path) -> Path:
    return tmp_path / "home" / "Library" / "LaunchAgents"


@pytest.fixture
def launchctl(monkeypatch: pytest.MonkeyPatch) -> FakeLaunchctl:
    fake = FakeLaunchctl()
    monkeypatch.setattr(MacOSLaunchdScheduler, "_run_launchctl", fake)
    return fake


@pytest.fixture
def scheduler(tmp_path: Path, launchctl: FakeLaunchctl) -> MacOSLaunchdScheduler:
    return build_scheduler(tmp_path)


def plist_for(launch_agents: Path, schedule_id: UUID = SCHEDULE_ID) -> Path:
    return build_plist_path(launch_agents, schedule_id)


def write_plist(launch_agents: Path, schedule_id: UUID) -> Path:
    path = plist_for(launch_agents, schedule_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<plist/>", encoding="utf-8")
    return path


# --- register_job -------------------------------------------------------------


def test_register_writes_one_plist_and_bootstraps_it(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    launch_agents: Path,
    tmp_path: Path,
) -> None:
    scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)

    path = plist_for(launch_agents)
    plist = plistlib.loads(path.read_bytes())
    assert plist["Label"] == build_label(SCHEDULE_ID)
    assert plist["ProgramArguments"] == ["/opt/warmpass/bin/warmpass", *ARGUMENTS]
    assert plist["StartCalendarInterval"] == [
        {"Hour": 9, "Minute": 0, "Weekday": 1},
        {"Hour": 11, "Minute": 0, "Weekday": 1},
    ]
    assert launchctl.calls == [("bootstrap", DOMAIN, str(path))]
    assert (tmp_path / "logs").is_dir()
    assert [p.name for p in launch_agents.iterdir()] == [path.name]


def test_register_refuses_an_existing_plist_and_leaves_it_alone(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl, launch_agents: Path
) -> None:
    existing = write_plist(launch_agents, SCHEDULE_ID)

    with pytest.raises(
        SchedulingError, match="LaunchAgent plist already exists"
    ) as exc_info:
        scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)

    assert str(existing) in str(exc_info.value)
    assert existing.read_text(encoding="utf-8") == "<plist/>"
    assert launchctl.calls == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(
            subprocess.CalledProcessError(1, "launchctl", stderr="denied"),
            f"Could not register schedule {SCHEDULE_ID} with launchd: denied",
            id="rejected",
        ),
        pytest.param(
            OSError("no such file"),
            f"Could not register schedule {SCHEDULE_ID} with launchd: no such file",
            id="cannot-run",
        ),
        pytest.param(
            subprocess.TimeoutExpired("launchctl", 30),
            f"Registration of schedule {SCHEDULE_ID} timed out.",
            id="timeout",
        ),
    ],
)
def test_register_failure_reports_the_error_and_keeps_the_plist(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    launch_agents: Path,
    error: BaseException,
    message: str,
) -> None:
    launchctl.failures["bootstrap"] = error

    with pytest.raises(SchedulingError) as exc_info:
        scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)

    assert str(exc_info.value) == message
    assert plist_for(launch_agents).is_file()


def test_register_reports_a_plist_that_cannot_be_written_and_never_runs_launchctl(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl, tmp_path: Path
) -> None:
    (tmp_path / "home" / "Library").mkdir(parents=True)
    (tmp_path / "home" / "Library" / "LaunchAgents").write_text("", encoding="utf-8")

    with pytest.raises(SchedulingError, match="Could not create plist"):
        scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)

    assert launchctl.calls == []


# --- unregister_job -----------------------------------------------------------


def test_unregister_boots_the_job_out_and_removes_its_plist(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl, launch_agents: Path
) -> None:
    path = write_plist(launch_agents, SCHEDULE_ID)

    scheduler.unregister_job(SCHEDULE_ID)

    assert launchctl.calls == [("bootout", f"{DOMAIN}/{build_label(SCHEDULE_ID)}")]
    assert not path.exists()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(
            subprocess.CalledProcessError(1, "launchctl", stderr="denied"),
            f"Could not unload schedule {SCHEDULE_ID}: denied.",
            id="rejected",
        ),
        pytest.param(
            OSError("no such file"),
            f"Could not run launchctl for schedule {SCHEDULE_ID}: no such file.",
            id="cannot-run",
        ),
        pytest.param(
            subprocess.TimeoutExpired("launchctl", 30),
            f"Removing schedule {SCHEDULE_ID} timed out.",
            id="timeout",
        ),
    ],
)
def test_unregister_failure_keeps_the_plist(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    launch_agents: Path,
    error: BaseException,
    message: str,
) -> None:
    path = write_plist(launch_agents, SCHEDULE_ID)
    launchctl.failures["bootout"] = error

    with pytest.raises(SchedulingError) as exc_info:
        scheduler.unregister_job(SCHEDULE_ID)

    assert str(exc_info.value) == message
    assert path.exists()


# --- get_job ------------------------------------------------------------------


def test_get_job_is_none_when_neither_the_plist_nor_loaded_job_exists(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl
) -> None:
    assert scheduler.get_job(SCHEDULE_ID) is None
    assert launchctl.calls == [("print", DOMAIN), ("list",)]


def test_get_job_reports_loaded_job_with_a_missing_plist(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    launch_agents: Path,
) -> None:
    launchctl.outputs["list"] = launchctl_list_output(build_label(SCHEDULE_ID))

    with pytest.raises(
        SchedulingError, match="is loaded in launchd, but its plist is missing"
    ) as exc_info:
        scheduler.get_job(SCHEDULE_ID)

    assert str(SCHEDULE_ID) in str(exc_info.value)
    assert not plist_for(launch_agents).exists()


def test_get_job_returns_what_was_registered_after_checking_it_is_loaded(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl
) -> None:
    scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)
    launchctl.calls.clear()

    job = scheduler.get_job(SCHEDULE_ID)

    assert job is not None
    assert job.schedule_id == SCHEDULE_ID
    assert job.command == ["/opt/warmpass/bin/warmpass", *ARGUMENTS]
    assert job.triggers == TRIGGERS
    assert launchctl.calls == [("print", f"{DOMAIN}/{build_label(SCHEDULE_ID)}")]


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(
            subprocess.CalledProcessError(113, "launchctl", stderr="not found"),
            "Cannot verify that schedule",
            id="not-loaded",
        ),
        pytest.param(
            subprocess.TimeoutExpired("launchctl", 30), "timed out", id="timeout"
        ),
        pytest.param(OSError("no such file"), "Cannot run launchctl", id="cannot-run"),
    ],
)
def test_get_job_reports_a_plist_it_cannot_confirm_is_loaded(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    error: BaseException,
    message: str,
) -> None:
    scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)
    launchctl.failures["print"] = error

    with pytest.raises(SchedulingError, match=message):
        scheduler.get_job(SCHEDULE_ID)


def test_get_job_reports_a_corrupt_plist_and_leaves_it_untouched(
    scheduler: MacOSLaunchdScheduler, launch_agents: Path
) -> None:
    path = write_plist(launch_agents, SCHEDULE_ID)
    path.write_bytes(b"not a plist")

    with pytest.raises(SchedulingError, match="Invalid plist"):
        scheduler.get_job(SCHEDULE_ID)

    assert path.read_bytes() == b"not a plist"


def test_get_job_reports_an_unreadable_plist(
    scheduler: MacOSLaunchdScheduler, launch_agents: Path
) -> None:
    plist_for(launch_agents).mkdir(parents=True)

    with pytest.raises(SchedulingError, match="Cannot read plist"):
        scheduler.get_job(SCHEDULE_ID)


def test_get_job_rejects_a_plist_whose_label_belongs_to_another_schedule(
    scheduler: MacOSLaunchdScheduler, launch_agents: Path
) -> None:
    scheduler.register_job(OTHER_ID, arguments=ARGUMENTS, triggers=TRIGGERS)
    plist_for(launch_agents).write_bytes(
        plist_for(launch_agents, OTHER_ID).read_bytes()
    )

    with pytest.raises(SchedulingError, match="does not match its filename"):
        scheduler.get_job(SCHEDULE_ID)


# --- list_job_ids -------------------------------------------------------------


def test_list_job_ids_is_empty_when_no_plists_or_loaded_jobs_exist(
    scheduler: MacOSLaunchdScheduler,
) -> None:
    assert scheduler.list_job_ids() == set()


def test_list_job_ids_includes_loaded_jobs_without_a_launch_agents_directory(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl
) -> None:
    launchctl.outputs["list"] = launchctl_list_output(build_label(SCHEDULE_ID))

    assert scheduler.list_job_ids() == {SCHEDULE_ID}


def test_list_job_ids_combines_warmpass_plists_and_loaded_jobs(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    launch_agents: Path,
) -> None:
    write_plist(launch_agents, SCHEDULE_ID)
    (launch_agents / "com.example.unrelated.plist").write_text("", encoding="utf-8")
    (launch_agents / ".DS_Store").write_text("", encoding="utf-8")
    launchctl.outputs["list"] = launchctl_list_output(build_label(OTHER_ID))

    assert scheduler.list_job_ids() == {SCHEDULE_ID, OTHER_ID}


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("dev.warmpass.schedule.not-a-uuid.plist", id="not-a-uuid"),
        pytest.param(
            f"dev.warmpass.schedule.{str(SCHEDULE_ID).upper()}.plist", id="upper-case"
        ),
    ],
)
def test_list_job_ids_rejects_malformed_warmpass_filenames(
    scheduler: MacOSLaunchdScheduler, launch_agents: Path, name: str
) -> None:
    launch_agents.mkdir(parents=True)
    (launch_agents / name).write_text("", encoding="utf-8")

    with pytest.raises(SchedulingError, match="Invalid schedule plist filename"):
        scheduler.list_job_ids()


def test_list_job_ids_rejects_a_noncanonical_loaded_label(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl
) -> None:
    label = f"dev.warmpass.schedule.{str(SCHEDULE_ID).upper()}"
    launchctl.outputs["list"] = launchctl_list_output(label)

    with pytest.raises(
        SchedulingError, match="Invalid loaded schedule label"
    ) as exc_info:
        scheduler.list_job_ids()

    assert label in str(exc_info.value)


# --- clear_jobs ---------------------------------------------------------------


def test_clear_only_touches_jobs_and_plists_with_the_warmpass_prefix(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl, launch_agents: Path
) -> None:
    owned = write_plist(launch_agents, SCHEDULE_ID)
    unrelated = launch_agents / "com.example.unrelated.plist"
    unrelated.write_text("", encoding="utf-8")
    loaded_without_plist = build_label(OTHER_ID)
    launchctl.outputs["list"] = launchctl_list_output(
        build_label(SCHEDULE_ID), loaded_without_plist, loaded_without_plist
    )

    scheduler.clear_jobs()

    assert sorted(launchctl.targets("bootout")) == sorted(
        [
            f"{DOMAIN}/{build_label(SCHEDULE_ID)}",
            f"{DOMAIN}/{loaded_without_plist}",
        ]
    )
    assert not owned.exists()
    assert unrelated.exists()


@pytest.mark.parametrize(
    "output",
    [
        pytest.param("", id="empty"),
        pytest.param("unexpected\n", id="wrong-header"),
        pytest.param("PID\tStatus\tLabel\n-\t0\n", id="malformed-row"),
    ],
)
def test_clear_refuses_to_act_on_unexpected_launchctl_output(
    scheduler: MacOSLaunchdScheduler,
    launchctl: FakeLaunchctl,
    launch_agents: Path,
    output: str,
) -> None:
    path = write_plist(launch_agents, SCHEDULE_ID)
    launchctl.outputs["list"] = output

    with pytest.raises(SchedulingError, match="Unexpected launchctl list output"):
        scheduler.clear_jobs()

    assert launchctl.targets("bootout") == []
    assert path.exists()


def test_clear_removes_no_files_when_discovery_fails(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl, launch_agents: Path
) -> None:
    path = write_plist(launch_agents, SCHEDULE_ID)
    launchctl.failures["print"] = subprocess.TimeoutExpired("launchctl", 30)

    with pytest.raises(SchedulingError, match="Cannot discover loaded schedules"):
        scheduler.clear_jobs()

    assert launchctl.targets("bootout") == []
    assert path.exists()


def test_clear_removes_no_files_when_a_job_cannot_be_unloaded(
    scheduler: MacOSLaunchdScheduler, launchctl: FakeLaunchctl, launch_agents: Path
) -> None:
    path = write_plist(launch_agents, SCHEDULE_ID)
    launchctl.outputs["list"] = launchctl_list_output(build_label(SCHEDULE_ID))
    launchctl.failures["bootout"] = subprocess.CalledProcessError(
        1, "launchctl", stderr="denied"
    )

    with pytest.raises(
        SchedulingError, match="Could not clear all launchd jobs"
    ) as exc_info:
        scheduler.clear_jobs()

    assert f"Cannot unload {build_label(SCHEDULE_ID)}: denied" in str(exc_info.value)
    assert path.exists()


# --- the adapter's own process handling, against a stand-in launchctl ---------


def write_stand_in_launchctl(tmp_path: Path, *, exit_status: int, stderr: str) -> Path:
    script = tmp_path / "launchctl"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > '{tmp_path / 'launchctl.args'}'\n"
        f"echo '{stderr}' >&2\n"
        f"exit {exit_status}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_stand_in_launchctl_receives_the_bootout_target_and_success_removes_the_plist(
    tmp_path: Path, launch_agents: Path
) -> None:
    scheduler = build_scheduler(
        tmp_path, write_stand_in_launchctl(tmp_path, exit_status=0, stderr="")
    )
    path = write_plist(launch_agents, SCHEDULE_ID)

    scheduler.unregister_job(SCHEDULE_ID)

    arguments = (tmp_path / "launchctl.args").read_text(encoding="utf-8").split()
    assert arguments == ["bootout", f"{DOMAIN}/{build_label(SCHEDULE_ID)}"]
    assert not path.exists()


def test_stand_in_launchctl_failure_surfaces_its_stderr_and_keeps_the_plist(
    tmp_path: Path, launch_agents: Path
) -> None:
    scheduler = build_scheduler(
        tmp_path,
        write_stand_in_launchctl(tmp_path, exit_status=3, stderr="no such service"),
    )
    path = write_plist(launch_agents, SCHEDULE_ID)

    with pytest.raises(SchedulingError, match="no such service"):
        scheduler.unregister_job(SCHEDULE_ID)

    assert path.exists()
