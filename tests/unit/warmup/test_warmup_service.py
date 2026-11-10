from unittest.mock import Mock

import pytest

from warmpass.agents.base import WarmupError
from warmpass.warmup.service import WarmupService


def test_warmup_delegates_to_agent() -> None:
    agent = Mock()
    agent.warmup.return_value = None

    assert WarmupService(agent).warmup() is None
    agent.warmup.assert_called_once_with()


def test_warmup_propagates_agent_error() -> None:
    agent = Mock()
    error = WarmupError("Warmup failed")
    agent.warmup.side_effect = error

    with pytest.raises(WarmupError) as exc_info:
        WarmupService(agent).warmup()

    assert exc_info.value is error
    agent.warmup.assert_called_once_with()
