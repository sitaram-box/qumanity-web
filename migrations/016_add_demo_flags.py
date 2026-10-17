"""Adds users.is_demo and users.is_removed (2026-10-17), needed for the Collective Board's
test-post framework (Decision 2, Decision 3) and for excluding demo/retired accounts from every
member-count query. Schema-only -- no environment-specific data changes belong in a migration
file, since this same file replays against every database (local, production, any future
staging) through tools/run_migrations.py's shared tracking table. Marking any SPECIFIC existing
row as demo is a one-time, environment-specific fix and belongs in its own script
(scripts/mark_existing_demo_users.py), never here.

Both columns default to 0 -- every existing row, on every database this runs against, is
real and active until something explicitly says otherwise.
"""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "is_demo" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
    if "is_removed" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_removed INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("    users.is_demo / users.is_removed ready (both default 0).")
