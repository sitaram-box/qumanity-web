"""Adds admin_export_log (2026-10-18), for the Admin member-export tool
(api_admin_users_export in app.py). Every successful export -- JSON preview or CSV download --
writes one row here: who, when, which filters, how many rows. This matches the accountability
already established for the one other place the system shows someone else's Private ID
(recovery_core.reveal_private_code, logged to id_recovery_reveals, "every reveal is logged") --
a bulk export of every member's Private ID is at least as sensitive as a single reveal, so it
gets the same treatment.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_export_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user_id INTEGER NOT NULL,
            exported_at TEXT NOT NULL,
            level TEXT,
            location_id TEXT,
            period TEXT,
            row_count INTEGER NOT NULL,
            format TEXT NOT NULL
        )
    """)
    conn.commit()
    print("    admin_export_log ready.")
