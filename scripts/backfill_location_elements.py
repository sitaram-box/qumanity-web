#!/usr/bin/env python3
"""One-time (and safely re-runnable) correction for location_elements (2026-10-17): rebuilds
every row so total_users means PRESENT-location real members (is_demo=0, is_removed=0) -- the
actual definition of "member of this location," matching how voting/updates have always worked
-- and birth_users is a new, separate, metadata-only column ("born here," never counted toward
total_users). This also undoes the demo-user pollution left by every registration since the
Election pilot (2026-09-29): update_location_stats() runs unconditionally at registration,
before is_demo is ever set, so it has never excluded demo users from the live incremental path
it feeds (that live path is UNCHANGED by this script -- this is a one-time correction of the
stored table, not a change to registration).

    QM_DB_PATH=/path/to/real.db python3 scripts/backfill_location_elements.py
    QM_DB_PATH=/path/to/real.db python3 scripts/backfill_location_elements.py --dry-run
    python3 scripts/backfill_location_elements.py --force   # local default DB

--dry-run computes and prints everything a real run would, but writes nothing -- see
elemental_core.recompute_location_elements()'s own dry_run parameter.

Reuses elemental_core.recompute_location_elements() -- the actual rebuild logic lives there, not
duplicated here. Idempotent: a full rebuild from the CURRENT is_demo=0/is_removed=0 population
every time -- running it twice in a row, with nothing else changing in between, corrects 0 rows
the second time. Touches ONLY location_elements -- no karma, wallet, or any other table.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if not os.environ.get("QM_DB_PATH") and "--force" not in sys.argv:
    sys.exit(
        "Refusing to run: no QM_DB_PATH set and --force not passed. Either set QM_DB_PATH to the "
        "database you actually mean (e.g. when running this from the Railway console), or pass "
        "--force to confirm you mean the local default DB.\n"
    )

import elemental_core  # noqa: E402
from db import get_db  # noqa: E402

FIELDS = ("total_users", "birth_users", "fire_count", "earth_count", "air_count", "water_count")


def main():
    dry_run = "--dry-run" in sys.argv
    conn = get_db()

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(location_elements)")}
    if "birth_users" not in cols:
        sys.exit("location_elements.birth_users does not exist yet -- run migrations/018_add_birth_users_column.py first.")

    before = {
        (r["location_id"], r["location_type"]): {f: r[f] for f in FIELDS}
        for r in conn.execute(f"SELECT location_id, location_type, {', '.join(FIELDS)} FROM location_elements")
    }
    result = elemental_core.recompute_location_elements(conn, dry_run=dry_run)
    after = result["new_rows"]  # {(location_id, location_type): {total_users, birth_users, fire_count, ...}}
    conn.close()

    all_keys = set(before) | set(after)
    corrected, unchanged = [], []
    for key in all_keys:
        b = before.get(key)
        a = after.get(key)
        (corrected if b != a else unchanged).append((key, b, a))

    label = "DRY RUN -- nothing written" if dry_run else "APPLIED"
    print(f"[{label}]")
    print(f"Counted {result['real_users_counted']} real user(s) (is_demo=0, is_removed=0).")
    print(f"location_elements: {result['rows_before']} row(s) before -> {result['rows_after']} row(s) after.")
    print(f"{len(corrected)} row(s) corrected, {len(unchanged)} row(s) already correct.\n")

    if corrected:
        print(f"{'location_id':<20} {'type':<10} {'total before':>13} {'total after':>12} {'birth before':>13} {'birth after':>12}")
        for key, b, a in sorted(corrected, key=lambda x: -(x[1]["total_users"] if x[1] else 0)):
            b_total = b["total_users"] if b else 0
            a_total = a["total_users"] if a else 0
            b_birth = b["birth_users"] if b else 0
            a_birth = a["birth_users"] if a else 0
            print(f"{key[0]:<20} {key[1]:<10} {b_total:>13} {a_total:>12} {b_birth:>13} {a_birth:>12}")


if __name__ == "__main__":
    main()
