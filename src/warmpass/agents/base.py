from abc import abstractmethod
from typing import Final, Protocol

from warmpass.agents.models import WarmupResult

WARMUP_PROMPT: Final[str] = "Reply with OK. Do not use tools or inspect files."


class WarmupAgent(Protocol):
    @abstractmethod
    def warmup(self) -> WarmupResult: ...
