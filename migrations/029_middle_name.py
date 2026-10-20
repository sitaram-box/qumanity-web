"""Adds users.middle_name (2026-10-20): optional, kept separate from the existing free-text
`name` column (which stays the full display name, unchanged everywhere it's already shown).
Feeds the new Family Group naming logic (family_core._name_code()) and, longer term, any formal
document that wants first/middle/last apart. Blank means no middle name -- nothing backfills it.
"""
from __future__ import annotations

def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "middle_name" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN middle_name TEXT")
    conn.commit()
    print("    users.middle_name ready (default NULL).")
