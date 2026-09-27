"""Broker interface. SimBroker (backtest) and AlpacaPaperBroker (live) implement it."""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from tradebot.types import Account, ExitReason, Fill, Order, Position, Side, TimeInForce


class Broker(Protocol):
    def submit_entry(
        self, symbol: str, side: Side, qty: int, tp: float, sl: float, tif: TimeInForce
    ) -> str:
        """Market entry with TP/SL bracket legs (server-side OCO in live). Returns order id.

        SimBroker fills at the next bar's open plus slippage; bracket legs are checked on
        every subsequent bar (gap through a level fills at the open; TP+SL in one bar -> SL).
        """
        ...

    def submit_exit(self, symbol: str, reason: ExitReason, tif: TimeInForce) -> str:
        """Cancel the position's bracket legs, then close it at market (or MOC for TIME)."""
        ...

    def positions(self) -> dict[str, Position]: ...

    def open_orders(self) -> list[Order]: ...

    def account(self) -> Account: ...

    def fills_since(self, ts: pd.Timestamp) -> list[Fill]: ...

    def is_shortable(self, symbol: str) -> bool:
        """Easy-to-borrow check. SimBroker: True for the whole universe (documented assumption)."""
        ...
