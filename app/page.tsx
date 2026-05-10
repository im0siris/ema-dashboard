// app/page.tsx
"use client";

import { useState, useEffect } from "react";
import {
  supabase,
  ScanRun,
  ScanResult,
  CompressionRow,
  asCompressionRow,
} from "@/lib/supabase";

// ==========================================================================
// Color helpers
// ==========================================================================

function alignmentColor(a: string) {
  if (a === "BULLISH")
    return { bg: "#0d2818", text: "#34d399", border: "#065f26" };
  if (a === "BEARISH")
    return { bg: "#2d1215", text: "#f87171", border: "#7f1d1d" };
  if (a === "MIXED")
    return { bg: "#1e1b2e", text: "#a78bfa", border: "#4c3a8a" };
  // INSUFFICIENT_DATA or other
  return { bg: "#1a1a24", text: "#6b7280", border: "#2a2a3e" };
}

function spreadColor(s: number) {
  if (s < 0.5) return "#22c55e";
  if (s < 1.0) return "#34d399";
  if (s < 1.5) return "#a3e635";
  if (s < 2.0) return "#facc15";
  if (s < 2.5) return "#fb923c";
  return "#f87171";
}

function regimeColor(label: string | null) {
  if (label === "RISK_ON_FULL")
    return { bg: "#0d2818", text: "#34d399", border: "#065f26" };
  if (label === "RISK_ON_SHORT")
    return { bg: "#162a1c", text: "#a3e635", border: "#3f6212" };
  if (label === "MIXED")
    return { bg: "#1e1b2e", text: "#a78bfa", border: "#4c3a8a" };
  if (label === "RISK_OFF")
    return { bg: "#2d1215", text: "#f87171", border: "#7f1d1d" };
  return { bg: "#1a1a24", text: "#6b7280", border: "#2a2a3e" };
}

// ==========================================================================
// Types for the recurring tickers analysis
// ==========================================================================

interface RecurringTicker {
  ticker: string;
  name: string;
  appearances: number;
  avgSpread: number;
  latestSpread: number;
  latestAlignment: string;
  latestClose: number;
  marketCapM: number;
  spreadTrend: number[];
}

// ==========================================================================
// Main Dashboard Component
// ==========================================================================

const COMPRESSION_MODE = "compression";

export default function Dashboard() {
  // Data state
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [results, setResults] = useState<CompressionRow[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  // Recurring tickers state
  const [recurringTickers, setRecurringTickers] = useState<RecurringTicker[]>(
    [],
  );
  const [minAppearances, setMinAppearances] = useState(3);
  const [loadingRecurring, setLoadingRecurring] = useState(false);

  // Filter / UI state
  const [activeTab, setActiveTab] = useState<
    "results" | "recurring" | "config" | "history"
  >("results");
  const [filterAlignment, setFilterAlignment] = useState("ALL");
  const [maxSpread, setMaxSpread] = useState(3.0);
  const [searchTicker, setSearchTicker] = useState("");
  const [sortBy, setSortBy] = useState<keyof CompressionRow>("spread_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Config state
  const [configMinMc, setConfigMinMc] = useState(200);
  const [configMaxMc, setConfigMaxMc] = useState(1000);

  // ---- Load scan runs (compression mode only for now) on mount ----
  useEffect(() => {
    async function loadRuns() {
      const { data } = await supabase
        .from("scan_runs")
        .select("*")
        .eq("mode", COMPRESSION_MODE)
        .order("scanned_at", { ascending: false })
        .limit(50);

      if (data && data.length > 0) {
        setScanRuns(data);
        setSelectedRunId(data[0].id);
      }
      setLoading(false);
    }
    loadRuns();
  }, []);

  // ---- Load results when selected run changes ----
  useEffect(() => {
    if (!selectedRunId) return;

    async function loadResults() {
      const { data } = await supabase
        .from("scan_results")
        .select("*")
        .eq("scan_run_id", selectedRunId);

      if (data) {
        const rows = (data as ScanResult[]).map(asCompressionRow);
        rows.sort((a, b) => a.spread_pct - b.spread_pct);
        setResults(rows);
      }
    }
    loadResults();
  }, [selectedRunId]);

  // ---- Load recurring tickers when tab is selected or minAppearances changes ----
  useEffect(() => {
    if (activeTab !== "recurring" || scanRuns.length === 0) return;

    async function loadRecurring() {
      setLoadingRecurring(true);

      const recentRunIds = scanRuns.slice(0, 20).map((r) => r.id);

      const { data } = await supabase
        .from("scan_results")
        .select("*, scan_runs!inner(scanned_at)")
        .in("scan_run_id", recentRunIds)
        .eq("mode", COMPRESSION_MODE)
        .order("scan_run_id", { ascending: true });

      if (!data) {
        setLoadingRecurring(false);
        return;
      }

      type RowWithRun = ScanResult & { scan_runs: { scanned_at: string } };

      // Group results by ticker
      const tickerMap = new Map<string, RowWithRun[]>();
      for (const row of data as RowWithRun[]) {
        if (!tickerMap.has(row.ticker)) tickerMap.set(row.ticker, []);
        tickerMap.get(row.ticker)!.push(row);
      }

      const recurring: RecurringTicker[] = [];
      for (const [ticker, rows] of tickerMap) {
        if (rows.length < minAppearances) continue;

        const sorted = rows.sort(
          (a, b) =>
            new Date(a.scan_runs.scanned_at).getTime() -
            new Date(b.scan_runs.scanned_at).getTime(),
        );
        const projected = sorted.map(asCompressionRow);
        const latest = projected[projected.length - 1];
        const avgSpread =
          projected.reduce((sum, r) => sum + r.spread_pct, 0) / projected.length;

        recurring.push({
          ticker,
          name: latest.name,
          appearances: projected.length,
          avgSpread: Math.round(avgSpread * 100) / 100,
          latestSpread: latest.spread_pct,
          latestAlignment: latest.alignment,
          latestClose: latest.close,
          marketCapM: latest.market_cap_m,
          spreadTrend: projected.map((r) => r.spread_pct),
        });
      }

      recurring.sort((a, b) => {
        if (b.appearances !== a.appearances)
          return b.appearances - a.appearances;
        return a.avgSpread - b.avgSpread;
      });

      setRecurringTickers(recurring);
      setLoadingRecurring(false);
    }

    loadRecurring();
  }, [activeTab, scanRuns, minAppearances]);

  // ---- Filter & sort results ----
  const filtered = results
    .filter((r) => filterAlignment === "ALL" || r.alignment === filterAlignment)
    .filter((r) => r.spread_pct <= maxSpread)
    .filter(
      (r) =>
        !searchTicker ||
        r.ticker.toLowerCase().includes(searchTicker.toLowerCase()),
    )
    .sort((a, b) => {
      const aVal = a[sortBy] ?? 0;
      const bVal = b[sortBy] ?? 0;
      return sortDir === "asc" ? (aVal > bVal ? 1 : -1) : aVal < bVal ? 1 : -1;
    });

  const handleSort = (col: keyof CompressionRow) => {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortBy(col);
      setSortDir("asc");
    }
  };

  const currentRun = scanRuns.find((r) => r.id === selectedRunId);

  // ---- Loading state ----
  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a12] flex items-center justify-center">
        <p className="text-gray-500 font-mono">Loading scanner data...</p>
      </div>
    );
  }

  // ---- Empty state ----
  if (scanRuns.length === 0) {
    return (
      <div className="min-h-screen bg-[#0a0a12] flex items-center justify-center p-8">
        <div className="text-center font-mono max-w-md">
          <h1 className="text-xl font-bold text-purple-400 mb-4">
            EMA SCANNER v3
          </h1>
          <p className="text-gray-500 mb-6">
            No compression scans found yet. Run your first scan:
          </p>
          <code className="block bg-[#12121e] border border-[#2a2a3e] rounded p-4 text-green-400 text-sm">
            python scanner.py --mode compression
          </code>
          <p className="text-gray-600 text-xs mt-4">
            Results will appear here automatically after the run completes.
          </p>
          <p className="text-gray-700 text-[10px] mt-3">
            (If this is your first v3 run, ensure
            legacy/migrations/001_recreate_tables.sql has been applied.)
          </p>
        </div>
      </div>
    );
  }

  // ==========================================================================
  // RENDER
  // ==========================================================================

  return (
    <div className="min-h-screen bg-[#0a0a12] text-[#e2e2e8] font-mono text-sm">
      {/* ---- HEADER ---- */}
      <div className="border-b border-[#1a1a2e] px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e88]" />
          <span className="text-[15px] font-bold tracking-wider">
            EMA SCANNER
          </span>
          <span className="text-[11px] text-gray-600">v3.0</span>
          {currentRun && (
            <span className="text-[10px] text-purple-400 border border-[#4c3a8a] bg-[#1e1b2e] rounded px-2 py-[2px] uppercase tracking-wider">
              {currentRun.mode}
            </span>
          )}
          {currentRun?.regime_state && (
            <span
              className="text-[10px] border rounded px-2 py-[2px] uppercase tracking-wider"
              style={{
                background: regimeColor(currentRun.regime_state).bg,
                color: regimeColor(currentRun.regime_state).text,
                borderColor: regimeColor(currentRun.regime_state).border,
              }}
            >
              {currentRun.regime_state}
            </span>
          )}
        </div>
        {currentRun && (
          <div className="text-[11px] text-gray-500 flex gap-2 flex-wrap justify-end">
            <span>Last scan:</span>
            <span className="text-purple-400">
              {new Date(currentRun.scanned_at).toLocaleString()}
            </span>
            <span className="text-gray-700">|</span>
            <span className="text-green-400">
              {currentRun.kept_count} results
            </span>
            <span className="text-gray-700">|</span>
            <span className="text-gray-400">
              ${currentRun.min_market_cap_m}M-${currentRun.max_market_cap_m}M
            </span>
          </div>
        )}
      </div>

      {/* ---- TABS ---- */}
      <div className="flex border-b border-[#1a1a2e]">
        {(["results", "recurring", "config", "history"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-2.5 text-xs font-semibold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === tab
                ? "text-purple-400 border-purple-400"
                : "text-gray-600 border-transparent hover:text-gray-400"
            }`}
          >
            {tab === "recurring" ? "Recurring" : tab}
          </button>
        ))}
      </div>

      <div className="p-6">
        {/* ================================================================
            RESULTS TAB
            ================================================================ */}
        {activeTab === "results" && (
          <div>
            {currentRun && (
              <div className="mb-4 px-3 py-2 bg-[#0e0e1a] border border-[#1a1a2e] rounded-md text-[11px] text-gray-500 flex gap-4 flex-wrap">
                <span>Scan #{currentRun.id}</span>
                <span>
                  Mode:{" "}
                  <span className="text-gray-300">{currentRun.mode}</span>
                </span>
                <span>
                  MC:{" "}
                  <span className="text-gray-300">
                    ${currentRun.min_market_cap_m}M - $
                    {currentRun.max_market_cap_m}M
                  </span>
                </span>
                <span>
                  Universe:{" "}
                  <span className="text-gray-300">
                    {currentRun.universe_size}
                  </span>
                </span>
                <span>
                  Kept:{" "}
                  <span className="text-green-400">
                    {currentRun.kept_count}
                  </span>
                </span>
                {currentRun.regime_state && (
                  <span>
                    Regime:{" "}
                    <span
                      style={{
                        color: regimeColor(currentRun.regime_state).text,
                      }}
                    >
                      {currentRun.regime_state}
                    </span>
                  </span>
                )}
              </div>
            )}

            {/* Filters */}
            <div className="flex gap-4 mb-4 flex-wrap items-end">
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1">
                  Ticker
                </label>
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchTicker}
                  onChange={(e) => setSearchTicker(e.target.value)}
                  className="bg-[#12121e] border border-[#2a2a3e] rounded px-3 py-1.5 text-xs w-24 outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1">
                  Alignment
                </label>
                <div className="flex gap-1">
                  {["ALL", "BULLISH", "BEARISH", "MIXED"].map((a) => {
                    const c =
                      a === "ALL"
                        ? { bg: "#1e1b2e", text: "#a78bfa", border: "#4c3a8a" }
                        : alignmentColor(a);
                    return (
                      <button
                        key={a}
                        onClick={() => setFilterAlignment(a)}
                        className="px-2.5 py-1 rounded text-[10px] font-semibold tracking-wide border transition-all"
                        style={{
                          borderColor:
                            filterAlignment === a ? c.border : "#2a2a3e",
                          background:
                            filterAlignment === a ? c.bg : "transparent",
                          color: filterAlignment === a ? c.text : "#4a4a6a",
                        }}
                      >
                        {a}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1">
                  Max Spread:{" "}
                  <span style={{ color: spreadColor(maxSpread) }}>
                    {maxSpread.toFixed(1)}%
                  </span>
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={3.0}
                  step={0.1}
                  value={maxSpread}
                  onChange={(e) => setMaxSpread(parseFloat(e.target.value))}
                  className="w-36 accent-purple-500"
                />
              </div>
              <div className="ml-auto text-xs text-gray-500">
                {filtered.length} stocks
              </div>
            </div>

            {/* Results table */}
            <div className="overflow-x-auto border border-[#1a1a2e] rounded-md">
              <table className="w-full">
                <thead>
                  <tr className="bg-[#0e0e1a]">
                    {[
                      { key: "ticker", label: "Ticker" },
                      { key: "name", label: "Name" },
                      {
                        key: "market_cap_m",
                        label: "MC ($M)",
                        sortable: true,
                      },
                      { key: "close", label: "Close", sortable: true },
                      { key: "spread_pct", label: "Spread", sortable: true },
                      { key: "alignment", label: "Alignment" },
                      { key: "score", label: "Score", sortable: true },
                    ].map((col) => (
                      <th
                        key={col.key}
                        onClick={() =>
                          col.sortable &&
                          handleSort(col.key as keyof CompressionRow)
                        }
                        className={`px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e] whitespace-nowrap ${col.sortable ? "cursor-pointer hover:text-gray-400" : ""}`}
                      >
                        {col.label}{" "}
                        {col.sortable &&
                          (sortBy === col.key
                            ? sortDir === "asc"
                              ? "up"
                              : "down"
                            : "")}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r, i) => (
                    <tr
                      key={r.id}
                      className={`${i % 2 === 0 ? "bg-[#0a0a12]" : "bg-[#0e0e18]"} hover:bg-[#14142a] transition-colors`}
                    >
                      <td className="px-3 py-2 font-bold">
                        <a
                          href={`https://finance.yahoo.com/quote/${r.ticker}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-purple-400 hover:underline"
                        >
                          {r.ticker}
                        </a>
                      </td>
                      <td className="px-3 py-2 text-gray-500 max-w-[200px] truncate">
                        {r.name}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        ${r.market_cap_m}
                      </td>
                      <td className="px-3 py-2 tabular-nums font-semibold">
                        ${r.close.toFixed(2)}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div className="w-14 h-1.5 bg-[#1e1e2e] rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${Math.min((r.spread_pct / maxSpread) * 100, 100)}%`,
                                background: spreadColor(r.spread_pct),
                              }}
                            />
                          </div>
                          <span
                            className="font-semibold tabular-nums"
                            style={{ color: spreadColor(r.spread_pct) }}
                          >
                            {r.spread_pct.toFixed(2)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className="px-2.5 py-0.5 rounded text-[10px] font-bold tracking-wide border"
                          style={{
                            background: alignmentColor(r.alignment).bg,
                            color: alignmentColor(r.alignment).text,
                            borderColor: alignmentColor(r.alignment).border,
                          }}
                        >
                          {r.alignment}
                        </span>
                      </td>
                      <td className="px-3 py-2 tabular-nums text-gray-300 font-semibold">
                        {r.score.toFixed(0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ================================================================
            RECURRING TICKERS TAB
            ================================================================ */}
        {activeTab === "recurring" && (
          <div>
            <div className="flex items-end gap-6 mb-5">
              <div>
                <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-1">
                  RECURRING TICKERS
                </h2>
                <p className="text-gray-600 text-[11px]">
                  Tickers appearing in multiple recent compression scans -
                  persistent compression often precedes a breakout.
                </p>
              </div>
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1">
                  Min appearances:{" "}
                  <span className="text-purple-400">{minAppearances}</span>
                </label>
                <input
                  type="range"
                  min={2}
                  max={10}
                  step={1}
                  value={minAppearances}
                  onChange={(e) => setMinAppearances(parseInt(e.target.value))}
                  className="w-32 accent-purple-500"
                />
              </div>
              <div className="ml-auto text-xs text-gray-500">
                {loadingRecurring
                  ? "Loading..."
                  : `${recurringTickers.length} tickers`}
              </div>
            </div>

            {!loadingRecurring && recurringTickers.length === 0 && (
              <div className="text-center py-12 text-gray-600">
                <p className="text-sm mb-2">
                  No recurring tickers with {minAppearances}+ appearances.
                </p>
                <p className="text-xs">
                  Lower the threshold or run more scans across multiple days.
                </p>
              </div>
            )}

            {!loadingRecurring && recurringTickers.length > 0 && (
              <div className="overflow-x-auto border border-[#1a1a2e] rounded-md">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[#0e0e1a]">
                      {[
                        "Ticker",
                        "Name",
                        "Appearances",
                        "Spread Trend",
                        "Latest Spread",
                        "Avg Spread",
                        "Alignment",
                        "Close",
                        "MC ($M)",
                      ].map((h) => (
                        <th
                          key={h}
                          className="px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e] whitespace-nowrap"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {recurringTickers.map((r, i) => (
                      <tr
                        key={r.ticker}
                        className={`${i % 2 === 0 ? "bg-[#0a0a12]" : "bg-[#0e0e18]"} hover:bg-[#14142a] transition-colors`}
                      >
                        <td className="px-3 py-2 font-bold">
                          <a
                            href={`https://finance.yahoo.com/quote/${r.ticker}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-purple-400 hover:underline"
                          >
                            {r.ticker}
                          </a>
                        </td>
                        <td className="px-3 py-2 text-gray-500 max-w-[180px] truncate">
                          {r.name}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={`font-bold ${r.appearances >= 5 ? "text-green-400" : r.appearances >= 3 ? "text-yellow-400" : "text-gray-400"}`}
                          >
                            {r.appearances}x
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-end gap-[2px] h-4">
                            {r.spreadTrend.map((s, idx) => {
                              const maxS = Math.max(...r.spreadTrend, 1);
                              const height = Math.max((s / maxS) * 16, 2);
                              return (
                                <div
                                  key={idx}
                                  style={{
                                    width: 4,
                                    height,
                                    borderRadius: 1,
                                    background: spreadColor(s),
                                    opacity:
                                      idx === r.spreadTrend.length - 1
                                        ? 1
                                        : 0.5,
                                  }}
                                />
                              );
                            })}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className="font-semibold tabular-nums"
                            style={{ color: spreadColor(r.latestSpread) }}
                          >
                            {r.latestSpread.toFixed(2)}%
                          </span>
                        </td>
                        <td className="px-3 py-2 tabular-nums text-gray-400">
                          {r.avgSpread.toFixed(2)}%
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className="px-2.5 py-0.5 rounded text-[10px] font-bold tracking-wide border"
                            style={{
                              background: alignmentColor(r.latestAlignment).bg,
                              color: alignmentColor(r.latestAlignment).text,
                              borderColor: alignmentColor(r.latestAlignment)
                                .border,
                            }}
                          >
                            {r.latestAlignment}
                          </span>
                        </td>
                        <td className="px-3 py-2 tabular-nums font-semibold">
                          ${r.latestClose.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          ${r.marketCapM}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ================================================================
            CONFIG TAB
            ================================================================ */}
        {activeTab === "config" && (
          <div className="max-w-lg">
            <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-5">
              SCAN PARAMETERS
            </h2>
            <p className="text-gray-500 text-xs mb-6 leading-relaxed">
              Configure the market-cap range, then copy the command and run it
              in PowerShell. Spread, alignment, and SMA50 gates are baked into
              the compression mode (config.py). Results land in Supabase and
              appear here automatically.
            </p>
            <div className="flex flex-col gap-5">
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">
                  Min Market Cap (millions)
                </label>
                <input
                  type="number"
                  value={configMinMc}
                  onChange={(e) => setConfigMinMc(Number(e.target.value))}
                  className="bg-[#12121e] border border-[#2a2a3e] rounded px-3 py-2 text-sm w-40 outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">
                  Max Market Cap (millions)
                </label>
                <input
                  type="number"
                  value={configMaxMc}
                  onChange={(e) => setConfigMaxMc(Number(e.target.value))}
                  className="bg-[#12121e] border border-[#2a2a3e] rounded px-3 py-2 text-sm w-40 outline-none focus:border-purple-500"
                />
              </div>
              <div className="mt-2">
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">
                  Terminal Command
                </label>
                <div className="bg-[#12121e] border border-[#2a2a3e] rounded p-3 text-green-400 text-xs flex items-center justify-between gap-3">
                  <span>
                    <span className="text-gray-600">$</span> python scanner.py
                    --mode compression --min-mc {configMinMc} --max-mc{" "}
                    {configMaxMc}
                  </span>
                  <button
                    onClick={() =>
                      navigator.clipboard.writeText(
                        `python scanner.py --mode compression --min-mc ${configMinMc} --max-mc ${configMaxMc}`,
                      )
                    }
                    className="px-2 py-1 bg-[#1e1b2e] border border-[#4c3a8a] rounded text-purple-400 text-[10px] font-semibold hover:bg-[#2a2548] transition-colors whitespace-nowrap"
                  >
                    Copy
                  </button>
                </div>
                <p className="text-[11px] text-gray-600 mt-2 leading-relaxed">
                  Run this in <code>C:\Coding\ema-scanner\</code>. After the
                  scan completes, refresh this page.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================
            HISTORY TAB
            ================================================================ */}
        {activeTab === "history" && (
          <div>
            <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-5">
              SCAN HISTORY
            </h2>
            <div className="border border-[#1a1a2e] rounded-md overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-[#0e0e1a]">
                    {[
                      "#",
                      "Date",
                      "Mode",
                      "Regime",
                      "MC Range",
                      "Universe",
                      "Kept",
                      "",
                    ].map((h) => (
                      <th
                        key={h}
                        className="px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e]"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {scanRuns.map((run, i) => (
                    <tr
                      key={run.id}
                      className={`${selectedRunId === run.id ? "bg-[#14142a]" : i % 2 === 0 ? "bg-[#0a0a12]" : "bg-[#0e0e18]"} hover:bg-[#14142a] transition-colors`}
                    >
                      <td className="px-3 py-2.5 text-gray-600">#{run.id}</td>
                      <td className="px-3 py-2.5">
                        {new Date(run.scanned_at).toLocaleString()}
                      </td>
                      <td className="px-3 py-2.5 text-purple-400">
                        {run.mode}
                      </td>
                      <td
                        className="px-3 py-2.5"
                        style={{
                          color: regimeColor(run.regime_state).text,
                        }}
                      >
                        {run.regime_state ?? "-"}
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">
                        ${run.min_market_cap_m}M - ${run.max_market_cap_m}M
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">
                        {run.universe_size}
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-green-400 font-semibold">
                          {run.kept_count}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <button
                          onClick={() => {
                            setSelectedRunId(run.id);
                            setActiveTab("results");
                          }}
                          className={`border rounded px-3 py-1 text-[11px] font-semibold transition-colors ${
                            selectedRunId === run.id
                              ? "bg-purple-500/20 border-purple-500 text-purple-300"
                              : "bg-[#1e1b2e] border-[#4c3a8a] text-purple-400 hover:bg-[#2a2548]"
                          }`}
                        >
                          {selectedRunId === run.id ? "Viewing" : "View"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
