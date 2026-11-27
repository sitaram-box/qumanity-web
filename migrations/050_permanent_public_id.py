"""Adds users.public_id_12 -- the permanent, location-independent 12-digit Public ID (2026-11-28,
the Admin's own explicit architecture decision): "a user must have ONE permanent identity that the
whole world can search, regardless of how many times they travel and change their dynamic
account_id." Unlike private_id_9digit (the login credential, never shown on a Q-Card) and
account_id/account_ids.search_code (both already existed, and both change every time a user's
present location changes -- see social_core.record_new_account_id()), this is generated exactly
ONCE, at registration, and is never regenerated or rotated for any reason.

Backfills EVERY existing user, not just real/non-demo ones -- a permanent root identity is
meaningful for every account regardless of is_demo, and withholding it from the 500 election-pilot
demo voters would just be a NULL this migration would need to explain away later for no benefit.

Not an admin-triggerable button (unlike migrations/047/048's DOB-ID pair) -- there is no Admin
Panel exposure for this one. It runs automatically via tools/run_migrations.py the same way every
other migration does, with no separate confirm step: a 12-digit Public ID carries none of the
DOB-ID migration's "changes an existing LOGIN credential" risk, it is a brand-new column with
nothing else depending on its value yet.
"""
from __future__ import annotations

import id_generator


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "public_id_12" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN public_id_12 TEXT")
        conn.commit()
        print("    users.public_id_12 ready (default NULL).")

    # A UNIQUE index, not a UNIQUE column constraint -- SQLite's ALTER TABLE ADD COLUMN can't add
    # a UNIQUE constraint directly (same reason id_migrations/q_cards use a separate CREATE UNIQUE
    # INDEX for their own unique columns elsewhere in this codebase). NULL-safe: SQLite indexes
    # treat every NULL as distinct from every other NULL, so this is a no-op until the backfill
    # below actually assigns real values.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_public_id_12 ON users(public_id_12)")
    conn.commit()

    rows = conn.execute("SELECT id FROM users WHERE public_id_12 IS NULL").fetchall()
    for row in rows:
        code = id_generator.generate_public_id_12(conn)
        conn.execute("UPDATE users SET public_id_12 = ? WHERE id = ?", (code, row["id"]))
        conn.commit()
    if rows:
        print(f"    backfilled public_id_12 for {len(rows)} existing user(s).")
