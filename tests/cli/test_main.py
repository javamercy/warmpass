import pytest
from typer.testing import CliRunner

from tests.support.fakes import FakeAgentProcess, FakeOSJobScheduler
from warmpass.cli.main import app

runner = CliRunner()


@pytest.mark.parametrize(
    "command",
    [
        pytest.param([], id="root"),
        pytest.param(["warmup"], id="warmup"),
        pytest.param(["schedule"], id="schedule"),
        pytest.param(["schedule", "add"], id="schedule-add"),
        pytest.param(["schedule", "remove"], id="schedule-remove"),
        pytest.param(["schedule", "clear"], id="schedule-clear"),
        pytest.param(["schedule", "get"], id="schedule-get"),
        pytest.param(["schedule", "list"], id="schedule-list"),
    ],
)
@pytest.mark.usefixtures("cli_service")
def test_help_exits_zero_without_side_effects(
    command: list[str],
    agent_process: FakeAgentProcess,
    fake_scheduler: FakeOSJobScheduler,
) -> None:
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert agent_process.calls == []
    assert fake_scheduler.calls == []
