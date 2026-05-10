"""Central config for thresholds, paths, magic numbers.

All scorer thresholds and pipeline parameters live here. Modes pick from
this menu — they don't define their own thresholds.
"""
from pathlib import Path

# === Paths ===
CACHE_DIR = Path.home() / ".cache" / "ema-scanner"

# === Universe (NASDAQ screener) ===
UNIVERSE_API = "https://api.nasdaq.com/api/screener/stocks"
UNIVERSE_PAGE_SIZE = 5000
UNIVERSE_MAX_OFFSET = 10000
UNIVERSE_RETRY_COUNT = 3
UNIVERSE_RETRY_BACKOFF_S = 5  # linear: 5, 10, 15

# === Universe filtering: non-equity blocklist ===
# Names containing any of these substrings are dropped (case-insensitive).
NON_EQUITY_NAME_KEYWORDS = [
    "Notes due",
    "% Notes",
    "Preferred",
    "Trust",
    "Fund",
    "Acquisition Corp",
    "Warrant",
    "Unit",
    "Right",
    "Senior",
    "Subordinated",
    "Fixed-to-Floating",
    "Convertible",
    "Depositary Shares",
    "Municipals",         # closed-end muni bond funds (BNY Mellon Strategic Municipals etc.)
    "Cmn Shs of BI",      # closed-end fund "Common Shares of Beneficial Interest"
    "Mortgage Capital",   # mortgage REITs trade like bonds, not common equity (e.g. INVESCO Mortgage Capital)
]
# Symbol suffixes that typically mean warrant/unit/right (only triggers on 5+ char tickers).
NON_EQUITY_TICKER_SUFFIXES = ("W", "U", "R")

# === Default market cap range (millions USD) ===
DEFAULT_MIN_MC_M = 200
DEFAULT_MAX_MC_M = 1000

# === yfinance batching ===
YF_BATCH_SIZE = 50
YF_DEFAULT_PERIOD = "6mo"
YF_INTER_BATCH_SLEEP_S = 0.5
YF_MIN_ROWS = 50
YF_TIMEOUT_S = 20

# === Supabase ===
SUPABASE_BATCH_INSERT = 500

# === Scorer: compression ===
COMPRESSION_SCORE_MAX_SPREAD_PCT = 5.0  # 0% spread → 100, 5%+ spread → 0 (linear decay)
COMPRESSION_DEFAULT_MAX_SPREAD = 3.0    # gate on this in compression mode

# === Scorer: flat_against_band ===
FLAT_THRESHOLD_PCT = 1.5
FLAT_DECAY_LIMIT_PCT = 5.0

# === Scorer: squeeze ===
SQUEEZE_OVERHEAD_MAX_PCT = 5.0
SQUEEZE_SLOPE_LOOKBACK = 5

# === Scorer: weekly_setup ===
WEEKLY_CROSS_LOOKBACK_WEEKS = 4

# === Scorer: base_break ===
BASE_BREAK_LOOKBACK_MONTHS = 60   # 5 years
BASE_BREAK_VOL_MULTIPLIER = 1.5
BASE_BREAK_VOL_LOOKBACK_MONTHS = 12

# === Scorer: volume_profile ===
VOL_PROFILE_RECENT = 5
VOL_PROFILE_BASELINE = 50
VOL_PROFILE_ANOMALY_RATIO = 3.0

# === Output / display ===
DEFAULT_TOP_N = 20
NAME_TRUNCATE = 40
