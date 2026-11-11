"""Adds admin_location_views (2026-11-12), the audit trail for the Location Board Explorer (LBE):
every time an Admin or a currently-serving council head opens or closes a location board through
the Multi-View dock, one row is written here -- who, which location, when, and how the board was
found (an LBE Location ID search, an LBE Account ID search, or the older hierarchical drill-down).

Not admin_export_log: that table's schema (exported_at, period, row_count, format) is shaped for
bulk member-data exports, a different action with different fields -- forcing LBE board views into
it would mean half its columns are always NULL for one kind of event and half for the other.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_location_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            location_level TEXT NOT NULL,
            location_id TEXT NOT NULL,
            location_name TEXT,
            source TEXT,
            viewed_at TEXT NOT NULL
        )
    """)
    conn.commit()
    print("    admin_location_views ready.")
