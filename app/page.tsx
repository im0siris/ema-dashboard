// app/page.tsx
"use client";

import { useState, useEffect } from "react";
import { supabase, ScanRun, ScanResult } from "@/lib/supabase";

// ---- Color helpers (same logic as the preview artifact) ----

function alignmentColor(a: string) {
  if (a === "BULLISH")
    return { bg: "#0d2818", text: "#34d399", border: "#065f26" };
  if (a === "BEARISH")
    return { bg: "#2d1215", text: "#f87171", border: "#7f1d1d" };
  return { bg: "#1e1b2e", text: "#a78bfa", border: "#4c3a8a" };
}

function spreadColor(s: number) {
  if (s < 0.5) return "#22c55e";
  if (s < 1.0) return "#34d399";
  if (s < 1.5) return "#a3e635";
  if (s < 2.0) return "#facc15";
  if (s < 2.5) return "#fb923c";
  return "#f87171";
}

// ---- Main Page Component ----

export default function Dashboard() {
  // Data state
  const [scanRuns, setScanRuns] = useState<ScanRun[]>([]);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  // Filter state
  const [activeTab, setActiveTab] = useState<"results" | "config" | "history">(
    "results",
  );
  const [filterAlignment, setFilterAlignment] = useState("ALL");
  const [maxSpread, setMaxSpread] = useState(3.0);
  const [searchTicker, setSearchTicker] = useState("");
  const [sortBy, setSortBy] = useState<keyof ScanResult>("spread_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Config state
  const [configMinMc, setConfigMinMc] = useState(200);
  const [configMaxMc, setConfigMaxMc] = useState(1000);
  const [configSpread, setConfigSpread] = useState(3.0);

  // ---- Load scan runs on mount ----
  useEffect(() => {
    async function loadRuns() {
      const { data, error } = await supabase
        .from("scan_runs")
        .select("*")
        .order("scanned_at", { ascending: false })
        .limit(20);

      if (data && data.length > 0) {
        setScanRuns(data);
        setSelectedRunId(data[0].id); // Auto-select latest
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
        .eq("scan_run_id", selectedRunId)
        .order("spread_pct", { ascending: true });

      if (data) setResults(data);
    }
    loadResults();
  }, [selectedRunId]);

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

  const handleSort = (col: keyof ScanResult) => {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortBy(col);
      setSortDir("asc");
    }
  };

  const currentRun = scanRuns.find((r) => r.id === selectedRunId);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a12] flex items-center justify-center">
        <p className="text-gray-500 font-mono">Loading scanner data...</p>
      </div>
    );
  }

  if (scanRuns.length === 0) {
    return (
      <div className="min-h-screen bg-[#0a0a12] flex items-center justify-center p-8">
        <div className="text-center font-mono max-w-md">
          <h1 className="text-xl font-bold text-purple-400 mb-4">
            EMA/SMA SCANNER
          </h1>
          <p className="text-gray-500 mb-6">
            No scan data found yet. Run your first scan:
          </p>
          <code className="block bg-[#12121e] border border-[#2a2a3e] rounded p-4 text-green-400 text-sm">
            python scanner.py
          </code>
          <p className="text-gray-600 text-xs mt-4">
            Results will appear here automatically.
          </p>
        </div>
      </div>
    );
  }

  // ---- Render (same visual structure as the preview artifact) ----
  // You now have the full Supabase-connected dashboard!
  // The JSX below follows the same pattern as the preview.
  // For brevity, I'll show the key data-connected parts:

  return (
    <div className="min-h-screen bg-[#0a0a12] text-[#e2e2e8] font-mono text-sm">
      {/* Header */}
      <div className="border-b border-[#1a1a2e] px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_#22c55e88]" />
          <span className="text-[15px] font-bold tracking-wider">
            EMA/SMA SCANNER
          </span>
          <span className="text-[11px] text-gray-600">v2.0</span>
        </div>
        {currentRun && (
          <div className="text-[11px] text-gray-500 flex gap-2">
            <span>Last scan:</span>
            <span className="text-purple-400">
              {new Date(currentRun.scanned_at).toLocaleString()}
            </span>
            <span className="text-gray-700">|</span>
            <span className="text-green-400">
              {currentRun.total_results} results
            </span>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#1a1a2e]">
        {(["results", "config", "history"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-2.5 text-xs font-semibold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === tab
                ? "text-purple-400 border-purple-400"
                : "text-gray-600 border-transparent hover:text-gray-400"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="p-6">
        {activeTab === "results" && (
          <div>
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

            {/* Table */}
            <div className="overflow-x-auto border border-[#1a1a2e] rounded-md">
              <table className="w-full">
                <thead>
                  <tr className="bg-[#0e0e1a]">
                    {[
                      { key: "ticker", label: "Ticker" },
                      { key: "name", label: "Name" },
                      { key: "market_cap_m", label: "MC ($M)", sortable: true },
                      { key: "close_price", label: "Close", sortable: true },
                      { key: "spread_pct", label: "Spread", sortable: true },
                      { key: "alignment", label: "Alignment" },
                      {
                        key: "volume_ratio",
                        label: "Vol Ratio",
                        sortable: true,
                      },
                    ].map((col) => (
                      <th
                        key={col.key}
                        onClick={() =>
                          col.sortable &&
                          handleSort(col.key as keyof ScanResult)
                        }
                        className={`px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e] whitespace-nowrap ${col.sortable ? "cursor-pointer hover:text-gray-400" : ""}`}
                      >
                        {col.label}{" "}
                        {col.sortable &&
                          (sortBy === col.key
                            ? sortDir === "asc"
                              ? "↑"
                              : "↓"
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
                        ${Number(r.close_price).toFixed(2)}
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
                            {Number(r.spread_pct).toFixed(2)}%
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
                      <td
                        className="px-3 py-2 tabular-nums"
                        style={{
                          color:
                            r.volume_ratio > 1.2
                              ? "#22c55e"
                              : r.volume_ratio > 1.0
                                ? "#a3e635"
                                : "#6b7280",
                          fontWeight: r.volume_ratio > 1.2 ? 700 : 400,
                        }}
                      >
                        {Number(r.volume_ratio).toFixed(2)}x{" "}
                        {r.volume_ratio > 1.2 && "▲"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "config" && (
          <div className="max-w-lg">
            <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-5">
              SCAN PARAMETERS
            </h2>
            <p className="text-gray-500 text-xs mb-6 leading-relaxed">
              Configure parameters below. The terminal command updates live —
              copy and run it.
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
              <div>
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">
                  Max Spread %
                </label>
                <input
                  type="number"
                  step={0.1}
                  value={configSpread}
                  onChange={(e) => setConfigSpread(Number(e.target.value))}
                  className="bg-[#12121e] border border-[#2a2a3e] rounded px-3 py-2 text-sm w-40 outline-none focus:border-purple-500"
                />
              </div>
              <div className="mt-2">
                <label className="block text-[10px] text-gray-600 uppercase tracking-widest mb-1.5">
                  Terminal Command
                </label>
                <div className="bg-[#12121e] border border-[#2a2a3e] rounded p-3 text-green-400 text-xs">
                  <span className="text-gray-600">$</span> python scanner.py
                  --min-mc {configMinMc} --max-mc {configMaxMc} --spread{" "}
                  {configSpread}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "history" && (
          <div>
            <h2 className="text-sm font-bold text-purple-400 tracking-wider mb-5">
              SCAN HISTORY
            </h2>
            <div className="border border-[#1a1a2e] rounded-md overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-[#0e0e1a]">
                    {["Date", "MC Range", "Max Spread", "Results", ""].map(
                      (h) => (
                        <th
                          key={h}
                          className="px-3 py-2 text-left text-[10px] font-semibold text-gray-600 uppercase tracking-wider border-b border-[#1a1a2e]"
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {scanRuns.map((run, i) => (
                    <tr
                      key={run.id}
                      className={`${selectedRunId === run.id ? "bg-[#14142a]" : i % 2 === 0 ? "bg-[#0a0a12]" : "bg-[#0e0e18]"}`}
                    >
                      <td className="px-3 py-2.5">
                        {new Date(run.scanned_at).toLocaleString()}
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">
                        ${run.min_market_cap_m}M – ${run.max_market_cap_m}M
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">
                        {run.max_spread_pct}%
                      </td>
                      <td className="px-3 py-2.5">
                        <span className="text-green-400 font-semibold">
                          {run.total_results}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <button
                          onClick={() => {
                            setSelectedRunId(run.id);
                            setActiveTab("results");
                          }}
                          className="bg-[#1e1b2e] border border-[#4c3a8a] rounded px-3 py-1 text-purple-400 text-[11px] font-semibold hover:bg-[#2a2548] transition-colors"
                        >
                          View
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
