-- Item 9: Citizen Report (FIR-equivalent). Additive only -- two new tables, zero changes to any
-- existing table. See docs/reports_design.md. Rollback: DROP TABLE report_updates; DROP TABLE
-- reports; (updates table first, FK order). Kept in sync with reports_core.py's own
-- ensure_tables(), same belt-and-suspenders pattern as migrations/012_announcements.sql.

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,       -- always 'village' at creation
    body TEXT NOT NULL,
    anonymous INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',          -- open|in_progress|resolved|denied|escalated
    current_holder_level TEXT,           -- village|tehsil|district|state|zone|country|continent|earth
    current_holder_id TEXT,
    escalation_path TEXT DEFAULT '[]',   -- JSON [{level, id, at, outcome}, ...]
    sla_deadline TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reports_holder ON reports(current_holder_level, current_holder_id);
CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, sla_deadline);

CREATE TABLE IF NOT EXISTS report_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    author_user_id TEXT NOT NULL,
    author_role TEXT,                    -- council_member|admin|system
    update_type TEXT NOT NULL,           -- acknowledged|needs_time|resolved|denied|escalated|comment
    message TEXT,
    new_deadline TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES reports(id)
);
CREATE INDEX IF NOT EXISTS idx_report_updates ON report_updates(report_id, created_at);
