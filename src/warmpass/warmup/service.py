from typing import Final

from warmpass.warmup.base import WarmupAgent

WARMUP_PROMPT: Final[str] = "ONLY reply with OK. Do not use tools or inspect files."


class WarmupService:
    def __init__(self, agent: WarmupAgent) -> None:
        self._agent = agent

    def warmup(self, model: str | None = None) -> None:
        self._agent.warmup(WARMUP_PROMPT, model)
