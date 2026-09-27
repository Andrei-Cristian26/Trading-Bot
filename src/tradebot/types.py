"""Core value types shared by backtest and live. Timestamps are tz-aware (America/New_York)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import IntEnum, StrEnum

import pandas as pd


class Side(IntEnum):
    SHORT = -1
    FLAT = 0
    LONG = 1


class AssetClass(StrEnum):
    ETF = "etf"
    STOCK = "stock"


class ExitReason(StrEnum):
    TP = "tp"
    SL = "sl"
    TIME = "time"
    REVERSAL = "reversal"
    KILL_SWITCH = "kill_switch"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    OPG = "opg"  # market-on-open (entries signaled on the 16:00 bar)
    CLS = "cls"  # market-on-close (time exits)


class OrderStatus(StrEnum):
    NEW = "new"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class TargetPosition:
    """A strategy's desired entry. Barriers are absolute RAW prices fixed at signal time."""

    symbol: str
    side: Side
    score: float  # ranking key: model probability (ml) or momentum magnitude (baseline)
    signal_time: pd.Timestamp  # close time of the bar the signal was computed on
    tp: float
    sl: float
    expiry: date  # trading day on whose close the time exit fires


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    side: Side
    qty: int  # always positive; direction is `side`
    avg_entry: float
    entry_time: pd.Timestamp
    tp: float
    sl: float
    expiry: date


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    symbol: str
    side: Side  # direction of the trade (LONG = buy, SHORT = sell)
    qty: int
    tif: TimeInForce
    status: OrderStatus
    submitted_at: pd.Timestamp
    tp: float | None = None  # bracket legs, if any
    sl: float | None = None
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: int
    price: float
    time: pd.Timestamp
    costs: float  # slippage already in `price`; this is fees (+ borrow on close)
    reason: ExitReason | None = None  # set on exits


@dataclass(frozen=True, slots=True)
class Account:
    equity: float
    cash: float
    buying_power: float
    as_of: pd.Timestamp
