"""Verifies the Council Update feature (docs/test_cycle_design.md, Path 2 decision): a board
post kind that is never voted on, never freezes/elevates/rewards, and carries only optional
Agree/Disagree reactions.

Standalone script, no test framework -- this project has none installed (checked: no pytest in
requirements.txt or the venv) -- so this follows the same convention already proven earlier in
this task (the throwaway-DB-via-the-real-migration-pipeline harness, PASS/FAIL printing, exit 1
on failure), not a new dependency.

IMPORTANT: db.py computes DB_PATH once, at its own import time, from QM_DB_PATH. The throwaway
DB path is reserved and QM_DB_PATH is set BEFORE any project module is imported below -- setting
it later (e.g. right before a test_client() call) would have no effect, since `db` would already
be imported (transitively, via board_core/app) with the wrong path baked in.

Run with: python3 -I tests/test_council_updates.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile

ROOT = "/Users/macmudgal/Desktop/Qumanity_DPG"
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH  # must happen before any import below

import board_core
import reactions_core

NOW = dt.datetime.now(dt.timezone.utc)
FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def build_schema(path):
    """Real schema + the full real migration pipeline (002/007 for cycle_id/pipeline_level,
    015-017 for this task's own tables/columns) -- never a hand-picked subset, so this runs
    against exactly the schema production has. Raw sqlite3 here, not db.get_db(), since the
    schema doesn't exist yet for get_db()'s PRAGMA foreign_keys = ON to attach to meaningfully."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(open(os.path.join(ROOT, "db", "schema.sql")).read())
    conn.commit()
    conn.execute("ALTER TABLE users ADD COLUMN private_id_9digit TEXT")
    conn.commit()

    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import importlib
    import run_migrations
    importlib.reload(run_migrations)
    run_migrations._ensure_migrations_table(conn)
    run_migrations._ensure_source_tables(conn)
    files = sorted(
        list(run_migrations.MIGRATIONS_DIR.glob("*.sql")) + list(run_migrations.MIGRATIONS_DIR.glob("*.py")),
        key=lambda p: p.name,
    )
    for f in files:
        (run_migrations._run_sql_file if f.suffix == ".sql" else run_migrations._run_py_file)(conn, f)
    return conn


LOCATION = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_counter = [0]


def make_user(conn, name, is_demo=0) -> int:
    _counter[0] += 1
    cur = conn.execute(
        """INSERT INTO users (name, gender, dob, tob, birth_location_json, present_location_json,
                               private_id_9digit, is_demo, is_removed)
           VALUES (?, 'female', '1990-01-01', '08:00', ?, ?, ?, ?, 0)""",
        (name, json.dumps(LOCATION), json.dumps(LOCATION), f"T{_counter[0]:08d}", is_demo),
    )
    conn.commit()
    return cur.lastrowid


print("=== Setup: one council member (acting as Admin for this test), one ordinary member, one demo voter ===")
conn = build_schema(_DB_PATH)
council_id = make_user(conn, "Council Author")
member_id = make_user(conn, "Ordinary Member")
demo_id = make_user(conn, "Demo Voter 1", is_demo=1)

cu_id = board_core.create_council_update(conn, council_id, LOCATION, "Weekly cleanliness drive Saturday 8am.", level="village", now=NOW)
print(f"  council update created, id={cu_id}")

print("\n=== Visibility: council updates are visible to every signed-in member, not hidden like test posts ===")
view_member = board_core.board_view(conn, member_id, LOCATION, "village", now=NOW, is_admin=False)
view_demo = board_core.board_view(conn, demo_id, LOCATION, "village", now=NOW, is_admin=False)
ids_member = {p["id"] for p in view_member["posts"]}
ids_demo = {p["id"] for p in view_demo["posts"]}
check("ordinary member sees the council update", cu_id in ids_member)
check("demo viewer sees the council update", cu_id in ids_demo)

print("\n=== Payload shape: post_kind, can_vote, reactions ===")
cu_payload = next(p for p in view_member["posts"] if p["id"] == cu_id)
check("post_kind == 'council_update'", cu_payload["post_kind"] == "council_update")
check("can_vote is False", cu_payload["can_vote"] is False)
check("reactions key present with all-zero counts (no reactions cast yet)",
      cu_payload.get("reactions") == {"agree": 0, "disagree": 0, "read": 0, "mine": None})

print("\n=== A member post has NO reactions key (reaction_counts is council_update-only) ===")
member_post_id = board_core.create_post(conn, member_id, LOCATION, "An ordinary member post.", level="village", now=NOW)
view_member2 = board_core.board_view(conn, member_id, LOCATION, "village", now=NOW, is_admin=False)
mp_payload = next(p for p in view_member2["posts"] if p["id"] == member_post_id)
check("member post payload has no 'reactions' key", "reactions" not in mp_payload)

print("\n=== Voting on a council update is rejected server-side, with a specific error ===")
try:
    board_core.cast_vote(conn, member_id, LOCATION, cu_id, 1, now=NOW)
    check("cast_vote() raises on a council_update post", False)
except ValueError as e:
    check(f"cast_vote() raised ValueError: {e!r}", str(e) == "This post is not open for voting")
except Exception as e:
    check(f"cast_vote() raised the WRONG exception type: {type(e).__name__}: {e}", False)

print("\n=== The same rejection through the real HTTP route (/api/board/vote), not just the function ===")
import app as appmod  # imported AFTER QM_DB_PATH was set above, so its own get_db() calls use this same throwaway file

client = appmod.app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = member_id
r = client.post("/api/board/vote", json={"post_id": cu_id, "value": 1})
check(f"HTTP route returns 400 (got {r.status_code})", r.status_code == 400)
body = r.get_json() or {}
check(f"HTTP route error message matches (got {body.get('error')!r})",
      body.get("error") == "This post is not open for voting")

print("\n=== Reactions: cast via the existing generic route, counted, 'mine' reflects the caller ===")
r = client.post(f"/api/reactions/board_post/{cu_id}", json={"reaction": "agree"})
check(f"reaction POST succeeds (got {r.status_code})", r.status_code == 200)
counts = reactions_core.counts_for(conn, "board_post", [cu_id], member_id)
check("agree count is 1 after casting", counts[cu_id]["agree"] == 1)
check("'mine' reflects the caller's own reaction", counts[cu_id]["mine"] == "agree")

print("\n=== Reactions on a non-council_update post are rejected (the small validation added to app.py) ===")
r = client.post(f"/api/reactions/board_post/{member_post_id}", json={"reaction": "agree"})
check(f"reaction on a member post returns 400 (got {r.status_code})", r.status_code == 400)

print("\n=== settle() is a complete no-op for a council_update post ===")
before = dict(conn.execute("SELECT status, score, elevated_to FROM board_posts WHERE id=?", (cu_id,)).fetchone())
board_core.settle(conn, NOW)
board_core.settle(conn, NOW + dt.timedelta(days=30))  # even far in the future, nothing changes
after = dict(conn.execute("SELECT status, score, elevated_to FROM board_posts WHERE id=?", (cu_id,)).fetchone())
check(f"status unchanged ({before['status']} -> {after['status']})", before == after)
check("status is still 'published' (never 'active'/'frozen'/'elevated'/'removed')", after["status"] == "published")
star_count = conn.execute("SELECT COUNT(*) FROM recognition_stars WHERE post_id=?", (cu_id,)).fetchone()[0]
check("no recognition star was ever written", star_count == 0)
wallet_balance_row = conn.execute(
    "SELECT balance_qoins FROM wallets WHERE owner_type='user' AND owner_id=?", (str(council_id),)
).fetchone()
check("the author's wallet was never touched (no row, or balance 0)",
      wallet_balance_row is None or wallet_balance_row["balance_qoins"] == 0)

os.remove(_DB_PATH)
print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s) -- {FAILS}")
    sys.exit(1)
print("ALL COUNCIL UPDATE TESTS PASSED")
