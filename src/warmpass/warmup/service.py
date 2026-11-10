from warmpass.agents.base import WarmupAgent


class WarmupService:
    def __init__(self, agent: WarmupAgent):
        self._agent = agent

    def warmup(self) -> None:
        self._agent.warmup()
