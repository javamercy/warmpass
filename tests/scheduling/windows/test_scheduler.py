"""Windows Task Scheduler adapter, with `schtasks` faked at the one method that runs it.

The adapter has no POSIX-only code, so these tests run on every OS.
"""

import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from warmpass.scheduling.base import SchedulingError
from warmpass.scheduling.models import ScheduledTrigger, WeekDay
from warmpass.scheduling.windows.scheduler import WindowsTaskScheduler
from warmpass.scheduling.windows.task_xml import build_task_name, parse_task_xml

SCHEDULE_ID = UUID("e44215ce-26c9-41c4-96d7-67f0940496e4")
OTHER_ID = UUID("0a6f1d0e-3b0c-4a53-9d63-2f5d6f9a7b11")
ARGUMENTS = ["warmup", "--agent", "codex"]
TRIGGERS = [
    ScheduledTrigger(hour=9, minute=0, weekday=WeekDay.MONDAY),
    ScheduledTrigger(hour=11, minute=0, weekday=WeekDay.MONDAY),
]


class FakeSchtasks:
    """Records schtasks invocations. Failures and output are keyed by operation:
    `create`, `delete`, `query_xml` (one task), or `list` (all tasks)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failures: dict[str, BaseException] = {}
        self.outputs: dict[str, str] = {}
        self.created_xml: bytes | None = None
        self.created_xml_path: Path | None = None

    def __call__(self, *args: str) -> str:
        self.calls.append(args)
        operation = self._operation(args)
        if operation == "create":
            self.created_xml_path = Path(args[args.index("/xml") + 1])
            self.created_xml = self.created_xml_path.read_bytes()
        failure = self.failures.get(operation)
        if failure is not None:
            raise failure
        return self.outputs.get(operation, "")

    def deleted_names(self) -> list[str]:
        return [call[2] for call in self.calls if call[0] == "/delete"]

    @staticmethod
    def _operation(args: tuple[str, ...]) -> str:
        match args[0]:
            case "/create":
                return "create"
            case "/delete":
                return "delete"
            case "/query":
                return "query_xml" if "/xml" in args else "list"
            case _:
                raise AssertionError(f"Unexpected schtasks arguments: {args}")


@pytest.fixture
def schtasks(monkeypatch: pytest.MonkeyPatch) -> FakeSchtasks:
    fake = FakeSchtasks()
    monkeypatch.setattr(WindowsTaskScheduler, "_run_schtasks", fake)
    return fake


@pytest.fixture
def scheduler(tmp_path: Path, schtasks: FakeSchtasks) -> WindowsTaskScheduler:
    return WindowsTaskScheduler(
        warmpass_executable=Path("/opt/warmpass/warmpass.exe"),
        schtasks_executable=Path("schtasks-is-faked"),
        user_id="DOMAIN\\user",
        home=tmp_path / "home",
    )


def task_list(*names: str) -> str:
    return "".join(f'"{name}","N/A","Ready"\n' for name in names)


# --- register_job -------------------------------------------------------------


def test_register_creates_one_task_from_a_temporary_xml_file_and_removes_the_file(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)

    (call,) = schtasks.calls
    assert call[:4] == ("/create", "/tn", build_task_name(SCHEDULE_ID), "/xml")
    assert schtasks.created_xml is not None
    job = parse_task_xml(SCHEDULE_ID, schtasks.created_xml)
    assert job.command[1:] == ARGUMENTS
    assert job.triggers == TRIGGERS
    assert schtasks.created_xml_path is not None
    assert not schtasks.created_xml_path.exists()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(
            subprocess.CalledProcessError(1, "schtasks", stderr="Access is denied"),
            "Access is denied",
            id="rejected",
        ),
        pytest.param(
            OSError("no such file"), "Could not run schtasks", id="cannot-run"
        ),
        pytest.param(
            subprocess.TimeoutExpired("schtasks", 30),
            "may have been registered",
            id="timeout-is-unknown-outcome",
        ),
    ],
)
def test_register_failure_keeps_the_record_and_removes_the_temporary_file(
    scheduler: WindowsTaskScheduler,
    schtasks: FakeSchtasks,
    error: BaseException,
    message: str,
) -> None:
    schtasks.failures["create"] = error

    with pytest.raises(SchedulingError, match=message) as exc_info:
        scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)

    assert "record was retained" in str(exc_info.value)
    assert schtasks.created_xml_path is not None
    assert not schtasks.created_xml_path.exists()


# --- unregister_job -----------------------------------------------------------


def test_unregister_deletes_the_task_by_name(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    scheduler.unregister_job(SCHEDULE_ID)

    assert schtasks.calls == [("/delete", "/tn", build_task_name(SCHEDULE_ID), "/f")]


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(
            subprocess.CalledProcessError(1, "schtasks", stderr="denied"), id="rejected"
        ),
        pytest.param(OSError("no such file"), id="cannot-run"),
        pytest.param(subprocess.TimeoutExpired("schtasks", 30), id="timeout"),
    ],
)
def test_unregister_failure_says_the_record_was_retained(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks, error: BaseException
) -> None:
    schtasks.failures["delete"] = error

    with pytest.raises(SchedulingError, match="record was retained"):
        scheduler.unregister_job(SCHEDULE_ID)


# --- get_job ------------------------------------------------------------------


def test_get_job_returns_the_registered_task(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    scheduler.register_job(SCHEDULE_ID, arguments=ARGUMENTS, triggers=TRIGGERS)
    assert schtasks.created_xml is not None
    schtasks.outputs["query_xml"] = schtasks.created_xml.decode("utf-16")

    job = scheduler.get_job(SCHEDULE_ID)

    assert job is not None
    assert job.command[1:] == ARGUMENTS
    assert job.triggers == TRIGGERS


def test_get_job_is_none_when_the_query_fails_and_the_task_is_not_listed(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.failures["query_xml"] = subprocess.CalledProcessError(1, "schtasks")
    schtasks.outputs["list"] = task_list(r"\Microsoft\Windows\Defrag")

    assert scheduler.get_job(SCHEDULE_ID) is None


def test_get_job_reports_a_task_that_is_listed_but_cannot_be_queried(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.failures["query_xml"] = subprocess.CalledProcessError(
        1, "schtasks", stderr="Access is denied"
    )
    schtasks.outputs["list"] = task_list("\\" + build_task_name(SCHEDULE_ID))

    with pytest.raises(SchedulingError, match="Cannot verify Windows task"):
        scheduler.get_job(SCHEDULE_ID)


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(
            subprocess.TimeoutExpired("schtasks", 30), "timed out", id="timeout"
        ),
        pytest.param(
            OSError("no such file"), "Could not run schtasks", id="cannot-run"
        ),
    ],
)
def test_get_job_does_not_treat_an_unavailable_scheduler_as_a_missing_task(
    scheduler: WindowsTaskScheduler,
    schtasks: FakeSchtasks,
    error: BaseException,
    message: str,
) -> None:
    schtasks.failures["query_xml"] = error

    with pytest.raises(SchedulingError, match=message):
        scheduler.get_job(SCHEDULE_ID)


def test_get_job_reports_xml_it_cannot_parse(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.outputs["query_xml"] = "<Task"

    with pytest.raises(SchedulingError, match="Invalid task XML"):
        scheduler.get_job(SCHEDULE_ID)


# --- list_job_ids -------------------------------------------------------------


def test_list_job_ids_returns_only_warmpass_tasks(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.outputs["list"] = task_list(
        "\\" + build_task_name(SCHEDULE_ID),
        r"\Microsoft\Windows\Defrag\ScheduledDefrag",
        build_task_name(OTHER_ID),
    )

    assert scheduler.list_job_ids() == {SCHEDULE_ID, OTHER_ID}


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("dev.warmpass.schedule.not-a-uuid", id="not-a-uuid"),
        pytest.param(
            f"dev.warmpass.schedule.{str(SCHEDULE_ID).upper()}", id="upper-case"
        ),
    ],
)
def test_list_job_ids_rejects_malformed_warmpass_task_names(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks, name: str
) -> None:
    schtasks.outputs["list"] = task_list("\\" + name)

    with pytest.raises(SchedulingError, match="Invalid Windows task name"):
        scheduler.list_job_ids()


def test_list_job_ids_reports_a_failed_listing(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.failures["list"] = subprocess.TimeoutExpired("schtasks", 30)

    with pytest.raises(SchedulingError, match="timed out"):
        scheduler.list_job_ids()


# --- clear_jobs ---------------------------------------------------------------


def test_clear_deletes_only_warmpass_tasks(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.outputs["list"] = task_list(
        "\\" + build_task_name(SCHEDULE_ID),
        r"\Microsoft\Windows\Defrag\ScheduledDefrag",
        "\\" + build_task_name(OTHER_ID),
    )

    scheduler.clear_jobs()

    assert sorted(schtasks.deleted_names()) == sorted(
        [build_task_name(SCHEDULE_ID), build_task_name(OTHER_ID)]
    )


def test_clear_attempts_every_task_and_reports_the_ones_that_failed(
    scheduler: WindowsTaskScheduler, schtasks: FakeSchtasks
) -> None:
    schtasks.outputs["list"] = task_list(
        "\\" + build_task_name(SCHEDULE_ID), "\\" + build_task_name(OTHER_ID)
    )
    schtasks.failures["delete"] = subprocess.CalledProcessError(
        1, "schtasks", stderr="denied"
    )

    with pytest.raises(SchedulingError, match="Could not clear all") as exc_info:
        scheduler.clear_jobs()

    assert len(schtasks.deleted_names()) == 2
    assert build_task_name(SCHEDULE_ID) in str(exc_info.value)
    assert build_task_name(OTHER_ID) in str(exc_info.value)


# --- the adapter's own process handling, against a stand-in schtasks ---------


def write_stand_in_schtasks(tmp_path: Path, *, exit_status: int, stderr: str) -> Path:
    args_file = tmp_path / "schtasks.args"
    body = (
        "import pathlib, sys\n"
        f"pathlib.Path({str(args_file)!r}).write_text("
        "'\\n'.join(sys.argv[1:]), encoding='utf-8')\n"
        f"sys.stderr.write({stderr!r})\n"
        f"raise SystemExit({exit_status})\n"
    )
    if sys.platform == "win32":
        script_py = tmp_path / "schtasks_stand_in.py"
        script_py.write_text(body, encoding="utf-8")
        wrapper = tmp_path / "schtasks.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script_py}" %*\n', encoding="utf-8")
        return wrapper

    script = tmp_path / "schtasks"
    script.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    script.chmod(0o755)
    return script


def test_stand_in_schtasks_receives_the_delete_arguments(tmp_path: Path) -> None:
    scheduler = WindowsTaskScheduler(
        warmpass_executable=Path("/opt/warmpass/warmpass.exe"),
        schtasks_executable=write_stand_in_schtasks(tmp_path, exit_status=0, stderr=""),
        user_id="DOMAIN\\user",
        home=tmp_path / "home",
    )

    scheduler.unregister_job(SCHEDULE_ID)

    arguments = (tmp_path / "schtasks.args").read_text(encoding="utf-8").splitlines()
    assert arguments == ["/delete", "/tn", build_task_name(SCHEDULE_ID), "/f"]


def test_stand_in_schtasks_failure_surfaces_its_stderr(tmp_path: Path) -> None:
    scheduler = WindowsTaskScheduler(
        warmpass_executable=Path("/opt/warmpass/warmpass.exe"),
        schtasks_executable=write_stand_in_schtasks(
            tmp_path, exit_status=1, stderr="Access is denied"
        ),
        user_id="DOMAIN\\user",
        home=tmp_path / "home",
    )

    with pytest.raises(SchedulingError, match="Access is denied"):
        scheduler.unregister_job(SCHEDULE_ID)
