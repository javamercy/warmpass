from enum import StrEnum

from pydantic import BaseModel


class WarmupAgentType(StrEnum):
    CODEX = "codex"
    ANTIGRAVITY = "antigravity"


class WarmupStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class WarmupResult(BaseModel):
    agent: WarmupAgentType
    status: WarmupStatus
    message: str
    exit_code: int | None = None
