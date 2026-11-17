"""Verifies the Local Areas backend (2026-11-18): sub-divisions within a village, a pure
membership/identity layer with no Collective Board of its own (Decision 2 of the approved
architecture). Covers create_local_area() (Founder-or-Nayak/Nayika-gated, duplicate/blank-name
rejection), list_local_areas()/members_of(), the first FREE join and its village-residency gate,
the one-active-Local-Area-at-a-time lock, request_move()'s idempotency, decide_move_request()'s own
admin gate, leave_local_area(), and -- the rule this file exists specifically to pin down -- that
the hard lock survives a leave: a direct re-join is refused even after leaving, and only an
approved move request can get a member back in.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure. Follows
the same pattern as tests/test_family_tree.py and tests/test_group_members.py.

Run with: python3 tests/test_local_areas.py (not -I -- isolated mode hides this machine's Flask
install).
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"
os.environ["QM_ADMIN_PRIVATE_IDS"] = ""  # set to the Founder's own Private ID once registered below

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402

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


def register(name_prefix, village=VILLAGE_A):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": village, "present_location": village, "assisted": False,
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
print("1. create_local_area(): refused without Founder/Nayak-Nayika standing")
print("=" * 70)

plain = register("Plain Resident")
login(plain["private_code"])
res = client.post("/api/local-areas/create", json={"village_id": "CS.DL.3.4.1A", "name": "Sector 24 East"})
check("a plain resident with no council/founder standing is refused (403)", res.status_code == 403)

print()
print("=" * 70)
print("2. create_local_area(): the Founder can, with duplicate/blank-name validation")
print("=" * 70)

founder = register("The Founder")
os.environ["QM_ADMIN_PRIVATE_IDS"] = founder["private_code"]
login(founder["private_code"])
res = client.post("/api/local-areas/create", json={"village_id": "CS.DL.3.4.1A", "name": "Sector 24 East"})
check("the Founder can create a Local Area (201)", res.status_code == 201)
area_east_id = res.get_json()["id"]

res = client.post("/api/local-areas/create", json={"village_id": "CS.DL.3.4.1A", "name": "Sector 24 West"})
check("a second, differently-named Local Area in the same village also succeeds", res.status_code == 201)
area_west_id = res.get_json()["id"]

res = client.post("/api/local-areas/create", json={"village_id": "CS.DL.3.4.1A", "name": "Sector 24 East"})
check("a duplicate name in the same village is rejected (400)", res.status_code == 400)

res = client.post("/api/local-areas/create", json={"village_id": "CS.DL.3.4.1A", "name": ""})
check("a blank name is rejected (400)", res.status_code == 400)

print()
print("=" * 70)
print("3. list_local_areas() / members_of()")
print("=" * 70)

res = client.get("/api/local-areas/list", query_string={"village_id": "CS.DL.3.4.1A"})
check("list succeeds (200)", res.status_code == 200)
names = {a["name"] for a in res.get_json()["local_areas"]}
check("both created Local Areas are listed", {"Sector 24 East", "Sector 24 West"} <= names)
check("member_count starts at 0 for a freshly created Local Area",
      next(a for a in res.get_json()["local_areas"] if a["id"] == area_east_id)["member_count"] == 0)

res = client.get(f"/api/local-areas/{area_east_id}/members")
check("members list for an empty Local Area succeeds with an empty list",
      res.status_code == 200 and res.get_json()["members"] == [])

res = client.get("/api/local-areas/999999/members")
check("members list for a nonexistent Local Area is 404", res.status_code == 404)

print()
print("=" * 70)
print("4. join_local_area(): the first FREE join, and the village-residency gate")
print("=" * 70)

logout()
resident = register("Village Resident", village=VILLAGE_A)
login(resident["private_code"])
res = client.post("/api/local-areas/join", json={"local_area_id": area_east_id})
check("the first join succeeds (201)", res.status_code == 201)

res = client.get(f"/api/local-areas/{area_east_id}/members")
check("resident now shows up in the member list", any(m["user_id"] == resident["user_id"] for m in res.get_json()["members"]))

logout()
outsider = register("Outsider Elsewhere", village=VILLAGE_B)
login(outsider["private_code"])
res = client.post("/api/local-areas/join", json={"local_area_id": area_east_id})
check("someone who lives in a DIFFERENT village is refused (400), not silently joined", res.status_code == 400)

print()
print("=" * 70)
print("5. The one-active-at-a-time lock, and request_move()'s own idempotency")
print("=" * 70)

login(resident["private_code"])
res = client.post("/api/local-areas/join", json={"local_area_id": area_west_id})
check("already being in a Local Area blocks a second DIRECT join (400)", res.status_code == 400)

res = client.post("/api/local-areas/request-move", json={"to_local_area_id": area_west_id})
check("request-move to a different Local Area succeeds (201)", res.status_code == 201)
move_req_id = res.get_json()["request_id"]

res = client.post("/api/local-areas/request-move", json={"to_local_area_id": area_west_id})
check("an immediate duplicate request-move is idempotent (200, already_pending), not a duplicate row",
      res.status_code == 200 and res.get_json()["status"] == "already_pending")
check("the SAME request_id is returned, not a new row", res.get_json()["request_id"] == move_req_id)

print()
print("=" * 70)
print("6. decide_move_request(): admin-gated, and actually moves the membership")
print("=" * 70)

login(plain["private_code"])
res = client.post(f"/api/local-areas/requests/{move_req_id}/decide", json={"decision": "approve"})
check("a non-admin cannot decide a move request (403)", res.status_code == 403)

login(founder["private_code"])
res = client.post(f"/api/local-areas/requests/{move_req_id}/decide", json={"decision": "approve"})
check("the Founder approves the move request (200)", res.status_code == 200)

res = client.get(f"/api/local-areas/{area_east_id}/members")
check("resident is no longer in East's member list", not any(m["user_id"] == resident["user_id"] for m in res.get_json()["members"]))
res = client.get(f"/api/local-areas/{area_west_id}/members")
check("resident is now in West's member list", any(m["user_id"] == resident["user_id"] for m in res.get_json()["members"]))

res = client.post(f"/api/local-areas/requests/{move_req_id}/decide", json={"decision": "approve"})
check("deciding an already-decided request is rejected (400)", res.status_code == 400)

print()
print("=" * 70)
print("7. THE HARD LOCK (this file's own reason to exist): leaving never clears it -- only an")
print("   approved move request can get a member back into a Local Area, even the same one")
print("=" * 70)

login(resident["private_code"])
res = client.post("/api/local-areas/leave", json={})
check("leave succeeds (200)", res.status_code == 200)
res = client.get(f"/api/local-areas/{area_west_id}/members")
check("resident no longer in West's member list after leaving", not any(m["user_id"] == resident["user_id"] for m in res.get_json()["members"]))

res = client.post("/api/local-areas/leave", json={})
check("leaving again with no active membership is rejected (400)", res.status_code == 400)

res = client.post("/api/local-areas/join", json={"local_area_id": area_east_id})
check("a DIRECT re-join after leaving is still refused (400) -- the lock survives a leave, "
      "status='left' is a history row, not a deleted one", res.status_code == 400)

res = client.post("/api/local-areas/request-move", json={"to_local_area_id": area_east_id})
check("request-move after leaving succeeds instead (201)", res.status_code == 201)
rejoin_req_id = res.get_json()["request_id"]

login(founder["private_code"])
res = client.post(f"/api/local-areas/requests/{rejoin_req_id}/decide", json={"decision": "approve"})
check("the Founder approves the re-join (200)", res.status_code == 200)
res = client.get(f"/api/local-areas/{area_east_id}/members")
check("resident is back in East's member list after the approved re-join -- the SAME row is "
      "reactivated (UNIQUE(user_id, local_area_id)), not a second membership row",
      any(m["user_id"] == resident["user_id"] for m in res.get_json()["members"]))

print()
print("=" * 70)
print("8. decide_move_request() with decision='deny'")
print("=" * 70)

logout()
denied_resident = register("Denied Resident", village=VILLAGE_A)
login(denied_resident["private_code"])
res = client.post("/api/local-areas/join", json={"local_area_id": area_west_id})
check("denied_resident's own first join succeeds", res.status_code == 201)
res = client.post("/api/local-areas/request-move", json={"to_local_area_id": area_east_id})
check("denied_resident requests a move to East", res.status_code == 201)
deny_req_id = res.get_json()["request_id"]

login(founder["private_code"])
res = client.post(f"/api/local-areas/requests/{deny_req_id}/decide", json={"decision": "deny"})
check("the Founder can deny a move request (200)", res.status_code == 200)

res = client.get(f"/api/local-areas/{area_west_id}/members")
check("denied_resident STAYS in West's member list -- a denial changes nothing",
      any(m["user_id"] == denied_resident["user_id"] for m in res.get_json()["members"]))
res = client.get(f"/api/local-areas/{area_east_id}/members")
check("denied_resident never appears in East's member list", not any(m["user_id"] == denied_resident["user_id"] for m in res.get_json()["members"]))

res = client.post(f"/api/local-areas/requests/{deny_req_id}/decide", json={"decision": "approve"})
check("deciding an already-denied request is rejected too (400)", res.status_code == 400)

print()
print("=" * 70)
print("9. list_local_areas(): my_local_area_id / my_pending_move_to / can_manage")
print("=" * 70)

login(resident["private_code"])
res = client.post("/api/local-areas/request-move", json={"to_local_area_id": area_west_id})
check("resident requests another move (to West again), left pending for this section", res.status_code == 201)
pending_check_req_id = res.get_json()["request_id"]

res = client.get("/api/local-areas/list", query_string={"village_id": "CS.DL.3.4.1A"})
check("my_local_area_id reports resident's own active Local Area (East)", res.get_json()["my_local_area_id"] == area_east_id)
check("my_pending_move_to reports the just-requested West move", res.get_json()["my_pending_move_to"] == area_west_id)
check("a plain resident's can_manage is False", res.get_json()["can_manage"] is False)

login(founder["private_code"])
res = client.get("/api/local-areas/list", query_string={"village_id": "CS.DL.3.4.1A"})
check("the Founder's can_manage is True", res.get_json()["can_manage"] is True)
check("the Founder has no active Local Area of their own -- my_local_area_id is None", res.get_json()["my_local_area_id"] is None)
check("the Founder has no pending move request either -- my_pending_move_to is None", res.get_json()["my_pending_move_to"] is None)

print()
print("=" * 70)
print("10. GET /api/local-areas/requests: pending list, can_manage-gated")
print("=" * 70)

login(plain["private_code"])
res = client.get("/api/local-areas/requests", query_string={"village_id": "CS.DL.3.4.1A"})
check("a non-admin cannot view the pending-requests list (403)", res.status_code == 403)

login(founder["private_code"])
res = client.get("/api/local-areas/requests", query_string={"village_id": "CS.DL.3.4.1A"})
check("the Founder can view the pending-requests list (200)", res.status_code == 200)
pending_ids = {r["id"] for r in res.get_json()["requests"]}
check("resident's own just-requested move shows up in the pending list", pending_check_req_id in pending_ids)
entry = next(r for r in res.get_json()["requests"] if r["id"] == pending_check_req_id)
check("the entry names the requester and both Local Areas by name, not just id",
      bool(entry["user_name"]) and entry["from_name"] == "Sector 24 East" and entry["to_name"] == "Sector 24 West")

res = client.post(f"/api/local-areas/requests/{pending_check_req_id}/decide", json={"decision": "deny"})
check("cleaning up: the Founder denies this request so it doesn't dangle", res.status_code == 200)
res = client.get("/api/local-areas/requests", query_string={"village_id": "CS.DL.3.4.1A"})
check("a decided request no longer appears in the pending list", pending_check_req_id not in {r["id"] for r in res.get_json()["requests"]})

print()
print("=" * 70)
print("11. Local Area chat: membership-gated read/send, admin override")
print("=" * 70)

login(resident["private_code"])  # still active in East
res = client.post(f"/api/local-areas/{area_east_id}/chat", json={"text": "Hello East!"})
check("an active member can send a chat message (201)", res.status_code == 201)
res = client.get(f"/api/local-areas/{area_east_id}/chat")
check("an active member can read the chat (200)", res.status_code == 200)
check("the message appears, flagged as mine", any(m["text"] == "Hello East!" and m["mine"] for m in res.get_json()["messages"]))

login(denied_resident["private_code"])  # active in West, not East
res = client.get(f"/api/local-areas/{area_east_id}/chat")
check("a member of a DIFFERENT Local Area cannot read this one's chat (403)", res.status_code == 403)
res = client.post(f"/api/local-areas/{area_east_id}/chat", json={"text": "Sneaking in"})
check("...nor send a message to it (403)", res.status_code == 403)

login(founder["private_code"])
res = client.get(f"/api/local-areas/{area_east_id}/chat")
check("the Founder can read ANY Local Area's chat without being a member (admin override)", res.status_code == 200)
res = client.post(f"/api/local-areas/{area_east_id}/chat", json={"text": "A note from the Founder"})
check("...and send to it too", res.status_code == 201)

login(resident["private_code"])
res = client.post(f"/api/local-areas/{area_east_id}/chat", json={"text": ""})
check("a blank message is rejected (400)", res.status_code == 400)
res = client.post(f"/api/local-areas/{area_east_id}/chat", json={"text": "x" * 1001})
check("a message over 1000 characters is rejected (400)", res.status_code == 400)

res = client.post("/api/local-areas/999999/chat", json={"text": "hi"})
check("sending to a nonexistent Local Area's chat is a 404", res.status_code == 404)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
