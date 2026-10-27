"""Verifies election_test_scheduler.daily_tick() end to end: nomination week picks candidates,
voting week casts votes from both demo pools (the 50-account board-test naming convention and the
500-account election-pilot naming convention -- functionally identical to election_core, which
scopes only on village + sun sign, never is_demo or name, but kept visibly distinct here so the
test demonstrates both), a second tick never double-votes, and a closed cycle is left untouched by
further ticks.

Standalone script, same convention as tests/test_post_kinds.py: no test framework (none installed
in this project), a throwaway DB built from the real migration pipeline, PASS/FAIL printing, exit
1 on failure.

Run with: python3 -I tests/test_election_test_scheduler.py
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

import election_core
import election_test_scheduler

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


PILOT_VILLAGE = election_core.PILOT_VILLAGE_ID  # CS.DL.3.4.1A, Rohini Sector 24
PILOT_LOCATION = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": PILOT_VILLAGE, "name": "Rohini Sector 24"},
}
OTHER_VILLAGE_LOCATION = {**PILOT_LOCATION, "village": {"id": "CS.DL.3.4.1B", "name": "Some Other Village"}}

_counter = [0]


def make_user(conn, name, gender, age, sun_sign, is_demo=1, location=None) -> int:
    """age is simply TODAY's age (dob backdated from the real wall clock) -- correct for
    nomination_eligible()/voting_eligible()'s own age math, which is also wall-clock-based,
    independent of whatever simulate_date a test later ticks against."""
    _counter[0] += 1
    today = dt.date.today()
    # Jan 1 (not today's own month/day): guarantees _age_years() -- which subtracts 1 if
    # (today.month, today.day) < (dob.month, dob.day) -- always lands on exactly `age`,
    # regardless of what day this test itself happens to run on.
    dob = dt.date(today.year - age, 1, 1).isoformat()
    loc = location or PILOT_LOCATION
    cur = conn.execute(
        """INSERT INTO users (name, gender, dob, tob, birth_location_json, present_location_json,
                               private_id_9digit, is_demo, is_removed)
           VALUES (?, ?, ?, '08:00', ?, ?, ?, ?, 0)""",
        (name, gender, dob, json.dumps(loc), json.dumps(loc), f"P{_counter[0]:08d}", is_demo),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.execute(
        "INSERT INTO user_zodiac (user_id, sun_sign, sun_element) VALUES (?, ?, 'Fire')",
        (user_id, sun_sign),
    )
    conn.commit()
    return user_id


conn = build_schema(_DB_PATH)

# ---- The pilot village's Aries population for this test -------------------------------------
# Aries: 03-21 -> 04-19. Nomination days 1-8 (Mar21-28), voting days 9-22 (Mar29-Apr11),
# closed the rest of the window (Apr12-19).
NOMINATION_DAY = "2027-03-21"
VOTING_DAY = "2027-03-29"
VOTING_DAY_2 = "2027-04-05"
CLOSED_DAY = "2027-04-15"
CLOSED_DAY_2 = "2027-04-18"

candidate_ids = {"male": [], "female": []}
for i in range(3):
    candidate_ids["male"].append(make_user(conn, f"Aries Candidate M{i}", "male", 30, "Aries"))
    candidate_ids["female"].append(make_user(conn, f"Aries Candidate F{i}", "female", 30, "Aries"))

# Pool 1: the 50-account board-test naming convention (scripts/seed_demo_voters.py). Ages kept
# OUTSIDE the 25-60 candidacy window (nomination_eligible()) so these voters can never be picked
# as candidates themselves, leaving the "picked candidates == candidate_ids" check unambiguous.
board_test_voter_ids = []
for i in range(3):
    board_test_voter_ids.append(make_user(conn, f"Demo Voter {i}", "male", 18, "Aries"))
    board_test_voter_ids.append(make_user(conn, f"Demo Voter {i + 10}", "female", 18, "Aries"))

# Pool 2: the 500-account election-pilot naming convention (scripts/seed_election_demo.py). Same
# reasoning -- ages outside 25-60.
pilot_voter_ids = []
for i in range(3):
    pilot_voter_ids.append(make_user(conn, f"Priya Sharma {i}", "female", 22, "Aries"))
    pilot_voter_ids.append(make_user(conn, f"Rahul Verma {i}", "male", 65, "Aries"))

all_voter_ids = set(candidate_ids["male"] + candidate_ids["female"] + board_test_voter_ids + pilot_voter_ids)

# Control rows that must NEVER vote in this cycle.
wrong_sign_id = make_user(conn, "Taurus Resident", "male", 30, "Taurus")
wrong_village_id = make_user(conn, "Aries Elsewhere", "male", 30, "Aries", location=OTHER_VILLAGE_LOCATION)

print(f"=== Set up: {len(candidate_ids['male']) + len(candidate_ids['female'])} candidate-eligible, "
      f"{len(board_test_voter_ids)} board-test voters, {len(pilot_voter_ids)} election-pilot voters, "
      f"2 control (non-matching) residents ===")

# ---- 1. Nomination week: candidates picked --------------------------------------------------
print("\n=== Nomination week (2027-03-21) ===")
result_nom = election_test_scheduler.daily_tick(conn, simulate_date=NOMINATION_DAY)
check(f"status is 'nomination' (got {result_nom['status']!r})", result_nom["status"] == "nomination")
check("'picked' is populated", result_nom["picked"] is not None)
check("'cast' is None on a nomination tick", result_nom["cast"] is None)
cand_rows = conn.execute(
    "SELECT user_id, gender FROM election_candidates ec JOIN election_cycles c ON c.id = ec.election_cycle_id "
    "WHERE c.village_id = ? AND c.zodiac_sign = 'Aries' AND c.year = 2027", (PILOT_VILLAGE,),
).fetchall()
check(f"3 male + 3 female candidates were written (got {len(cand_rows)})", len(cand_rows) == 6)
picked_male = {r["user_id"] for r in cand_rows if r["gender"] == "male"}
picked_female = {r["user_id"] for r in cand_rows if r["gender"] == "female"}
check("the picked candidates are exactly the eligible Aries pool (male)", picked_male == set(candidate_ids["male"]))
check("the picked candidates are exactly the eligible Aries pool (female)", picked_female == set(candidate_ids["female"]))

# A second nomination-week tick must not create duplicates (auto_nominate's own top-up rule).
election_test_scheduler.daily_tick(conn, simulate_date="2027-03-22")
cand_rows_2 = conn.execute(
    "SELECT COUNT(*) AS n FROM election_candidates ec JOIN election_cycles c ON c.id = ec.election_cycle_id "
    "WHERE c.village_id = ? AND c.zodiac_sign = 'Aries' AND c.year = 2027", (PILOT_VILLAGE,),
).fetchone()
check(f"a second nomination tick does not add more candidates (still {cand_rows_2['n']})", cand_rows_2["n"] == 6)

# ---- 2. Voting week: votes cast from both demo pools ----------------------------------------
print("\n=== Voting week (2027-03-29) ===")
result_vote = election_test_scheduler.daily_tick(conn, simulate_date=VOTING_DAY)
check(f"status is 'voting' (got {result_vote['status']!r})", result_vote["status"] == "voting")
check("'picked' is None on a voting tick", result_vote["picked"] is None)
check("'cast' is populated", result_vote["cast"] is not None)
total_cast_tick1 = result_vote["cast"]["male"] + result_vote["cast"]["female"]
check(f"every eligible resident voted on the first tick (cast {total_cast_tick1}, expected {len(all_voter_ids)})",
      total_cast_tick1 == len(all_voter_ids))
check(f"nobody was skipped on the first tick (skipped {result_vote['cast']['skipped']})", result_vote["cast"]["skipped"] == 0)

votes_after_tick1 = conn.execute(
    "SELECT voter_user_id FROM election_votes v JOIN election_cycles c ON c.id = v.election_cycle_id "
    "WHERE c.village_id = ? AND c.zodiac_sign = 'Aries' AND c.year = 2027", (PILOT_VILLAGE,),
).fetchall()
voted_ids = {r["voter_user_id"] for r in votes_after_tick1}
check("every eligible Aries resident of the pilot village has a vote", voted_ids == all_voter_ids)
check("the board-test pool (Demo Voter N) voted", set(board_test_voter_ids) <= voted_ids)
check("the election-pilot pool (Priya/Rahul N) voted", set(pilot_voter_ids) <= voted_ids)
check("the Taurus resident (wrong sign) did NOT vote", wrong_sign_id not in voted_ids)
check("the Aries resident of another village did NOT vote", wrong_village_id not in voted_ids)

# ---- 3. Idempotency: a second voting tick must not double-vote ------------------------------
print("\n=== Idempotency: second voting tick (2027-04-05, still within the voting window) ===")
result_vote_2 = election_test_scheduler.daily_tick(conn, simulate_date=VOTING_DAY_2)
check(f"status is still 'voting' (got {result_vote_2['status']!r})", result_vote_2["status"] == "voting")
check(f"no NEW votes are cast the second time (cast {result_vote_2['cast']['male'] + result_vote_2['cast']['female']})",
      result_vote_2["cast"]["male"] + result_vote_2["cast"]["female"] == 0)
check(f"everyone already-voted is now reported skipped (skipped {result_vote_2['cast']['skipped']}, expected {len(all_voter_ids)})",
      result_vote_2["cast"]["skipped"] == len(all_voter_ids))
dupes = conn.execute(
    """SELECT voter_user_id, gender, COUNT(*) AS n FROM election_votes v
       JOIN election_cycles c ON c.id = v.election_cycle_id
       WHERE c.village_id = ? AND c.zodiac_sign = 'Aries' AND c.year = 2027
       GROUP BY voter_user_id, gender HAVING COUNT(*) > 1""", (PILOT_VILLAGE,),
).fetchall()
check(f"no voter has more than one vote for their own gender (found {len(dupes)} duplicate(s))", len(dupes) == 0)
votes_after_tick2 = conn.execute(
    "SELECT COUNT(*) AS n FROM election_votes v JOIN election_cycles c ON c.id = v.election_cycle_id "
    "WHERE c.village_id = ? AND c.zodiac_sign = 'Aries' AND c.year = 2027", (PILOT_VILLAGE,),
).fetchone()
check(f"total vote count is unchanged by the second tick (still {votes_after_tick2['n']})",
      votes_after_tick2["n"] == len(all_voter_ids))

# ---- 4. Closed cycle: tallied once, then left untouched -------------------------------------
print("\n=== Closed cycle (2027-04-15) ===")
result_closed = election_test_scheduler.daily_tick(conn, simulate_date=CLOSED_DAY)
check(f"status is 'closed' (got {result_closed['status']!r})", result_closed["status"] == "closed")
check("'picked' is None on a closed tick", result_closed["picked"] is None)
check("'cast' is None on a closed tick", result_closed["cast"] is None)
council_row_1 = conn.execute(
    "SELECT * FROM village_council WHERE village_id = ? AND zodiac_sign = 'Aries' AND year = 2027", (PILOT_VILLAGE,),
).fetchone()
check("village_council was tallied for this cycle", council_row_1 is not None)
if council_row_1:
    check("a male head was elected", council_row_1["male_head_user_id"] in candidate_ids["male"])
    check("a female head was elected", council_row_1["female_head_user_id"] in candidate_ids["female"])

election_test_scheduler.daily_tick(conn, simulate_date=CLOSED_DAY_2)
council_rows_2 = conn.execute(
    "SELECT * FROM village_council WHERE village_id = ? AND zodiac_sign = 'Aries' AND year = 2027", (PILOT_VILLAGE,),
).fetchall()
check(f"a second closed-week tick writes no extra village_council row (still {len(council_rows_2)})", len(council_rows_2) == 1)
if council_rows_2:
    check("the council winners are unchanged by the second closed tick",
          dict(council_rows_2[0]) == dict(council_row_1))
votes_after_closed = conn.execute(
    "SELECT COUNT(*) AS n FROM election_votes v JOIN election_cycles c ON c.id = v.election_cycle_id "
    "WHERE c.village_id = ? AND c.zodiac_sign = 'Aries' AND c.year = 2027", (PILOT_VILLAGE,),
).fetchone()
check(f"vote count is unchanged by the closed ticks (still {votes_after_closed['n']})",
      votes_after_closed["n"] == len(all_voter_ids))

print(f"\n{'=' * 60}")
if FAILS:
    print(f"FAILED {len(FAILS)} check(s):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("ALL ELECTION-TEST-SCHEDULER CHECKS PASSED")
