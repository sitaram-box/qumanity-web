-- Phase 3: a singleton row tracking the most recent pipeline transfer, for the admin status
-- endpoint. Not used for any eligibility decision (that's cycle_state + the N-2 safety rule,
-- enforced in pipeline_core._check_safety against cycle_state directly) -- purely informational.

CREATE TABLE IF NOT EXISTS pipeline_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_transfer_level VARCHAR(20),
    last_transfer_cycle_id VARCHAR(50),
    last_transfer_completed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO pipeline_state (id) VALUES (1);
