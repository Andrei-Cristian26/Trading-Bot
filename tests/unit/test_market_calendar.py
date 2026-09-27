from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from tradebot.config import AlpacaSecrets
from tradebot.market_calendar import TZ, MarketCalendar


def et(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=TZ)


def test_full_day_has_seven_bars_ending_at_close(calendar: MarketCalendar) -> None:
    ends = calendar.bar_ends(date(2024, 7, 2))
    assert [e.strftime("%H:%M") for e in ends] == [
        "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:00"
    ]  # fmt: skip
    assert all(str(e.tz) == TZ for e in ends)


def test_half_day_is_truncated_at_early_close(calendar: MarketCalendar) -> None:
    ends = calendar.bar_ends(date(2024, 7, 3))
    assert [e.strftime("%H:%M") for e in ends] == ["10:30", "11:30", "12:30", "13:00"]


def test_winter_session_times_are_eastern(calendar: MarketCalendar) -> None:
    open_, close = calendar.open_close(date(2024, 1, 2))
    assert open_ == pd.Timestamp("2024-01-02 14:30", tz="UTC")  # EST = UTC-5
    assert close == pd.Timestamp("2024-01-02 21:00", tz="UTC")


def test_holiday_and_coverage(calendar: MarketCalendar) -> None:
    assert calendar.is_session(date(2024, 7, 3))
    assert not calendar.is_session(date(2024, 7, 4))
    with pytest.raises(KeyError):
        calendar.open_close(date(2024, 7, 4))
    with pytest.raises(KeyError):
        calendar.is_session(date(2023, 12, 29))  # before the calendar starts


def test_sessions_between(calendar: MarketCalendar) -> None:
    assert calendar.sessions_between(date(2024, 7, 3), date(2024, 7, 7)) == [
        date(2024, 7, 3),
        date(2024, 7, 5),
    ]


@pytest.mark.parametrize(
    ("day", "n", "expected"),
    [
        (date(2024, 7, 1), 4, date(2024, 7, 8)),
        (date(2024, 7, 3), 1, date(2024, 7, 5)),  # skips the holiday
        (date(2024, 7, 4), 1, date(2024, 7, 5)),  # from a non-session day
        (date(2024, 7, 4), -1, date(2024, 7, 3)),
        (date(2024, 7, 5), -1, date(2024, 7, 3)),
        (date(2024, 7, 8), -4, date(2024, 7, 1)),
        (date(2024, 7, 5), 0, date(2024, 7, 5)),
    ],
)
def test_shift(calendar: MarketCalendar, day: date, n: int, expected: date) -> None:
    assert calendar.shift(day, n) == expected


def test_shift_errors(calendar: MarketCalendar) -> None:
    with pytest.raises(KeyError):
        calendar.shift(date(2024, 7, 4), 0)  # not a session
    with pytest.raises(KeyError):
        calendar.shift(date(2024, 7, 8), 1)  # beyond the calendar


def test_session_of(calendar: MarketCalendar) -> None:
    assert calendar.session_of(et("2024-07-02 09:30")) == date(2024, 7, 2)
    assert calendar.session_of(et("2024-07-02 15:59")) == date(2024, 7, 2)
    assert calendar.session_of(et("2024-07-02 16:00")) is None  # the close is exclusive
    assert calendar.session_of(et("2024-07-02 09:29")) is None
    assert calendar.session_of(et("2024-07-03 13:00")) is None  # half-day close
    assert calendar.session_of(pd.Timestamp("2024-07-02 19:59", tz="UTC")) == date(2024, 7, 2)


def test_parquet_roundtrip(calendar: MarketCalendar, tmp_path: Path) -> None:
    path = tmp_path / "calendar.parquet"
    calendar.to_parquet(path)
    loaded = MarketCalendar.read_parquet(path)
    pd.testing.assert_frame_equal(loaded.sessions, calendar.sessions)


def test_rejects_naive_times() -> None:
    naive = pd.DataFrame(
        {"open": [pd.Timestamp("2024-07-02 09:30")], "close": [pd.Timestamp("2024-07-02 16:00")]}
    )
    with pytest.raises(ValueError, match="tz-aware"):
        MarketCalendar(naive)


def _have_keys() -> bool:
    try:
        AlpacaSecrets()
    except ValidationError:
        return False
    return True


@pytest.mark.network
@pytest.mark.skipif(not _have_keys(), reason="no Alpaca keys")
def test_alpaca_calendar_known_days() -> None:
    cal = MarketCalendar.from_alpaca(date(2018, 12, 1), date(2024, 7, 10))
    assert not cal.is_session(date(2018, 12, 5))  # market closed: national day of mourning
    assert not cal.is_session(date(2024, 7, 4))
    assert cal.open_close(date(2024, 7, 3))[1] == et("2024-07-03 13:00")
    assert len(cal.bar_ends(date(2024, 7, 2))) == 7
