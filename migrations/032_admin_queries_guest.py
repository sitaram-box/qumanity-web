"""Makes admin_queries.user_id nullable + adds guest_name/guest_contact (2026-10-28): the new
public AI Support ticket route (POST /api/support/ticket) accepts anonymous submissions -- no
login required -- so a ticket's author is no longer always a real users.id. SQLite can't ALTER a
column FROM NOT NULL TO nullable in place; this rebuilds the table (the standard SQLite pattern --
create the new shape, copy every row across, drop the old table, rename it back) rather than skip
that and leave anonymous tickets unable to insert at all.

admin_query_replies is untouched -- only the Admin ever replies, always a real, logged-in user, so
author_user_id stays NOT NULL exactly as it already is.

admin_queries_core.list_open() (the Admin Panel feed) must change its own JOIN to a LEFT JOIN as
part of this same feature -- an INNER JOIN would silently drop every anonymous ticket (no
matching users row) from the feed entirely; that code change ships in the same commit as this
migration, not here (this file only owns the schema)."""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(admin_queries)")}
    if "guest_name" in cols:
        print("    admin_queries.guest_name/guest_contact already present -- nothing to do.")
        return
    conn.executescript("""
        CREATE TABLE admin_queries_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guest_name TEXT,
            guest_contact TEXT,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        );
        INSERT INTO admin_queries_new (id, user_id, category, subject, body, status, created_at)
            SELECT id, user_id, category, subject, body, status, created_at FROM admin_queries;
        DROP TABLE admin_queries;
        ALTER TABLE admin_queries_new RENAME TO admin_queries;
        CREATE INDEX IF NOT EXISTS idx_admin_queries_user ON admin_queries(user_id);
        CREATE INDEX IF NOT EXISTS idx_admin_queries_status ON admin_queries(status, created_at);
    """)
    conn.commit()
    print("    admin_queries.user_id now nullable; guest_name/guest_contact ready (anonymous AI Support tickets).")
