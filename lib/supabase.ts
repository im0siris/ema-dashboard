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

// ---------- full_setup mode projection ----------

export interface FullSetupRow {
  id: number;
  scan_run_id: number;
  ticker: string;
  name: string;
  market_cap_m: number;
  composite_score: number;
  // alignment scorer
  alignment_label: string;
  alignment_count: number;
  alignment_score: number;
  // flat_against_band
  flat_distance_pct: number;
  flat_is_inside_band: boolean;
  flat_score: number;
  // squeeze
  squeeze_active: boolean;
  squeeze_overhead_ma: string | null;
  squeeze_score: number;
  // weekly_setup
  weekly_score: number;
  weekly_alignment_count: number;
  weekly_cross: boolean;
  // base_break
  base_break_active: boolean;
  base_break_years: number;
  base_break_score: number;
  // volume_profile
  volume_label: string;
  volume_ratio: number;
  volume_is_anomaly: boolean;
}

export function asFullSetupRow(r: ScanResult): FullSetupRow {
  const s = r.scorer_scores ?? {};
  const num = (k: string) => Number(s[k] ?? 0);
  const str = (k: string, dflt = "") => String(s[k] ?? dflt);
  const bool = (k: string) => Boolean(s[k]);
  return {
    id: r.id,
    scan_run_id: r.scan_run_id,
    ticker: r.ticker,
    name: r.name ?? "",
    market_cap_m: Number(r.market_cap_m ?? 0),
    composite_score: Number(r.composite_score ?? 0),
    alignment_label: str("alignment_label", "INSUFFICIENT_DATA"),
    alignment_count: num("alignment_count"),
    alignment_score: num("alignment_score"),
    flat_distance_pct: num("flat_against_band_distance_pct"),
    flat_is_inside_band: bool("flat_against_band_is_inside_band"),
    flat_score: num("flat_against_band_score"),
    squeeze_active: bool("squeeze_active"),
    squeeze_overhead_ma:
      s["squeeze_overhead_ma"] == null
        ? null
        : String(s["squeeze_overhead_ma"]),
    squeeze_score: num("squeeze_score"),
    weekly_score: num("weekly_setup_score"),
    weekly_alignment_count: num("weekly_setup_alignment_count"),
    weekly_cross: bool("weekly_setup_9ema_crossed_200sma_recent"),
    base_break_active: bool("base_break_active"),
    base_break_years: num("base_break_years_of_base"),
    base_break_score: num("base_break_score"),
    volume_label: str("volume_profile_label", "INSUFFICIENT_DATA"),
    volume_ratio: num("volume_profile_ratio"),
    volume_is_anomaly: bool("volume_profile_is_anomaly"),
  };
}

// ---------- Mode registry ----------

export type ScanMode = "compression" | "full_setup";

export const MODE_LABELS: Record<ScanMode, string> = {
  compression: "Compression",
  full_setup: "Full Setup",
};

export const ALL_MODES: ScanMode[] = ["compression", "full_setup"];
