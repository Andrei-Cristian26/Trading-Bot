from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from tradebot.data.download import download_symbol, month_starts
from tradebot.data.store import MINUTE_COLUMNS, Store


def _bars(symbol: str, start: datetime, n: int) -> pd.DataFrame:
    ts = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 10.0,
         "trade_count": 1.0, "vwap": 1.0},
        index=pd.MultiIndex.from_product([[symbol], ts], names=["symbol", "timestamp"]),
    )  # fmt: skip
    return df


@dataclass
class FakeResult:
    df: pd.DataFrame


@dataclass
class FakeClient:
    calls: list[tuple[datetime, datetime]] = field(default_factory=list)

    def get_stock_bars(self, request_params: Any) -> FakeResult:
        # alpaca-py converts request times to naive UTC
        start = request_params.start.replace(tzinfo=UTC)
        end = request_params.end.replace(tzinfo=UTC)
        self.calls.append((start, end))
        if start.year < 2020:  # symbol "didn't exist" yet
            return FakeResult(pd.DataFrame())
        return FakeResult(_bars("XYZ", start.replace(hour=14, minute=30), 5))


def test_month_starts() -> None:
    assert month_starts(date(2016, 1, 15), date(2016, 3, 2)) == [
        date(2016, 1, 1), date(2016, 2, 1), date(2016, 3, 1)
    ]  # fmt: skip
    dec_jan = [date(2016, 12, 1), date(2017, 1, 1)]
    assert month_starts(date(2016, 12, 5), date(2017, 1, 1)) == dec_jan


def test_download_resumes_and_refetches_partial(tmp_path: Path) -> None:
    store = Store(tmp_path)
    client = FakeClient()
    cutoff = datetime(2020, 3, 15, 16, tzinfo=UTC)

    assert download_symbol(client, store, "XYZ", date(2019, 12, 1), cutoff, "sip") == 4
    assert store.has_minutes("XYZ", date(2019, 12, 1))  # empty month stored -> not refetched
    assert store.has_minutes("XYZ", date(2020, 2, 1))
    assert not store.has_minutes("XYZ", date(2020, 3, 1))  # in progress -> partial only
    assert store.minute_path("XYZ", date(2020, 3, 1), partial=True).exists()
    assert client.calls[-1][1] == cutoff  # capped at cutoff

    # Second run, same cutoff: only the partial month is fetched again.
    client.calls.clear()
    assert download_symbol(client, store, "XYZ", date(2019, 12, 1), cutoff, "sip") == 1

    # Month later: March becomes complete, partial file replaced.
    later = datetime(2020, 4, 2, 16, tzinfo=UTC)
    assert download_symbol(client, store, "XYZ", date(2019, 12, 1), later, "sip") == 2
    assert store.has_minutes("XYZ", date(2020, 3, 1))
    assert not store.minute_path("XYZ", date(2020, 3, 1), partial=True).exists()


def test_store_roundtrip(tmp_path: Path) -> None:
    store = Store(tmp_path)
    for m in (date(2020, 1, 1), date(2020, 2, 1)):
        df = _bars("XYZ", datetime(m.year, m.month, 2, 14, 30, tzinfo=UTC), 3).reset_index()
        store.write_minutes("XYZ", m, df[MINUTE_COLUMNS])
    out = store.read_minutes("XYZ")
    assert len(out) == 6 and out["timestamp"].is_monotonic_increasing
    assert len(store.read_minutes("XYZ", start=date(2020, 2, 10))) == 3
    assert str(out["timestamp"].dt.tz) == "UTC"


def test_store_rejects_duplicates(tmp_path: Path) -> None:
    df = _bars("XYZ", datetime(2020, 1, 2, 14, 30, tzinfo=UTC), 2).reset_index()[MINUTE_COLUMNS]
    with pytest.raises(ValueError, match="duplicate"):
        Store(tmp_path).write_minutes("XYZ", date(2020, 1, 1), pd.concat([df, df]))
