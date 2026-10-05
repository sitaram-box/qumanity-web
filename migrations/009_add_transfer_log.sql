-- Phase 3: an audit trail of every pipeline transfer attempt (manual-trigger only in this
-- phase -- see docs/phase_3_report.md). One row per from_level->to_level hop per cycle.

CREATE TABLE IF NOT EXISTS transfer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_level VARCHAR(20) NOT NULL,
    to_level VARCHAR(20) NOT NULL,
    cycle_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    records_moved INTEGER DEFAULT 0,
    holdings_created INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'in_progress',
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_transfer_log_cycle ON transfer_log(cycle_id);
CREATE INDEX IF NOT EXISTS idx_transfer_log_status ON transfer_log(status);
