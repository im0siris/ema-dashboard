// lib/supabase.ts
// Supabase client + v3 schema types.
// v3 stores per-scorer outputs in a `scorer_scores` JSONB column so the
// schema doesn't need to change every time a new scorer is added.

import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseKey);

// ---------- v3 Supabase row shapes ----------

export interface ScanRun {
  id: number;
  invocation_id: string;
  scanned_at: string;
  mode: string;
  regime_state: string | null;
  min_market_cap_m: number;
  max_market_cap_m: number;
  universe_size: number;
  kept_count: number;
}

export interface ScanRequest {
  id: number;
  requested_at: string;
  mode: string;
  min_market_cap_m: number | null;
  max_market_cap_m: number | null;
  status: "pending" | "running" | "completed" | "failed" | string;
  started_at: string | null;
  completed_at: string | null;
  scan_run_id: number | null;
  error_message: string | null;
}

export interface ScanResult {
  id: number;
  scan_run_id: number;
  ticker: string;
  name: string | null;
  market_cap_m: number | null;
  mode: string;
  composite_score: number | null;
  scorer_scores: Record<string, unknown>;
}

// ---------- Mode-specific projections (extracted from scorer_scores) ----------

export interface CompressionRow {
  id: number;
  scan_run_id: number;
  ticker: string;
  name: string;
  market_cap_m: number;
  close: number;
  ema9: number;
  ema21: number;
  sma50: number;
  spread_pct: number;
  alignment: "BULLISH" | "BEARISH" | "MIXED" | "INSUFFICIENT_DATA" | string;
  above_sma50: boolean;
  score: number;
}

export function asCompressionRow(r: ScanResult): CompressionRow {
  const s = r.scorer_scores ?? {};
  const num = (k: string) => Number(s[k] ?? 0);
  return {
    id: r.id,
    scan_run_id: r.scan_run_id,
    ticker: r.ticker,
    name: r.name ?? "",
    market_cap_m: Number(r.market_cap_m ?? 0),
    close: num("compression_close"),
    ema9: num("compression_ema9"),
    ema21: num("compression_ema21"),
    sma50: num("compression_sma50"),
    spread_pct: num("compression_pct"),
    alignment: String(s["compression_alignment"] ?? "INSUFFICIENT_DATA"),
    above_sma50: Boolean(s["compression_above_sma50"]),
    score: num("compression_score"),
  };
}
