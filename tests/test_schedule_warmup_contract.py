"""The contract between `schedule` and `warmup`.

Installed OS jobs run `warmpass <arguments>` using whatever arguments `schedule`
registered. If `warmup` renames or drops an option, existing jobs fail silently
at the scheduled time. This test builds the arguments `schedule` registers and
runs them through the real app.
"""

from datetime import time

import pytest
from typer.testing import CliRunner

from tests.support.fakes import FakeAgentProcess, FakeOSJobScheduler
from warmpass.agents.models import AgentType
from warmpass.cli.main import app
from warmpass.scheduling.models import DailyTrigger, HourlyWindow
from warmpass.scheduling.service import SchedulerService


@pytest.mark.parametrize("agent", list(AgentType))
@pytest.mark.parametrize(
    ("model", "model_arguments"),
    [
        pytest.param(None, [], id="agent-default"),
        pytest.param("custom-model", ["--model", "custom-model"], id="selected-model"),
    ],
)
def test_registered_job_arguments_run_as_a_warmup(
    agent: AgentType,
    model: str | None,
    model_arguments: list[str],
    scheduler_service: SchedulerService,
    fake_scheduler: FakeOSJobScheduler,
    agent_process: FakeAgentProcess,
) -> None:
    scheduler_service.add(
        agent=agent,
        trigger=DailyTrigger(window=HourlyWindow(from_=time(9), every=2)),
        model=model,
    )
    (job,) = fake_scheduler.jobs.values()
    arguments_without_executable = job.command[1:]

    assert arguments_without_executable == [
        "warmup",
        "--agent",
        agent.value,
        *model_arguments,
    ]

    result = CliRunner().invoke(app, arguments_without_executable, input="")

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    (call,) = agent_process.calls
    assert call.command.count("--model") == model_arguments.count("--model")
    if model_arguments:
        assert call.command[-2:] == model_arguments
