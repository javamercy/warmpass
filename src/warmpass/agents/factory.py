from typing import assert_never

from warmpass.agents.base import WarmupAgent
from warmpass.agents.models import AgentType


def create_warmup_agent(agent_type: AgentType) -> WarmupAgent:
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
