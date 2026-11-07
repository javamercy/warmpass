from typing import assert_never

from warmpass.agents.base import WarmupAgent
from warmpass.agents.models import WarmupAgentType


def create_warmup_agent(agent_type: WarmupAgentType) -> WarmupAgent:
    match agent_type:
        case WarmupAgentType.CODEX:
            from warmpass.agents.codex import CodexWarmupAgent

            return CodexWarmupAgent()

        case WarmupAgentType.ANTIGRAVITY:
            from warmpass.agents.antigravity import AntigravityWarmupAgent

            return AntigravityWarmupAgent()

        case _:
            assert_never(agent_type)
