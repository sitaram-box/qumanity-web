"""Verifies the Group Members feature (2026-10-25): a proper member list (avatar/name/role) and
an admin-initiated "Add Member by Public ID" invite, for both personal groups (Friends/Business/
Custom -- social_core.py) and Family Groups (family_core.py).

Covers:
  - social_core.find_person() now carries profile_picture_url.
  - social_core.group_messages()'s members list carries is_admin (the group's owner, and only
    the owner -- personal groups have no multi-admin concept).
  - family_core.invite_to_group() / group_members_for(): admin-only, rejects a non-admin, an
    already-a-member target, a duplicate pending invite, and inviting yourself; the target
    receives a people_requests row (kind='family_group_invite') they must accept before
    anything changes, exactly like social_core.send_group_invite()'s existing personal-group
    flow -- never an immediate join.
  - social_core.decide_request()'s new 'family_group_invite' branch adds the DECIDER (not the
    sender) as a plain member, with no founder-admin grant.
  - social_core.inbox()'s join condition picks up 'family_group_invite' rows too, and carries
    family_group_name for them (the same fix also covers the pre-existing 'family_group_join'
    inbox-text bug, where the frontend read a field name the backend never actually returned).

Standalone script, no test framework (none installed in this project), PASS/FAIL printing, exit 1
on failure -- same pattern as every other tests/test_*.py file in this project.

Run with: python3 tests/test_group_members.py (not -I -- isolated mode hides this machine's
Flask install).
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

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402

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


def register(name_prefix, gender="male"):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": gender, "dob": "1990-06-15", "tob": "06:00",
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


def search_code_for(user_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT search_code FROM account_ids WHERE user_id = ? AND is_current = 1", (user_id,)).fetchone()
    conn.close()
    return row["search_code"]


print("=" * 70)
print("1. Personal groups (Friends/Business/Custom): find_person() + members role field")
print("=" * 70)

owner = register("Group Owner", gender="female")
member = register("Group Member", gender="male")
outsider = register("Group Outsider")

login(owner["private_code"])
res = client.post("/api/people/groups/create", json={"category": "custom", "name": "Members Test Group"})
group_id = res.get_json()["id"]

res = client.get("/api/people/search", query_string={"q": search_code_for(member["user_id"])})
check("find_person() succeeds", res.status_code == 200)
found = res.get_json()
check("find_person() now carries a profile_picture_url key (null, no picture uploaded)",
      "profile_picture_url" in found and found["profile_picture_url"] is None)

res = client.post("/api/people/invite", json={"group_id": group_id, "user_id": member["user_id"]})
check("owner invites member", res.status_code == 201)
logout()
login(member["private_code"])
res = client.get("/api/people/inbox")
invite_req = next(r for r in res.get_json()["requests"] if r["kind"] == "group")
res = client.post(f"/api/people/inbox/{invite_req['id']}/decide", json={"decision": "accept"})
check("member accepts the group invite", res.status_code == 200)

res = client.get(f"/api/people/groups/{group_id}/messages")
owner_row = next(m for m in res.get_json()["members"] if m["user_id"] == owner["user_id"])
member_row = next(m for m in res.get_json()["members"] if m["user_id"] == member["user_id"])
check("the owner's member row has is_admin=True", owner_row["is_admin"] is True)
check("a plain member's row has is_admin=False", member_row["is_admin"] is False)
check("member rows carry profile_picture_url for the avatar sweep", "profile_picture_url" in member_row)

print()
print("=" * 70)
print("2. Family Groups: invite_to_group() / group_members_for()")
print("=" * 70)

logout()
fam_admin = register("Family Group Admin")
login(fam_admin["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Invite Test Father", "action": "create"}, "mother": {"name": "Invite Test Mother", "action": "create"},
})
parents_group_id = res.get_json()["parents_group_id"]

logout()
fam_target = register("Family Invite Target")
fam_stranger = register("Family Non Admin")

login(fam_admin["private_code"])
res = client.get(f"/api/family-groups/{parents_group_id}/members")
check("admin can view the member list", res.status_code == 200)
check("the member list has exactly 1 entry (the admin, the only member so far)", len(res.get_json()["members"]) == 1)
check("the single member is flagged is_admin=True", res.get_json()["members"][0]["is_admin"] is True)
check("the single member is flagged you=True (it's the caller)", res.get_json()["members"][0]["you"] is True)

# invite_to_group() takes an already-resolved user_id (the admin confirms a name/avatar via
# /api/people/search first), not a raw Public ID string -- matching social_core.send_group_invite()'s
# own signature, not link_node_to_user()'s. Self-invite guard: inviting your own user_id should
# be rejected before anything else.
res = client.post(f"/api/family-groups/{parents_group_id}/invite", json={"user_id": fam_admin["user_id"]})
check("an admin cannot invite themselves (400)", res.status_code == 400)

res = client.post(f"/api/family-groups/{parents_group_id}/invite", json={"user_id": 999999999})
check("a user_id that doesn't exist is rejected (404)", res.status_code == 404)

res = client.post(f"/api/family-groups/{parents_group_id}/invite", json={"user_id": fam_target["user_id"]})
check("admin invites a real target by their resolved user_id (201)", res.status_code == 201)

res = client.post(f"/api/family-groups/{parents_group_id}/invite", json={"user_id": fam_target["user_id"]})
check("a duplicate pending invite to the same target is rejected (400)", res.status_code == 400)

logout()
login(fam_stranger["private_code"])
res = client.post(f"/api/family-groups/{parents_group_id}/invite", json={"user_id": fam_target["user_id"]})
check("a non-admin cannot invite anyone into someone else's unit (403)", res.status_code == 403)
res = client.get(f"/api/family-groups/{parents_group_id}/members")
check("a non-member also cannot view the member list (404, not 403 -- same scoped-404 convention as the rest of family_core.py)", res.status_code == 404)

logout()
login(fam_target["private_code"])
res = client.get("/api/people/inbox")
reqs = res.get_json()["requests"]
invite_req2 = next(r for r in reqs if r["kind"] == "family_group_invite")
check("the invite shows the correct family_group_name, not a stray undefined/null", bool(invite_req2.get("family_group_name")))
res = client.post(f"/api/people/inbox/{invite_req2['id']}/decide", json={"decision": "accept"})
check("target accepts the family group invite (200)", res.status_code == 200)

res = client.get(f"/api/family-groups/{parents_group_id}/members")
check("the accepted target now appears in the member list", any(m["user_id"] == fam_target["user_id"] for m in res.get_json()["members"]))
target_row = next(m for m in res.get_json()["members"] if m["user_id"] == fam_target["user_id"])
check("the invited target joined as a PLAIN member, no founder-admin grant from a generic invite", target_row["is_admin"] is False)

logout()
login(fam_admin["private_code"])
res = client.post(f"/api/family-groups/{parents_group_id}/invite", json={"user_id": fam_target["user_id"]})
check("inviting someone who is already a member is rejected (400)", res.status_code == 400)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
