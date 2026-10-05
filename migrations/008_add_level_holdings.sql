-- Phase 3: level_holdings -- the computed aggregate for one (level, level_id, cycle_id). Written
-- by pipeline_core.transfer_level() each time a cycle's data arrives at a new level. Upserted
-- (UNIQUE(level, level_id, cycle_id)), never duplicated -- see docs/phase_3_report.md Decision 7.

CREATE TABLE IF NOT EXISTS level_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level VARCHAR(20) NOT NULL,
    level_id VARCHAR(50) NOT NULL,
    cycle_id VARCHAR(50) NOT NULL,
    summary_json TEXT NOT NULL,
    source_ids TEXT,
    record_counts TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(level, level_id, cycle_id)
);

CREATE INDEX IF NOT EXISTS idx_holding_level_cycle ON level_holdings(level, cycle_id);
CREATE INDEX IF NOT EXISTS idx_holding_level_id ON level_holdings(level_id);
