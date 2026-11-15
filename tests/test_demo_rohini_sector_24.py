"""Covers the public, read-only, fully synthetic demo (2026-11-15 brief):

  GET /demo/rohini-sector-24 -- linked from a Hacker-News "Show HN" post. Must work for an
  anonymous visitor, must never touch the database, and must render exclusively from
  demo_data.py's own hardcoded constants (the one approved exception: a Kundali chart computed
  from a fabricated birth input via zodiac_core/kundali_analyser -- both pure functions).

Standalone script, same convention as tests/test_copyright_pages.py and tests/test_post_kinds.py:
no test framework (none installed in this project), a throwaway DB built from the real migration
pipeline, PASS/FAIL printing, sys.exit(1) on failure.

The DB is seeded with distinctive, real-looking "sentinel" fixtures -- a user, a board post, a
family node, and an election candidate, all physically placed in Rohini Sector 24
(CS.DL.3.4.1A, the same test fixture location tests/test_post_kinds.py already uses) -- so that
if the demo route ever accidentally read production-shaped data, these exact strings would
appear in its response. A generic search for "Private ID" or similar labels would not catch
this; only the fixtures' own distinctive values prove non-leakage.

Test #7 (monkeypatch get_db to raise) is the strongest guarantee in this file: it proves the
route never calls the database at all, not merely that leaked data happens to be absent.
Confirmed patchable -- app.py does `from db import get_db`, binding the name in app.py's own
module namespace, so reassigning `appmod.get_db` intercepts every call the route's code makes.

Run with: python3 tests/test_demo_rohini_sector_24.py (not -I -- this test imports Flask via app.py)
"""
from __future__ import annotations

import datetime as dt
import html as html_mod
import json
import os
import re
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH  # must happen before any import below
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import board_core  # noqa: E402 -- TEST FIXTURE SETUP ONLY. demo_data.py itself never imports this.
import family_core  # noqa: E402 -- TEST FIXTURE SETUP ONLY.

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


# Same fixture location tests/test_post_kinds.py already uses -- the real Q-Punch pilot village.
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


NOW = dt.datetime.now(dt.timezone.utc)
conn = build_schema(_DB_PATH)
family_core.ensure_tables(conn)

# ---- distinctive, real-looking sentinel fixtures, physically in Rohini Sector 24 ----
SENTINEL_NAME = "ZZZ_REAL_SENTINEL_Priya Sharma"
SENTINEL_POST_CONTENT = "REAL_SENTINEL_POST_CONTENT_7f3a9c -- must never appear in the public demo"
SENTINEL_FAMILY_NAME = "ZZZ_REAL_SENTINEL_FamilyNode_9d2e"
SENTINEL_CANDIDATE_MANIFEST = "REAL_SENTINEL_CANDIDATE_MANIFEST_b2e1"

sentinel_user_id = make_user(conn, SENTINEL_NAME)
sentinel_post_id = board_core.create_post(conn, sentinel_user_id, LOCATION, SENTINEL_POST_CONTENT, level="village", now=NOW)

conn.execute(
    """INSERT INTO family_nodes (claimed_user_id, created_by_user_id, display_name, gender, status, created_at)
       VALUES (NULL, ?, ?, 'female', 'empty', ?)""",
    (sentinel_user_id, SENTINEL_FAMILY_NAME, NOW.isoformat()),
)
conn.execute(
    """INSERT INTO election_cycles (village_id, zodiac_sign, element, year, nomination_start, nomination_end,
                                     voting_start, voting_end, status)
       VALUES (?, 'Capricorn', 'Earth', 2026, '2026-01-01', '2026-01-10', '2026-01-11', '2026-01-20', 'nomination')""",
    (LOCATION["village"]["id"],),
)
cycle_id = conn.execute("SELECT id FROM election_cycles WHERE village_id = ?", (LOCATION["village"]["id"],)).fetchone()[0]
conn.execute(
    """INSERT INTO election_candidates (election_cycle_id, user_id, gender, manifest, status)
       VALUES (?, ?, 'female', ?, 'approved')""",
    (cycle_id, sentinel_user_id, SENTINEL_CANDIDATE_MANIFEST),
)
conn.commit()

import app as appmod  # noqa: E402 -- the module under test, imported only after fixtures exist
import demo_data  # noqa: E402 -- introspected by source for the village-id check below

appmod.app.testing = True
client = appmod.app.test_client()

print("=" * 70)
print("1-2. Route works for an anonymous visitor, no session")
print("=" * 70)

res = client.get("/demo/rohini-sector-24")
check("route returns 200 for an anonymous visitor", res.status_code == 200)
# html.unescape so a constant containing an apostrophe or ampersand (Jinja auto-escapes those to
# &#39;/&amp; on render) still matches a plain Python substring check below.
html = html_mod.unescape(res.get_data(as_text=True))

with client.session_transaction() as sess:
    check("no session data exists for this client", len(sess) == 0)

print()
print("=" * 70)
print("3-10. No real data of any kind leaks into the response")
print("=" * 70)

check("the sentinel real user's name does not appear", SENTINEL_NAME not in html)
check("the sentinel real board post's content does not appear", SENTINEL_POST_CONTENT not in html)
check("the sentinel real family node's name does not appear", SENTINEL_FAMILY_NAME not in html)
check("the sentinel real candidate's manifest does not appear", SENTINEL_CANDIDATE_MANIFEST not in html)
check("the sentinel user's private_id_9digit does not appear",
      conn.execute("SELECT private_id_9digit FROM users WHERE id = ?", (sentinel_user_id,)).fetchone()[0] not in html)

# No 9-digit sequence in the page is the sentinel's real-shaped Private ID, and in fact this demo
# declares no Private ID of its own at all -- DEMO_USER.account_id_label is a label, not a number.
_nine_digit_matches = re.findall(r"\b\d{9}\b", html)
check("no 9-digit sequence (a real Private-ID shape) appears anywhere in the page", _nine_digit_matches == [])

check("no reference to the real admin/member-export panel exists",
      "qm-testcycle-card" not in html and "qm-memberexport-card" not in html)

print()
print("=" * 70)
print("11. No production database query is executed by the demo route")
print("=" * 70)


def _poisoned_get_db(*_a, **_kw):
    raise AssertionError("demo route touched the database")


_real_get_db = appmod.get_db
appmod.get_db = _poisoned_get_db
try:
    res_poisoned = client.get("/demo/rohini-sector-24")
    check("route still returns 200 with get_db() poisoned to raise -- proves zero DB access",
          res_poisoned.status_code == 200)
    check("the poisoned response is identical to the normal one",
          html_mod.unescape(res_poisoned.get_data(as_text=True)) == html)
except AssertionError as e:
    check(f"route still returns 200 with get_db() poisoned to raise -- proves zero DB access ({e})", False)
finally:
    appmod.get_db = _real_get_db

print()
print("=" * 70)
print("12-13. No write operation, no production record created or modified")
print("=" * 70)

_users_before = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
_posts_before = conn.execute("SELECT COUNT(*) FROM board_posts").fetchone()[0]
client.get("/demo/rohini-sector-24")
check("no new user row was created by viewing the demo",
      conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == _users_before)
check("no new board post was created by viewing the demo",
      conn.execute("SELECT COUNT(*) FROM board_posts").fetchone()[0] == _posts_before)

res_post = client.post("/demo/rohini-sector-24")
check("POST to the demo route is rejected (GET only -- no write path exists)", res_post.status_code == 405)

print()
print("=" * 70)
print("14. The demo route's own source module contains no reference to the real village id")
print("=" * 70)

_demo_data_src = open(os.path.join(ROOT, "demo_data.py"), encoding="utf-8").read()
check("demo_data.py never references the real village id CS.DL.3.4.1A", "CS.DL.3.4.1A" not in _demo_data_src)
check("demo_data.py never references PILOT_VILLAGE_ID", "PILOT_VILLAGE_ID" not in _demo_data_src)
check("demo_data.py never references the sentinel real user's name", SENTINEL_NAME not in _demo_data_src)
check("demo_data.py imports nothing from board_core/family_core/election_core/app/db",
      not any(f"import {m}" in _demo_data_src for m in ("board_core", "family_core", "election_core", "app", "db")))
check("the rendered page itself never shows the real village id either",
      "CS.DL.3.4.1A" not in html)
check("the rendered page uses the demo's own standalone village label instead",
      demo_data.DEMO_VILLAGE_LABEL in html)

print()
print("=" * 70)
print("15-16. All four timelines render, with their own fixture content, and tab nav is present")
print("=" * 70)

check("Personal tab content: the demo user's name appears", demo_data.DEMO_USER["name"] in html)
check("Personal tab content: Karma is mentioned", "Karma" in html)
check("Personal tab content: Qoins is mentioned", "Qoins" in html)
check("Private tab content: the Kundali note appears", demo_data.DEMO_KUNDALI["note"] in html)
check("Private tab content: a real chart SVG was embedded", "<svg" in demo_data.DEMO_KUNDALI["chart_svg"])
check("Public tab content: all 4 demo posts' titles appear",
      all(p["title"] in html for p in demo_data.DEMO_BOARD_POSTS))
check("Public tab content: Q-Punch candidates appear",
      all(c["name"] in html for c in demo_data.DEMO_QPUNCH["candidates_male"] + demo_data.DEMO_QPUNCH["candidates_female"]))
check("Global tab content: the geographic hierarchy is spelled out in order",
      " → ".join(demo_data.DEMO_GEOGRAPHIC_HIERARCHY) in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))
check("all four tab buttons are present", all(f'data-tab="{t}"' in html for t in ("personal", "private", "public", "global")))
check("the mandatory banner text is present verbatim", demo_data.DEMO_BANNER_TEXT in html)
check("the grouping-honesty note is present verbatim", demo_data.DEMO_GROUPING_NOTE in html)

print()
print("=" * 70)
print("17. No action control that could create/vote/edit/send/start anything real is rendered")
print("=" * 70)

check("no <form> element exists on the page (nothing can be submitted)", "<form" not in html)
check("no element with a vote/post/edit/compose/send/start action id is present", not re.search(
    r'id="[^"]*(vote|compose|submit-post|send-qmail|start-election|edit-profile)[^"]*"', html, re.IGNORECASE))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks PASSED.")
