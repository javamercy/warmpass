from datetime import UTC, time

import pytest
from pydantic import ValidationError

from warmpass.scheduling.models import HourlyWindow, WeekDay, WeeklyTrigger


def test_window_accepts_a_range_that_ends_at_midnight() -> None:
    window = HourlyWindow(from_=time(22), until=time(0), every=1)

    assert window.until == time(0)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param({"every": 0}, "greater than 0", id="every-zero"),
        pytest.param({"every": 6}, "less than or equal to 5", id="every-six"),
        pytest.param({"every": "2"}, "valid integer", id="every-not-an-int"),
        pytest.param(
            {"from_": time(9), "until": time(9), "every": 2},
            "cannot be the same",
            id="from-equals-until",
        ),
        pytest.param(
            {"until": time(0), "every": 2},
            "would contain no runs",
            id="until-midnight-without-from",
        ),
        pytest.param(
            {"from_": time(9, 0, 30), "every": 2},
            "minute precision",
            id="seconds",
        ),
        pytest.param(
            {"until": time(9, 0, 0, 5), "every": 2},
            "minute precision",
            id="microseconds",
        ),
    ],
)
def test_window_rejects_invalid_values(fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        HourlyWindow.model_validate(fields)


def test_window_rejects_timezone_aware_times() -> None:
    with pytest.raises(ValidationError, match="must not include a timezone"):
        HourlyWindow(from_=time(9, tzinfo=UTC), every=2)


@pytest.mark.parametrize(
    ("days", "window", "message"),
    [
        pytest.param([], HourlyWindow(every=2), "at least 1", id="no-days"),
        pytest.param(
            [WeekDay.MONDAY, WeekDay.MONDAY],
            HourlyWindow(every=2),
            "Duplicate weekdays",
            id="duplicate-days",
        ),
        pytest.param(
            [WeekDay.MONDAY],
            HourlyWindow(from_=time(22), until=time(3), every=2),
            "cannot cross midnight",
            id="crosses-midnight",
        ),
    ],
)
def test_weekly_trigger_rejects_invalid_values(
    days: list[WeekDay], window: HourlyWindow, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        WeeklyTrigger(days=days, window=window)
