"""Adds the id_migrations table (2026-11-25): an audit log of every private_id_9digit change made
by scripts/migrate_to_dob_ids.py (the one-off DOB-ID backfill) and, longer term, any other re-roll
of a user's login ID -- so support can answer "what was my old ID" after the switch, since
private_id_9digit is a live login credential, not a cosmetic label.

scripts/migrate_to_dob_ids.py also creates this table itself (CREATE TABLE IF NOT EXISTS, same
literal) so it stays runnable standalone against a database that hasn't run this migration file --
see that script's own docstring.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS id_migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        old_private_id_9digit TEXT,
        new_private_id_9digit TEXT NOT NULL,
        migrated_at TEXT NOT NULL
    )""")
    conn.commit()
    print("    id_migrations table ready.")
