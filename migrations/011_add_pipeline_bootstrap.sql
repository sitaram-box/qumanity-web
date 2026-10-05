-- Phase 5: bootstrap state (Year 1 vs Year 2 — see docs/phase_5_report.md Decision 1) and a
-- minimal admin notification log (no general-purpose notification/email system existed to reuse
-- — notify_core.py is a narrow per-user chat/request unread-badge counter, not an event log).

CREATE TABLE IF NOT EXISTS pipeline_bootstrap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_1_start_amavasya TIMESTAMP NOT NULL,
    year_2_start_amavasya TIMESTAMP NOT NULL,
    pipeline_active BOOLEAN DEFAULT 0,
    activated_at TIMESTAMP,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS admin_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_notifications_read ON admin_notifications(read_at);
