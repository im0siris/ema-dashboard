"""yfinance data layer: daily download, weekly/monthly resample, disk cache."""
import shutil
import time
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

import config
import indicators


def clear_cache() -> None:
    if config.CACHE_DIR.exists():
        shutil.rmtree(config.CACHE_DIR)


def _cache_dir(today: str | None = None) -> Path:
    today = today or date.today().isoformat()
    p = config.CACHE_DIR / today
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_path_for(ticker: str) -> Path:
    return _cache_dir() / f"{ticker}_daily.pkl"


def _resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("W-FRI").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def _resample_monthly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("ME").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna()


def build_frames(daily_raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Given lowercase daily OHLCV, return augmented {daily, weekly, monthly}."""
    weekly_raw = _resample_weekly(daily_raw)
    monthly_raw = _resample_monthly(daily_raw)
    return {
        "daily": indicators.add_mas(daily_raw),
        "weekly": indicators.add_mas(weekly_raw),
        "monthly": indicators.add_mas(monthly_raw),
    }


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase OHLCV columns; keep only the five we need; drop NaN rows."""
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[keep].dropna()


def download_with_cache(
    tickers: list[str],
    use_cache: bool = True,
    period: str | None = None,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Returns {ticker: {daily, weekly, monthly}}. Pickle disk cache, keyed by today's date."""
    period = period or config.YF_DEFAULT_PERIOD
    out: dict[str, dict[str, pd.DataFrame]] = {}
    to_fetch: list[str] = []

    if use_cache:
        for t in tickers:
            cp = _cache_path_for(t)
            if cp.exists():
                try:
                    df = pd.read_pickle(cp)
                    if len(df) >= config.YF_MIN_ROWS:
                        out[t] = build_frames(df)
                        continue
                except Exception:
                    pass
            to_fetch.append(t)
    else:
        to_fetch = list(tickers)

    if to_fetch:
        print(f"  Cache: {len(out)} hits, {len(to_fetch)} to fetch")
        fetched = _yf_batch_download(to_fetch, period)
        for ticker, df in fetched.items():
            if use_cache:
                df.to_pickle(_cache_path_for(ticker))
            out[ticker] = build_frames(df)
    elif use_cache:
        print(f"  Cache: all {len(out)} tickers hit (no fetch needed)")

    return out


def _yf_batch_download(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    """Batch yfinance download. Returns {ticker -> normalized lowercase daily DataFrame}."""
    all_data: dict[str, pd.DataFrame] = {}
    failed_batches = 0
    bs = config.YF_BATCH_SIZE
    total_batches = (len(tickers) + bs - 1) // bs

    for i in range(0, len(tickers), bs):
        batch = tickers[i : i + bs]
        n = (i // bs) + 1
        print(f"    Batch {n}/{total_batches} ({len(batch)} tickers)...", end="", flush=True)

        try:
            raw = yf.download(
                batch,
                period=period,
                progress=False,
                group_by="ticker",
                threads=True,
                timeout=config.YF_TIMEOUT_S,
                auto_adjust=True,
            )
        except Exception as e:
            print(f" [error: {str(e)[:50]}]")
            failed_batches += 1
            continue

        if raw is None or raw.empty:
            print(" [empty]")
            continue

        if len(batch) == 1:
            ticker = batch[0]
            df = raw.copy()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(0)
            df = _normalize_columns(df)
            if len(df) >= config.YF_MIN_ROWS:
                all_data[ticker] = df
                print(" [1 OK]")
            else:
                print(" [too few rows]")
        else:
            available = raw.columns.get_level_values(0).unique()
            ok = 0
            for ticker in batch:
                if ticker in available:
                    try:
                        df = _normalize_columns(raw[ticker])
                        if len(df) >= config.YF_MIN_ROWS:
                            all_data[ticker] = df
                            ok += 1
                    except Exception:
                        pass
            print(f" [{ok} OK]")

        if i + bs < len(tickers):
            time.sleep(config.YF_INTER_BATCH_SLEEP_S)

    print(f"  Downloaded data for {len(all_data)} tickers ({failed_batches} batches failed)")
    return all_data
