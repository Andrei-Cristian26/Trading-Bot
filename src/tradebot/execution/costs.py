"""Cost model shared by labels, SimBroker, and the entry-edge threshold. Implemented in phase 3."""

from __future__ import annotations

from dataclasses import dataclass

from tradebot.config import CostsConfig, Universe
from tradebot.types import Side


@dataclass(frozen=True)
class CostModel:
    cfg: CostsConfig
    universe: Universe
    multiplier: float = 1.0  # stress tests use 2.0 / 3.0

    def fill_price(self, symbol: str, side: Side, ref_price: float) -> float:
        """Reference price moved against us by slippage + half-spread (bps by asset class)."""
        raise NotImplementedError("phase 3")

    def reg_fees(self, qty: int, price: float, is_sell: bool) -> float:
        """SEC fee (on sell notional) + FINRA TAF (per share sold, capped). Zero on buys."""
        raise NotImplementedError("phase 3")

    def borrow_fee(self, notional: float, days: float) -> float:
        """Short borrow accrual: notional * borrow_apr * days / 365."""
        raise NotImplementedError("phase 3")

    def round_trip_bps(self, symbol: str) -> float:
        """Expected round-trip cost in bps, used by labels and the entry threshold."""
        raise NotImplementedError("phase 3")

    def scaled(self, k: float) -> CostModel:
        return CostModel(self.cfg, self.universe, self.multiplier * k)
