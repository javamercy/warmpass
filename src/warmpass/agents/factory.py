from typing import assert_never

from warmpass.agents.antigravity import AntigravityWarmupAgent
from warmpass.agents.base import WarmupAgent
from warmpass.agents.codex import CodexWarmupAgent
from warmpass.agents.models import WarmupAgentType


def get_warmup_agent_by_type(agent_type: WarmupAgentType) -> WarmupAgent:
    match agent_type:
        case WarmupAgentType.CODEX:
            return CodexWarmupAgent()
        case WarmupAgentType.ANTIGRAVITY:
            return AntigravityWarmupAgent()
        case _:
            assert_never(agent_type)