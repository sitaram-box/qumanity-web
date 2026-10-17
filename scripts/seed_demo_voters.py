#!/usr/bin/env python3
"""Demo voter accounts for testing the Collective Board's post -> vote -> reward -> freeze path
(NOT the Election pilot's demo population -- see the WARNING below), plus the initial
post_testing testing_windows row for the Post Testing cycle (docs/test_cycle_design.md).

    QM_DB_PATH=/path/to/real.db python3 scripts/seed_demo_voters.py          # default N=50
    QM_DB_PATH=/path/to/real.db python3 scripts/seed_demo_voters.py --n=20
    python3 scripts/seed_demo_voters.py --force                              # local default DB

Creates N users named "Demo Voter 1".."Demo Voter N", resident in Rohini Sector 24
(election_core.PILOT_VILLAGE_ID), through the real /api/auth/register route (same technique as
scripts/seed_election_demo.py) -- so Private IDs, PINs, zodiac and kundali are all real, valid
data, not stubs. Their 0_Earth folders are NOT written (folder_connector disabled here). The
admin account is never touched.

WARNING -- is_demo is NOT exclusive to this script. scripts/seed_election_demo.py already set
is_demo=1 on 500 unrelated Election-pilot residents of this same village. To never retire or
miscount THOSE users, every operation here is scoped to BOTH is_demo=1 AND a "Demo Voter N"
name -- never to is_demo=1 alone. scripts/retire_demo_voters.py uses the identical scope.

After seeding, creates the initial post_testing window via test_cycle_scheduler.start_window()
-- the SAME function the admin panel's "Start a new test period" button calls, so this script
exercises no code path the rest of the feature doesn't already use. Skipped (with a clear
message, not an error) if an active post_testing window already exists -- re-running this
script never creates a second one.
"""
import argparse
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if not os.environ.get("QM_DB_PATH") and "--force" not in sys.argv:
    sys.exit(
        "Refusing to run: no QM_DB_PATH set and --force not passed. Either set QM_DB_PATH to the "
        "database you actually mean to seed (e.g. the Railway volume path, when running this from "
        "the Railway console), or pass --force to confirm you mean the local default DB.\n"
    )

import app as appmod  # noqa: E402
import election_core  # noqa: E402
import folder_connector  # noqa: E402
import test_cycle_scheduler  # noqa: E402
from db import get_db  # noqa: E402

DEFAULT_N = 50
DEMO_VOTER_PIN = "70070"
DEMO_VOTER_DOB = "1996-06-15"   # fixed, arbitrary -- voting eligibility doesn't depend on age here
DEMO_VOTER_TOB = "12:00"
VILLAGE = election_core.PILOT_VILLAGE_ID
NAME_PREFIX = "Demo Voter"
VOTE_DISTRIBUTION = {"+1": 0.5, "0": 0.3, "-1": 0.2}


def _village_location() -> dict:
    conn = get_db()
    row = conn.execute(
        "SELECT present_location_json FROM users WHERE json_extract(present_location_json, '$.village.id') = ? "
        "ORDER BY id LIMIT 1", (VILLAGE,),
    ).fetchone()
    conn.close()
    if not row:
        sys.exit(f"No member lives in {VILLAGE} yet -- the admin account should.")
    return json.loads(row["present_location_json"])


def _ensure_columns(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "is_demo" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
    if "is_removed" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_removed INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def _existing() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, private_id_9digit FROM users WHERE is_demo = 1 AND name LIKE ? ORDER BY id",
        (f"{NAME_PREFIX} %",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_users(n: int) -> list[dict]:
    conn = get_db()
    _ensure_columns(conn)
    conn.close()
    existing = _existing()
    have = len(existing)
    if have >= n:
        print(f"{have} demo voter(s) already exist (>= requested {n}) -- not adding more.")
        return existing

    where = _village_location()
    folder_connector.register_user_folder = lambda *a, **k: None  # keep 0_Earth free of test data
    new_made = []
    for i in range(have + 1, n + 1):
        name = f"{NAME_PREFIX} {i}"
        client = appmod.app.test_client()
        r = client.post("/api/auth/register", json={
            "name": name, "gender": "male" if i % 2 else "female",
            "dob": DEMO_VOTER_DOB, "tob": DEMO_VOTER_TOB,
            "pin": DEMO_VOTER_PIN, "birth_location": where, "present_location": where,
        })
        if r.status_code != 201:
            sys.exit(f"Registration failed for {name}: {r.status_code} {r.get_data(as_text=True)[:200]}")
        body = r.get_json()
        new_made.append({"id": body["user_id"], "name": name, "private_id_9digit": body["private_code"]})

    conn = get_db()
    conn.executemany("UPDATE users SET is_demo = 1 WHERE id = ?", [(m["id"],) for m in new_made])
    conn.commit()
    conn.close()
    return existing + new_made


def create_testing_window(demo_user_count: int) -> dict | None:
    """Reuses test_cycle_scheduler.start_window() -- the SAME function the admin panel's own
    "Start a new test period" button calls -- so a window created here behaves identically to
    one created through the UI. Returns None (and prints why) if one is already active; never
    raises, since "a window already exists" is an expected, non-error outcome on a re-run."""
    conn = get_db()
    try:
        window = test_cycle_scheduler.start_window(conn, demo_user_count, VOTE_DISTRIBUTION)
    except ValueError as e:
        print(f"Testing window not created: {e}")
        conn.close()
        return None
    conn.close()
    return window


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=DEFAULT_N)
    p.add_argument("--force", action="store_true")  # already checked above; accepted so argparse doesn't reject it
    args = p.parse_args()

    made = create_users(args.n)
    print(f"\n{len(made)} demo voter(s) total, resident in {VILLAGE}.")
    print(f"PIN for every demo voter: {DEMO_VOTER_PIN}\n")
    print(f"{'Private ID':<12} Name")
    for m in made:
        print(f"{m['private_id_9digit']:<12} {m['name']}")

    print()
    window = create_testing_window(len(made))
    if window:
        print(f"post_testing window started: {window['start_date']} -> {window['end_date']} "
              f"(status={window['status']}, demo_user_count={window['demo_user_count']})")


if __name__ == "__main__":
    main()
