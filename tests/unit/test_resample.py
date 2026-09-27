from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_minutes
from tradebot.data.resample import resample_hourly
from tradebot.market_calendar import TZ, MarketCalendar


def et(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=TZ)


def test_bar_counts_and_labels(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-01-02", "2024-07-02", "2024-07-03", "2024-07-04"])
    bars = resample_hourly(minutes, calendar, now=None)
    ends = pd.DatetimeIndex(bars.index)
    per_day = bars.groupby(ends.date).size()
    assert per_day.to_dict() == {
        pd.Timestamp("2024-01-02").date(): 7,  # EST
        pd.Timestamp("2024-07-02").date(): 7,  # EDT
        pd.Timestamp("2024-07-03").date(): 4,  # half day; 07-04 holiday has none
    }
    assert str(ends.tz) == TZ
    assert bars.index.name == "end"
    assert list(ends[ends.date == pd.Timestamp("2024-07-02").date()].strftime("%H:%M")) == [
        "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:00"
    ]  # fmt: skip
    assert bars.loc[et("2024-07-02 10:30"), "n_minutes"] == 60
    assert bars.loc[et("2024-07-02 16:00"), "n_minutes"] == 30
    assert bars.loc[et("2024-07-03 13:00"), "n_minutes"] == 30


def test_ohlcv_aggregation(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"])
    bars = resample_hourly(minutes, calendar, now=None)
    src = minutes.tz_convert(TZ).loc["2024-07-02 09:30":"2024-07-02 10:29"]
    first = bars.loc[et("2024-07-02 10:30")]
    assert first["open"] == src["open"].iloc[0]
    assert first["high"] == src["high"].max()
    assert first["low"] == src["low"].min()
    assert first["close"] == src["close"].iloc[-1]
    assert first["volume"] == src["volume"].sum()
    assert first["trade_count"] == 60
    assert first["vwap"] == pytest.approx((src["vwap"] * src["volume"]).sum() / src["volume"].sum())


def test_bucket_boundaries_are_start_inclusive(calendar: MarketCalendar) -> None:
    # Minutes are labeled by START: the minute starting 10:30 belongs to the bar ending 11:30.
    minutes = make_minutes(["2024-07-02"])
    local = pd.DatetimeIndex(minutes.index).tz_convert(TZ)
    bars = resample_hourly(minutes, calendar, now=None)
    at = {
        t: minutes.loc[local == et(f"2024-07-02 {t}")].iloc[0] for t in ("09:30", "10:29", "10:30")
    }
    assert bars.loc[et("2024-07-02 10:30"), "open"] == at["09:30"]["open"]
    assert bars.loc[et("2024-07-02 10:30"), "close"] == at["10:29"]["close"]
    assert bars.loc[et("2024-07-02 11:30"), "open"] == at["10:30"]["open"]


def test_post_close_minute_is_dropped(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02", "2024-07-03"])
    local = pd.DatetimeIndex(minutes.index).tz_convert(TZ)
    # A huge print at 16:00 (and 13:00 on the half day) must not leak into the last bar.
    for t in ("2024-07-02 16:00", "2024-07-03 13:00"):
        minutes.loc[local == et(t), ["high", "volume"]] = [1e9, 1e9]
    bars = resample_hourly(minutes, calendar, now=None)
    for end, last_minute in (
        ("2024-07-02 16:00", "2024-07-02 15:59"),
        ("2024-07-03 13:00", "2024-07-03 12:59"),
    ):
        bar = bars.loc[et(end)]
        assert bar["high"] < 1e9 and bar["volume"] < 1e9
        assert bar["close"] == minutes.loc[local == et(last_minute), "close"].iloc[0]


def test_empty_bucket_produces_no_row(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"])
    local = pd.DatetimeIndex(minutes.index).tz_convert(TZ)
    gap = (local >= et("2024-07-02 11:30")) & (local < et("2024-07-02 12:30"))
    bars = resample_hourly(minutes[~gap], calendar, now=None)
    assert et("2024-07-02 12:30") not in bars.index
    assert len(bars) == 6


def test_now_drops_unfinished_buckets(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"], last="12:14")  # data stops mid-bucket
    bars = resample_hourly(minutes, calendar, now=et("2024-07-02 12:15"))
    assert list(pd.DatetimeIndex(bars.index).strftime("%H:%M")) == ["10:30", "11:30"]


def test_missing_optional_columns(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"]).drop(columns=["vwap", "trade_count"])
    bars = resample_hourly(minutes, calendar, now=None)
    assert bars["vwap"].isna().all() and bars["trade_count"].isna().all()
    assert bars["volume"].gt(0).all()


def test_zero_volume_bucket_has_nan_vwap(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"])
    minutes["volume"] = 0.0
    assert resample_hourly(minutes, calendar, now=None)["vwap"].isna().all()


def test_no_session_minutes_gives_empty_frame(calendar: MarketCalendar) -> None:
    bars = resample_hourly(make_minutes(["2024-07-04"]), calendar, now=None)  # holiday
    assert bars.empty and str(pd.DatetimeIndex(bars.index).tz) == TZ


def test_input_validation(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"])
    with pytest.raises(ValueError, match="tz-aware"):
        resample_hourly(minutes.tz_localize(None), calendar, now=None)
    with pytest.raises(ValueError, match="duplicate"):
        resample_hourly(pd.concat([minutes, minutes.iloc[:1]]), calendar, now=None)
    with pytest.raises(ValueError, match="missing columns"):
        resample_hourly(minutes.drop(columns=["close"]), calendar, now=None)
    with pytest.raises(ValueError, match="outside the calendar"):
        resample_hourly(make_minutes(["2024-07-09"]), calendar, now=None)


def test_input_order_does_not_matter(calendar: MarketCalendar) -> None:
    minutes = make_minutes(["2024-07-02"])
    shuffled = minutes.iloc[np.random.default_rng(0).permutation(len(minutes))]
    pd.testing.assert_frame_equal(
        resample_hourly(shuffled, calendar, now=None), resample_hourly(minutes, calendar, now=None)
    )


def test_now_is_required(calendar: MarketCalendar) -> None:
    # Forgetting `now` must fail loudly: a partial last hour would look like a complete bar.
    with pytest.raises(TypeError):
        resample_hourly(make_minutes(["2024-07-02"]), calendar)  # type: ignore[call-arg]
