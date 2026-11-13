from datetime import time

import pytest

from warmpass.cli.schedule_output import format_trigger
from warmpass.scheduling.models import (
    DailyTrigger,
    HourlyWindow,
    ScheduleTrigger,
    WeekDay,
    WeeklyTrigger,
)


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        pytest.param(
            DailyTrigger(window=HourlyWindow(every=1)),
            "Daily, every hour, [00:00–24:00) (local time)",
            id="all-day-hourly",
        ),
        pytest.param(
            DailyTrigger(window=HourlyWindow(from_=time(9), until=time(17), every=2)),
            "Daily, every 2 hours, [09:00–17:00) (local time)",
            id="daily-window",
        ),
        pytest.param(
            DailyTrigger(window=HourlyWindow(from_=time(22), until=time(3), every=2)),
            "Daily, every 2 hours, [22:00–03:00 next day) (local time)",
            id="crosses-midnight",
        ),
        pytest.param(
            WeeklyTrigger(
                days=[WeekDay.FRIDAY, WeekDay.MONDAY],
                window=HourlyWindow(from_=time(9), every=3),
            ),
            "Mon, Fri, every 3 hours, [09:00–24:00) (local time)",
            id="weekly-days-sorted",
        ),
    ],
)
def test_format_trigger_describes_the_window(
    trigger: ScheduleTrigger, expected: str
) -> None:
    assert format_trigger(trigger) == expected
