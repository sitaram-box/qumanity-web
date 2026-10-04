-- Phase 2 (lunar-cycle archival system): tracks which lunar cycle is currently "active" -- the
-- cycle_id every stamped write (migration 002) gets at write time. See
-- docs/lunar_cycle_system.md / docs/phase_2_report.md.
--
-- Mirrors cycle_middleware.py's own SCHEMA constant -- same pattern as db/schema.sql vs. every
-- *_core.py module's lazy ensure_tables() already used throughout this codebase: this file is
-- the auditable migration; cycle_middleware.py self-heals the same table (and seeds its first
-- row from lunar_calendar's own live computation) if a DB somehow never ran this file.
--
-- Additive only -- no existing table, column or row is touched.

CREATE TABLE IF NOT EXISTS cycle_state (
    cycle_id TEXT PRIMARY KEY,       -- e.g. "Bhadrapada_2026" -- see lunar_calendar.get_current_cycle_id()
    start_date TEXT NOT NULL,        -- ISO 8601, this cycle's starting Amavasya (IST)
    mid_date TEXT NOT NULL,          -- ISO 8601, this cycle's Purnima (IST)
    end_date TEXT NOT NULL,          -- ISO 8601, this cycle's ending Amavasya (IST)
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'closed' -- exactly one row is ever 'active'
    activated_at TEXT NOT NULL,
    closed_at TEXT,
    activated_by TEXT                -- 'system:auto-seed' or an admin's identifier, see cycle_middleware.transition_to()
);

CREATE INDEX IF NOT EXISTS idx_cycle_state_status ON cycle_state(status);
CREATE INDEX IF NOT EXISTS idx_cycle_state_activated_at ON cycle_state(activated_at);
