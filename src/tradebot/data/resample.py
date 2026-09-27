"""Resample Alpaca 1-minute bars into session-aligned hourly bars.

Input: one symbol's minute bars as Alpaca returns them, indexed by bar START time (tz-aware,
UTC from the API; any tz is accepted), with columns open/high/low/close/volume and
optionally trade_count/vwap.

Only regular-session minutes are kept: a minute starting at t belongs to a session when
open <= t < close. That drops pre/post-market, non-trading days, the post-close minute that starts
at 16:00 ET (13:00 on half days), and anything after it.

Output: one row per (non-empty) hourly bucket, indexed by bucket END time in
America/New_York (see market_calendar for the grid). Buckets with no minute bars produce no
row; nothing is forward-filled or invented. `n_minutes` counts the minute bars in each
bucket so data-quality checks can spot thin buckets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tradebot.market_calendar import BAR_LENGTH, TZ, MarketCalendar

PRICE_COLS = ("open", "high", "low", "close")
OUT_COLS = ("open", "high", "low", "close", "volume", "trade_count", "vwap", "n_minutes")


def session_minutes(minutes: pd.DataFrame, calendar: MarketCalendar) -> pd.DataFrame:
    """Keep only regular-session minutes; add `session_open` / `session_close` columns.

    The returned index is converted to America/New_York (still bar START times).
    """
    idx = minutes.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None:
        raise ValueError("minute bars need a tz-aware DatetimeIndex of bar start times")
    if idx.has_duplicates:
        raise ValueError("minute bars have duplicate timestamps")

    out = minutes.set_axis(idx.tz_convert(TZ)).sort_index()
    local = pd.DatetimeIndex(out.index)
    days = local.tz_localize(None).normalize()

    sessions = calendar.sessions
    uncovered = days[(days < sessions.index[0]) | (days > sessions.index[-1])]
    if len(uncovered):
        raise ValueError(
            f"minute bars from {uncovered[0].date()} to {uncovered[-1].date()} fall outside "
            f"the calendar ({calendar.first} to {calendar.last})"
        )

    # Session open/close for each minute's date (NaT on non-trading days, which then fail
    # both comparisons and are dropped).
    opens = pd.DatetimeIndex(sessions["open"].reindex(days)).tz_convert(TZ)
    closes = pd.DatetimeIndex(sessions["close"].reindex(days)).tz_convert(TZ)
    in_session = (local >= opens) & (local < closes)
    out = out[in_session]
    out["session_open"] = opens[in_session]
    out["session_close"] = closes[in_session]
    return out


def resample_hourly(
    minutes: pd.DataFrame, calendar: MarketCalendar, now: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Aggregate one symbol's minute bars into hourly bars labeled by END time.

    `now`: drop buckets ending after this time. Pass it whenever the minute data may stop
    partway through a bucket (e.g. a download that ends mid-session); an unfinished bucket
    would otherwise look like a complete bar.
    """
    missing = [c for c in (*PRICE_COLS, "volume") if c not in minutes.columns]
    if missing:
        raise ValueError(f"minute bars missing columns: {missing}")

    m = session_minutes(minutes, calendar)
    if m.empty:
        return _empty()

    # Bucket k covers [open + k h, open + (k+1) h), truncated at the close.
    start = pd.DatetimeIndex(m.index)
    open_ = pd.DatetimeIndex(m["session_open"])
    close = pd.DatetimeIndex(m["session_close"])
    k = np.floor_divide((start - open_).to_numpy(), BAR_LENGTH.to_timedelta64())
    end = open_ + pd.to_timedelta((k + 1) * BAR_LENGTH.to_timedelta64())
    m["end"] = end.where(end <= close, close)

    for col in ("trade_count", "vwap"):
        if col not in m.columns:
            m[col] = np.nan
    m["_pv"] = m["vwap"] * m["volume"]

    g = m.groupby("end", sort=True)
    bars = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(),
            "trade_count": g["trade_count"].sum(min_count=1),
            "_pv": g["_pv"].sum(min_count=1),
            "n_minutes": g.size(),
        }
    )
    # Volume-weighted average of the minute VWAPs; undefined for zero-volume buckets.
    bars["vwap"] = bars.pop("_pv") / bars["volume"].where(bars["volume"] > 0)

    if now is not None:
        bars = bars[bars.index <= now]
    # Fixed resolution so the output dtype doesn't depend on the input's (pandas >= 3 infers it).
    bars.index = pd.DatetimeIndex(bars.index, name="end").as_unit("ns")
    return bars[list(OUT_COLS)]


def _empty() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], tz=TZ, name="end").as_unit("ns")
    dtypes = {c: "float64" for c in OUT_COLS} | {"n_minutes": "int64"}
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in dtypes.items()}, index=idx)
