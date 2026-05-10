"""
EMA/SMA Compression Scanner v2 — with Supabase Integration
============================================================
Same scanning logic as v1, but now pushes results to a Supabase
database instead of (or in addition to) CSV files. This gives you:
  - Historical scan data across days/weeks/months
  - A real database you can query from a web dashboard
  - No more Excel sheet management

SETUP:
  1. pip install yfinance pandas ta python-dotenv
  2. Create a .env file with your Supabase credentials (see .env.example)
  3. Run the SQL migration in Supabase to create the tables
  4. python scanner.py

The scanner can also still export to CSV with --output flag.
"""

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

# python-dotenv loads variables from a .env file into os.environ
# This keeps your Supabase credentials out of the code
from dotenv import load_dotenv

# Load .env file from the same directory as this script
load_dotenv()


# =============================================================================
# SUPABASE CONNECTION (via REST API — no SDK needed)
# =============================================================================
# Instead of the heavy `supabase` Python SDK (which has build issues on
# Python 3.14), we talk directly to the Supabase REST API using urllib.
# Supabase exposes a PostgREST API at your-project.supabase.co/rest/v1/
# that accepts simple HTTP requests with JSON bodies.
# This is lighter, has zero dependencies, and works on any Python version.
# =============================================================================

class SupabaseREST:
    """
    Minimal Supabase client using only urllib (no extra dependencies).

    Supabase's REST API is just PostgREST — you send HTTP requests with
    your API key in the headers and JSON data in the body.
    """

    def __init__(self, url: str, key: str):
        # The REST endpoint is always at /rest/v1/
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": key,                    # Required: your anon key
            "Authorization": f"Bearer {key}", # Required: same key as Bearer token
            "Content-Type": "application/json",
            "Prefer": "return=representation", # Makes INSERT return the created row
        }

    def insert(self, table: str, data: dict | list) -> dict:
        """
        Insert one row (dict) or multiple rows (list of dicts) into a table.

        Args:
            table: Table name (e.g., "scan_runs")
            data: Dict for single row, list of dicts for batch insert

        Returns:
            The inserted row(s) as parsed JSON

        How it works:
            POST https://your-project.supabase.co/rest/v1/scan_runs
            Headers: apikey, Authorization, Content-Type, Prefer
            Body: JSON of the row(s) to insert
        """
        url = f"{self.base_url}/{table}"
        body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=self.headers, method="POST")
        response = urllib.request.urlopen(req, timeout=30)
        return json.loads(response.read())


def get_supabase_client() -> SupabaseREST:
    """
    Creates a Supabase REST client using credentials from .env file.

    Required .env variables:
        SUPABASE_URL=https://your-project.supabase.co
        SUPABASE_KEY=your-anon-key-here

    Where to find these:
        1. Go to your Supabase project dashboard
        2. Settings → API
        3. Copy "Project URL" and "anon/public" key
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Missing Supabase credentials!\n"
            "Create a .env file with:\n"
            "  SUPABASE_URL=https://your-project.supabase.co\n"
            "  SUPABASE_KEY=your-anon-key\n"
            "See .env.example for reference."
        )

    return SupabaseREST(url, key)


# =============================================================================
# SUPABASE: SAVE SCAN RESULTS
# =============================================================================

def save_scan_to_supabase(supabase: SupabaseREST, results: list[dict], params: dict):
    """
    Saves a scan run and its results to Supabase.

    We use two tables:
      - scan_runs: One row per scan execution (timestamp, parameters used)
      - scan_results: One row per stock per scan (the actual findings)

    This two-table design lets you:
      - Compare scans over time ("was AAPL compressed last week too?")
      - Track which parameters you used for each scan
      - Query results by date, spread, alignment, etc.
    """
    # --- Step 1: Create a scan_run record ---
    scan_run = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "min_market_cap_m": params["min_mc"],
        "max_market_cap_m": params["max_mc"],
        "max_spread_pct": params["max_spread"],
        "total_universe": params.get("total_universe", 0),
        "total_filtered": params.get("total_filtered", 0),
        "total_results": len(results),
    }

    response = supabase.insert("scan_runs", scan_run)
    scan_run_id = response[0]["id"]
    print(f"  Created scan run #{scan_run_id}")

    # --- Step 2: Insert all results linked to this scan run ---
    if not results:
        print("  No results to save.")
        return scan_run_id

    # Prepare rows for batch insert
    rows = []
    for r in results:
        rows.append({
            "scan_run_id": scan_run_id,
            "ticker": r["Ticker"],
            "name": r["Name"],
            "market_cap_m": r["MC ($M)"],
            "close_price": r["Close"],
            "ema9": r["EMA9"],
            "ema21": r["EMA21"],
            "sma50": r["SMA50"],
            "spread_pct": r["Spread %"],
            "alignment": r["Alignment"],
            "volume_ratio": r["Vol Ratio"],
        })

    # Batch insert in chunks of 500 to stay within API limits
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        supabase.insert("scan_results", batch)
        print(f"  Saved {min(i + batch_size, len(rows))}/{len(rows)} results...")

    print(f"  All {len(rows)} results saved to Supabase!")
    return scan_run_id


# =============================================================================
# STOCK UNIVERSE (same as v1, with retry logic)
# =============================================================================

def fetch_stock_universe():
    """Fetches all US-traded stocks from the NASDAQ screener API."""
    all_rows = []
    base_url = "https://api.nasdaq.com/api/screener/stocks"

    for offset in range(0, 10000, 5000):
        url = f"{base_url}?tableType=traded&limit=5000&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        success = False
        for attempt in range(1, 4):
            try:
                response = urllib.request.urlopen(req, timeout=30)
                data = json.loads(response.read())
                rows = data["data"]["table"]["rows"]
                all_rows.extend(rows)
                print(f"  Fetched {len(all_rows)} stocks so far...")
                success = True
                break
            except Exception as e:
                wait = attempt * 5
                print(f"  Attempt {attempt}/3 failed: {str(e)[:80]}")
                if attempt < 3:
                    print(f"  Retrying in {wait} seconds...")
                    time.sleep(wait)

        if not success:
            if len(all_rows) > 0:
                print(f"  Could not fetch more stocks, continuing with {len(all_rows)} already loaded.")
                break
            else:
                raise RuntimeError(
                    "Could not connect to NASDAQ API after 3 attempts. "
                    "Check your internet connection and try again."
                )

        if len(data["data"]["table"]["rows"]) < 5000:
            break
        time.sleep(2)

    print(f"  Total stocks in universe: {len(all_rows)}")
    return all_rows


def parse_market_cap(mc_string):
    """Converts market cap string like '500,000,000' to integer."""
    if not mc_string or mc_string in ("", "NA", "N/A"):
        return 0
    try:
        return int(mc_string.replace(",", ""))
    except ValueError:
        return 0


def filter_by_market_cap(stocks, min_mc_millions, max_mc_millions):
    """Filters stocks by market cap range (in millions)."""
    min_mc = min_mc_millions * 1_000_000
    max_mc = max_mc_millions * 1_000_000

    filtered = []
    for stock in stocks:
        mc = parse_market_cap(stock.get("marketCap", ""))
        if min_mc <= mc <= max_mc:
            filtered.append({
                "symbol": stock["symbol"],
                "name": stock["name"],
                "market_cap": mc,
            })

    print(f"  Stocks in ${min_mc_millions}M–${max_mc_millions}M range: {len(filtered)}")
    return filtered


# =============================================================================
# PRICE DATA DOWNLOAD (same as v1 with smaller batches)
# =============================================================================

def download_price_data(tickers, period="6mo"):
    """Downloads daily OHLCV data for a list of tickers using yfinance."""
    batch_size = 50
    all_data = {}
    failed_count = 0

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size
        print(f"  Downloading batch {batch_num}/{total_batches} ({len(batch)} tickers)...", end="", flush=True)

        try:
            raw = yf.download(
                batch,
                period=period,
                progress=False,
                group_by="ticker",
                threads=True,
                timeout=20,
            )

            if raw.empty:
                print(f" [empty result]")
                continue

            if len(batch) == 1:
                ticker = batch[0]
                df = raw.copy()
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(0)
                df = df.dropna()
                if len(df) >= 50:
                    all_data[ticker] = df
            else:
                available_tickers = raw.columns.get_level_values(0).unique()
                batch_success = 0
                for ticker in batch:
                    if ticker in available_tickers:
                        try:
                            df = raw[ticker].dropna()
                            if len(df) >= 50:
                                all_data[ticker] = df
                                batch_success += 1
                        except (KeyError, Exception):
                            failed_count += 1
                            continue
                print(f" [{batch_success} OK]")

        except Exception as e:
            print(f" [ERROR: {str(e)[:50]}]")
            failed_count += 1
            continue

        if i + batch_size < len(tickers):
            time.sleep(0.5)

    print(f"  Successfully downloaded data for {len(all_data)} tickers ({failed_count} failed — this is normal)")
    return all_data


# =============================================================================
# EMA/SMA COMPRESSION CALCULATION (same as v1)
# =============================================================================

def calculate_compression(df):
    """Calculates EMA/SMA compression metrics for a single stock."""
    try:
        close = df["Close"]
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        sma50 = close.rolling(window=50).mean()

        latest_close = close.iloc[-1]
        latest_ema9 = ema9.iloc[-1]
        latest_ema21 = ema21.iloc[-1]
        latest_sma50 = sma50.iloc[-1]

        if pd.isna(latest_sma50):
            return None

        ma_values = [latest_ema9, latest_ema21, latest_sma50]
        spread_pct = (max(ma_values) - min(ma_values)) / latest_close * 100

        if latest_ema9 > latest_ema21 > latest_sma50:
            alignment = "BULLISH"
        elif latest_ema9 < latest_ema21 < latest_sma50:
            alignment = "BEARISH"
        else:
            alignment = "MIXED"

        above_all = latest_close > max(ma_values)
        below_all = latest_close < min(ma_values)

        if "Volume" in df.columns:
            avg_volume_20 = df["Volume"].iloc[-20:].mean()
            recent_volume_5 = df["Volume"].iloc[-5:].mean()
            volume_ratio = recent_volume_5 / avg_volume_20 if avg_volume_20 > 0 else 1.0
        else:
            volume_ratio = 1.0

        return {
            "close": round(float(latest_close), 2),
            "ema9": round(float(latest_ema9), 2),
            "ema21": round(float(latest_ema21), 2),
            "sma50": round(float(latest_sma50), 2),
            "spread_pct": round(float(spread_pct), 2),
            "alignment": alignment,
            "above_all_ma": above_all,
            "below_all_ma": below_all,
            "volume_ratio": round(float(volume_ratio), 2),
        }

    except Exception:
        return None


# =============================================================================
# MAIN SCAN FUNCTION
# =============================================================================

def run_scan(min_mc=200, max_mc=1000, max_spread=3.0, top_n=20, save_to_db=True):
    """
    Main scanning function. Now with optional Supabase integration.

    Args:
        save_to_db: If True, saves results to Supabase. If False, terminal-only.
    """
    print("=" * 60)
    print("  EMA/SMA COMPRESSION SCANNER v2")
    print(f"  Market Cap: ${min_mc}M – ${max_mc}M")
    print(f"  Max Spread: {max_spread}%")
    print(f"  Database: {'Supabase' if save_to_db else 'None (terminal only)'}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # --- Connect to Supabase (if enabled) ---
    supabase = None
    if save_to_db:
        try:
            supabase = get_supabase_client()
            print("\n  Connected to Supabase ✓")
        except Exception as e:
            print(f"\n  Warning: Could not connect to Supabase: {e}")
            print("  Continuing without database. Results will only be in terminal/CSV.")
            save_to_db = False

    # --- Phase 1: Get stock universe ---
    print("\n[1/4] Fetching stock universe from NASDAQ...")
    all_stocks = fetch_stock_universe()

    # --- Phase 2: Filter by market cap ---
    print(f"\n[2/4] Filtering by market cap (${min_mc}M – ${max_mc}M)...")
    filtered_stocks = filter_by_market_cap(all_stocks, min_mc, max_mc)
    tickers = [s["symbol"] for s in filtered_stocks]
    stock_info = {s["symbol"]: s for s in filtered_stocks}

    # --- Phase 3: Download price data ---
    print(f"\n[3/4] Downloading price data for {len(tickers)} stocks...")
    print("  (This may take a few minutes for 1000+ stocks)")
    price_data = download_price_data(tickers)

    # --- Phase 4: Calculate compression ---
    print(f"\n[4/4] Scanning for EMA/SMA compression...")
    results = []

    for ticker, df in price_data.items():
        metrics = calculate_compression(df)
        if metrics and metrics["spread_pct"] <= max_spread:
            info = stock_info.get(ticker, {})
            results.append({
                "Ticker": ticker,
                "Name": info.get("name", "")[:40],
                "MC ($M)": round(info.get("market_cap", 0) / 1_000_000),
                "Close": metrics["close"],
                "EMA9": metrics["ema9"],
                "EMA21": metrics["ema21"],
                "SMA50": metrics["sma50"],
                "Spread %": metrics["spread_pct"],
                "Alignment": metrics["alignment"],
                "Vol Ratio": metrics["volume_ratio"],
            })

    results.sort(key=lambda x: x["Spread %"])
    df_results = pd.DataFrame(results[:top_n])

    # --- Display results ---
    print("\n" + "=" * 60)
    print(f"  RESULTS: {len(results)} stocks with spread < {max_spread}%")
    print(f"  Showing top {min(top_n, len(results))} by tightest compression")
    print("=" * 60)

    if len(df_results) > 0:
        print(df_results.to_string(index=False))
    else:
        print("  No stocks found matching criteria.")

    # --- Save to Supabase ---
    if save_to_db and supabase and len(results) > 0:
        print(f"\n[DB] Saving {len(results)} results to Supabase...")
        scan_params = {
            "min_mc": min_mc,
            "max_mc": max_mc,
            "max_spread": max_spread,
            "total_universe": len(all_stocks),
            "total_filtered": len(filtered_stocks),
        }
        save_scan_to_supabase(supabase, results, scan_params)

    print("\n" + "-" * 60)
    print("  LEGEND:")
    print("  Spread %  = How tight the MAs are (lower = tighter = stronger)")
    print("  Alignment = BULLISH (EMA9>EMA21>SMA50), BEARISH (opposite), MIXED")
    print("  Vol Ratio = Recent 5d volume / 20d average (>1 = increasing volume)")
    print("-" * 60)

    return pd.DataFrame(results)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Scan SMID-cap stocks for EMA/SMA compression setups (v2 with Supabase)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scanner.py                             # Default scan, saves to Supabase
  python scanner.py --no-db                     # Terminal only, no database
  python scanner.py --min-mc 500 --max-mc 2000  # Custom market cap range
  python scanner.py --spread 2.0 --top 10       # Tighter filter
  python scanner.py --output watchlist.csv       # Also save to CSV
        """,
    )

    parser.add_argument("--min-mc", type=float, default=200,
                        help="Minimum market cap in millions (default: 200)")
    parser.add_argument("--max-mc", type=float, default=1000,
                        help="Maximum market cap in millions (default: 1000)")
    parser.add_argument("--spread", type=float, default=3.0,
                        help="Maximum MA spread %% to include (default: 3.0)")
    parser.add_argument("--top", type=int, default=20,
                        help="Number of top results to display (default: 20)")
    parser.add_argument("--output", type=str, default=None,
                        help="Also save full results to CSV file")
    parser.add_argument("--no-db", action="store_true",
                        help="Skip Supabase, terminal output only")

    args = parser.parse_args()

    results_df = run_scan(
        min_mc=args.min_mc,
        max_mc=args.max_mc,
        max_spread=args.spread,
        top_n=args.top,
        save_to_db=not args.no_db,
    )

    if args.output and len(results_df) > 0:
        results_df.to_csv(args.output, index=False)
        print(f"\n  Full results saved to: {args.output}")


if __name__ == "__main__":
    main()
