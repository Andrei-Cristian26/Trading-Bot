from __future__ import annotations

import pytest
from pydantic import ValidationError

from tradebot.config import Universe, load_config

REQUIRED_ETFS = {"SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU",
                 "XLB", "XLRE", "XLC"}  # fmt: skip


def test_default_universe() -> None:
    u = load_config().universe
    assert set(u.etfs) == REQUIRED_ETFS
    assert 45 <= len(u.stocks) <= 60
    assert len(set(u.symbols)) == len(u.symbols)
    assert all(u.sector_etf(s) in u.etfs for s in u.stocks)
    assert set(u.market_context) == {"SPY", "QQQ"}


def test_duplicate_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        Universe(market_context=("SPY",), etfs=("SPY", "XLK"), stocks={"SPY": "XLK"})


def test_unknown_sector_rejected() -> None:
    with pytest.raises(ValidationError, match="sector ETF"):
        Universe(market_context=("SPY",), etfs=("SPY",), stocks={"AAPL": "XLK"})


def test_lowercase_rejected() -> None:
    with pytest.raises(ValidationError, match="uppercase"):
        Universe(market_context=("SPY",), etfs=("SPY", "XLK"), stocks={"aapl": "XLK"})
