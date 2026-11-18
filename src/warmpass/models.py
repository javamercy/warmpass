"""Shared domain models and enumerations across Warmpass features."""

from enum import StrEnum


class AgentType(StrEnum):
    """Supported coding agents; values are the public CLI and schedule record spellings."""

    CODEX = "codex"
    ANTIGRAVITY = "antigravity"
    CLAUDE = "claude"
