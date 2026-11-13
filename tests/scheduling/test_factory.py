import pytest

from warmpass.scheduling.base import SchedulerError
from warmpass.scheduling.factory import create_os_job_scheduler


@pytest.mark.parametrize("platform", ["linux", "freebsd"])
def test_unsupported_platform_fails_with_its_name(platform: str) -> None:
    with pytest.raises(SchedulerError, match=f"Unsupported platform '{platform}'"):
        create_os_job_scheduler(platform)
