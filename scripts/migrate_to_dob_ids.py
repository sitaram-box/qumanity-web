"""One-off: migrates every existing (non-demo, non-Admin) user's private_id_9digit from the old
random scheme (id_generator.generate_private_code) to the new DOB-based decreasing scheme
(id_generator.generate_dob_id / country_digit_for) -- see the Phase 1 research + Phase 2 build
thread, 2026-11-25.

NOT safe to re-run: there is no way to tell a DOB-derived ID from a random one after the fact, so
running this a second time would re-migrate every included user again, assigning a *different* new
ID each time (the "how many users already share this (dob, country_digit)" count will have
changed). Run it exactly once against production. Modeled on the retired
scripts/_retired/migrate_private_codes.py's safety pattern (a flag the script refuses to run
without) and its "commit per row, safe to interrupt and inspect partway" shape.

Excludes:
  - Every CURRENT private_id_9digit listed in QM_ADMIN_PRIVATE_IDS (comma-separated), read fresh
    at run time -- the same env var and format _is_admin() uses in app.py.
  - Every is_demo = 1 user: the Rohini Sector 24 election pilot's 500 demo voters must not have
    their login IDs changed mid-pilot.
  - Any user with no dob, an unparseable dob, or no resolvable birth_location.country.id: logged
    as a warning and skipped, not a crash -- left for manual follow-up.

Usage:
    python3 scripts/migrate_to_dob_ids.py --confirm
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

if "--confirm" not in sys.argv:
    print(__doc__)
    print("Refusing to run without --confirm.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: F401,E402  (runs ensure_database_ready()/_ensure_user_columns() at import time)
import id_generator  # noqa: E402
from db import get_db  # noqa: E402


def _ensure_id_migrations_table(conn) -> None:
    """Same literal as migrations/048_id_migrations_table.py -- kept here too so this script stays
    runnable standalone against a database that hasn't run that migration file yet."""
    conn.execute("""CREATE TABLE IF NOT EXISTS id_migrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        old_private_id_9digit TEXT,
        new_private_id_9digit TEXT NOT NULL,
        migrated_at TEXT NOT NULL
    )""")
    conn.commit()


def main() -> None:
    conn = get_db()
    _ensure_id_migrations_table(conn)

    admin_ids = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not admin_ids:
        print("[warn] QM_ADMIN_PRIVATE_IDS is unset or empty -- no user will be excluded as Admin.")

    demo_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_demo = 1").fetchone()[0]

    rows = conn.execute(
        "SELECT id, dob, birth_location_json, private_id_9digit FROM users "
        "WHERE is_demo = 0 ORDER BY id ASC"
    ).fetchall()

    migrated = skipped_admin = skipped_bad_data = 0
    for row in rows:
        if row["private_id_9digit"] in admin_ids:
            skipped_admin += 1
            continue

        if not row["dob"]:
            print(f"[warn] user {row['id']}: no dob -- skipped")
            skipped_bad_data += 1
            continue
        try:
            dob = dt.date.fromisoformat(row["dob"])
        except ValueError:
            print(f"[warn] user {row['id']}: unparseable dob {row['dob']!r} -- skipped")
            skipped_bad_data += 1
            continue

        try:
            birth_location = json.loads(row["birth_location_json"] or "{}")
        except (TypeError, ValueError):
            birth_location = {}
        country_id = (birth_location.get("country") or {}).get("id")
        if not country_id:
            print(f"[warn] user {row['id']}: no birth_location.country.id -- skipped")
            skipped_bad_data += 1
            continue

        country_digit = id_generator.country_digit_for(country_id)
        old_code = row["private_id_9digit"]
        new_code = id_generator.generate_dob_id(conn, dob, country_digit)

        conn.execute(
            "UPDATE users SET private_id_9digit = ?, dob_id_country_digit = ? WHERE id = ?",
            (new_code, country_digit, row["id"]),
        )
        conn.execute(
            """INSERT INTO id_migrations (user_id, old_private_id_9digit, new_private_id_9digit, migrated_at)
               VALUES (?, ?, ?, ?)""",
            (row["id"], old_code, new_code, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        migrated += 1

    conn.close()
    print(
        f"Migrated {migrated} user(s). "
        f"Skipped {skipped_admin} Admin ID(s), {demo_count} demo user(s), "
        f"{skipped_bad_data} with missing/unparseable data."
    )


if __name__ == "__main__":
    main()
