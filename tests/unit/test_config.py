from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tradebot.config import AlpacaSecrets, load_config
from tradebot.types import AssetClass


def test_default_config_loads() -> None:
    cfg = load_config()
    assert cfg.portfolio.max_positions == 5
    assert cfg.exits.tp_mult == 2.0
    assert cfg.exits.sl_mult == 1.0
    assert cfg.path(cfg.live.state_db).is_absolute()


def test_breakeven_win_rate() -> None:
    assert load_config().exits.breakeven_win_rate == pytest.approx(1 / 3)


def test_hash_is_stable_and_sensitive() -> None:
    a, b = load_config(), load_config()
    assert a.config_hash() == b.config_hash()
    changed = load_config(overrides={"exits": {"tp_mult": 2.5}})
    assert changed.config_hash() != a.config_hash()


def test_hash_independent_of_checkout_location(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    (tmp_path / "config").mkdir()
    for name in ("default.yaml", "universe.yaml"):
        (tmp_path / "config" / name).write_text((repo / "config" / name).read_text())
    assert load_config(tmp_path / "config" / "default.yaml").config_hash() == (
        load_config().config_hash()
    )


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        load_config(overrides={"exits": {"tp_mul": 3.0}})


def test_cap_above_gross_rejected() -> None:
    with pytest.raises(ValidationError):
        load_config(overrides={"portfolio": {"max_gross": 0.2, "cap_etf": 0.25}})


def test_stress_multipliers_need_baseline() -> None:
    with pytest.raises(ValidationError):
        load_config(overrides={"costs": {"stress_multipliers": [2.0, 3.0]}})


def test_live_trading_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setenv("ALPACA_PAPER", "false")
    with pytest.raises(ValidationError):
        AlpacaSecrets(_env_file=None)


def test_secrets_not_in_config_dump() -> None:
    dump = str(load_config().model_dump()).lower()
    assert "api_key" not in dump and "secret" not in dump


def test_asset_class() -> None:
    u = load_config().universe
    assert u.asset_class("SPY") is AssetClass.ETF
    assert u.asset_class("AAPL") is AssetClass.STOCK
    with pytest.raises(KeyError):
        u.asset_class("NOPE")
