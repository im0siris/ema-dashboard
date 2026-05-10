# EMA Scanner v3

Multi-mode SMID-cap setup scanner. Daily/weekly/monthly EMA & SMA signals, market-regime gating, Supabase persistence.

## Quickstart

```
pip install -r requirements.txt
cp .env.example .env       # fill in Supabase creds, or always pass --no-db
python scanner.py --mode compression
```

## CLI

| Flag | Default | Notes |
|------|---------|-------|
| `--mode NAME` | required | See `--list-modes` |
| `--list-modes` | – | List modes; stubs flagged |
| `--min-mc N --max-mc N` | 200 / 1000 | Market cap range in $M |
| `--top N` | 20 | Top N rows in console |
| `--output path.csv` | – | Also write CSV |
| `--no-cache` | off | Bypass disk cache |
| `--clear-cache` | – | Wipe cache and exit |
| `--include-non-equity` | off | Skip preferreds/notes/SPAC filter |
| `--no-db` | off | Skip Supabase write |
| `--no-regime` | off | Skip SPY/QQQ regime computation |

## Modes

- `compression` — implemented. EMA9/EMA21/SMA50 compression, BULLISH alignment, close > SMA50.
- `full_setup` — STUB. Composite of alignment + flat_against_band + squeeze + weekly_setup + base_break + volume_profile. Scorers raise `NotImplementedError` until filled in.

## Architecture

```
scanner.py        # CLI dispatch
config.py         # All thresholds, paths
universe.py       # NASDAQ fetch + non-equity filter
data.py           # yfinance + disk cache + resample
indicators.py     # EMA/SMA/volume column augmentation
regime.py         # SPY/QQQ regime gate
output.py         # Console / CSV / Supabase REST
modes.py          # Mode = scorers + weights + gates + sort key
scorers/
  base.py            # Scorer ABC
  compression.py     # implemented
  flat_against_band.py / alignment.py / squeeze.py /
  weekly_setup.py / base_break.py / volume_profile.py   # stubs
tests/test_scorers.py
legacy/                # scanner-v2.py + baseline CSV + SQL migrations
```

## Cache

`~/.cache/ema-scanner/{YYYY-MM-DD}/` — pickle-cached daily OHLCV per ticker plus universe.json. Same-day reruns are instant; next-day runs miss naturally.

## Database migration

Before first run with Supabase enabled, execute `legacy/migrations/001_recreate_tables.sql` against your Supabase project. The v3 schema differs from v2.

## Tests

```
python -m pytest
```
