from datetime import time
from pathlib import Path
from uuid import uuid4

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.macos.plist import PlistConfiguration
from warmpass.scheduling.models import DailyTrigger, WarmupSchedule


def test_daily_schedule_creates_calender_interval() -> None:
    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.CODEX,
        trigger=DailyTrigger(at=time(23, 23)),
    )

    configuration = PlistConfiguration.from_schedule(
        schedule=schedule,
        program_arguments=["warmup", "--agent", "codex"],
        executable=Path("/usr/local/bin/warmpass"),
        home=Path("/home/test-user"),
        log_directory=Path("/home/test-user/logs"),
        executable_search_path="/usr/local/bin:/usr/bin",
    )

    assert configuration.StartCalendarInterval == {
        "Hour": 23,
        "Minute": 23,
    }
