"""US equity market calendar (Alpaca): trading sessions and the hourly bar grid.

Sessions come from Alpaca's calendar endpoint, which lists every trading day with its
open/close as America/New_York wall-clock times: holidays are absent and half days close
early (13:00). All timestamps returned here are tz-aware America/New_York.

Hourly bars are anchored at the session open and labeled by their END time:
[09:30,10:30) ... [14:30,15:30), then [15:30,16:00). The last bar of a session is
truncated at the close, so a full day has 7 bars and a 13:00 half day has 4.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Self, cast

import pandas as pd

from tradebot.config import AlpacaSecrets

TZ = "America/New_York"
BAR_LENGTH = pd.Timedelta(hours=1)


class MarketCalendar:
    """Trading sessions indexed by date. Built from Alpaca, or from a saved frame."""

    def __init__(self, sessions: pd.DataFrame) -> None:
        """`sessions`: columns `open`, `close` (tz-aware America/New_York), one row per day."""
        frame = sessions[["open", "close"]].copy()
        for col in ("open", "close"):
            if str(frame[col].dt.tz) != TZ:
                raise ValueError(f"calendar {col} must be tz-aware {TZ}")
        frame.index = pd.DatetimeIndex(
            frame["open"].dt.tz_localize(None).dt.normalize(), name="date"
        )
        frame = frame.sort_index()
        if frame.index.has_duplicates:
            raise ValueError("calendar has duplicate dates")
        if (frame["close"] <= frame["open"]).any():
            raise ValueError("calendar has a session closing at or before its open")
        self._df = frame
        self._days = pd.DatetimeIndex(frame.index)  # naive session dates, sorted
        self._open = pd.DatetimeIndex(frame["open"])
        self._close = pd.DatetimeIndex(frame["close"])

    @classmethod
    def from_alpaca(cls, start: date, end: date, secrets: AlpacaSecrets | None = None) -> Self:
        """Fetch sessions in [start, end] from Alpaca's calendar endpoint."""
        from alpaca.trading.client import TradingClient
        from alpaca.trading.models import Calendar
        from alpaca.trading.requests import GetCalendarRequest

        secrets = secrets or AlpacaSecrets()
        client = TradingClient(
            secrets.api_key.get_secret_value(), secrets.secret_key.get_secret_value(), paper=True
        )
        days = cast(list[Calendar], client.get_calendar(GetCalendarRequest(start=start, end=end)))
        return cls.from_wall_times((d.open, d.close) for d in days)

    @classmethod
    def from_wall_times(cls, sessions: Iterable[tuple[datetime, datetime]]) -> Self:
        """Build from naive (open, close) New York wall-clock datetimes, as Alpaca returns them."""
        rows = list(sessions)
        frame = pd.DataFrame(rows, columns=["open", "close"])
        for col in ("open", "close"):
            frame[col] = pd.to_datetime(frame[col]).dt.tz_localize(TZ)
        return cls(frame)

    @classmethod
    def read_parquet(cls, path: Path) -> Self:
        return cls(pd.read_parquet(path))

    def to_parquet(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._df.reset_index(drop=True).to_parquet(path)

    @property
    def sessions(self) -> pd.DataFrame:
        """Copy of the sessions frame: index = naive session date, columns open/close (ET)."""
        return self._df.copy()

    @property
    def first(self) -> date:
        return self._days[0].date()

    @property
    def last(self) -> date:
        return self._days[-1].date()

    def is_session(self, day: date) -> bool:
        self._check_covered(day)
        return pd.Timestamp(day) in self._days

    def open_close(self, day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
        """Open and close of a trading day. KeyError if `day` is not a session."""
        self._check_covered(day)
        i = self._days.get_loc(pd.Timestamp(day))  # KeyError if not a session
        assert isinstance(i, int)
        return self._open[i], self._close[i]

    def sessions_between(self, start: date, end: date) -> list[date]:
        """Trading days in [start, end]."""
        idx = self._days
        return [d.date() for d in idx[(idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))]]

    def shift(self, day: date, n: int) -> date:
        """The trading day `n` sessions after (n > 0) or before (n < 0) `day`.

        `day` need not be a session: shift(saturday, 1) is the following Monday (if open),
        and shift(day, 0) is `day` itself only when it is a session.
        """
        if n == 0:
            if not self.is_session(day):
                raise KeyError(f"{day} is not a trading session")
            return day
        self._check_covered(day)
        idx = self._days
        ts = pd.Timestamp(day)
        if n > 0:  # sessions strictly after `day` start at searchsorted(side="right")
            pos = int(idx.searchsorted(ts, side="right")) + n - 1
        else:  # sessions strictly before `day` end at searchsorted(side="left") - 1
            pos = int(idx.searchsorted(ts, side="left")) + n
        if not 0 <= pos < len(idx):
            raise KeyError(f"calendar does not extend {n} sessions from {day}")
        return idx[pos].date()

    def bar_ends(self, day: date) -> list[pd.Timestamp]:
        """END timestamps of the hourly bars of one session (last bar truncated at the close)."""
        open_, close = self.open_close(day)
        ends: list[pd.Timestamp] = []
        end = open_ + BAR_LENGTH
        while end < close:
            ends.append(end)
            end += BAR_LENGTH
        ends.append(close)
        return ends

    def session_of(self, ts: pd.Timestamp) -> date | None:
        """The trading day whose regular session contains `ts` (open <= ts < close), else None."""
        et = ts.tz_convert(TZ)
        day = et.date()
        if not self.is_session(day):
            return None
        open_, close = self.open_close(day)
        return day if open_ <= et < close else None

    def _check_covered(self, day: date) -> None:
        if not self.first <= day <= self.last:
            raise KeyError(f"{day} is outside the calendar ({self.first} to {self.last})")
