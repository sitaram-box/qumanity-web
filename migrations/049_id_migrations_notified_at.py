"""Adds id_migrations.notified_at (2026-11-25): set when a migrated user has been emailed their
new DOB-based Private ID (app.py's /api/admin/notify-id-change). NULL means "not yet notified" --
the bulk-notify route selects WHERE notified_at IS NULL, so clicking "Notify Migrated Users" more
than once never re-emails anyone who was already successfully notified.
"""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(id_migrations)")}
    if "notified_at" not in cols:
        conn.execute("ALTER TABLE id_migrations ADD COLUMN notified_at TEXT")
    conn.commit()
    print("    id_migrations.notified_at ready (default NULL).")
