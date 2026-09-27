from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from tradebot.market_calendar import MarketCalendar

# Real 2024 sessions (subset): a winter week (EST) and the July 4th week (EDT), which has a
# 13:00 half day on 07-03 and the 07-04 holiday. Dates not listed count as closed.
SESSIONS = [
    ("2024-01-02", "16:00"),
    ("2024-01-03", "16:00"),
    ("2024-07-01", "16:00"),
    ("2024-07-02", "16:00"),
    ("2024-07-03", "13:00"),
    ("2024-07-05", "16:00"),
    ("2024-07-08", "16:00"),
]


@pytest.fixture
def calendar() -> MarketCalendar:
    return MarketCalendar.from_wall_times(
        (datetime.fromisoformat(f"{d} 09:30"), datetime.fromisoformat(f"{d} {c}"))
        for d, c in SESSIONS
    )


def make_minutes(days: list[str], first: str = "04:00", last: str = "19:59") -> pd.DataFrame:
    """Synthetic Alpaca-style minute bars: UTC index of bar START times, every minute of
    `first`..`last` New York time on each day (so pre/post-market and 16:00 are included).
    Values are deterministic functions of the row number `i`."""
    stamps = [
        pd.date_range(f"{d} {first}", f"{d} {last}", freq="1min", tz="America/New_York")
        for d in days
    ]
    idx = pd.DatetimeIndex(stamps[0].append(stamps[1:])).tz_convert("UTC").rename("timestamp")
    i = np.arange(len(idx), dtype="float64")
    return pd.DataFrame(
        {
            "open": 100 + i,
            "high": 100.5 + i,
            "low": 99.5 + i,
            "close": 100.25 + i,
            "volume": 100 + i % 7,
            "trade_count": np.ones(len(idx)),
            "vwap": 100.1 + i,
        },
        index=idx,
    )
