"""Risk manager: the last gate between strategy signals and the broker. Implemented in phase 3."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tradebot.config import PortfolioConfig, RiskConfig, Universe
from tradebot.execution.broker import Broker
from tradebot.strategies.base import BarContext
from tradebot.types import TargetPosition


@dataclass
class RiskManager:
    portfolio: PortfolioConfig
    risk: RiskConfig
    universe: Universe
    halted: bool = False  # set by the kill switch; persisted in live; manual reset only

    def approve(
        self, candidates: Sequence[TargetPosition], ctx: BarContext, broker: Broker
    ) -> list[TargetPosition]:
        """Filter ranked candidates: halt/daily-loss gate, free slots (max_positions),
        no duplicate symbols, shorts only if allowed and shortable, gross <= max_gross."""
        raise NotImplementedError("phase 3")

    def size(self, target: TargetPosition, equity: float, price: float) -> int:
        """Whole shares, floored, within the per-position cap (20% stock / 25% ETF)."""
        raise NotImplementedError("phase 3")

    def daily_loss_hit(self, equity: float, start_of_day_equity: float) -> bool:
        raise NotImplementedError("phase 3")

    def kill_switch_hit(self, equity: float, peak_equity: float) -> bool:
        """Drawdown from peak >= max_drawdown_kill -> caller flattens and sets `halted`."""
        raise NotImplementedError("phase 3")
