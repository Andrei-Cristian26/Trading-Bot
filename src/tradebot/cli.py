"""`tradebot` command line. Holdout data is reachable ONLY via the `holdout` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from tradebot.config import DEFAULT_CONFIG, load_config

app = typer.Typer(no_args_is_help=True, add_completion=False)

ConfigOpt = Annotated[Path, typer.Option("--config", "-c", help="Config YAML")]
HoldoutFlag = Annotated[bool, typer.Option("--holdout", help="Required: unlocks holdout data")]


@app.command()
def config(path: ConfigOpt = DEFAULT_CONFIG) -> None:
    """Validate the config and print its hash."""
    cfg = load_config(path)
    u = cfg.universe
    typer.echo(f"config ok  hash={cfg.config_hash()[:12]}")
    typer.echo(f"universe: {len(u.etfs)} ETFs, {len(u.stocks)} stocks")
    typer.echo(f"break-even win rate (gross): {cfg.exits.breakeven_win_rate:.1%}")


def _todo(phase: int) -> None:
    typer.echo(f"not implemented yet (phase {phase})", err=True)
    raise typer.Exit(1)


@app.command()
def data(
    path: ConfigOpt = DEFAULT_CONFIG,
    symbols: Annotated[str | None, typer.Option(help="Comma-separated; default: universe")] = None,
    start: Annotated[str | None, typer.Option(help="YYYY-MM-DD; default: data.start")] = None,
    workers: Annotated[int, typer.Option(min=1, max=8)] = 4,
) -> None:
    """Download / update raw 1-minute bars (resumable; safe to re-run)."""
    from datetime import date

    from tradebot.config import AlpacaSecrets
    from tradebot.data.download import download_universe
    from tradebot.data.store import Store

    cfg = load_config(path)
    universe = list(cfg.universe.symbols)
    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else universe
    results = download_universe(
        syms,
        Store(cfg.path(cfg.data.store_dir)),
        date.fromisoformat(start) if start else cfg.data.start,
        cfg.data.feed_hist,
        AlpacaSecrets(),
        workers=workers,
    )
    failed = sorted(set(syms) - set(results))
    typer.echo(f"done: {len(results)}/{len(syms)} symbols, {sum(results.values())} months fetched")
    if failed:
        typer.echo(f"FAILED: {', '.join(failed)} (re-run to resume)", err=True)
        raise typer.Exit(1)


@app.command()
def backtest(path: ConfigOpt = DEFAULT_CONFIG) -> None:
    """Walk-forward backtest on pre-holdout data, with full report."""
    _todo(3)


@app.command()
def train(path: ConfigOpt = DEFAULT_CONFIG) -> None:
    """Train walk-forward LightGBM models."""
    _todo(4)


@app.command()
def holdout(path: ConfigOpt = DEFAULT_CONFIG, confirm: HoldoutFlag = False) -> None:
    """Single logged evaluation on the locked holdout."""
    if not confirm:
        typer.echo("refusing: pass --holdout to unlock holdout data (run is logged)", err=True)
        raise typer.Exit(2)
    _todo(5)


@app.command()
def live(path: ConfigOpt = DEFAULT_CONFIG) -> None:
    """Run the paper-trading loop."""
    _todo(6)


@app.command()
def compare(path: ConfigOpt = DEFAULT_CONFIG) -> None:
    """Compare paper-trading results against a backtest over the same period."""
    _todo(6)
