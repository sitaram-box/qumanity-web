"""Verifies all three board post kinds together -- 'member', 'test', 'council_update' -- and the
contract between board_core.py's payload and static/js/board.js's rendering of it.

Standalone script, same convention as tests/test_council_updates.py and the earlier reward-path
harness: no test framework (none installed in this project), a throwaway DB built from the real
migration pipeline, PASS/FAIL printing, exit 1 on failure.

Badge TEXT itself (e.g. the literal string "Admin · Test") is a static/js/board.js rendering
concern with no JS runtime available here -- this file verifies the DATA that drives it
(post_kind, is_demo_post) is correct in the payload, plus a source-level contract check that
board.js's postBadge() actually branches on those exact fields with the exact strings. The
rendered-in-a-browser confirmation already happened during file 5/6's verification pass.

Run with: python3 -I tests/test_post_kinds.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH  # must happen before any import below -- see
                                      # test_council_updates.py's comment for why

import board_core
import wallet_core

NOW = dt.datetime.now(dt.timezone.utc)
FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def build_schema(path):
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
        (name, json.dumps(LOCATION), json.dumps(LOCATION), f"P{_counter[0]:08d}", is_demo),
    )
    conn.commit()
    return cur.lastrowid


conn = build_schema(_DB_PATH)

admin_id = make_user(conn, "Admin Author")
demo_id = make_user(conn, "Demo Voter 1", is_demo=1)
real_member_id = make_user(conn, "Real Member")
voters = [make_user(conn, f"Voter {i}") for i in range(10)]  # 10 ordinary members, for the member-post elevation check

print("=== Scenario: a member post, voted to clear Village's threshold (10), elevates ===")
member_pid = board_core.create_post(conn, admin_id, LOCATION, "Real civic post.", level="village", now=NOW)
for v in voters:
    board_core.cast_vote(conn, v, LOCATION, member_pid, 1, now=NOW)
row = conn.execute("SELECT score FROM board_posts WHERE id=?", (member_pid,)).fetchone()
check(f"score reached 10 from 10 real votes (got {row['score']})", row["score"] == 10)

conn.execute("UPDATE board_posts SET voting_end = ? WHERE id = ?", ((NOW - dt.timedelta(days=1)).isoformat(), member_pid))
conn.commit()
board_core.settle(conn, NOW)
row = conn.execute("SELECT status, elevated_to, post_kind, is_demo_post FROM board_posts WHERE id=?", (member_pid,)).fetchone()
check("member post elevated (score >= threshold)", row["status"] == "elevated")
check("post_kind in payload-backing row is 'member'", row["post_kind"] == "member")
check("is_demo_post is 0 for a real member post", row["is_demo_post"] == 0)
child = conn.execute("SELECT level, post_kind FROM board_posts WHERE id=?", (row["elevated_to"],)).fetchone()
check("elevated child is at Tehsil", child["level"] == "tehsil")
check("elevated child is also post_kind='member'", child["post_kind"] == "member")
bal = wallet_core.wallet_balance(conn, "user", str(admin_id))
check(f"real author's wallet WAS credited for real (got {bal})", bal > 0)
star_count = conn.execute("SELECT COUNT(*) FROM recognition_stars WHERE post_id=?", (member_pid,)).fetchone()[0]
check("a real recognition star WAS written for the real post", star_count == 1)

print("\n=== Scenario: a test post, voted under threshold, freezes -- never rewarded for real ===")
test_pid = board_core.create_post(conn, admin_id, LOCATION, "Admin-tagged test post.", level="village",
                                   now=NOW, post_kind="test", is_demo_post=False)
board_core.cast_vote(conn, demo_id, LOCATION, test_pid, 1, now=NOW)  # score 1, well under 10 -> freezes

print("\n=== Visibility while the test post is still ACTIVE (voting open) ===")
view_real = board_core.board_view(conn, real_member_id, LOCATION, "village", now=NOW, is_admin=False)
view_demo_active = board_core.board_view(conn, demo_id, LOCATION, "village", now=NOW, is_admin=False)
view_admin_active = board_core.board_view(conn, admin_id, LOCATION, "village", now=NOW, is_admin=True)
check("real member does NOT see the active test post", test_pid not in {p["id"] for p in view_real["posts"]})
check("demo viewer DOES see the active test post", test_pid in {p["id"] for p in view_demo_active["posts"]})
check("Admin DOES see the active test post", test_pid in {p["id"] for p in view_admin_active["posts"]})

conn.execute("UPDATE board_posts SET voting_end = ? WHERE id = ?", ((NOW - dt.timedelta(days=1)).isoformat(), test_pid))
conn.commit()
board_core.settle(conn, NOW)
row = conn.execute("SELECT status, post_kind, is_demo_post, test_reward_inr FROM board_posts WHERE id=?", (test_pid,)).fetchone()
check("test post froze (score 1 < threshold 10)", row["status"] == "frozen")
check("post_kind is 'test'", row["post_kind"] == "test")
check("is_demo_post is 0 (Admin-tagged, not scheduler-created)", row["is_demo_post"] == 0)
check(f"test_reward_inr WAS computed and stored (got {row['test_reward_inr']})", row["test_reward_inr"] == 10)  # rank 1 of 1 -> village max

print("\n=== Visibility AFTER freeze -- now visible to everyone ===")
view_real2 = board_core.board_view(conn, real_member_id, LOCATION, "village", now=NOW, is_admin=False)
check("real member DOES see the frozen test post now", test_pid in {p["id"] for p in view_real2["posts"]})
tp_payload = next(p for p in view_real2["posts"] if p["id"] == test_pid)
check("payload's post_kind == 'test'", tp_payload["post_kind"] == "test")
check("payload's is_demo_post == False", tp_payload["is_demo_post"] is False)
check("can_vote is False once frozen", tp_payload["can_vote"] is False)

print("\n=== The frozen test post shows the test record, with exact fields ===")
tr = tp_payload.get("test_record")
check("test_record is present", tr is not None)
if tr:
    check("test_record has voting_start", "voting_start" in tr)
    check("test_record has voting_end", "voting_end" in tr)
    check(f"test_record.final_score == 1 (got {tr['final_score']})", tr["final_score"] == 1)
    check(f"test_record.reward_inr == 10 (got {tr['reward_inr']})", tr["reward_inr"] == 10)
    check(f"test_record.demo_voter_count == 1 (got {tr['demo_voter_count']})", tr["demo_voter_count"] == 1)

print("\n=== No real reward, no real karma, no real recognition star for the test post ===")
bal2 = wallet_core.wallet_balance(conn, "user", str(admin_id))
check(f"Admin's real wallet balance is UNCHANGED from the member-post credit above (still {bal}, got {bal2})", bal2 == bal)
star_count2 = conn.execute("SELECT COUNT(*) FROM recognition_stars WHERE post_id=?", (test_pid,)).fetchone()[0]
check("no recognition star was written for the test post", star_count2 == 0)

print("\n=== A demo-authored test post (is_demo_post=True) ===")
demo_test_pid = board_core.create_post(conn, demo_id, LOCATION, "Demo Voter 1's own test post.", level="village",
                                        now=NOW, post_kind="test", is_demo_post=True)
row = conn.execute("SELECT post_kind, is_demo_post FROM board_posts WHERE id=?", (demo_test_pid,)).fetchone()
check("post_kind == 'test'", row["post_kind"] == "test")
check("is_demo_post == 1 for a scheduler-style demo post", row["is_demo_post"] == 1)

print("\n=== Council update: visible to all, not votable, reactions enabled, inert to settle() ===")
cu_id = board_core.create_council_update(conn, admin_id, LOCATION, "Council update for the matrix check.", level="village", now=NOW)
view_real3 = board_core.board_view(conn, real_member_id, LOCATION, "village", now=NOW, is_admin=False)
cu_payload = next(p for p in view_real3["posts"] if p["id"] == cu_id)
check("council update visible to an ordinary member", cu_id in {p["id"] for p in view_real3["posts"]})
check("post_kind == 'council_update'", cu_payload["post_kind"] == "council_update")
check("can_vote is False", cu_payload["can_vote"] is False)
check("reactions key is present", "reactions" in cu_payload)
try:
    board_core.cast_vote(conn, real_member_id, LOCATION, cu_id, 1, now=NOW)
    check("voting on a council update is rejected", False)
except ValueError:
    check("voting on a council update is rejected", True)
before_cu = dict(conn.execute("SELECT status FROM board_posts WHERE id=?", (cu_id,)).fetchone())
board_core.settle(conn, NOW + dt.timedelta(days=1))
after_cu = dict(conn.execute("SELECT status FROM board_posts WHERE id=?", (cu_id,)).fetchone())
check("settle() never changes a council update's status", before_cu == after_cu)

print("\n=== Source-level contract: board.js actually branches on post_kind/is_demo_post with the four exact badge strings ===")
board_js = open(os.path.join(ROOT, "static", "js", "board.js")).read()
check("postBadge() checks post_kind === 'council_update'", "post_kind === \"council_update\"" in board_js)
check("'Council Update' badge string present", '"Council Update"' in board_js)
check("postBadge() checks post_kind === 'test'", "post_kind === \"test\"" in board_js)
check("'Admin · Test' badge string present", '"Admin · Test"' in board_js)
check("'Demo · Test' badge string present", '"Demo · Test"' in board_js)
check("the council_update branch skips vote buttons (returns b before the vote-button block)",
      board_js.index('post_kind === "council_update"') < board_js.index("p.can_vote"))

os.remove(_DB_PATH)
print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s) -- {FAILS}")
    sys.exit(1)
print("ALL POST-KIND TESTS PASSED")
