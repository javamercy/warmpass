import os
import sys
from datetime import time
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from warmpass.agents.models import WarmupAgentType
from warmpass.scheduling.macos.plist import build_plist_path
from warmpass.scheduling.macos.scheduler import MacOSLaunchdWarmupScheduler
from warmpass.scheduling.models import DailyTrigger, WarmupSchedule

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Tests on macOS launchd scheduler",
)


def test_add_and_get_schedule_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    schedule = WarmupSchedule(
        id=uuid4(),
        agent=WarmupAgentType.ANTIGRAVITY,
        trigger=DailyTrigger(at=time(23, 23)),
    )

    scheduler.add(schedule)

    plist_path = build_plist_path(scheduler._launch_agents_directory, schedule.id)

    assert plist_path.is_file()
    assert scheduler.get(schedule.id) == schedule
    run_launchctl.assert_called_once_with(
        "bootstrap",
        f"gui/{os.getuid()}",
        str(plist_path),
    )
