# Trading-Bot

An hourly long/short trading system: research first, then Alpaca paper trading. The
backtest and live runs share the same feature, strategy, risk and cost code.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design, the rules that keep backtests honest,
and coding conventions.

## Status
- [x] Phase 1: scaffold, config, interfaces
- [ ] Phase 2: data pipeline (downloader done; resampling, adjustment, holdout lock to do)
- [ ] Phase 3: backtester, baseline strategy, reports
- [ ] Phase 4: features, labels, walk-forward LightGBM
- [ ] Phase 5: holdout evaluation
- [ ] Phase 6: live paper runner

## Setup (macOS)
```sh
brew install uv libomp          # libomp is needed by LightGBM
git clone git@github.com:Andrei-Cristian26/Trading-Bot.git && cd Trading-Bot
uv sync                         # creates .venv with Python 3.12 + all deps
uv run pre-commit install       # ruff + mypy on every commit
cp .env.example .env            # then add your Alpaca PAPER keys
uv run pytest
uv run tradebot config          # validates config, prints its hash
```
On Linux, install `libgomp1` instead of `libomp`.

Alpaca keys: sign up at alpaca.markets, switch to the **Paper** account, and generate
API keys. The free plan is enough. Never commit `.env`.

## Key design choices
- **Bars:** built from 1-minute SIP bars into session-aligned hourly buckets:
  09:30–10:30, …, 14:30–15:30, then 15:30–16:00 as a final 30-minute bar. This gives 7 bars
  per full day, truncated on half days, and follows the Alpaca market calendar. A bar is
  timestamped by its end time.
- **History:** 2016 to today. The most recent 18 months are a locked holdout, reachable
  only via `tradebot holdout --holdout`, and every run is logged.
- **Exits:** ATR-scaled take-profit/stop-loss (defaults 2x / 1x daily ATR14), a 5-trading-day
  time limit, and signal reversal. Live TP/SL are server-side bracket orders.
- **Costs:** slippage + half-spread (2 bps ETFs, 5 bps stocks per side), SEC/FINRA sell
  fees and short borrow. They're included in labels, and results are stress-tested at 2x/3x.
- **Universe:** 15 ETFs + ~50 current large caps in `config/universe.yaml`. The stock list
  has survivorship bias, so stock results are reported separately and treated as optimistic.
