-- Migration 002 - scan_requests table for UI-triggered scans.
--
-- Run this AFTER 001_recreate_tables.sql.
--
-- Workflow:
--   1. Dashboard "Run Scan" button INSERTs a row with status='pending'
--   2. Local scanner_worker.py polls for status='pending', picks the oldest
--   3. Worker UPDATEs status='running', runs scanner.py via subprocess
--   4. On success: status='completed' + scan_run_id linked to the new scan_runs row
--   5. On failure: status='failed' + error_message populated
--   6. Dashboard polls the in-flight request and reloads when status='completed'

CREATE TABLE scan_requests (
    id                BIGSERIAL PRIMARY KEY,
    requested_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    mode              TEXT            NOT NULL,
    min_market_cap_m  DOUBLE PRECISION,
    max_market_cap_m  DOUBLE PRECISION,
    status            TEXT            NOT NULL DEFAULT 'pending',
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    scan_run_id       BIGINT          REFERENCES scan_runs(id) ON DELETE SET NULL,
    error_message     TEXT
);

CREATE INDEX scan_requests_status_idx     ON scan_requests (status, requested_at);
CREATE INDEX scan_requests_requested_idx  ON scan_requests (requested_at DESC);

-- Same RLS posture as the other tables (anon-key insert/update from both
-- dashboard and worker).
ALTER TABLE scan_requests DISABLE ROW LEVEL SECURITY;
