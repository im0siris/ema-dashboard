-- Migration 001 — recreate scan_runs / scan_results for v3 multi-mode scanner.
-- WARNING: drops existing data. Per the design discussion, v2 rows were dev-stage only.

DROP TABLE IF EXISTS scan_results;
DROP TABLE IF EXISTS scan_runs;

CREATE TABLE scan_runs (
    id                BIGSERIAL PRIMARY KEY,
    invocation_id     UUID            NOT NULL,
    scanned_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    mode              TEXT            NOT NULL,
    regime_state      TEXT,
    min_market_cap_m  DOUBLE PRECISION,
    max_market_cap_m  DOUBLE PRECISION,
    universe_size     INTEGER,
    kept_count        INTEGER
);

CREATE INDEX scan_runs_invocation_idx ON scan_runs (invocation_id);
CREATE INDEX scan_runs_mode_idx       ON scan_runs (mode);
CREATE INDEX scan_runs_scanned_at_idx ON scan_runs (scanned_at DESC);

CREATE TABLE scan_results (
    id              BIGSERIAL PRIMARY KEY,
    scan_run_id     BIGINT          NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    ticker          TEXT            NOT NULL,
    name            TEXT,
    market_cap_m    DOUBLE PRECISION,
    mode            TEXT            NOT NULL,
    composite_score DOUBLE PRECISION,
    scorer_scores   JSONB           NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX scan_results_run_idx    ON scan_results (scan_run_id);
CREATE INDEX scan_results_ticker_idx ON scan_results (ticker);
CREATE INDEX scan_results_mode_idx   ON scan_results (mode);

-- Disable RLS so the anon/publishable key can insert (matches v2 behavior).
-- For a public-read dashboard with private writes, you'd instead enable RLS
-- with a SELECT-only policy for anon and use a service-role key for inserts.
ALTER TABLE scan_runs    DISABLE ROW LEVEL SECURITY;
ALTER TABLE scan_results DISABLE ROW LEVEL SECURITY;
