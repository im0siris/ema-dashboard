// lib/supabase.ts
// Creates a Supabase client instance for use throughout the app.
// We use environment variables so credentials aren't hardcoded.

import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseKey);

// TypeScript types matching our database schema
export interface ScanRun {
  id: number;
  scanned_at: string;
  min_market_cap_m: number;
  max_market_cap_m: number;
  max_spread_pct: number;
  total_universe: number;
  total_filtered: number;
  total_results: number;
}

export interface ScanResult {
  id: number;
  scan_run_id: number;
  ticker: string;
  name: string;
  market_cap_m: number;
  close_price: number;
  ema9: number;
  ema21: number;
  sma50: number;
  spread_pct: number;
  alignment: "BULLISH" | "BEARISH" | "MIXED";
  volume_ratio: number;
}
