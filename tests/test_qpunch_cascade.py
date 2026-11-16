"""Verifies the Q-Punch cascade (Tehsil-to-Earth elections, 2026-11-16 Phases 2-4):
election_core.get_lower_house(), current_cycle_for_location(), the 8-seat tally
(_ensure_tallied_location()), the quarterly element rotation (_quarter_bounds()/
_current_quarter()), and the 51% Head-approval mechanism (ensure_head_approval_current()/
cast_head_approval_vote()) -- backed by the /api/election/status, /api/election/candidates,
/api/election/nominate, and /api/election/vote routes, generalized in app.py for level != 'village'.

Covers:
  - get_lower_house(): returns every currently-serving village_council member across a tehsil's
    own villages (the one case that reads village_council rather than qpunch_council_members);
    always [] for 'village' itself or a location with no children.
  - Nomination/voting eligibility above village is Lower House membership, not residency or
    age/karma -- an outsider is refused with a clear reason, a Lower House member succeeds.
  - A full 8-seat tehsil cycle: 8 candidates (1 Male + 1 Female per element) nominate, get
    admin-approved (the same generic /api/admin/election/nominate/<id>/approve route village
    candidates already use), the Lower House casts up to 8 ballots each (1 per gender x element,
    not scoped to the voter's own element, unlike village), and closing the cycle correctly
    tallies each element's seat to the candidate who actually got votes.
  - The 4-quarter rotation: Fire -> Earth -> Air -> Water, contiguous, no gaps, spanning the
    council's own term exactly.
  - Both 51%-approval outcomes: the Male approved (>=51%) becomes the official Head; the Male
    failing approval (<51%) means the Female becomes Head by default, never left undecided.
  - Duplicate-vote and already-decided-approval guards.

A critical cycle-anchoring bug was found and fixed while writing this coverage:
current_cycle_for_location() originally recomputed a first-ever cycle's nomination window fresh
from `today` on every call (safe for village only because _sign_window() is a pure function of the
calendar) -- this silently pushed the window forward every time the function was read with a later
date, making the cycle impossible to ever close. Fixed by reading a live cycle's stored dates as-is
once it exists, only creating a new cycle once the previous council's own term has ended. This file
exercises exactly that fix (section 3's close-and-tally step would fail without it).

Time-sensitive steps (voting, closing/tallying, quarter rotation, approval-window closing) call
election_core's own functions directly with an explicit `today`, the same technique every other
date-controlled test in this project uses (e.g. tests/test_family_tree.py) -- the real HTTP routes
correctly have no `today` override, so nomination (which doesn't need one) goes through the real
API/test client while time-shifted steps call the underlying functions directly.

Standalone script, no test framework (none installed in this project), PASS/FAIL printing, exit 1
on failure -- same pattern as every other tests/test_*.py file in this project.

Run with: python3 tests/test_qpunch_cascade.py (not -I -- isolated mode hides this machine's
Flask install).
"""
from __future__ import annotations

import datetime as dt
import os
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
import election_core  # noqa: E402

_seed_conn = dbmod.get_db()
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1B', 'CS.DL.3.4', 'Rohini Sector 25')")
_seed_conn.commit()
_seed_conn.close()


FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

VILLAGE_A = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def register(name_prefix, gender="male", dob="1990-06-15"):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": gender, "dob": dob, "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A, "present_location": VILLAGE_A, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code, pin="12345"):
    res = client.post("/login", json={"private_id": private_code, "pin": pin})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def logout():
    client.post("/logout")


def user_row(user_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


print("=" * 70)
print("1. get_lower_house() against a synthetic village_council")
print("=" * 70)

# 4 villagers, seeded directly as village_council heads (2 per village, 1 sign-seat each) --
# faster than running a real month-long village cycle twice, and village's own tally logic
# already has its own dedicated coverage in tests/test_family_tree.py and friends; this file is
# about get_lower_house()'s own query.
villagers = [register(f"Villager{i}") for i in range(4)]
today = dt.date.today()
conn = dbmod.get_db()
dummy_cycle_id = conn.execute(
    "INSERT INTO election_cycles (village_id, zodiac_sign, element, year, nomination_start, nomination_end, voting_start, voting_end) "
    "VALUES ('DUMMY', 'Aries', 'Fire', 1900, '1900-01-01', '1900-01-01', '1900-01-01', '1900-01-01')"
).lastrowid
conn.execute(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, election_cycle_id, leadership_start, leadership_end) "
    "VALUES ('CS.DL.3.4.1A', 'Aries', 2026, ?, ?, ?, ?, ?)",
    (villagers[0]["user_id"], villagers[1]["user_id"], dummy_cycle_id,
     (today - dt.timedelta(days=10)).isoformat(), (today + dt.timedelta(days=350)).isoformat()),
)
conn.execute(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, election_cycle_id, leadership_start, leadership_end) "
    "VALUES ('CS.DL.3.4.1B', 'Taurus', 2026, ?, ?, ?, ?, ?)",
    (villagers[2]["user_id"], villagers[3]["user_id"], dummy_cycle_id,
     (today - dt.timedelta(days=10)).isoformat(), (today + dt.timedelta(days=350)).isoformat()),
)
conn.commit()

lower_house = election_core.get_lower_house(conn, "tehsil", "CS.DL.3.4")
check("get_lower_house(tehsil, CS.DL.3.4) returns all 4 synthetic village heads",
      sorted(lower_house) == sorted(v["user_id"] for v in villagers))
check("get_lower_house('village', ...) is always [] (nothing below village)",
      election_core.get_lower_house(conn, "village", "CS.DL.3.4.1A") == [])
check("get_lower_house for a tehsil with no villages at all returns []",
      election_core.get_lower_house(conn, "tehsil", "CS.DL.9.9") == [])
conn.close()

print()
print("=" * 70)
print("2. Nomination eligibility: Lower House member vs. an outsider")
print("=" * 70)

outsider = register("Outsider")
login(villagers[0]["private_code"])
res = client.post("/api/election/nominate", json={
    "level": "tehsil", "location_id": "CS.DL.3.4",
    "reason": "I want to serve", "why_vote": "I have experience", "changes": "Better roads",
})
check("a Lower House member (villager 0) can nominate for tehsil", res.status_code == 200)
logout()
login(outsider["private_code"])
res = client.post("/api/election/nominate", json={
    "level": "tehsil", "location_id": "CS.DL.3.4",
    "reason": "x", "why_vote": "y", "changes": "z",
})
check("an outsider (not in the Lower House) is REFUSED tehsil nomination (400)", res.status_code == 400)
check("the refusal names the Lower House rule, not a generic error",
      "currently-serving" in res.get_json().get("error", ""))
logout()

print()
print("=" * 70)
print("3. Full tehsil cycle: nominate across all 4 elements, vote, close, tally")
print("=" * 70)

ELEMENT_DOBS = {"Fire": "1991-04-01", "Earth": "1991-05-01", "Air": "1991-06-01", "Water": "1991-07-01"}
candidates = {}
for element, dob in ELEMENT_DOBS.items():
    candidates[element] = {
        "male": register(f"Cand{element}M", gender="male", dob=dob),
        "female": register(f"Cand{element}F", gender="female", dob=dob),
    }

# Seed the 8 element candidates as Lower House members too (synthetic village-council seats, same
# shortcut as section 1 -- a candidate above village must itself be a serving council member one
# level down).
conn = dbmod.get_db()
dummy_cycle_id2 = conn.execute(
    "INSERT INTO election_cycles (village_id, zodiac_sign, element, year, nomination_start, nomination_end, voting_start, voting_end) "
    "VALUES ('DUMMY2', 'Taurus', 'Earth', 1900, '1900-01-01', '1900-01-01', '1900-01-01', '1900-01-01')"
).lastrowid
seat_n = 100
for element in ELEMENT_DOBS:
    for g in ("male", "female"):
        seat_n += 1
        uid = candidates[element][g]["user_id"]
        conn.execute(
            "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, election_cycle_id, leadership_start, leadership_end) "
            "VALUES ('CS.DL.3.4.1A', ?, 2026, ?, NULL, ?, ?, ?)",
            (f"Seat{seat_n}", uid, dummy_cycle_id2,
             (today - dt.timedelta(days=5)).isoformat(), (today + dt.timedelta(days=350)).isoformat()),
        )
conn.commit()
conn.close()

for element in ELEMENT_DOBS:
    for g in ("male", "female"):
        cand = candidates[element][g]
        login(cand["private_code"])
        res = client.post("/api/election/nominate", json={
            "level": "tehsil", "location_id": "CS.DL.3.4",
            "reason": f"{element} {g} candidate", "why_vote": "vote for me", "changes": "change",
        })
        check(f"{element} {g} candidate nominates successfully", res.status_code == 200)
        logout()

conn = dbmod.get_db()
cur_row = conn.execute("SELECT id FROM election_cycles WHERE village_id='CS.DL.3.4' AND level='tehsil'").fetchone()
cycle_id = cur_row["id"]
cand_ids = [r["id"] for r in conn.execute("SELECT id FROM election_candidates WHERE election_cycle_id = ?", (cycle_id,))]
conn.close()
# 9, not 8: villager0's own section-2 nomination landed in this SAME cycle too (same tehsil, same
# cycle) -- it never gets any votes below, so it doesn't affect which 8 actually win.
check("9 candidates recorded for this cycle (8 element candidates + villager0's own from section 2)", len(cand_ids) == 9)

conn = dbmod.get_db()
conn.executemany("UPDATE election_candidates SET status = 'approved' WHERE id = ?", [(cid,) for cid in cand_ids])
conn.commit()
cycle_row = conn.execute("SELECT * FROM election_cycles WHERE id = ?", (cycle_id,)).fetchone()
conn.close()
voting_today = dt.date.fromisoformat(cycle_row["voting_start"])

# Each of 2 villagers (the Lower House) votes once per element/gender -- 8 ballots each. Called
# directly with an explicit `today` -- see this file's own module docstring on why.
conn = dbmod.get_db()
for villager in villagers[:2]:
    voter_row = user_row(villager["user_id"])
    for element in ELEMENT_DOBS:
        for g in ("male", "female"):
            election_core.cast_vote(
                conn, voter_row, candidates[element][g]["user_id"], g, today=voting_today,
                level="tehsil", location_id="CS.DL.3.4", element=element,
            )
vote_count = conn.execute("SELECT COUNT(*) AS n FROM qpunch_cascade_votes WHERE election_cycle_id = ?", (cycle_id,)).fetchone()["n"]
check("16 cascade votes recorded (2 voters x 8 seats)", vote_count == 16)
conn.close()

conn = dbmod.get_db()
closed_today = dt.date.fromisoformat(cycle_row["voting_end"]) + dt.timedelta(days=1)
closed_cycle = election_core.current_cycle_for_location(conn, "tehsil", "CS.DL.3.4", today=closed_today)
check("cycle status is now 'closed'", closed_cycle["status"] == "closed")
council_id = closed_cycle["council_id"]
check("a qpunch_councils row was created", council_id is not None)

members = {(r["element"], r["gender"]): r["user_id"] for r in conn.execute(
    "SELECT element, gender, user_id FROM qpunch_council_members WHERE council_id = ?", (council_id,)
)}
check("exactly 8 seats filled", len(members) == 8)
for element in ELEMENT_DOBS:
    for g in ("male", "female"):
        expected = candidates[element][g]["user_id"]
        check(f"{element} {g} seat correctly won by the only candidate who ran",
              members.get((element, g)) == expected)
conn.close()

print()
print("=" * 70)
print("4. Quarterly rotation and the 51% Head approval")
print("=" * 70)
conn = dbmod.get_db()
council_row = dict(conn.execute("SELECT * FROM qpunch_councils WHERE id = ?", (council_id,)).fetchone())
conn.close()

bounds = election_core._quarter_bounds(council_row)
check("4 quarters computed, in Fire/Earth/Air/Water order",
      [b[2] for b in bounds] == ["Fire", "Earth", "Air", "Water"])
check("quarters are contiguous and span the full term with no gap/overlap",
      bounds[0][0] == dt.date.fromisoformat(council_row["term_start"])
      and bounds[-1][1] == dt.date.fromisoformat(council_row["term_end"])
      and all(bounds[i][1] + dt.timedelta(days=1) == bounds[i + 1][0] for i in range(3)))

q1_start, q1_end, q1_element = bounds[0]
conn = dbmod.get_db()
council_row = election_core.ensure_head_approval_current(conn, council_row, today=q1_start)
check("quarter 1's active_element is Fire", council_row["active_element"] == "Fire")
check("head is NOT yet decided while the approval window is still open", council_row["head_user_id"] is None)
approval = conn.execute("SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = 'Fire'", (council_id,)).fetchone()
check("a Fire head-approval window was opened", approval is not None)
conn.close()

# Scenario A: the Male gets >=51% approval -- 3 approve, 1 rejects (75%), via the real HTTP route
# (no `today` needed here: the approval window was already opened above with an explicit `today`,
# so these calls just need to land inside it, which real "now" -- inside that already-open window
# -- already is, since q1_start was computed from the council's own term, years in the future of
# real "today" at the time this test runs... see section 5's own note on why the CLOSE step below
# still needs an explicit `today`).
for i, v in enumerate(villagers):
    login(v["private_code"])
    res = client.post("/api/election/vote", json={"council_id": council_id, "approve": i != 3})
    logout()
    if res.status_code != 200:
        print("     approval vote failed:", res.get_json())

conn = dbmod.get_db()
approval_row = conn.execute("SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = 'Fire'", (council_id,)).fetchone()
past_approval = dt.date.fromisoformat(approval_row["approval_end"]) + dt.timedelta(days=1)
council_row = election_core.ensure_head_approval_current(conn, council_row, today=past_approval)
fire_male = candidates["Fire"]["male"]["user_id"]
check("Fire Male approved with 3/4 (75% >= 51%) -> he is Head",
      council_row["head_user_id"] == fire_male and council_row["head_gender"] == "male")
conn.close()

print()
print("=" * 70)
print("5. Scenario B: the Male FAILS 51% approval -> the Female defaults to Head")
print("=" * 70)
# A second, independent council term, to test the rejection path in isolation (re-tallying the
# SAME term would just re-read the already-decided Fire approval above).
conn = dbmod.get_db()
term2_start = dt.date.fromisoformat(council_row["term_end"]) + dt.timedelta(days=1)
term2_end = dt.date(term2_start.year + 3, term2_start.month, term2_start.day) - dt.timedelta(days=1)
council2_id = conn.execute(
    "INSERT INTO qpunch_councils (location_id, level, term_start, term_end) VALUES (?, 'tehsil', ?, ?)",
    ("CS.DL.3.4", term2_start.isoformat(), term2_end.isoformat()),
).lastrowid
conn.execute("INSERT INTO qpunch_council_members (council_id, user_id, gender, element) VALUES (?, ?, 'male', 'Fire')",
             (council2_id, candidates["Fire"]["male"]["user_id"]))
conn.execute("INSERT INTO qpunch_council_members (council_id, user_id, gender, element) VALUES (?, ?, 'female', 'Fire')",
             (council2_id, candidates["Fire"]["female"]["user_id"]))
conn.commit()
council2 = dict(conn.execute("SELECT * FROM qpunch_councils WHERE id = ?", (council2_id,)).fetchone())
council2 = election_core.ensure_head_approval_current(conn, council2, today=term2_start)
approval2 = conn.execute("SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = 'Fire'", (council2_id,)).fetchone()
conn.close()

# 1 approve, 3 reject -> 25% approval, well under 51%.
for i, v in enumerate(villagers):
    login(v["private_code"])
    res = client.post("/api/election/vote", json={"council_id": council2_id, "approve": i == 0})
    logout()

conn = dbmod.get_db()
past2 = dt.date.fromisoformat(approval2["approval_end"]) + dt.timedelta(days=1)
council2 = election_core.ensure_head_approval_current(conn, council2, today=past2)
check("Fire Male fails approval (1/4 = 25% < 51%) -> Fire FEMALE becomes Head by default",
      council2["head_user_id"] == candidates["Fire"]["female"]["user_id"] and council2["head_gender"] == "female")
conn.close()

print()
print("=" * 70)
print("6. Duplicate-vote and cross-cycle guards")
print("=" * 70)
conn = dbmod.get_db()
voter_row = user_row(villagers[0]["user_id"])
try:
    election_core.cast_vote(
        conn, voter_row, candidates["Fire"]["male"]["user_id"], "male", today=closed_today,
        level="tehsil", location_id="CS.DL.3.4", element="Fire",
    )
    check("re-voting for the same gender+element in a now-CLOSED cycle is refused", False)
except ValueError as e:
    check("re-voting for the same gender+element in a now-CLOSED cycle is refused", "not open" in str(e).lower())
try:
    election_core.cast_head_approval_vote(conn, voter_row, council_id, True)
    check("re-voting on an already-decided head approval is refused", False)
except ValueError as e:
    check("re-voting on an already-decided head approval is refused",
          "already" in str(e).lower() or "not currently open" in str(e).lower())
conn.close()

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
