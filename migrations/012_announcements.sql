-- Item 8: Announcements. Additive only -- two new tables, zero changes to any existing table.
-- See docs/announcements_design.md. Rollback: DROP TABLE announcement_reads; DROP TABLE announcements;
-- (reads table first, FK order). Kept in sync with announcements_core.py's own ensure_tables(), which
-- runs the same CREATE TABLE IF NOT EXISTS statements at boot regardless of whether this migration
-- has been run -- the same redundant-but-harmless belt-and-suspenders pattern Phase 2 already uses
-- (cycle_middleware.ensure_tables() + migrations/001_add_cycle_state.sql).

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,   -- earth|continent|country|zone|state|district|tehsil|village
    author_user_id TEXT NOT NULL,
    title TEXT,
    body TEXT NOT NULL,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ann_location ON announcements(location_id, created_at DESC);

CREATE TABLE IF NOT EXISTS announcement_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(announcement_id, user_id),
    FOREIGN KEY (announcement_id) REFERENCES announcements(id)
);
