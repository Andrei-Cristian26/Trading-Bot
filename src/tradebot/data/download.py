"""Download raw 1-minute bars from Alpaca into the Store. Resumable and idempotent.

A month is fetched once it is complete and never again; the current (incomplete) month is
re-fetched on every run. Downloads include holdout-period data: the holdout guard lives in
the feed/loader layer, not here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from functools import partial
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import structlog
from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from tradebot.config import AlpacaSecrets
from tradebot.data.store import MINUTE_COLUMNS, Store, empty_minutes

log = structlog.get_logger()

NY = ZoneInfo("America/New_York")
SIP_DELAY = timedelta(minutes=16)  # free plan cannot query the most recent 15 min of SIP
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class BarsClient(Protocol):
    def get_stock_bars(self, request_params: StockBarsRequest) -> Any: ...


def month_starts(start: date, end: date) -> list[date]:
    """First day of every calendar month touching [start, end]."""
    out, m = [], start.replace(day=1)
    while m <= end:
        out.append(m)
        m = _next_month(m)
    return out


def _next_month(m: date) -> date:
    return date(m.year + m.month // 12, m.month % 12 + 1, 1)


def _et_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=NY)


def fetch_month(
    client: BarsClient, symbol: str, month: date, cutoff: datetime, feed: str
) -> pd.DataFrame:
    """Raw minute bars for one ET calendar month, capped at `cutoff`."""
    end = min(_et_midnight(_next_month(month)) - timedelta(microseconds=1), cutoff)
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=_et_midnight(month),
        end=end,
        adjustment=Adjustment.RAW,
        feed=DataFeed(feed),
    )
    df: pd.DataFrame = client.get_stock_bars(req).df
    if df.empty:
        return empty_minutes()
    df = df.reset_index()
    df = df[df["symbol"] == symbol] if "symbol" in df.columns else df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for c in MINUTE_COLUMNS[1:]:
        df[c] = df[c].astype("float64")
    return df[MINUTE_COLUMNS].reset_index(drop=True)


def with_retry[T](fn: Callable[[], T], what: str, attempts: int = 6) -> T:
    for i in range(attempts):
        try:
            return fn()
        except APIError as e:
            if e.status_code not in RETRYABLE_STATUS or i == attempts - 1:
                raise
            err: Exception = e
        except requests.RequestException as e:
            if i == attempts - 1:
                raise
            err = e
        wait = 2**i
        log.warning("retrying", what=what, attempt=i + 1, wait_s=wait, error=str(err)[:200])
        time.sleep(wait)
    raise AssertionError("unreachable")


def download_symbol(
    client: BarsClient, store: Store, symbol: str, start: date, cutoff: datetime, feed: str
) -> int:
    """Fetch every missing or incomplete month for one symbol. Returns months fetched."""
    fetched = 0
    for month in month_starts(start, cutoff.astimezone(NY).date()):
        complete = _et_midnight(_next_month(month)) <= cutoff
        if complete and store.has_minutes(symbol, month):
            continue
        fetch = partial(fetch_month, client, symbol, month, cutoff, feed)
        df = with_retry(fetch, f"{symbol} {month:%Y-%m}")
        store.write_minutes(symbol, month, df, complete=complete)
        fetched += 1
    return fetched


def download_universe(
    symbols: Sequence[str],
    store: Store,
    start: date,
    feed: str,
    secrets: AlpacaSecrets,
    workers: int = 4,
) -> dict[str, int]:
    """Download all symbols in parallel (one client per worker task)."""
    cutoff = datetime.now(UTC) - SIP_DELAY
    key, sec = secrets.api_key.get_secret_value(), secrets.secret_key.get_secret_value()

    def one(symbol: str) -> int:
        client = StockHistoricalDataClient(key, sec)
        return download_symbol(client, store, symbol, start, cutoff, feed)

    results: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, s): s for s in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                results[sym] = fut.result()
                log.info("symbol_done", symbol=sym, months_fetched=results[sym],
                         done=len(results), total=len(symbols))  # fmt: skip
            except Exception:
                log.exception("symbol_failed", symbol=sym)
    return results
