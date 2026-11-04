from warmpass.agents.base import WarmupAgent
from warmpass.agents.models import WarmupResult


class WarmupService:
    def __init__(self, agent: WarmupAgent):
        self._agent = agent

    def warmup(self) -> WarmupResult:
        return self._agent.warmup()
