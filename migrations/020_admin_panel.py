"""Admin Panel (2026-10-18): general queries/complaints that fit neither Citizen Reports
(reports_core.py -- village-first council escalation ladder, NOT NULL location) nor ID recovery
(recovery_core.py -- already its own secure, logged reveal flow). "My karma looks wrong", "I
can't find my account" -- inherently Admin-only from the start, no location, no escalation.

admin_queries / admin_query_replies mirror reports_core.py's reports/report_updates shape
(a ticket + an append-only reply log) deliberately, rather than inventing a different pattern.

No schema change needed for notify_core.py: chat_read_state.kind is a plain TEXT column with no
CHECK constraint (verified by reading its SCHEMA directly) -- adding a third kind ('query',
alongside the existing 'private'/'group') is an application-level change only (notify_core.py's
own mark_read()/summary()/recent_items()), not a migration.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS admin_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_queries_user ON admin_queries(user_id);
        CREATE INDEX IF NOT EXISTS idx_admin_queries_status ON admin_queries(status, created_at);

        CREATE TABLE IF NOT EXISTS admin_query_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id INTEGER NOT NULL,
            author_user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (query_id) REFERENCES admin_queries(id)
        );
        CREATE INDEX IF NOT EXISTS idx_admin_query_replies_query ON admin_query_replies(query_id, created_at);
    """)
    conn.commit()
    print("    admin_queries / admin_query_replies ready.")
