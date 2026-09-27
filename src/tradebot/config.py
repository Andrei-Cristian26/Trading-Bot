"""Typed configuration: YAML tunables (AppConfig) + secrets from .env (AlpacaSecrets).

Secrets are deliberately a separate object so they can never leak into config dumps,
config hashes, reports, or the holdout log.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, time
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tradebot.types import AssetClass

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataConfig(_Strict):
    start: date
    holdout_months: int = Field(gt=0)
    feed_hist: Literal["sip", "iex"]
    feed_live: Literal["sip", "iex"]
    volume_lag_minutes: int = Field(ge=0)
    store_dir: Path


class BarsConfig(_Strict):
    timeframe: Literal["1h"]
    session_open: time


class PortfolioConfig(_Strict):
    initial_equity: float = Field(gt=0)
    max_positions: int = Field(gt=0)
    max_gross: float = Field(gt=0, le=1.0)
    cap_stock: float = Field(gt=0, le=1.0)
    cap_etf: float = Field(gt=0, le=1.0)
    allow_short: bool

    @model_validator(mode="after")
    def _caps_within_gross(self) -> Self:
        if max(self.cap_stock, self.cap_etf) > self.max_gross:
            raise ValueError("per-position cap exceeds max_gross")
        return self


class ExitsConfig(_Strict):
    atr_period: int = Field(gt=1)
    tp_mult: float = Field(gt=0)
    sl_mult: float = Field(gt=0)
    max_hold_days: int = Field(gt=0)
    reversal_exit: bool

    @property
    def breakeven_win_rate(self) -> float:
        """Gross break-even win rate if every trade exits at TP or SL (costs make it higher)."""
        return self.sl_mult / (self.tp_mult + self.sl_mult)


class CostsConfig(_Strict):
    slip_bps_etf: float = Field(ge=0)
    slip_bps_stock: float = Field(ge=0)
    sec_fee_per_million: float = Field(ge=0)
    finra_taf_per_share: float = Field(ge=0)
    finra_taf_max_per_trade: float = Field(ge=0)
    borrow_apr: float = Field(ge=0)
    stress_multipliers: tuple[float, ...]

    @model_validator(mode="after")
    def _includes_baseline(self) -> Self:
        if 1.0 not in self.stress_multipliers:
            raise ValueError("stress_multipliers must include 1.0")
        return self


class RiskConfig(_Strict):
    daily_loss_limit: float = Field(gt=0, lt=1)
    max_drawdown_kill: float = Field(gt=0, lt=1)


class StrategyConfig(_Strict):
    name: Literal["baseline", "ml"]
    entry_threshold: float = Field(gt=0, lt=1)
    min_edge_bps: float = Field(ge=0)


class FeaturesConfig(_Strict):
    drop: tuple[str, ...] = ()


class ModelConfig(_Strict):
    train_years: int = Field(gt=0)
    test_months: int = Field(gt=0)
    embargo_days: int = Field(ge=0)
    seed: int
    lgbm: dict[str, Any]


class LiveConfig(_Strict):
    bar_delay_s: int = Field(ge=0)
    state_db: Path
    lock_ttl_s: int = Field(gt=0)


class SanityConfig(_Strict):
    max_sharpe: float = Field(gt=0)
    max_win_rate: float = Field(gt=0, le=1)


class Universe(_Strict):
    market_context: tuple[str, ...]
    etfs: tuple[str, ...]
    stocks: dict[str, str]  # symbol -> sector ETF

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        symbols = [*self.etfs, *self.stocks]
        dupes = {s for s in symbols if symbols.count(s) > 1}
        if dupes:
            raise ValueError(f"duplicate symbols: {sorted(dupes)}")
        bad_case = [s for s in symbols if s != s.upper()]
        if bad_case:
            raise ValueError(f"symbols must be uppercase: {bad_case}")
        missing_sector = {s: e for s, e in self.stocks.items() if e not in self.etfs}
        if missing_sector:
            raise ValueError(f"sector ETF not in etfs: {missing_sector}")
        missing_ctx = [s for s in self.market_context if s not in self.etfs]
        if missing_ctx:
            raise ValueError(f"market_context symbols not in etfs: {missing_ctx}")
        return self

    @property
    def symbols(self) -> tuple[str, ...]:
        return (*self.etfs, *self.stocks)

    def asset_class(self, symbol: str) -> AssetClass:
        if symbol in self.etfs:
            return AssetClass.ETF
        if symbol in self.stocks:
            return AssetClass.STOCK
        raise KeyError(f"{symbol} not in universe")

    def sector_etf(self, symbol: str) -> str | None:
        return self.stocks.get(symbol)


class AppConfig(_Strict):
    data: DataConfig
    universe_file: Path
    bars: BarsConfig
    portfolio: PortfolioConfig
    exits: ExitsConfig
    costs: CostsConfig
    risk: RiskConfig
    strategy: StrategyConfig
    features: FeaturesConfig
    model: ModelConfig
    live: LiveConfig
    sanity: SanityConfig
    universe: Universe

    # Not part of the dump/hash: the hash must be identical on every machine.
    _root: Path = PrivateAttr(default=REPO_ROOT)

    def path(self, p: Path) -> Path:
        """Resolve a config path against the repo root."""
        return p if p.is_absolute() else self._root / p

    def config_hash(self) -> str:
        """Stable sha256 of the resolved config (universe included, secrets excluded)."""
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def load_config(path: Path = DEFAULT_CONFIG, overrides: dict[str, Any] | None = None) -> AppConfig:
    """Load YAML config + universe. `overrides` is a nested dict merged over the YAML."""
    path = path.resolve()
    root = path.parent.parent
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    if overrides:
        raw = _deep_merge(raw, overrides)
    universe_path = Path(raw["universe_file"])
    if not universe_path.is_absolute():
        universe_path = root / universe_path
    raw["universe"] = yaml.safe_load(universe_path.read_text())
    cfg = AppConfig.model_validate(raw)
    cfg._root = root
    return cfg


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            v = _deep_merge(out[k], v)
        out[k] = v
    return out


class AlpacaSecrets(BaseSettings):
    """Alpaca credentials from environment / .env. Paper trading only, enforced."""

    model_config = SettingsConfigDict(
        env_prefix="ALPACA_", env_file=REPO_ROOT / ".env", extra="ignore", frozen=True
    )

    api_key: SecretStr
    secret_key: SecretStr
    paper: bool = True

    @model_validator(mode="after")
    def _paper_only(self) -> Self:
        if not self.paper:
            raise ValueError("ALPACA_PAPER must be true: this system only trades paper accounts")
        return self
