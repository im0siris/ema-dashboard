#!/usr/bin/env python3
"""Polls Supabase scan_requests; runs scanner.py for each pending row.

Usage:
    python scanner_worker.py

Keep this running in a terminal while you want the dashboard's "Run Scan"
button to do anything. Ctrl+C to stop.

Workflow per request:
    1. Pick the oldest status='pending' row
    2. UPDATE status='running', set started_at
    3. subprocess scanner.py --mode <mode> --min-mc N --max-mc N
    4. Parse SCAN_RUN_ID=<n> from stdout
    5. UPDATE status='completed' with scan_run_id  (or 'failed' with error_message)
"""
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from output import get_supabase_client

POLL_INTERVAL_S = 5
SCAN_TIMEOUT_S = 1800  # 30 minutes
SCANNER = Path(__file__).resolve().parent / "scanner.py"
RUN_ID_RX = re.compile(r"^SCAN_RUN_ID=(\d+)$", re.MULTILINE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_scanner(mode: str, min_mc: float, max_mc: float) -> tuple[bool, int | None, str]:
    """Returns (success, scan_run_id, output_tail)."""
    cmd = [
        sys.executable, str(SCANNER),
        "--mode", mode,
        "--min-mc", f"{min_mc:g}",
        "--max-mc", f"{max_mc:g}",
    ]
    print(f"  $ {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=SCANNER.parent,
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return False, None, f"Scanner timed out after {SCAN_TIMEOUT_S}s."
    except Exception as e:
        return False, None, f"Scanner exception: {e}"

    full_output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    success = (proc.returncode == 0)
    scan_run_id = None
    m = RUN_ID_RX.search(full_output)
    if m:
        scan_run_id = int(m.group(1))
    if not success and not full_output.strip():
        full_output = f"Scanner exited with code {proc.returncode} (no output)."
    return success, scan_run_id, full_output[-2000:]  # last 2KB only


def process_one(client, req: dict) -> None:
    rid = req["id"]
    mode = req.get("mode") or "compression"
    min_mc = req.get("min_market_cap_m") or 200
    max_mc = req.get("max_market_cap_m") or 1000

    print(f"\n[{datetime.now():%H:%M:%S}] Picking up request #{rid}: "
          f"mode={mode}, mc=${min_mc:g}M-${max_mc:g}M")

    # Mark running
    try:
        client.update("scan_requests", f"?id=eq.{rid}", {
            "status": "running",
            "started_at": now_iso(),
        })
    except Exception as e:
        print(f"  ! could not mark request running: {e}")
        return

    success, scan_run_id, output_tail = run_scanner(mode, min_mc, max_mc)

    update = {
        "status": "completed" if success else "failed",
        "completed_at": now_iso(),
    }
    if scan_run_id:
        update["scan_run_id"] = scan_run_id
    if not success:
        update["error_message"] = output_tail

    try:
        client.update("scan_requests", f"?id=eq.{rid}", update)
        if success:
            extra = f" (scan_run #{scan_run_id})" if scan_run_id else " (no scan_run_id parsed)"
            print(f"  -> request #{rid} completed{extra}")
        else:
            print(f"  -> request #{rid} FAILED")
            print(f"     {output_tail.splitlines()[-1] if output_tail else ''}")
    except Exception as e:
        print(f"  ! could not mark request done: {e}")


def main() -> int:
    print("EMA Scanner Worker")
    print(f"  Poll interval: {POLL_INTERVAL_S}s")
    print(f"  Scanner:       {SCANNER}")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        client = get_supabase_client()
    except Exception as e:
        print(f"ERROR: cannot connect to Supabase: {e}")
        return 1

    print("Watching for pending scan_requests...")

    while True:
        try:
            pending = client.select(
                "scan_requests",
                "?status=eq.pending&order=requested_at.asc&limit=1",
            )
        except Exception as e:
            print(f"  [poll error: {str(e)[:120]}]")
            time.sleep(POLL_INTERVAL_S)
            continue

        if pending:
            process_one(client, pending[0])
        else:
            time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nWorker stopped.")
        sys.exit(0)
