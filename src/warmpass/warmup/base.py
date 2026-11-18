from typing import Protocol

from warmpass.errors import WarmpassError


class WarmupError(WarmpassError):
    """Error raised when an agent warmup operation fails or times out."""


class WarmupAgent(Protocol):
    def warmup(self, prompt: str, model: str | None = None) -> None: ...
