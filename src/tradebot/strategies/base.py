"""Strategy interface. Identical code runs in backtest and live."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from tradebot.data.feed import DataFeed
from tradebot.types import Position, Side, TargetPosition


@dataclass(frozen=True, slots=True)
class BarContext:
    feed: DataFeed  # clock = feed.now; strategies cannot see past it
    positions: Mapping[str, Position]
    equity: float


@dataclass(frozen=True, slots=True)
class Signals:
    """Output of one on_bar call."""

    entries: list[TargetPosition]  # candidates ranked by score, descending; risk picks from these
    directions: Mapping[str, Side]  # current signal per scored symbol (FLAT if below threshold);
    # the engine uses this for reversal exits: an open position exits if its direction flips.


class Strategy(Protocol):
    name: str

    def on_bar(self, ctx: BarContext) -> Signals:
        """Called once per hourly bar close. Must be a pure function of ctx.feed data <= now."""
        ...
