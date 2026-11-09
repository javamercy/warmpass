from typing import Protocol

from warmpass.agents.models import WarmupResult


class WarmupAgent(Protocol):
    def warmup(self) -> WarmupResult: ...
