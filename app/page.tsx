// app/page.tsx
"use client";

import { useState, useEffect } from "react";
import {
  supabase,
  ScanRun,
  ScanRequest,
  ScanResult,
  CompressionRow,
  FullSetupRow,
  asCompressionRow,
  asFullSetupRow,
  ScanMode,
  ALL_MODES,
  MODE_LABELS,
} from "@/lib/supabase";

// ==========================================================================
// Color helpers
// ==========================================================================

function alignmentColor(a: string) {
  if (a === "BULLISH" || a === "FULL_BULL")
    return { bg: "#0d2818", text: "#34d399", border: "#065f26" };
  if (a === "PARTIAL_BULL")
    return { bg: "#162a1c", text: "#a3e635", border: "#3f6212" };
  if (a === "BEARISH" || a === "BEAR")
    return { bg: "#2d1215", text: "#f87171", border: "#7f1d1d" };
  if (a === "MIXED")
    return { bg: "#1e1b2e", text: "#a78bfa", border: "#4c3a8a" };
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

function scoreColor(s: number) {
  if (s >= 80) return "#22c55e";
  if (s >= 60) return "#a3e635";
  if (s >= 40) return "#facc15";
  if (s >= 20) return "#fb923c";
  return "#6b7280";
}

// ==========================================================================
// Recurring tickers types
// ==========================================================================

interface RecurringTicker {
  ticker: string;
  name: string;
  appearances: number;
  avgScore: number;
  latestScore: number;
  marketCapM: number;
  scoreTrend: number[];
  // compression-mode extras
  latestSpread: number | null;
  latestAlignment: string | null;
}

// ==========================================================================
// Main Dashboard Component
// ==========================================================================

export default function Dashboard() {
  // Data
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedMode, setSelectedMode] = useState<ScanMode>("compression");
  const [loading, setLoading] = useState(true);

  // Recurring tickers
  const [recurringTickers, setRecurringTickers] = useState<RecurringTicker[]>(
    [],
  );
  const [minAppearances, setMinAppearances] = useState(3);
  const [loadingRecurring, setLoadingRecurring] = useState(false);

  // Filter / UI
  const [activeTab, setActiveTab] = useState<
    "results" | "recurring" | "config" | "history"
  >("results");
  const [filterAlignment, setFilterAlignment] = useState("ALL");
  const [maxSpread, setMaxSpread] = useState(3.0);
  const [minComposite, setMinComposite] = useState(0);
  const [searchTicker, setSearchTicker] = useState("");
  const [sortBy, setSortBy] = useState<string>("spread_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Config
  const [configMinMc, setConfigMinMc] = useState(200);
  const [configMaxMc, setConfigMaxMc] = useState(1000);

  // Scan-request state
  const [activeRequest, setActiveRequest] = useState<ScanRequest | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // ---- Reset sort when mode changes ----
  useEffect(() => {
    if (selectedMode === "compression") {
      setSortBy("spread_pct");
      setSortDir("asc");
    } else {
      setSortBy("composite_score");
      setSortDir("desc");
    }
    setSelectedRunId(null);
    setResults([]);
    setFilterAlignment("ALL");
  }, [selectedMode]);

  // ---- Load scan runs for selected mode ----
  async function loadRuns(selectLatest = false) {
    const { data } = await supabase
      .from("scan_runs")
      .select("*")
      .eq("mode", selectedMode)
      .order("scanned_at", { ascending: false })
      .limit(50);

    if (data && data.length > 0) {
      setScanRuns(data);
      if (selectLatest || !selectedRunId) setSelectedRunId(data[0].id);
    } else {
      setScanRuns([]);
      setSelectedRunId(null);
    }
    setLoading(false);
  }

  useEffect(() => {
    loadRuns(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMode]);

  // ---- Load results when selected run changes ----
  useEffect(() => {
    if (!selectedRunId) {
      setResults([]);
      return;
    }

    async function loadResults() {
      const { data } = await supabase
        .from("scan_results")
        .select("*")
        .eq("scan_run_id", selectedRunId)
        .limit(500);

      if (data) setResults(data as ScanResult[]);
    }
    loadResults();
  }, [selectedRunId]);

  // ---- Load recurring tickers (mode-aware) ----
  useEffect(() => {
    if (activeTab !== "recurring" || scanRuns.length === 0) return;

    async function loadRecurring() {
      setLoadingRecurring(true);

      const recentRunIds = scanRuns.slice(0, 20).map((r) => r.id);

      const { data } = await supabase
        .from("scan_results")
        .select("*, scan_runs!inner(scanned_at)")
        .in("scan_run_id", recentRunIds)
        .eq("mode", selectedMode)
        .order("scan_run_id", { ascending: true });

      if (!data) {
        setLoadingRecurring(false);
        return;
      }

      type RowWithRun = ScanResult & { scan_runs: { scanned_at: string } };

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
        const latest = sorted[sorted.length - 1];

        // Pick the right "score" field per mode
        let scoreOf: (r: ScanResult) => number;
        let latestSpread: number | null = null;
        let latestAlignment: string | null = null;
        if (selectedMode === "compression") {
          scoreOf = (r) => asCompressionRow(r).score;
          const proj = asCompressionRow(latest);
          latestSpread = proj.spread_pct;
          latestAlignment = proj.alignment;
        } else {
          scoreOf = (r) => asFullSetupRow(r).composite_score;
        }

        const scores = sorted.map(scoreOf);
        const avgScore = scores.reduce((s, v) => s + v, 0) / scores.length;

        recurring.push({
          ticker,
          name: latest.name ?? "",
          appearances: sorted.length,
          avgScore: Math.round(avgScore * 100) / 100,
          latestScore: scores[scores.length - 1],
          marketCapM: Number(latest.market_cap_m ?? 0),
          scoreTrend: scores,
          latestSpread,
          latestAlignment,
        });
      }

      recurring.sort((a, b) => {
        if (b.appearances !== a.appearances)
          return b.appearances - a.appearances;
        return b.avgScore - a.avgScore;
      });

      setRecurringTickers(recurring);
      setLoadingRecurring(false);
    }

    loadRecurring();
  }, [activeTab, scanRuns, minAppearances, selectedMode]);

  // ---- Poll active scan request ----
  useEffect(() => {
    if (!activeRequest) return;
    if (
      activeRequest.status === "completed" ||
      activeRequest.status === "failed"
    )
      return;

    const interval = setInterval(async () => {
      const { data } = await supabase
        .from("scan_requests")
        .select("*")
        .eq("id", activeRequest.id)
        .single();

      if (!data) return;
      setActiveRequest(data);

      if (data.status === "completed") {
        // If the completed run is for the currently selected mode, reload it
        if (data.mode === selectedMode) {
          await loadRuns(true);
          if (data.scan_run_id) setSelectedRunId(data.scan_run_id);
        }
        setTimeout(() => setActiveRequest(null), 2500);
      } else if (data.status === "failed") {
        setRunError(data.error_message ?? "Scan failed (no error message).");
      }
    }, 3000);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRequest?.id, activeRequest?.status, selectedMode]);

  // ---- Run Scan handler ----
  async function handleRunScan() {
    setRunError(null);
    const { data, error } = await supabase
      .from("scan_requests")
      .insert({
        mode: selectedMode,
        min_market_cap_m: configMinMc,
        max_market_cap_m: configMaxMc,
      })
      .select()
      .single();

    if (error || !data) {
      setRunError(`Could not queue scan: ${error?.message ?? "unknown error"}`);
      return;
    }
    setActiveRequest(data as ScanRequest);
  }

  function dismissRequest() {
    setActiveRequest(null);
    setRunError(null);
  }

  function handleSort(col: string) {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortBy(col);
      setSortDir("asc");
    }
  }

  // ---- Project + filter results per mode ----
  const compressionRows: CompressionRow[] =
    selectedMode === "compression" ? results.map(asCompressionRow) : [];
  const fullSetupRows: FullSetupRow[] =
    selectedMode === "full_setup" ? results.map(asFullSetupRow) : [];

  const filteredCompression = compressionRows
    .filter((r) => filterAlignment === "ALL" || r.alignment === filterAlignment)
    .filter((r) => r.spread_pct <= maxSpread)
    .filter(
      (r) =>
        !searchTicker ||
        r.ticker.toLowerCase().includes(searchTicker.toLowerCase()),
    )
    .sort((a, b) => {
      const aVal = (a as unknown as Record<string, unknown>)[sortBy] ?? 0;
      const bVal = (b as unknown as Record<string, unknown>)[sortBy] ?? 0;
      return sortDir === "asc" ? (aVal > bVal ? 1 : -1) : aVal < bVal ? 1 : -1;
    });

  const filteredFullSetup = fullSetupRows
    .filter((r) => r.composite_score >= minComposite)
    .filter(
      (r) =>
        !searchTicker ||
        r.ticker.toLowerCase().includes(searchTicker.toLowerCase()),
    )
    .sort((a, b) => {
      const aVal = (a as unknown as Record<string, unknown>)[sortBy] ?? 0;
      const bVal = (b as unknown as Record<string, unknown>)[sortBy] ?? 0;
      return sortDir === "asc" ? (aVal > bVal ? 1 : -1) : aVal < bVal ? 1 : -1;
    });

  const visibleCount =
    selectedMode === "compression"
      ? filteredCompression.length
      : filteredFullSetup.length;

  const currentRun = scanRuns.find((r) => r.id === selectedRunId);

  // ---- Loading ----
  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a12] flex items-center justify-center">
        <p className="text-gray-500 font-mono">Loading scanner data...</p>
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
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e88]" />
          <span className="text-[15px] font-bold tracking-wider">
            EMA SCANNER
          </span>
          <span className="text-[11px] text-gray-600">v3.0</span>

          {/* Mode switcher */}
          <div className="flex border border-[#2a2a3e] rounded overflow-hidden ml-2">
            {ALL_MODES.map((m) => (
              <button
                key={m}
                onClick={() => setSelectedMode(m)}
                className={`px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
                  selectedMode === m
                    ? "bg-purple-500/20 text-purple-300"
                    : "bg-transparent text-gray-500 hover:text-gray-300"
                }`}
              >
                {MODE_LABELS[m]}
              </button>
            ))}
          </div>

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
          {activeRequest && (
            <span
              className={`text-[10px] border rounded px-2 py-[2px] uppercase tracking-wider flex items-center gap-1.5 ${
                activeRequest.status === "running" ||
                activeRequest.status === "pending"
                  ? "border-yellow-500/50 bg-yellow-500/10 text-yellow-300"
                  : activeRequest.status === "completed"
                    ? "border-green-500/50 bg-green-500/10 text-green-300"
                    : "border-red-500/50 bg-red-500/10 text-red-300"
              }`}
            >
              {(activeRequest.status === "pending" ||
                activeRequest.status === "running") && (
                <span className="w-1.5 h-1.5 rounded-full bg-yellow-300 animate-pulse" />
              )}
              {activeRequest.status === "pending" && `Queued (${activeRequest.mode})`}
              {activeRequest.status === "running" && `Scanning (${activeRequest.mode})...`}
              {activeRequest.status === "completed" && "Done"}
              {activeRequest.status === "failed" && "Failed"}
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
            EMPTY STATE FOR THIS MODE
            ================================================================ */}
        {scanRuns.length === 0 && activeTab !== "config" && (
          <div className="text-center py-16 text-gray-500">
            <p className="mb-3">
              No <span className="text-purple-400">{selectedMode}</span> scans
              found yet.
            </p>
            <p className="text-xs text-gray-600">
              Go to the Config tab and click "Run Scan Now" to queue one.
            </p>
          </div>
        )}

        {/* ================================================================
            RESULTS TAB
            ================================================================ */}
        {activeTab === "results" && scanRuns.length > 0 && (
          <div>
            {currentRun && (
              <div className="mb-4 px-3 py-2 bg-[#0e0e1a] border border-[#1a1a2e] rounded-md text-[11px] text-gray-500 flex gap-4 flex-wrap">
                <span>Scan #{currentRun.id}</span>
                <span>
                  Mode:{" "}
                  <span className="text-purple-400">{currentRun.mode}</span>
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

              {selectedMode === "compression" && (
                <>
                  <div>
                    <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1">
                      Alignment
                    </label>
                    <div className="flex gap-1">
                      {["ALL", "BULLISH", "BEARISH", "MIXED"].map((a) => {
                        const c =
                          a === "ALL"
                            ? {
                                bg: "#1e1b2e",
                                text: "#a78bfa",
                                border: "#4c3a8a",
                              }
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
                </>
              )}

              {selectedMode === "full_setup" && (
                <div>
                  <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1">
                    Min Composite:{" "}
                    <span style={{ color: scoreColor(minComposite) }}>
                      {minComposite}
                    </span>
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={minComposite}
                    onChange={(e) => setMinComposite(parseInt(e.target.value))}
                    className="w-36 accent-purple-500"
                  />
                </div>
              )}

              <div className="ml-auto text-xs text-gray-500">
                {visibleCount} stocks
              </div>
            </div>

            {/* === COMPRESSION TABLE === */}
            {selectedMode === "compression" && (
              <div className="overflow-x-auto border border-[#1a1a2e] rounded-md">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[#0e0e1a]">
                      {[
                        { key: "ticker", label: "Ticker", sortable: true },
                        { key: "name", label: "Name", sortable: true },
                        { key: "market_cap_m", label: "MC ($M)", sortable: true },
                        { key: "close", label: "Close", sortable: true },
                        { key: "spread_pct", label: "Spread", sortable: true },
                        { key: "alignment", label: "Alignment", sortable: true },
                        { key: "score", label: "Score", sortable: true },
                      ].map((col) => (
                        <th
                          key={col.key}
                          onClick={() => col.sortable && handleSort(col.key)}
                          className={`px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e] whitespace-nowrap select-none ${col.sortable ? "cursor-pointer hover:text-gray-400" : ""}`}
                        >
                          {col.label}
                          {col.sortable && (
                            <span className="ml-1 text-[9px]">
                              {sortBy === col.key
                                ? sortDir === "asc"
                                  ? "▲"
                                  : "▼"
                                : "⇅"}
                            </span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCompression.map((r, i) => (
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
                        <td className="px-3 py-2 tabular-nums font-semibold">
                          <span style={{ color: scoreColor(r.score) }}>
                            {r.score.toFixed(0)}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* === FULL_SETUP TABLE === */}
            {selectedMode === "full_setup" && (
              <div className="overflow-x-auto border border-[#1a1a2e] rounded-md">
                <table className="w-full">
                  <thead>
                    <tr className="bg-[#0e0e1a]">
                      {[
                        // key MUST match a numeric/comparable field on FullSetupRow.
                        // For boolean signals we sort by their score (continuous) or
                        // _years (more useful than yes/no).
                        { key: "ticker", label: "Ticker", sortable: true },
                        { key: "name", label: "Name", sortable: true },
                        { key: "market_cap_m", label: "MC ($M)", sortable: true },
                        { key: "composite_score", label: "Composite", sortable: true },
                        { key: "alignment_count", label: "Alignment", sortable: true },
                        { key: "flat_distance_pct", label: "Flat %", sortable: true },
                        { key: "squeeze_score", label: "Squeeze", sortable: true },
                        { key: "weekly_score", label: "Weekly", sortable: true },
                        { key: "base_break_years", label: "Base Break", sortable: true },
                        { key: "volume_ratio", label: "Volume", sortable: true },
                      ].map((col) => (
                        <th
                          key={col.key}
                          onClick={() => col.sortable && handleSort(col.key)}
                          className={`px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e] whitespace-nowrap select-none ${col.sortable ? "cursor-pointer hover:text-gray-400" : ""}`}
                        >
                          {col.label}
                          {col.sortable && (
                            <span className="ml-1 text-[9px]">
                              {sortBy === col.key
                                ? sortDir === "asc"
                                  ? "▲"
                                  : "▼"
                                : "⇅"}
                            </span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFullSetup.map((r, i) => (
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
                        <td className="px-3 py-2 text-gray-500 max-w-[180px] truncate">
                          {r.name}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          ${r.market_cap_m}
                        </td>
                        <td className="px-3 py-2 tabular-nums font-bold">
                          <span style={{ color: scoreColor(r.composite_score) }}>
                            {r.composite_score.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wide border whitespace-nowrap"
                            style={{
                              background: alignmentColor(r.alignment_label).bg,
                              color: alignmentColor(r.alignment_label).text,
                              borderColor: alignmentColor(r.alignment_label)
                                .border,
                            }}
                          >
                            {r.alignment_label} ({r.alignment_count}/3)
                          </span>
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          <span
                            className={
                              r.flat_is_inside_band
                                ? "text-green-400 font-semibold"
                                : "text-gray-400"
                            }
                          >
                            {r.flat_distance_pct.toFixed(2)}%
                            {r.flat_is_inside_band && " in"}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          {r.squeeze_active ? (
                            <span className="text-green-400 font-bold">
                              YES{" "}
                              <span className="text-gray-500 font-normal">
                                ({r.squeeze_overhead_ma})
                              </span>
                            </span>
                          ) : (
                            <span className="text-gray-600">-</span>
                          )}
                        </td>
                        <td className="px-3 py-2 tabular-nums">
                          <span style={{ color: scoreColor(r.weekly_score) }}>
                            {r.weekly_score.toFixed(0)}
                          </span>
                          <span className="text-gray-600 text-[10px] ml-1">
                            ({r.weekly_alignment_count}/3
                            {r.weekly_cross && " +X"})
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          {r.base_break_active ? (
                            <span className="text-green-400 font-bold">
                              YES{" "}
                              <span className="text-gray-500 font-normal">
                                ({r.base_break_years.toFixed(1)}y)
                              </span>
                            </span>
                          ) : (
                            <span className="text-gray-600">-</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <span
                            className={
                              r.volume_is_anomaly
                                ? "text-yellow-400 font-bold"
                                : "text-gray-400"
                            }
                          >
                            {r.volume_label}{" "}
                            <span className="text-gray-600 text-[10px]">
                              ({r.volume_ratio.toFixed(2)}x)
                            </span>
                          </span>
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
            RECURRING TICKERS TAB
            ================================================================ */}
        {activeTab === "recurring" && scanRuns.length > 0 && (
          <div>
            <div className="flex items-end gap-6 mb-5">
              <div>
                <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-1">
                  RECURRING TICKERS ({MODE_LABELS[selectedMode]})
                </h2>
                <p className="text-gray-600 text-[11px]">
                  Tickers appearing in multiple recent {selectedMode} scans -
                  persistence often precedes a meaningful move.
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
                        "Score Trend",
                        "Latest Score",
                        "Avg Score",
                        ...(selectedMode === "compression"
                          ? ["Spread", "Alignment"]
                          : []),
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
                            {r.scoreTrend.map((s, idx) => {
                              const maxS = Math.max(...r.scoreTrend, 1);
                              const height = Math.max((s / maxS) * 16, 2);
                              return (
                                <div
                                  key={idx}
                                  style={{
                                    width: 4,
                                    height,
                                    borderRadius: 1,
                                    background: scoreColor(s),
                                    opacity:
                                      idx === r.scoreTrend.length - 1
                                        ? 1
                                        : 0.5,
                                  }}
                                />
                              );
                            })}
                          </div>
                        </td>
                        <td className="px-3 py-2 tabular-nums font-semibold">
                          <span style={{ color: scoreColor(r.latestScore) }}>
                            {r.latestScore.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-3 py-2 tabular-nums text-gray-400">
                          {r.avgScore.toFixed(1)}
                        </td>
                        {selectedMode === "compression" && (
                          <>
                            <td className="px-3 py-2">
                              {r.latestSpread !== null && (
                                <span
                                  className="font-semibold tabular-nums"
                                  style={{ color: spreadColor(r.latestSpread) }}
                                >
                                  {r.latestSpread.toFixed(2)}%
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              {r.latestAlignment && (
                                <span
                                  className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wide border"
                                  style={{
                                    background: alignmentColor(
                                      r.latestAlignment,
                                    ).bg,
                                    color: alignmentColor(r.latestAlignment)
                                      .text,
                                    borderColor: alignmentColor(
                                      r.latestAlignment,
                                    ).border,
                                  }}
                                >
                                  {r.latestAlignment}
                                </span>
                              )}
                            </td>
                          </>
                        )}
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
              Mode is selected in the header. Set the market-cap range below
              and click Run Scan Now. The local{" "}
              <code>scanner_worker.py</code> picks up the request from
              Supabase, runs the scanner, and the dashboard reloads when it
              finishes.
            </p>
            <div className="flex flex-col gap-5">
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">
                  Mode (set in header)
                </label>
                <div className="bg-[#12121e] border border-[#2a2a3e] rounded px-3 py-2 text-sm w-40 text-purple-300">
                  {MODE_LABELS[selectedMode]}
                </div>
              </div>
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

              <div className="mt-2 flex items-center gap-3">
                <button
                  onClick={handleRunScan}
                  disabled={
                    !!activeRequest &&
                    (activeRequest.status === "pending" ||
                      activeRequest.status === "running")
                  }
                  className="px-4 py-2 rounded text-xs font-semibold tracking-wide border transition-all bg-purple-500/15 border-purple-500/60 text-purple-300 hover:bg-purple-500/25 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {!activeRequest && `Run ${MODE_LABELS[selectedMode]} Scan`}
                  {activeRequest?.status === "pending" &&
                    "Queued (waiting for worker)..."}
                  {activeRequest?.status === "running" && "Scanning..."}
                  {activeRequest?.status === "completed" && "Done - reloading"}
                  {activeRequest?.status === "failed" && "Failed"}
                </button>

                {activeRequest && activeRequest.status !== "running" && (
                  <button
                    onClick={dismissRequest}
                    className="text-[11px] text-gray-500 hover:text-gray-300 underline-offset-2 hover:underline"
                  >
                    Dismiss
                  </button>
                )}
              </div>

              {activeRequest && (
                <div className="text-[11px]">
                  {activeRequest.status === "pending" && (
                    <p className="text-gray-500">
                      Queued {activeRequest.mode} at{" "}
                      {new Date(activeRequest.requested_at).toLocaleTimeString()}
                      . Make sure <code>scanner_worker.py</code> is running.
                    </p>
                  )}
                  {activeRequest.status === "running" && (
                    <p className="text-yellow-400">
                      {activeRequest.mode} scan started at{" "}
                      {activeRequest.started_at
                        ? new Date(activeRequest.started_at).toLocaleTimeString()
                        : "?"}
                      .{" "}
                      {activeRequest.mode === "full_setup"
                        ? "Full setup pulls 5y of data per ticker - first run may take 5-10 min."
                        : "2-5 minutes typical."}
                    </p>
                  )}
                  {activeRequest.status === "completed" && (
                    <p className="text-green-400">
                      Done. Loading run #{activeRequest.scan_run_id}...
                    </p>
                  )}
                  {activeRequest.status === "failed" && runError && (
                    <pre className="text-red-400 bg-[#1a0e10] border border-red-900/40 rounded p-2 max-h-40 overflow-auto whitespace-pre-wrap break-words">
                      {runError}
                    </pre>
                  )}
                </div>
              )}

              <p className="text-[11px] text-gray-600 mt-4 leading-relaxed border-t border-[#1a1a2e] pt-3">
                Worker setup: open a terminal once and run{" "}
                <code className="text-gray-400">
                  cd C:\Coding\ema-scanner; python scanner_worker.py
                </code>
                . Leave it open while you want the Run button to work.
              </p>
            </div>
          </div>
        )}

        {/* ================================================================
            HISTORY TAB
            ================================================================ */}
        {activeTab === "history" && scanRuns.length > 0 && (
          <div>
            <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-5">
              {MODE_LABELS[selectedMode].toUpperCase()} SCAN HISTORY
            </h2>
            <div className="border border-[#1a1a2e] rounded-md overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-[#0e0e1a]">
                    {[
                      "#",
                      "Date",
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
