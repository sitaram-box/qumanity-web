#!/usr/bin/env python3
"""One-time production data fix (2026-10-17): marks the two pre-existing demo/test accounts
found by the production audit -- id 25 ("Demo User", Bawana) and id 26 ("Demo Account",
Madurai) -- as is_demo=1. They predate the "Demo Voter N" naming convention entirely, so they
are scoped here by EXPLICIT id, never by a LIKE pattern (unlike scripts/seed_demo_voters.py /
scripts/retire_demo_voters.py, which scope to "Demo Voter %" because that population doesn't
exist yet when this script was written).

They are NOT deleted (Decision 1): different villages than Rohini Sector 24, cannot affect the
Rohini pilot by location alone, and their presence is a record of earlier testing worth keeping.

    QM_DB_PATH=/path/to/real.db python3 scripts/mark_existing_demo_users.py
    python3 scripts/mark_existing_demo_users.py --force

Idempotent: re-running after the rows are already is_demo=1 updates 0 rows and says so.
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
    if "is_demo" not in cols:
        sys.exit("users.is_demo does not exist yet -- run migrations/016_add_demo_flags.py first.")

    before = {r["id"]: r["is_demo"] for r in conn.execute(
        f"SELECT id, is_demo FROM users WHERE id IN ({','.join('?' * len(TARGET_IDS))})", TARGET_IDS
    )}
    missing = [i for i in TARGET_IDS if i not in before]
    if missing:
        print(f"WARNING: id(s) {missing} not found in this database -- skipping them.")

    cur = conn.execute(
        f"UPDATE users SET is_demo = 1 WHERE id IN ({','.join('?' * len(TARGET_IDS))}) AND is_demo = 0",
        TARGET_IDS,
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()

    print(f"Updated {updated} row(s) to is_demo=1.")
    for i in TARGET_IDS:
        if i in before:
            print(f"  id {i}: was is_demo={before[i]}")


if __name__ == "__main__":
    main()
