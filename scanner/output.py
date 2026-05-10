"""Output: console table, CSV export, Supabase REST writer."""
import json
import os
import urllib.request
from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv

import config

load_dotenv()


def print_table(results: list[dict], mode, top_n: int) -> None:
    if not results:
        print("\n  No stocks matched.")
        return

    print(f"\n  RESULTS: {len(results)} stocks passed mode '{mode.name}'")
    print(f"  Showing top {min(top_n, len(results))} (sorted by {mode.sort_by})")
    print("=" * 60)

    df = pd.DataFrame(results[:top_n])
    cols = mode.display_columns or list(df.columns)
    cols = [c for c in cols if c in df.columns]
    print(df[cols].to_string(index=False))


def write_csv(results: list[dict], path: str) -> None:
    if not results:
        return
    pd.DataFrame(results).to_csv(path, index=False)
    print(f"  Saved {len(results)} rows to {path}")


# -------- Supabase REST (ported from v2 — keep urllib, no SDK on Python 3.14+) --------

class SupabaseREST:
    def __init__(self, url: str, key: str):
        self.base_url = f"{url.rstrip('/')}/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def insert(self, table: str, data):
        url = f"{self.base_url}/{table}"
        body = json.dumps(data, default=str).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=self.headers, method="POST")
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    def select(self, table: str, query: str = ""):
        """GET with PostgREST query params, e.g. query='?status=eq.pending&limit=1'."""
        url = f"{self.base_url}/{table}{query}"
        req = urllib.request.Request(url, headers=self.headers)
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    def update(self, table: str, filter_query: str, data: dict):
        """PATCH rows matching filter_query (must include the leading '?'), e.g. '?id=eq.123'."""
        url = f"{self.base_url}/{table}{filter_query}"
        body = json.dumps(data, default=str).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=self.headers, method="PATCH")
        return json.loads(urllib.request.urlopen(req, timeout=30).read())


def get_supabase_client() -> SupabaseREST:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL/SUPABASE_KEY in .env")
    return SupabaseREST(url, key)


def write_supabase(
    results: list[dict],
    mode,
    regime_state,
    invocation_id: str,
    params: dict,
) -> int | None:
    """Inserts one scan_runs row + N scan_results rows. Returns scan_run_id or None on failure."""
    try:
        client = get_supabase_client()
    except Exception as e:
        print(f"  Supabase unavailable: {e}")
        return None

    scan_run = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "invocation_id": invocation_id,
        "mode": mode.name,
        "regime_state": regime_state.label if regime_state else None,
        "min_market_cap_m": params.get("min_mc"),
        "max_market_cap_m": params.get("max_mc"),
        "universe_size": params.get("universe_size", 0),
        "kept_count": len(results),
    }
    try:
        response = client.insert("scan_runs", scan_run)
        scan_run_id = response[0]["id"]
        print(f"  Created scan_runs row #{scan_run_id} for mode={mode.name}")
    except Exception as e:
        print(f"  Failed to write scan_runs: {e}")
        return None

    if not results:
        return scan_run_id

    rows = []
    top_level = {"ticker", "name", "market_cap_m", "composite_score"}
    for r in results:
        scorer_scores = {k: v for k, v in r.items() if k not in top_level}
        rows.append({
            "scan_run_id": scan_run_id,
            "ticker": r["ticker"],
            "name": r.get("name"),
            "market_cap_m": r.get("market_cap_m"),
            "mode": mode.name,
            "composite_score": r.get("composite_score"),
            "scorer_scores": scorer_scores,
        })

    bs = config.SUPABASE_BATCH_INSERT
    for i in range(0, len(rows), bs):
        batch = rows[i : i + bs]
        try:
            client.insert("scan_results", batch)
        except Exception as e:
            print(f"  Failed to insert batch starting at {i}: {e}")
            return scan_run_id

    print(f"  Saved {len(rows)} results to Supabase")
    return scan_run_id
