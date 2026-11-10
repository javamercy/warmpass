from typing import Protocol


class WarmupError(RuntimeError):
    pass


class WarmupAgent(Protocol):
    def warmup(self) -> None: ...
