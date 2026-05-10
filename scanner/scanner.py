#!/usr/bin/env python3
"""EMA Scanner - multi-mode CLI entry point.

Examples:
  python scanner.py --mode compression
  python scanner.py --mode compression --min-mc 500 --max-mc 5000 --top 30
  python scanner.py --list-modes
  python scanner.py --clear-cache
"""
import argparse
import sys
import uuid
from datetime import datetime

import config
import data
import output
import regime as regime_mod
import universe
from modes import MODES, composite_score, get_mode


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="EMA Scanner - multi-mode setup detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--mode", choices=list(MODES.keys()))
    p.add_argument("--list-modes", action="store_true")
    p.add_argument("--clear-cache", action="store_true")
    p.add_argument("--min-mc", type=float, default=config.DEFAULT_MIN_MC_M)
    p.add_argument("--max-mc", type=float, default=config.DEFAULT_MAX_MC_M)
    p.add_argument("--top", type=int, default=config.DEFAULT_TOP_N)
    p.add_argument("--output", type=str, default=None, help="CSV output path")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--include-non-equity", action="store_true",
                   help="Disable the preferreds/notes/SPACs/trusts filter")
    p.add_argument("--no-db", action="store_true")
    p.add_argument("--no-regime", action="store_true")
    return p.parse_args()


def list_modes() -> None:
    print("\nAvailable modes:")
    for m in MODES.values():
        flag = "" if m.implemented else "  [STUB]"
        print(f"  {m.name:18s}{flag}\n      {m.description}")
    print()


def score_ticker(ticker: str, frames: dict, mode, regime_state) -> dict | None:
    result: dict = {"ticker": ticker}
    for scorer in mode.scorers:
        result.update(scorer.score(frames, regime_state))
    result["composite_score"] = round(composite_score(result, mode.weights), 2)
    for gate in mode.gates:
        if not gate.passes(result):
            return None
    return result


def main() -> int:
    args = parse_args()

    if args.list_modes:
        list_modes()
        return 0

    if args.clear_cache:
        data.clear_cache()
        print("Cache cleared.")
        return 0

    if not args.mode:
        print("Error: --mode is required (or use --list-modes / --clear-cache)")
        return 2

    mode = get_mode(args.mode)
    if not mode.implemented:
        print(f"Error: mode {mode.name!r} is a stub - its scorers raise NotImplementedError.")
        print("Implemented modes:", [m.name for m in MODES.values() if m.implemented])
        return 2

    invocation_id = str(uuid.uuid4())
    use_cache = not args.no_cache

    print("=" * 60)
    print(f"  EMA SCANNER - mode={mode.name}")
    print(f"  Market cap: ${args.min_mc:.0f}M - ${args.max_mc:.0f}M")
    print(f"  Cache: {'enabled' if use_cache else 'disabled'}")
    print(f"  Date:  {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 60)

    # ---- Regime ----
    regime_state = None
    if not args.no_regime:
        print("\n[1/4] Computing market regime (SPY/QQQ)...")
        regime_state = regime_mod.compute_regime(use_cache=use_cache)
        print(regime_mod.format_regime(regime_state))
        if mode.regime_gate and regime_state.label == "RISK_OFF":
            print("\nMode is gated to skip RISK_OFF regimes - exiting.")
            return 0
        if mode.regime_warn and regime_state.label == "RISK_OFF":
            print("\nWARNING: regime is RISK_OFF - proceeding but expect noise.")

    # ---- Universe ----
    print("\n[2/4] Fetching stock universe...")
    raw_stocks = universe.fetch(use_cache=use_cache)
    universe_size = len(raw_stocks)

    if not args.include_non_equity:
        equity = [s for s in raw_stocks if universe.is_common_equity(s)]
        print(f"  Common-equity filter: kept {len(equity)} / {universe_size} "
              f"({universe_size - len(equity)} non-equity dropped)")
    else:
        equity = list(raw_stocks)

    stocks = universe.filter_by_market_cap(equity, args.min_mc, args.max_mc)
    print(f"  Market-cap filter: kept {len(stocks)} in ${args.min_mc:.0f}M-${args.max_mc:.0f}M")

    if not stocks:
        print("\n  No stocks matched filters.")
        return 0

    tickers = [s["symbol"] for s in stocks]
    info_by_ticker = {s["symbol"]: s for s in stocks}

    # ---- Data ----
    print(f"\n[3/4] Downloading price data for {len(tickers)} tickers...")
    frames_by_ticker = data.download_with_cache(
        tickers, use_cache=use_cache, period=mode.required_period
    )
    print(f"  Got data for {len(frames_by_ticker)} tickers")

    # ---- Score ----
    print(f"\n[4/4] Scoring with mode='{mode.name}'...")
    results: list[dict] = []
    for ticker, frames in frames_by_ticker.items():
        try:
            scored = score_ticker(ticker, frames, mode, regime_state)
        except NotImplementedError as e:
            print(f"  ERROR: {e}")
            return 2
        if scored is None:
            continue
        info = info_by_ticker.get(ticker, {})
        scored["name"] = (info.get("name") or "")[:config.NAME_TRUNCATE]
        scored["market_cap_m"] = round(info.get("market_cap", 0) / 1_000_000)
        results.append(scored)

    results.sort(key=lambda r: r.get(mode.sort_by, 0), reverse=mode.sort_desc)

    # ---- Output ----
    output.print_table(results, mode, args.top)

    if args.output:
        output.write_csv(results, args.output)

    if not args.no_db and results:
        params = {"min_mc": args.min_mc, "max_mc": args.max_mc, "universe_size": universe_size}
        try:
            run_id = output.write_supabase(results, mode, regime_state, invocation_id, params)
            if run_id:
                # Machine-readable line for scanner_worker.py to parse.
                print(f"SCAN_RUN_ID={run_id}")
        except Exception as e:
            print(f"  Supabase write skipped: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
