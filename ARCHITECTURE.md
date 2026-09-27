# Architecture

Read this before changing code.

## What this is
Hourly long/short research + paper-trading system on Alpaca (free tier). A rule-based
baseline and a LightGBM triple-barrier strategy share the same exits, costs, risk, and
execution code. The primary goal is **not fooling ourselves**: correctness over pretty
backtests.

## Layout
```
config/default.yaml     all tunables (validated; unknown keys are errors)
config/universe.yaml    ETFs + stocks (stock -> sector ETF)
config/holdout.lock     frozen holdout start date (committed; never edit by hand)
src/tradebot/
  config.py types.py cli.py
  market_calendar.py    Alpaca sessions (holidays, half days) + hourly bar grid
  data/ features/ labels/ models/ strategies/ risk/ execution/ backtest/ live/ reporting/
tests/unit  tests/anti_bias  tests/data_quality
logs/holdout_runs.jsonl permanent holdout audit log (committed, append-only)
data/                   local only (gitignored), rebuilt with `tradebot data`
  raw/minute/{SYM}/{YYYY-MM}.parquet          complete month, never refetched
  raw/minute/{SYM}/{YYYY-MM}.partial.parquet  current month, refetched every run
```

## Raw data
- Alpaca 1-min SIP bars, stored exactly as received: **unadjusted**, **UTC**, labeled by bar
  **start** time, extended hours included. One file per symbol per ET calendar month.
- Regular session = bar starts 09:30-15:59 ET. Alpaca also returns a 16:00 bar (the post-close
  minute), which is not part of the session.
- `tradebot data` is resumable and idempotent: re-run it any time to fill gaps or update.
  Full history is ~8.5k files, takes ~1 h on the free-tier rate limit, and uses a few GB.
- Holdout-period data IS downloaded; the holdout guard lives in the feed/loader layer.

## Data flow
```
Alpaca 1-min SIP bars -> session-aligned hourly bars (Parquet) -> DataFeed (clock-guarded)
  -> features -> Strategy.on_bar -> Signals -> RiskManager.approve/size -> Broker
Backtest: HistoricalFeed + SimBroker.   Live: LiveFeed + AlpacaPaperBroker.   Nothing else differs.
```

### Minute -> hourly bars (`data/resample.py`)
- Alpaca labels minute bars by their START time, in UTC.
- A minute starting at t is kept only if `open <= t < close` for its session (from
  `MarketCalendar`). This drops pre/post-market, holidays, and the post-close minute that
  starts at 16:00 ET (13:00 on half days).
- Buckets are anchored at the session open, 1 hour long, the last one truncated at the close:
  7 bars on a full day, 4 on a half day. Each bar is labeled by its END time in
  America/New_York.
- Empty buckets produce no row (nothing is forward-filled); `n_minutes` counts the minute
  bars in each bucket. Pass `now=` whenever the minute data may stop mid-bucket, so an
  unfinished bucket is never emitted as a complete bar.

## Invariants (every change must preserve these; most are enforced by tests)
1. **Data <= now.** Bars are labeled by their END timestamp. Strategies and features only see
   data through `DataFeed`, which never returns a bar ending after `feed.now`.
   Daily aggregates (ATR) use completed sessions only.
2. **Volume lag.** Volume/VWAP features use only bars ended >= `data.volume_lag_minutes`
   (15) before `now`, so live (IEX feed) and backtest (SIP) see identical volume data.
3. **Fills.** Signal at bar close t, entry at the open of bar t+1 (+ slippage). A gap
   through TP/SL fills at the open. A bar touching both TP and SL counts as SL. Time exit =
   close of the 5th trading day after entry.
4. **Barriers** are absolute raw prices: `close_t +/- mult * ATR14_daily`, fixed at signal time.
   The same formula is used by labels, backtest, and live bracket orders.
5. **Costs everywhere.** Labels, backtests, and the entry threshold all use `CostModel`. Every
   report shows 1x/2x/3x costs.
6. **Holdout is locked.** Any data at or after the `holdout.lock` date raises
   `HoldoutAccessError`, except via `tradebot holdout --holdout`, which appends to
   `logs/holdout_runs.jsonl`. Never tune anything (tp/sl mults, thresholds, features) on
   holdout results.
7. **Walk-forward only.** No random CV or shuffling. Train/test splits are purged of
   overlapping labels and embargoed by `model.embargo_days`.
8. **Paper only.** `AlpacaSecrets` refuses `ALPACA_PAPER=false`.
9. **Stocks have survivorship bias.** Always report ETF and stock results separately and
   label stock results as optimistic.
10. **Suspicious results are bugs until proven otherwise** (Sharpe > 3, win rate > 70%).

## Conventions
- Python 3.12, uv, `src/` layout, pandas. Timestamps are tz-aware `America/New_York`.
- Features are normalized ratios, never raw prices. Each feature is registered by name
  (`features/registry.py`) so `features.drop` in config can remove it.
- Config: add every tunable to `config/default.yaml` + its pydantic model. No magic numbers
  in strategy/risk code. `config_hash()` identifies a run; secrets are never in it.
- Secrets live only in `.env` (gitignored). Never log or print them.
- Logging: structlog, key-value events (`log.info("order_submitted", symbol=..., qty=...)`).
- Tests: any change touching data access, features, labels, or fills needs a test. Truncation
  lookahead tests live in `tests/anti_bias/`. Network tests are marked `@pytest.mark.network`.
- Before pushing: `uv run pre-commit run --all-files && uv run pytest`.
- Commits: plain descriptive messages.

## Commands
```
uv sync                                  install
uv run tradebot config                   validate config, print hash
uv run tradebot data [--symbols SPY,QQQ] download/update raw minute bars
uv run tradebot backtest                 backtest + report             (phase 3)
uv run tradebot train                    walk-forward models           (phase 4)
uv run tradebot holdout --holdout        single logged holdout run     (phase 5)
uv run tradebot live                     paper trading loop            (phase 6)
```
