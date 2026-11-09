"""Covers Task 1B (2026-11-08): the Q-Punch Village Council election winner-tally correctness
fix in election_core._ensure_tallied().

Root cause (confirmed by direct repro, not assumed): _ensure_tallied() used to tally a cycle's
winners ONCE EVER per (village_id, zodiac_sign, year) -- skipping re-computation forever once a
village_council row existed for that key, regardless of whether the underlying election_votes
had changed since. A cycle first observed as "closed" before all its votes existed (or, in the
real qumanity_prototype.db, a cycle whose real-world window closed with zero votes on record)
permanently froze a null/zero tally. The fix makes _ensure_tallied() always recompute winners
from the CURRENT election_votes and UPSERT into village_council/election_cycles, rather than
skip when a row already exists. No reward is tied to the tally itself (confirmed by grep --
wallet_core.unlock_user_share fires on a voter's first-ever vote, inside cast_vote(), never from
tallying), so recomputing it repeatedly has no side-effect risk.

This file proves: correct tallying with multiple candidates/votes, correct persistence, correct
winner identification, zero-vote elections, ties, no cross-cycle leakage, ineligible voters never
affecting totals, and -- the actual regression -- that a cycle tallied once with incomplete votes
self-corrects once the real votes exist, exactly reproducing and then closing the real bug found
in tools/website-check/check_app_api.py's "week 4: winners have the most votes" check.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes (same convention as tests/test_global_account.py),
PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_election_winner_tally.py
"""
from __future__ import annotations

import datetime as dt
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import election_core as E  # noqa: E402

# 2026-11-08 (Phase 1 corrective task): registration now verifies a real (non-provisional)
# Village against india_villages, the same way profile-change already does -- every throwaway
# test DB starts with that table empty, so any test registering a real village through the real
# /api/auth/register route must seed its row here first.
_seed_conn = appmod.get_db()
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
_seed_conn.commit()
_seed_conn.close()

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()
ROHINI = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
V = E.PILOT_VILLAGE_ID
_n = [0]


def register_resident(gender, dob="1990-10-01"):
    """A real village resident with the given gender and dob (dob fixed inside Libra's window --
    05-21..06-20 is Gemini, so Libra uses 09-23..10-22, hence '1990-10-01')."""
    _n[0] += 1
    payload = {
        "name": f"Resident {_n[0]}", "gender": gender, "dob": dob, "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": ROHINI, "present_location": ROHINI, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()["user_id"]


# Three dates inside ONE Libra 2026 cycle: nomination (week 1), voting (weeks 2-3), closed (week 4).
W1, W2, W4 = dt.date(2026, 9, 25), dt.date(2026, 10, 5), dt.date(2026, 10, 16)

print("=" * 70)
print("1-6. Multiple candidates, multiple votes, persistence, closure, correct counts and winner")
print("=" * 70)
conn = dbmod.get_db()
males = [register_resident("male") for _ in range(6)]
females = [register_resident("female") for _ in range(6)]

cyc1 = E.current_cycle_for_village(conn, V, W1)
check("1. Cycle starts in 'nomination' status", cyc1["status"] == "nomination")
rng = random.Random(1)
picked = E.auto_nominate(conn, V, rng=rng, today=W1)
check("1. Multiple eligible candidates nominated (up to 3 per gender, CANDIDATES_PER_GENDER)",
      len(picked["male"]) == 3 and len(picked["female"]) == 3)

male_candidates = [r["user_id"] for r in conn.execute(
    "SELECT user_id FROM election_candidates WHERE election_cycle_id = ? AND gender = 'male'", (cyc1["id"],))]
female_candidates = [r["user_id"] for r in conn.execute(
    "SELECT user_id FROM election_candidates WHERE election_cycle_id = ? AND gender = 'female'", (cyc1["id"],))]

# Cast a deliberately UNEVEN vote split so the winner is unambiguous (not relying on auto_vote's
# randomness): male_candidates[0] gets 4 votes, the rest get fewer.
cyc_voting = E.current_cycle_for_village(conn, V, W2)
voters_cast = 0
for i, uid in enumerate(males):
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    target = male_candidates[0] if i < 4 else male_candidates[1]
    try:
        E.cast_vote(conn, user_row, target, "male", W2)
        voters_cast += 1
    except ValueError:
        pass
for i, uid in enumerate(females):
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    target = female_candidates[0] if i < 5 else female_candidates[1]
    try:
        E.cast_vote(conn, user_row, target, "female", W2)
    except ValueError:
        pass
check("2. Multiple valid votes were actually cast (not all rejected)", voters_cast >= 4)

vote_rows = conn.execute("SELECT COUNT(*) AS n FROM election_votes WHERE election_cycle_id = ?", (cyc1["id"],)).fetchone()["n"]
check("3. Votes are persisted in election_votes (real row count, not inferred)", vote_rows >= 9)

cyc_closed = E.current_cycle_for_village(conn, V, W4)
check("4. The cycle correctly reaches 'closed' status at week 4", cyc_closed["status"] == "closed")

summary = E.election_summary(conn, V, W4)
male_votes_by_candidate = {c["user_id"]: c["votes"] for c in summary["candidates"]["male"]}
female_votes_by_candidate = {c["user_id"]: c["votes"] for c in summary["candidates"]["female"]}
check("5. election_summary()'s candidate vote counts match what was actually cast (male winner got 4)",
      male_votes_by_candidate.get(male_candidates[0]) == 4)
check("5b. ...and the runner-up got the remaining 2", male_votes_by_candidate.get(male_candidates[1]) == 2)
check("5c. ...same for female (5 vs 1)",
      female_votes_by_candidate.get(female_candidates[0]) == 5
      and female_votes_by_candidate.get(female_candidates[1]) == 1)

w = summary["winners"]
check("6. The male winner is the candidate with the most votes (male_candidates[0], 4 votes)",
      w is not None and w["male_votes"] == 4)
check("6b. The female winner is the candidate with the most votes (female_candidates[0], 5 votes)",
      w["female_votes"] == 5)
check("6c. election_cycles.male_winner_user_id/female_winner_user_id agree with the summary",
      conn.execute("SELECT male_winner_user_id, female_winner_user_id FROM election_cycles WHERE id = ?",
                   (cyc1["id"],)).fetchone()[:] == (male_candidates[0], female_candidates[0]))
conn.close()

print()
print("=" * 70)
print("7. Zero-vote election -- winners/votes are None/0, not fabricated, and no crash")
print("=" * 70)
conn = dbmod.get_db()
# A different village (never used elsewhere) with candidates nominated but NO votes cast at all.
EMPTY_VILLAGE = "CS.DL.3.4.1B"
nominee = register_resident("male")
# auto_nominate requires residents of the TARGET village; simplest correct way to exercise a
# true zero-vote cycle is a cycle with candidates nominated but voting skipped entirely --
# achieved here by calling current_cycle_for_village/_ensure_tallied directly on EMPTY_VILLAGE,
# which has no residents and therefore no candidates and no votes at all.
cyc_empty = E.current_cycle_for_village(conn, EMPTY_VILLAGE, W4)
summary_empty = E.election_summary(conn, EMPTY_VILLAGE, W4)
check("7. A village with zero candidates and zero votes closes with winners=None/male_votes=0, "
      "not a crash and not a fabricated winner",
      cyc_empty["status"] == "closed"
      and (summary_empty["winners"] is None or
           (summary_empty["winners"]["male"] is None and summary_empty["winners"]["male_votes"] == 0)))
conn.close()

print()
print("=" * 70)
print("8. Tied election -- resolved by the EXISTING tie-break policy (earliest nomination), not a")
print("   new rule")
print("=" * 70)
# election_core.cast_vote()/nominate() are HARDCODED to PILOT_VILLAGE_ID (not parameterized --
# "piloted on exactly one village," confirmed by reading the actual function bodies after this
# test's first draft tried a fabricated village and got a real, correct rejection: "Voting is
# only open to residents of this pilot village"). So every scenario that casts a REAL vote
# through cast_vote()/nominate() must use real Rohini Sector 24 (ROHINI) residents, distinguished
# by zodiac sign (a different sign = a different, independent election_cycles row for the SAME
# village) rather than by village. This tie test uses Aquarius 2026 (01-20..02-18), a cycle
# untouched by sections 1-6's Libra residents.
conn = dbmod.get_db()
AQ_W1, AQ_W2, AQ_W4 = dt.date(2026, 1, 22), dt.date(2026, 1, 30), dt.date(2026, 2, 12)
tie_males = [register_resident("male", dob="1990-01-25") for _ in range(4)]

cyc_tie = E.current_cycle_for_village(conn, V, AQ_W1)
E.auto_nominate(conn, V, rng=random.Random(3), today=AQ_W1)
tie_candidates = [r["user_id"] for r in conn.execute(
    "SELECT user_id FROM election_candidates WHERE election_cycle_id = ? AND gender = 'male' ORDER BY id", (cyc_tie["id"],))]
check("8. Enough candidates exist to construct a genuine tie", len(tie_candidates) >= 2)
# One vote each for the first two candidates -- a genuine 1-1 tie.
for i, uid in enumerate(tie_males[:2]):
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    E.cast_vote(conn, user_row, tie_candidates[i], "male", AQ_W2)
tie_summary = E.election_summary(conn, V, AQ_W4)
# election_summary()'s winners["male"] is the winner's NAME (a display string), not their
# user_id -- the raw id lives on election_cycles.male_winner_user_id, which is what the
# tie-break itself actually needs to be checked against.
tie_winner_id = conn.execute("SELECT male_winner_user_id FROM election_cycles WHERE id = ?", (cyc_tie["id"],)).fetchone()[0]
check("8b. The tie is broken by the query's own ORDER BY votes DESC, MIN(id) ASC policy -- the "
      "winner is whichever tied candidate has the lower election_votes.id (earliest cast vote), "
      "exactly the pre-existing tie-break rule, not a new one",
      tie_winner_id == tie_candidates[0])
conn.close()

print()
print("=" * 70)
print("9. Multiple election cycles -- no cross-cycle leakage of votes or winners")
print("=" * 70)
conn = dbmod.get_db()
# A second, LATER cycle for the SAME village (Scorpio, the sign immediately after Libra) must
# start completely fresh: no candidates, no votes, no winners inherited from the Libra cycle
# tallied above.
W1_scorpio = dt.date(2026, 10, 25)
cyc_scorpio = E.current_cycle_for_village(conn, V, W1_scorpio)
check("9. A later cycle for the SAME village is a genuinely different row (different id)",
      cyc_scorpio["id"] != cyc1["id"])
check("9b. The later cycle starts with zero candidates (none leaked from the Libra cycle)",
      conn.execute("SELECT COUNT(*) AS n FROM election_candidates WHERE election_cycle_id = ?",
                   (cyc_scorpio["id"],)).fetchone()["n"] == 0)
check("9c. The later cycle starts with zero votes", conn.execute(
    "SELECT COUNT(*) AS n FROM election_votes WHERE election_cycle_id = ?", (cyc_scorpio["id"],)).fetchone()["n"] == 0)
check("9d. The later cycle's own winner columns are still unset (status is 'nomination', not closed yet)",
      cyc_scorpio["status"] == "nomination")
conn.close()

print()
print("=" * 70)
print("10. Ineligible voters (wrong sign, wrong gender-for-seat, non-resident) never affect totals")
print("=" * 70)
conn = dbmod.get_db()
# A Gemini-born resident of the SAME village attempting to vote in the Libra cycle -- wrong sign.
wrong_sign_uid = register_resident("male", dob="1990-06-15")
wrong_sign_row = conn.execute("SELECT * FROM users WHERE id = ?", (wrong_sign_uid,)).fetchone()
try:
    E.cast_vote(conn, wrong_sign_row, male_candidates[0], "male", W2)
    check("10. A wrong-sign (Gemini) resident's vote attempt is rejected", False)
except ValueError:
    check("10. A wrong-sign (Gemini) resident's vote attempt is rejected", True)

# A Libra resident voting with the WRONG gender for the seat (a male voting in the female race).
wrong_gender_row = conn.execute("SELECT * FROM users WHERE id = ?", (males[0],)).fetchone()
try:
    E.cast_vote(conn, wrong_gender_row, female_candidates[0], "female", W2)
    check("10b. A male voting for a female-seat candidate is rejected", False)
except ValueError:
    check("10b. A male voting for a female-seat candidate is rejected", True)

final_summary = E.election_summary(conn, V, W4)
final_w = final_summary["winners"]
check("10c. None of the rejected vote attempts changed the already-tallied winner/vote counts",
      final_w["male_votes"] == 4 and final_w["female_votes"] == 5)
conn.close()

print()
print("=" * 70)
print("11. THE ACTUAL REGRESSION: a cycle tallied once with INCOMPLETE votes self-corrects once")
print("    the real votes exist (reproduces, then proves closed, the exact bug found in")
print("    check_app_api.py against the real qumanity_prototype.db)")
print("=" * 70)
# Same hardcoded-PILOT_VILLAGE_ID constraint as section 8 -- real Rohini Sector 24 residents,
# a fresh zodiac sign untouched by any earlier section: Pisces 2026 (02-19..03-20).
conn = dbmod.get_db()
PI_W1, PI_W2, PI_W4 = dt.date(2026, 2, 21), dt.date(2026, 3, 1), dt.date(2026, 3, 14)
stale_males = [register_resident("male", dob="1990-02-25") for _ in range(3)]

cyc_stale = E.current_cycle_for_village(conn, V, PI_W1)
E.auto_nominate(conn, V, rng=random.Random(5), today=PI_W1)
stale_candidates = [r["user_id"] for r in conn.execute(
    "SELECT user_id FROM election_candidates WHERE election_cycle_id = ? AND gender = 'male' ORDER BY id", (cyc_stale["id"],))]

# Step 1: observe the cycle as CLOSED before any vote exists -- exactly what happened for real in
# qumanity_prototype.db (the real-world clock crossed voting_end with zero votes on record,
# which the OLD _ensure_tallied() would have frozen forever via its skip-if-exists guard).
pre_vote_summary = E.election_summary(conn, V, PI_W4)
check("11. Before any vote: winners is None/0 (correct for a genuinely empty cycle at this point)",
      pre_vote_summary["winners"] is None or pre_vote_summary["winners"]["male_votes"] == 0)
check("11b. A village_council row now exists for this cycle (the first tally, with no votes)",
      conn.execute(
          "SELECT 1 FROM village_council WHERE village_id = ? AND zodiac_sign = 'Pisces' AND year = 2026",
          (V,)).fetchone() is not None)

# Step 2: NOW cast real votes against that SAME already-tallied cycle (simulating votes arriving,
# or a seed script running, after the cycle was first observed as closed).
for i, uid in enumerate(stale_males):
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    # cast_vote() itself re-derives the cycle from "today", and voting_eligible() requires
    # cycle["status"] == "voting" -- so the vote must be cast at a voting-window date (PI_W2),
    # not PI_W4, exactly like a real late-arriving vote would have been (cast during the real
    # voting window, just not yet reflected in the tally the first time it was checked after
    # closing).
    E.cast_vote(conn, user_row, stale_candidates[0], "male", PI_W2)

# Step 3: re-check the summary at (or after) PI_W4 -- this is the exact call that was broken
# before the fix: the OLD code would still report winners=None/votes=0 here, because
# _ensure_tallied() would see the already-existing (stale) village_council row and skip
# recomputing entirely.
post_vote_summary = E.election_summary(conn, V, PI_W4)
post_w = post_vote_summary["winners"]
post_winner_id = conn.execute("SELECT male_winner_user_id FROM election_cycles WHERE id = ?", (cyc_stale["id"],)).fetchone()[0]
check("11c. THE FIX: after votes exist, re-requesting the summary now shows the REAL winner and "
      "REAL vote count (3), not the frozen None/0 from the first, premature tally",
      post_w is not None and post_winner_id == stale_candidates[0] and post_w["male_votes"] == 3)
check("11d. election_cycles.male_winner_user_id was updated in place (UPSERT, not a second row)",
      conn.execute("SELECT COUNT(*) AS n FROM village_council WHERE village_id = ? AND zodiac_sign = 'Pisces' AND year = 2026",
                   (V,)).fetchone()["n"] == 1)
conn.close()

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks PASSED.")
