"""Verifies Upper House Sovereignty / the People's Vote (2026-11-16):
election_core.initiate_people_vote()/cast_people_vote()/tally_people_vote(), backed by the
/api/people-vote/initiate, /api/people-vote/cast, and /api/people-vote/status routes.

Covers:
  - A member of a location's own population (the Upper House, per _present_location_matches() --
    the same residency check cast_head_approval_vote() already uses) can initiate a People's Vote
    there; a second open vote for the same location is refused while one is already open.
  - Ballots: one per Upper House member per vote; a duplicate is refused.
  - Vote counts stay hidden (votes_for/votes_against both null) in GET /api/people-vote/status
    while a vote is still open -- the same "no running tallies mid-vote" convention
    election_summary()'s own show_votes flag already enforces for village elections.
  - Resolution uses the SAME 51%-of-ballots-cast threshold cast_head_approval_vote() uses (not a
    turnout/quorum rule), since the approved brief is explicit that Head Approval is one specific
    instance of this exact general power: 2 for / 1 against (67%) passes; 1 for / 3 against (25%)
    fails. A passed vote's own `status` is recorded as 'passed' (binding on the council -- actual
    enforcement against the council's own decisions is a separate, later task, not built here).
  - A resident of a DIFFERENT location is refused both initiating and voting there.
  - GET /api/people-vote/status always reports `is_upper_house`, even when no vote exists yet for
    that location (so a caller can decide whether to offer "Start a People's Vote" without
    guessing).

Time-sensitive steps (closing/tallying) call election_core.tally_people_vote() directly with an
explicit `today`, the same technique tests/test_qpunch_cascade.py and every other date-controlled
test in this project already use -- the real HTTP route correctly has no `today` override.

Standalone script, no test framework (none installed in this project), PASS/FAIL printing, exit 1
on failure -- same pattern as every other tests/test_*.py file in this project.

Run with: python3 tests/test_people_vote.py (not -I -- isolated mode hides this machine's Flask
install).
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
VILLAGE_B = {**VILLAGE_A, "village": {"id": "CS.DL.3.4.1B", "name": "Rohini Sector 25"}}

_n = [0]


def register(name_prefix, location=VILLAGE_A):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        # Birth location now stops at State (2026-11-19) -- present_location (unchanged) still
        # carries the full chain down to Village.
        "birth_location": {k: location[k] for k in ("continent", "country", "zone", "state")},
        "present_location": location, "assisted": False,
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


print("=" * 70)
print("1. Initiating: an Upper House member succeeds; a non-resident of this location is refused")
print("=" * 70)

a = register("Resident A")
b = register("Resident B")
c = register("Resident C")
outsider = register("Outsider", location=VILLAGE_B)

login(outsider["private_code"])
res = client.post("/api/people-vote/initiate", json={"level": "village", "location_id": "CS.DL.3.4.1A", "title": "X"})
check("a resident of a DIFFERENT village is refused initiating here (400)", res.status_code == 400)
check("the refusal names the population rule, not a generic error", "own population" in res.get_json().get("error", ""))
logout()

login(a["private_code"])
res = client.get("/api/people-vote/status", query_string={"level": "village", "location_id": "CS.DL.3.4.1A"})
check("status reports no vote yet", res.get_json()["vote"] is None)
check("status reports is_upper_house=True for a real resident, even with no vote yet", res.get_json()["is_upper_house"] is True)

res = client.post("/api/people-vote/initiate", json={
    "level": "village", "location_id": "CS.DL.3.4.1A",
    "title": "Repave the main road", "description": "The road has potholes",
})
check("a real resident (Upper House member) can initiate a People's Vote (201)", res.status_code == 201)
vote = res.get_json()
vote_id = vote["id"]
check("the new vote starts 'open' with hidden counts", vote["status"] == "open" and vote["votes_for"] is None and vote["votes_against"] is None)

res2 = client.post("/api/people-vote/initiate", json={"level": "village", "location_id": "CS.DL.3.4.1A", "title": "Second vote"})
check("a second open vote for the SAME location is refused while one is already open (400)", res2.status_code == 400)
logout()

print()
print("=" * 70)
print("2. Casting: one ballot per Upper House member, duplicates refused, counts stay hidden")
print("=" * 70)

login(a["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote_id, "in_favour": True})
check("A votes Yes", res.status_code == 200)
res_dup = client.post("/api/people-vote/cast", json={"vote_id": vote_id, "in_favour": True})
check("A double-voting on the same vote is refused (400)", res_dup.status_code == 400)
logout()

login(b["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote_id, "in_favour": True})
check("B votes Yes", res.status_code == 200)
logout()

login(c["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote_id, "in_favour": False})
check("C votes No", res.status_code == 200)
res_status = client.get("/api/people-vote/status", query_string={"level": "village", "location_id": "CS.DL.3.4.1A"})
check("counts stay hidden (null) while the vote is still open, even with 3 ballots cast",
      res_status.get_json()["vote"]["votes_for"] is None and res_status.get_json()["vote"]["votes_against"] is None)
check("the caller's own already_voted is reported correctly", res_status.get_json()["vote"]["already_voted"] is True)
logout()

login(outsider["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote_id, "in_favour": True})
check("a non-resident of this village is refused voting on it (400)", res.status_code == 400)
logout()

print()
print("=" * 70)
print("3. Resolution: 51% of ballots CAST, not a turnout/quorum rule -- matching Head Approval")
print("=" * 70)

conn = dbmod.get_db()
resolved = election_core.tally_people_vote(conn, vote_id, today=dt.date.today() + dt.timedelta(days=20))
conn.close()
check("2 for / 1 against (67% >= 51%) -> PASSED", resolved["status"] == "passed" and resolved["votes_for"] == 2 and resolved["votes_against"] == 1)

login(a["private_code"])
res_status2 = client.get("/api/people-vote/status", query_string={"level": "village", "location_id": "CS.DL.3.4.1A"})
check("status now reveals the real counts and the resolved outcome", res_status2.get_json()["vote"]["status"] == "passed"
      and res_status2.get_json()["vote"]["votes_for"] == 2 and res_status2.get_json()["vote"]["votes_against"] == 1)
logout()

print()
print("=" * 70)
print("4. A second vote, this time failing: 1 for / 3 against (25% < 51%)")
print("=" * 70)

login(a["private_code"])
res = client.post("/api/people-vote/initiate", json={"level": "village", "location_id": "CS.DL.3.4.1A", "title": "Second question"})
check("a new vote can be initiated now that the first one resolved", res.status_code == 201)
vote2_id = res.get_json()["id"]
res = client.post("/api/people-vote/cast", json={"vote_id": vote2_id, "in_favour": True})
check("A votes Yes on the second vote", res.status_code == 200)
logout()
login(b["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote2_id, "in_favour": False})
logout()
login(c["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote2_id, "in_favour": False})
logout()
d = register("Resident D")
login(d["private_code"])
res = client.post("/api/people-vote/cast", json={"vote_id": vote2_id, "in_favour": False})
logout()

conn = dbmod.get_db()
resolved2 = election_core.tally_people_vote(conn, vote2_id, today=dt.date.today() + dt.timedelta(days=40))
conn.close()
check("1 for / 3 against (25% < 51%) -> FAILED", resolved2["status"] == "failed" and resolved2["votes_for"] == 1 and resolved2["votes_against"] == 3)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
