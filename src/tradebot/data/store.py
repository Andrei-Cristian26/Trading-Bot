"""Parquet storage layout.

Raw minute bars are stored exactly as Alpaca returns them: unadjusted, UTC timestamps
labeled by bar START, extended hours included. One file per symbol per ET calendar month:
    {store_dir}/raw/minute/{symbol}/{YYYY-MM}.parquet           complete month, never refetched
    {store_dir}/raw/minute/{symbol}/{YYYY-MM}.partial.parquet   current month, refetched each run
Everything downstream (hourly bars, adjustment) is derived from these and can be rebuilt.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

MINUTE_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]


def empty_minutes() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="float64") for c in MINUTE_COLUMNS[1:]})
    df.insert(0, "timestamp", pd.Series(dtype="datetime64[ns, UTC]"))
    return df


@dataclass(frozen=True)
class Store:
    root: Path

    def minute_path(self, symbol: str, month: date, partial: bool = False) -> Path:
        suffix = ".partial.parquet" if partial else ".parquet"
        return self.root / "raw" / "minute" / symbol / f"{month:%Y-%m}{suffix}"

    def has_minutes(self, symbol: str, month: date) -> bool:
        """True only for a COMPLETE stored month."""
        return self.minute_path(symbol, month).exists()

    def minute_months(self, symbol: str) -> list[date]:
        d = self.root / "raw" / "minute" / symbol
        if not d.exists():
            return []
        return sorted({date.fromisoformat(p.name[:7] + "-01") for p in d.glob("*.parquet")})

    def write_minutes(
        self, symbol: str, month: date, df: pd.DataFrame, complete: bool = True
    ) -> None:
        """Atomic write (tmp file + rename): a crash never leaves a half-written month.
        Writing a complete month removes its .partial file."""
        if list(df.columns) != MINUTE_COLUMNS:
            raise ValueError(f"expected columns {MINUTE_COLUMNS}, got {list(df.columns)}")
        if df["timestamp"].duplicated().any():
            raise ValueError(f"{symbol} {month:%Y-%m}: duplicate timestamps")
        path = self.minute_path(symbol, month, partial=not complete)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        df.sort_values("timestamp").to_parquet(tmp, index=False)
        os.replace(tmp, path)
        if complete:
            self.minute_path(symbol, month, partial=True).unlink(missing_ok=True)

    def read_minutes(
        self, symbol: str, start: date | None = None, end: date | None = None
    ) -> pd.DataFrame:
        """All stored minute bars for `symbol` in months overlapping [start, end]."""
        months = [
            m
            for m in self.minute_months(symbol)
            if (start is None or m >= start.replace(day=1)) and (end is None or m <= end)
        ]
        if not months:
            return empty_minutes()
        frames = [
            pd.read_parquet(self.minute_path(symbol, m, partial=not self.has_minutes(symbol, m)))
            for m in months
        ]
        return pd.concat(frames, ignore_index=True).sort_values("timestamp", ignore_index=True)
