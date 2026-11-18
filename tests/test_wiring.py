from types import SimpleNamespace

import pytest

from warmpass import wiring
from warmpass.scheduling.base import SchedulingError


@pytest.mark.parametrize("platform", ["linux", "freebsd"])
def test_unsupported_platform_rejects_scheduler_creation(
    platform: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wiring, "sys", SimpleNamespace(platform=platform))

    with pytest.raises(SchedulingError, match=f"Unsupported platform '{platform}'"):
        wiring.create_os_job_scheduler()
