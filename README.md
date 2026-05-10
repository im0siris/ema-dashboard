# EMA Scanner

A modular, multi-mode stock screener that scans the US equity universe for technical setups built on moving-average geometry. Designed for swing traders and position investors who want to systematically surface candidates instead of eyeballing thousands of charts.

## What it does

Given a stock universe filtered by market cap, the scanner downloads daily OHLCV data, computes a standard set of moving averages (9 EMA, 21 EMA, 50/100/200 SMA), and runs configurable **scorer modules** against each ticker to identify specific setups.

Modes combine scorers with different weights and thresholds. The output is a ranked list (CSV, optional Supabase persistence) of candidates that match the criteria for that mode.

## Modes

| Mode | What it finds | Primary use case |
|------|---------------|------------------|
| `compression` | Stocks where 9 EMA, 21 EMA, and 50 SMA are tightly clustered (low spread %) | Pre-breakout candidates — direction agnostic |
| `stw-trade` | Price flat against the 9/21 EMA band, bullish MA stack, weekly chart confirms | Standard swing-trade entry setup |
| `stw-squeeze` | Price pinched between rising small EMAs and an overhead larger SMA (100/200) | Explosive breakout candidates |
| `stw-base-break` | Multi-year base breakouts on the monthly chart with volume confirmation | Long-term position entries |

Each mode applies a **market regime gate** (SPY/QQQ vs. 50/200 DMA) that runs once per scan and either gates execution, warns, or is ignored depending on mode configuration.

## Architecture

```
ema-scanner/
├── scanner.py           # CLI entry point
├── config.py            # All thresholds, keyword lists, defaults
├── universe.py          # NASDAQ screener fetch + non-equity filter
├── data.py              # yfinance wrapper, batch download, disk cache, weekly/monthly resampling
├── indicators.py        # MA computation (vectorized, returns augmented DataFrame)
├── regime.py            # Market regime gate (SPY/QQQ)
├── scorers/             # One file per setup detector
│   ├── base.py          # Scorer ABC
│   ├── compression.py
│   ├── alignment.py
│   ├── flat_against_band.py
│   ├── squeeze.py
│   ├── weekly_setup.py
│   ├── base_break.py
│   └── volume_profile.py
├── modes.py             # Mode definitions: scorers, weights, thresholds, regime policy
├── output.py            # CSV / Supabase / console formatting
├── tests/               # Pytest, synthetic OHLCV fixtures
└── legacy/              # Pre-refactor scanner + migration SQL + baseline CSVs
```

**Key design choices:**

- **Modular scorers.** Each scorer implements a common ABC (`score(frames, regime) -> ScoreResult`) and declares its required timeframes. Adding a new setup means adding one file.
- **Single MA computation.** `indicators.add_mas(df)` is the only place EMAs/SMAs are calculated. Scorers consume the augmented DataFrame.
- **Daily download, derive weekly/monthly via resampling.** No separate yfinance calls per timeframe — this avoids partial-period boundary issues with yfinance's native intervals.
- **Disk cache.** All yfinance responses cached under `~/.cache/ema-scanner/{YYYY-MM-DD}/` so same-day reruns are instant. `--no-cache` and `--clear-cache` flags available.
- **Aggressive non-equity filter.** Preferreds, notes, warrants, units, SPACs, and similar instruments are excluded by default via suffix and name-keyword heuristics. Bypass with `--include-non-equity`.
- **JSONB scorer outputs.** Supabase results table uses a JSONB column for per-scorer scores, so adding scorers does not require schema migrations.

## Installation

Requires Python 3.8+.

```bash
git clone https://github.com/im0siris/ema-scanner.git
cd ema-scanner
pip install -r requirements.txt
```

Dependencies: `yfinance`, `pandas`, `pytest`. Supabase persistence is optional and uses `urllib` from the standard library.

## Usage

```bash
# Default: compression mode, $200M-$1B market cap range
python scanner.py

# Specific mode
python scanner.py --mode stw-trade --top 30

# Custom market cap range (in millions)
python scanner.py --mode compression --min-mc 500 --max-mc 5000

# Skip cache, skip database, write to specific output
python scanner.py --mode stw-squeeze --no-cache --no-db --output results.csv

# List available modes
python scanner.py --list-modes

# Show what a mode does
python scanner.py --explain-mode stw-trade
```

## Configuration

All scorer thresholds and filter lists live in `config.py`. Common things you might want to adjust:

- `FLAT_THRESHOLD_PCT` — distance from the 9/21 EMA band that still counts as "flat"
- `SQUEEZE_OVERHEAD_MAX_PCT` — how close to the overhead MA price must be for a squeeze setup
- `NON_EQUITY_NAME_KEYWORDS` — keyword blocklist for the universe filter
- `DEFAULT_BATCH_SIZE` — number of tickers downloaded per yfinance call

## Supabase persistence (optional)

To persist scan results, set `SUPABASE_URL` and `SUPABASE_KEY` environment variables and run the migration once:

```bash
# In Supabase SQL Editor, paste and run:
legacy/migrations/001_recreate_tables.sql
```

This creates `scan_runs` (one row per `(invocation_id, mode)` pair) and `scan_results` (one row per ticker per mode, with `scorer_scores` as JSONB). All non-`--no-db` runs write to these tables.

## Testing

```bash
pytest tests/
```

Tests use synthetic OHLCV fixtures — no live yfinance calls. Each scorer has high-score, zero-score, and edge-case fixtures.

## Roadmap

- [ ] Earnings-date annotation (warn when a candidate has earnings within 14 days)
- [ ] Backtest harness — replay scanner against historical universe snapshots
- [ ] Optional fundamental overlay (revenue growth, gross margin) as soft scorer
- [ ] Slack/Discord webhook for daily candidates

## Out of scope

- Pattern detection (flags, pennants, head-and-shoulders) — too pattern-matching, too noisy
- Short interest — data sources are unreliable without a paid feed
- Real-time / intraday scanning — daily-close-based by design
- Web UI / dashboard — this is a CLI tool

## License

BUSL-1.1

## Disclaimer

This tool surfaces technical setups based on price and volume. It does not constitute investment advice. Trade your own thesis, manage your own risk.
