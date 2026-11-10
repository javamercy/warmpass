from unittest.mock import Mock
from uuid import UUID

from warmpass.agents.models import AgentType
from warmpass.scheduling.models import DailyTrigger, HourlyWindow
from warmpass.scheduling.service import WarmupSchedulerService


def test_add_creates_uuid_and_returns_registered_schedule() -> None:
    scheduler = Mock()
    service = WarmupSchedulerService(scheduler)
    trigger = DailyTrigger(window=HourlyWindow(every=5))

    schedule = service.add(AgentType.CODEX, trigger)

    assert isinstance(schedule.id, UUID)
    assert schedule.id.version == 4
    assert schedule.agent == AgentType.CODEX
    assert schedule.trigger == trigger
    scheduler.add.assert_called_once_with(schedule)


def test_clear_delegates_to_scheduler() -> None:
    scheduler = Mock()
    service = WarmupSchedulerService(scheduler)
    service.clear()
    scheduler.clear.assert_called_once_with()
