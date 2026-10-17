#!/usr/bin/env python3
"""One-time production data fix (2026-10-17): retires the two stray demo accounts found by the
production audit -- id 25 ("Demo User") and id 26 ("Demo Account"), already marked is_demo=1 by
scripts/mark_existing_demo_users.py. They are not part of the board-test cycle
(scripts/seed_demo_voters.py's "Demo Voter N" population, excluded from test_cycle_scheduler.py's
_demo_voters() by name as of this same fix) and serve no further purpose, but their rows are kept
-- a record of earlier testing worth keeping -- rather than deleted.

Sets is_removed=1, the same flag every other retirement in this codebase uses: the row stays,
sign-in is refused, and the account drops out of every public list and count. Does not touch
is_demo, which is already 1 and is not what gates sign-in.

Scoped by EXPLICIT id only, never by a LIKE pattern -- these two accounts predate the "Demo
Voter N" naming convention and must never be confused with that population.

    QM_DB_PATH=/path/to/real.db python3 scripts/retire_stray_demo_accounts.py
    python3 scripts/retire_stray_demo_accounts.py --force

Refuses to run if either target id is not is_demo=1 -- retiring a non-demo account by accident
through this script would be the wrong tool for that job.

Idempotent: re-running after the rows are already is_removed=1 updates 0 rows and says so.
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

from db import get_db  # noqa: E402

TARGET_IDS = (25, 26)


def main():
    conn = get_db()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "is_removed" not in cols:
        sys.exit("users.is_removed does not exist yet -- run migrations/016_add_demo_flags.py first.")

    rows = {r["id"]: (r["name"], r["is_demo"], r["is_removed"]) for r in conn.execute(
        f"SELECT id, name, is_demo, is_removed FROM users WHERE id IN ({','.join('?' * len(TARGET_IDS))})",
        TARGET_IDS,
    )}

    missing = [i for i in TARGET_IDS if i not in rows]
    if missing:
        sys.exit(f"Refusing to run: id(s) {missing} not found in this database.")

    not_demo = [i for i in TARGET_IDS if not rows[i][1]]
    if not_demo:
        sys.exit(
            f"Refusing to run: id(s) {not_demo} are not is_demo=1 in this database. "
            "This script only retires confirmed demo accounts, by design -- not what you meant? "
            "Check TARGET_IDS and the database you pointed QM_DB_PATH at."
        )

    cur = conn.execute(
        f"UPDATE users SET is_removed = 1 WHERE id IN ({','.join('?' * len(TARGET_IDS))}) AND is_removed = 0",
        TARGET_IDS,
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    print(f"Retired {updated} row(s) to is_removed=1.")
    for i in TARGET_IDS:
        name, is_demo, was_removed = rows[i]
        print(f"  id {i} ({name!r}): was is_demo={is_demo}, is_removed={was_removed}")


if __name__ == "__main__":
    main()
