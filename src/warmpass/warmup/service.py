"""Service that runs an immediate agent warmup with a minimal prompt."""

from typing import Final

from warmpass.warmup.base import WarmupAgent

WARMUP_PROMPT: Final[str] = "ONLY reply with OK. Do not use tools or inspect files."


class WarmupService:
    """Send the standard minimal warmup prompt to a configured agent adapter."""

    def __init__(self, agent: WarmupAgent) -> None:
        self._agent = agent

    def warmup(self, model: str | None = None) -> None:
        """Run an agent warmup that spends minimal quota to start the usage window, or raise WarmupError."""
        self._agent.warmup(WARMUP_PROMPT, model)
