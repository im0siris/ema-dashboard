"""NASDAQ universe fetch + non-equity filtering + market-cap filtering."""
import json
import time
import urllib.request
from datetime import date
from pathlib import Path

import config


def fetch(use_cache: bool = True) -> list[dict]:
    """Returns raw universe rows from NASDAQ. Cached per-day on disk."""
    if use_cache:
        cached = _load_cached_universe()
        if cached is not None:
            print(f"  Using cached universe ({len(cached)} rows)")
            return cached

    print("  Fetching universe from NASDAQ screener...")
    rows = _fetch_uncached()
    if use_cache:
        _save_cached_universe(rows)
    return rows


def _cache_path() -> Path:
    today = date.today().isoformat()
    p = config.CACHE_DIR / today / "universe.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_cached_universe() -> list[dict] | None:
    p = _cache_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cached_universe(rows: list[dict]) -> None:
    p = _cache_path()
    p.write_text(json.dumps(rows), encoding="utf-8")


def _fetch_uncached() -> list[dict]:
    all_rows: list[dict] = []
    for offset in range(0, config.UNIVERSE_MAX_OFFSET, config.UNIVERSE_PAGE_SIZE):
        url = (
            f"{config.UNIVERSE_API}?tableType=traded"
            f"&limit={config.UNIVERSE_PAGE_SIZE}&offset={offset}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        page_rows: list[dict] | None = None
        for attempt in range(1, config.UNIVERSE_RETRY_COUNT + 1):
            try:
                response = urllib.request.urlopen(req, timeout=30)
                data = json.loads(response.read())
                page_rows = data["data"]["table"]["rows"]
                all_rows.extend(page_rows)
                print(f"    Fetched {len(all_rows)} stocks so far...")
                break
            except Exception as e:
                wait = attempt * config.UNIVERSE_RETRY_BACKOFF_S
                print(f"    Attempt {attempt}/{config.UNIVERSE_RETRY_COUNT} failed: {str(e)[:80]}")
                if attempt < config.UNIVERSE_RETRY_COUNT:
                    print(f"    Retrying in {wait}s...")
                    time.sleep(wait)

        if page_rows is None:
            if all_rows:
                print(f"    Could not fetch more, continuing with {len(all_rows)} loaded.")
                break
            raise RuntimeError("Could not fetch NASDAQ universe after retries")

        if len(page_rows) < config.UNIVERSE_PAGE_SIZE:
            break
        time.sleep(2)

    print(f"  Total stocks in universe: {len(all_rows)}")
    return all_rows


def is_common_equity(stock: dict) -> bool:
    """Heuristic filter — drops preferreds, notes, trusts, SPACs, warrants, etc.

    Two cumulative checks:
      1. Name substring match against config.NON_EQUITY_NAME_KEYWORDS.
      2. Symbol suffix (>=5 chars) ending in W/U/R typically indicates
         warrant / unit / right.
    """
    name = (stock.get("name") or "").lower()
    symbol = (stock.get("symbol") or "").upper()

    for kw in config.NON_EQUITY_NAME_KEYWORDS:
        if kw.lower() in name:
            return False

    if len(symbol) >= 5 and symbol[-1] in config.NON_EQUITY_TICKER_SUFFIXES:
        return False

    return True


def parse_market_cap(mc_string: str | None) -> int:
    if not mc_string or mc_string in ("", "NA", "N/A"):
        return 0
    try:
        return int(str(mc_string).replace(",", ""))
    except ValueError:
        return 0


def filter_by_market_cap(stocks: list[dict], min_mc_m: float, max_mc_m: float) -> list[dict]:
    """Returns simplified stock dicts inside the market-cap range."""
    min_mc = min_mc_m * 1_000_000
    max_mc = max_mc_m * 1_000_000
    out = []
    for stock in stocks:
        mc = parse_market_cap(stock.get("marketCap", ""))
        if min_mc <= mc <= max_mc:
            out.append({
                "symbol": stock["symbol"],
                "name": stock["name"],
                "market_cap": mc,
            })
    return out
