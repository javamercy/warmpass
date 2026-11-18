"""Protocol and error types for agent warmup adapters."""

from typing import Protocol

from warmpass.errors import WarmpassError


class WarmupError(WarmpassError):
    """Error raised when an agent warmup operation fails or times out."""


class WarmupAgent(Protocol):
    """Protocol for an adapter that sends a warmup prompt to a coding agent."""

    def warmup(self, prompt: str, model: str | None = None) -> None:
        """Send a warmup prompt to the agent to start its usage window, using its default model when model is None, or raise WarmupError."""
        ...
