import sys
from typing import assert_never

from warmpass.models import AgentType
from warmpass.paths import get_store_directory
from warmpass.scheduling.base import OSJobScheduler, SchedulingError
from warmpass.scheduling.service import SchedulerService
from warmpass.scheduling.store import WarmupScheduleStore
from warmpass.warmup.base import WarmupAgent
from warmpass.warmup.service import WarmupService


def _create_warmup_agent(agent_type: AgentType) -> WarmupAgent:
    match agent_type:
        case AgentType.CODEX:
            from warmpass.agents.codex import CodexWarmupAgent

            return CodexWarmupAgent()

        case AgentType.ANTIGRAVITY:
            from warmpass.agents.antigravity import AntigravityWarmupAgent

            return AntigravityWarmupAgent()

        case AgentType.CLAUDE:
            from warmpass.agents.claude import ClaudeWarmupAgent

            return ClaudeWarmupAgent()

        case _:
            assert_never(agent_type)


def create_warmup_service(agent_type: AgentType) -> WarmupService:
    warmup_agent = _create_warmup_agent(agent_type)
    return WarmupService(warmup_agent)


def create_os_job_scheduler() -> OSJobScheduler:
    match sys.platform:
        case "darwin":
            from warmpass.scheduling.macos.factory import create_macos_warmup_scheduler

            return create_macos_warmup_scheduler()

        case "win32":
            from warmpass.scheduling.windows.factory import (
                create_windows_warmup_scheduler,
            )

            return create_windows_warmup_scheduler()

        case _:
            raise SchedulingError(f"Unsupported platform '{sys.platform}'. ")


def create_scheduler_service() -> SchedulerService:
    scheduler = create_os_job_scheduler()
    store = WarmupScheduleStore(directory=get_store_directory())
    return SchedulerService(store=store, scheduler=scheduler)
