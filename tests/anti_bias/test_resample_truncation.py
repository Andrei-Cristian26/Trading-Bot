"""Truncation test: resampling minute data cut off at time T must give exactly the same
bars as the full data for every bar ending at or before T, and no bar ending after T."""

from __future__ import annotations

import pandas as pd

from tests.conftest import make_minutes
from tradebot.data.resample import resample_hourly
from tradebot.market_calendar import TZ, MarketCalendar


def test_truncated_minutes_give_identical_completed_bars(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02", "2024-07-03", "2024-07-05"])
    full = resample_hourly(minutes, calendar)
    for cut in pd.date_range("2024-07-02 09:00", "2024-07-05 17:00", freq="17min", tz=TZ):
        # Minute bars are labeled by START: the minute starting at t is only known at t+1min.
        known = minutes[minutes.index + pd.Timedelta(minutes=1) <= cut]
        part = resample_hourly(known, calendar, now=cut)
        assert (part.index <= cut).all()
        pd.testing.assert_frame_equal(part, full[full.index <= cut])
