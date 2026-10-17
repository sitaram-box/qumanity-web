"""Adds location_elements.birth_users (2026-10-17): the membership-model correction that makes
location_elements.total_users mean PRESENT-location members (who actually votes/participates
there -- the real definition of "member of this location," already how voting and updates have
always worked), not birth location. birth_users is new, metadata-only -- "how many real users
(is_demo=0, is_removed=0) were born here" -- never counted toward total_users, never driving any
membership decision. See elemental_core.recompute_location_elements() for the corrected tallying
logic this column feeds; see scripts/backfill_location_elements.py for the one-time correction run.

Schema-only, like every other migration in this project -- no data backfill here (that's the
separate, explicit backfill script, same separation of concerns as migration 017's voted_at and
its own backfill)."""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(location_elements)")}
    if "birth_users" not in cols:
        conn.execute("ALTER TABLE location_elements ADD COLUMN birth_users INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    print("    location_elements.birth_users ready (default 0).")
