"""DataFeed: the ONLY way strategies/features see market data.

Invariant (enforced by implementations, tested in tests/anti_bias): no call can return a
bar whose end timestamp is later than the feed's current clock. Bars are labeled by their
END time, so "known at time t" == "bar_end <= t".
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

import pandas as pd


class HoldoutAccessError(RuntimeError):
    """Raised when non-holdout code asks for data at or after the locked holdout start."""


class LookaheadError(RuntimeError):
    """Raised when a caller asks for data beyond the feed's current clock."""


class DataFeed(Protocol):
    @property
    def now(self) -> pd.Timestamp:
        """Current clock: the end time of the most recent closed bar."""
        ...

    def bars(self, symbols: Sequence[str], lookback: int) -> pd.DataFrame:
        """Last `lookback` hourly bars per symbol ending at or before `now`.

        Long format: columns [symbol, end, open, high, low, close, volume, vwap, is_short_bar],
        adjusted prices. Volume/vwap of bars ended within `volume_lag_minutes` are NaN.
        """
        ...

    def daily_bars(self, symbols: Sequence[str], lookback: int) -> pd.DataFrame:
        """Last `lookback` COMPLETED sessions per symbol (never the in-progress session)."""
        ...

    def raw_price(self, symbol: str) -> float:
        """Unadjusted close of the latest closed bar: used for barriers and order prices."""
        ...

    def trading_days_after(self, day: date, n: int) -> date:
        """The n-th trading day after `day` (market calendar, holidays respected)."""
        ...
