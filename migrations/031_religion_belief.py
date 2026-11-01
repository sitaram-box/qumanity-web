"""Adds users.religion_belief and users.religion_locked_at (2026-10-28): an optional,
self-selected spiritual-path field that drives which scripture source the poems marquee
shows a signed-in member (see app.py's RELIGION_MARQUEE_SOURCES and poems.js).

One of 'hindu', 'christian', 'muslim', 'sikh', 'buddhist', 'jain', 'other',
'prefer_not_to_say', or NULL (never answered -- distinct from 'prefer_not_to_say', which is an
explicit answer). Set once, at or shortly after registration; religion_locked_at records when it
was first saved. Like every other identity-adjacent field in this codebase, it is NOT free to
edit after that -- a signed-in member who wants to change it submits a request through the Admin
Panel (not a village-council ticket like identity_core.py's id_change_a/birth_time_correction:
this field has no bearing on zodiac, Kundali, Private ID or location, so it doesn't need that
routing, just an admin decision)."""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "religion_belief" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN religion_belief TEXT")
    if "religion_locked_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN religion_locked_at TEXT")
    conn.commit()
    print("    users.religion_belief/religion_locked_at ready (default NULL -- never answered).")
