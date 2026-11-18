"""Verifies family_recovery_core.py and its /api/recovery/family/* and /api/qmail/family-recovery/*
routes (2026-11-13): Family Tree-based account recovery, additive to the two existing recovery
paths in recovery_core.py (OTP self-service, Admin-ticket), covered by tests/test_recovery_otp.py
and tests/test_id_recovery*.py respectively -- neither of those is touched here.

Covers: relationship verification in both modes (direct Private-ID lookup and graph-search-by-name),
the generic single-error-message behavior for every failure case, the full request lifecycle
(create -> family member reviews in their Qmail inbox -> share Private ID / approve PIN reset /
reject), one-pending-request-per-requester supersession, 72-hour request expiry and 24-hour
PIN-reset authorization expiry, single-use PIN-reset authorization (replay prevention), the
by-IP and by-target-Private-ID rate limits (3 attempts/24h, counting failures too), and the
security boundary that only the actual intended family member can act on a request.

Builds its own small Family Tree directly via SQL inserts into family_nodes/family_parent_links/
family_groups (the same tables family_core.py's own ensure_tables() creates) rather than driving
family_core's own high-level flows (activate_timeline/marry_timeline/etc.) -- family_recovery_core
only ever READS those tables, so a direct, minimal fixture tree is the simplest way to set up the
exact graph shapes each scenario needs.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure -- same conventions
as tests/test_family_tree.py and tests/test_qmail.py.

Run with: python3 tests/test_family_recovery.py (not -I -- isolated mode hides this machine's
Flask install).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import family_core  # noqa: E402
import family_recovery_core as frc  # noqa: E402

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
VILLAGE = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
_n = [0]


def register(name):
    _n[0] += 1
    payload = {
        "name": f"{name} {_n[0]}", "gender": "male", "dob": "1970-01-01", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        # Birth location now stops at State (2026-11-19) for a Sub-continent country.
        "birth_location": {k: VILLAGE[k] for k in ("continent", "country", "zone", "state")},
        "present_location": VILLAGE, "assisted": False,
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
    with client.session_transaction() as sess:
        sess.clear()


def reset_rate_limits():
    # app.py's _rate_limited() keys its by-IP bucket on the caller's address alone, so every call
    # this test client makes to /api/recovery/family/request -- across every section below, not
    # just the dedicated rate-limit section -- shares ONE bucket (the Flask test client always
    # presents the same remote_addr). Clearing between sections isolates each section's own
    # scenario; the dedicated rate-limit section below clears once and then deliberately lets its
    # own calls accumulate.
    appmod._RATE_LIMIT_HITS.clear()


def user_row(user_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def make_node(conn, user_id, now="2026-11-13T00:00:00+00:00"):
    cur = conn.execute(
        "INSERT INTO family_nodes (claimed_user_id, created_by_user_id, display_name, status, created_at, claimed_at) "
        "VALUES (?, ?, ?, 'claimed', ?, ?)",
        (user_id, user_id, user_row(user_id)["name"], now, now),
    )
    return cur.lastrowid


def link_parent(conn, parent_node_id, child_node_id, now="2026-11-13T00:00:00+00:00"):
    conn.execute(
        "INSERT INTO family_parent_links (parent_node_id, child_node_id, created_by_user_id, created_at) VALUES (?, ?, ?, ?)",
        (parent_node_id, child_node_id, 0, now),
    )


def link_spouse(conn, husband_node_id, wife_node_id, now="2026-11-13T00:00:00+00:00"):
    conn.execute(
        "INSERT INTO family_groups (name, created_by_user_id, husband_node_id, wife_node_id, created_at) "
        "VALUES ('Test Unit', 0, ?, ?, ?)",
        (husband_node_id, wife_node_id, now),
    )


# ---- Build one small, reusable Family Tree ----
# Dad --- Mom
#   |
#  Kid1 --- Spouse1      Kid2 (sibling of Kid1)
#
# Grandpa is Dad's own father (so Grandpa is Kid1's grandparent).
dad = register("Dad")
mom = register("Mom")
kid1 = register("Kid1")
kid2 = register("Kid2")
spouse1 = register("Spouse1")
grandpa = register("Grandpa")
stranger = register("Stranger")  # registered, but not placed anywhere in the tree below

conn = dbmod.get_db()
family_core.ensure_tables(conn)
n_dad = make_node(conn, dad["user_id"])
n_mom = make_node(conn, mom["user_id"])
n_kid1 = make_node(conn, kid1["user_id"])
n_kid2 = make_node(conn, kid2["user_id"])
n_spouse1 = make_node(conn, spouse1["user_id"])
n_grandpa = make_node(conn, grandpa["user_id"])
link_parent(conn, n_dad, n_kid1)
link_parent(conn, n_mom, n_kid1)
link_parent(conn, n_dad, n_kid2)
link_parent(conn, n_mom, n_kid2)
link_parent(conn, n_grandpa, n_dad)
link_spouse(conn, n_dad, n_mom)
link_spouse(conn, n_kid1, n_spouse1)
conn.commit()
conn.close()

DAD_PRIVATE = user_row(dad["user_id"])["private_id_9digit"]
DAD_NAME = user_row(dad["user_id"])["name"]
KID1_PRIVATE = user_row(kid1["user_id"])["private_id_9digit"]
KID1_NAME = user_row(kid1["user_id"])["name"]
KID2_NAME = user_row(kid2["user_id"])["name"]
SPOUSE1_NAME = user_row(spouse1["user_id"])["name"]
GRANDPA_PRIVATE = user_row(grandpa["user_id"])["private_id_9digit"]
GRANDPA_NAME = user_row(grandpa["user_id"])["name"]
STRANGER_NAME = user_row(stranger["user_id"])["name"]

print("=" * 70)
print("verify_relationship(): direct mode (requester supplies their own Private ID)")
print("=" * 70)

conn = dbmod.get_db()
result = frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID1_NAME, "father", requester_private_id=KID1_PRIVATE)
check("dad verified as kid1's father (direct mode)", result["verified_relationship"] == "parent"
      and result["family_member_user_id"] == dad["user_id"] and result["requester_user_id"] == kid1["user_id"])

try:
    frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID1_NAME, "brother", requester_private_id=KID1_PRIVATE)
    check("wrong relationship CATEGORY ('brother'/sibling, when dad is actually kid1's parent) is rejected", False)
except ValueError as e:
    check("wrong relationship CATEGORY ('brother'/sibling, when dad is actually kid1's parent) is rejected", str(e) == frc._GENERIC_VERIFICATION_ERROR)

try:
    frc.verify_relationship(conn, "000000000", DAD_NAME, KID1_NAME, "father", requester_private_id=KID1_PRIVATE)
    check("a non-existent family-member Private ID is rejected", False)
except ValueError as e:
    check("a non-existent family-member Private ID is rejected", str(e) == frc._GENERIC_VERIFICATION_ERROR)

try:
    frc.verify_relationship(conn, DAD_PRIVATE, "Totally Wrong Name", KID1_NAME, "father", requester_private_id=KID1_PRIVATE)
    check("a family-member name that doesn't match the Private ID is rejected", False)
except ValueError as e:
    check("a family-member name that doesn't match the Private ID is rejected", str(e) == frc._GENERIC_VERIFICATION_ERROR)

try:
    frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, "Totally Wrong Name", "father", requester_private_id=KID1_PRIVATE)
    check("a requester name that doesn't match the requester's own Private ID is rejected", False)
except ValueError as e:
    check("a requester name that doesn't match the requester's own Private ID is rejected", str(e) == frc._GENERIC_VERIFICATION_ERROR)

try:
    frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, STRANGER_NAME, "father", requester_private_id=user_row(stranger["user_id"])["private_id_9digit"])
    check("a real but UNRELATED requester (not in dad's tree at all) is rejected", False)
except ValueError as e:
    check("a real but UNRELATED requester (not in dad's tree at all) is rejected", str(e) == frc._GENERIC_VERIFICATION_ERROR)

# Family Tree cascade rewrite, Rule 5 (2026-11-15): grandparent is a relationship
# _graph_relation() still genuinely confirms (grandpa IS kid1's real grandparent in this fixture's
# graph, two hops up) -- but the nuclear-only tightening now refuses it anyway, deliberately, not
# as a side effect. This check used to assert ACCEPTANCE; it now asserts REFUSAL, with the same
# single generic message every other refusal in this file uses -- not "accepted or refused",
# a real, unsoftened assertion that the claim is rejected.
try:
    frc.verify_relationship(conn, GRANDPA_PRIVATE, GRANDPA_NAME, KID1_NAME, "grandfather", requester_private_id=KID1_PRIVATE)
    check("grandpa, a genuine grandparent confirmed by the graph, is correctly REFUSED under Rule 5's nuclear-only tightening (parent/child/sibling/spouse only)", False)
except ValueError as e:
    check("grandpa, a genuine grandparent confirmed by the graph, is correctly REFUSED under Rule 5's nuclear-only tightening (parent/child/sibling/spouse only)",
          str(e) == frc._GENERIC_VERIFICATION_ERROR)

# The inverse direction (2026-11-16, the follow-up `21d4016` itself flagged): a genuine grandCHILD
# claim must be refused too, not just grandparent -- "grandson"/"granddaughter"/"grandchild" all
# normalize to the same "grandchild" category (family_recovery_core.py's own relationship-category
# table), which NUCLEAR_RELATIONSHIPS does not include. Kid1 IS grandpa's real grandchild in this
# fixture's graph (two hops down through Dad) -- _graph_relation() would genuinely confirm it;
# Rule 5 refuses it anyway, same as the grandparent direction just above.
try:
    frc.verify_relationship(conn, KID1_PRIVATE, KID1_NAME, GRANDPA_NAME, "grandson", requester_private_id=GRANDPA_PRIVATE)
    check("kid1, a genuine grandchild confirmed by the graph, is correctly REFUSED under Rule 5's nuclear-only tightening (parent/child/sibling/spouse only)", False)
except ValueError as e:
    check("kid1, a genuine grandchild confirmed by the graph, is correctly REFUSED under Rule 5's nuclear-only tightening (parent/child/sibling/spouse only)",
          str(e) == frc._GENERIC_VERIFICATION_ERROR)

result = frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID2_NAME, "father", requester_private_id=user_row(kid2["user_id"])["private_id_9digit"])
check("dad verified as kid2's father too (second child, same parent)", result["verified_relationship"] == "parent")

print()
print("=" * 70)
print("verify_relationship(): graph-search mode (requester forgot their own Private ID too)")
print("=" * 70)

result = frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID1_NAME, "father")
check("kid1 discovered by name+relationship search under dad's tree (no Private ID given)",
      result["verified_relationship"] == "parent" and result["requester_user_id"] == kid1["user_id"])

check("search mode and direct mode agree on direction (claimed_relationship = family member's relation TO requester, in both modes)",
      frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID1_NAME, "father")["verified_relationship"]
      == frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID1_NAME, "father", requester_private_id=KID1_PRIVATE)["verified_relationship"])

try:
    frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, KID1_NAME, "son")
    check("the INVERTED relationship word ('son', when dad is actually the father) is rejected in search mode", False)
except ValueError as e:
    check("the INVERTED relationship word ('son', when dad is actually the father) is rejected in search mode", str(e) == frc._GENERIC_VERIFICATION_ERROR)

result = frc.verify_relationship(conn, KID1_PRIVATE, KID1_NAME, SPOUSE1_NAME, "husband")
check("spouse1 discovered as kid1's spouse by name search (symmetric relation)", result["verified_relationship"] == "spouse"
      and result["requester_user_id"] == spouse1["user_id"])

try:
    frc.verify_relationship(conn, DAD_PRIVATE, DAD_NAME, "Nobody By This Name", "son")
    check("a name with no match anywhere in the tree is rejected (zero candidates)", False)
except ValueError as e:
    check("a name with no match anywhere in the tree is rejected (zero candidates)", str(e) == frc._GENERIC_VERIFICATION_ERROR)

conn.close()

print()
print("=" * 70)
print("eligible_family_tree() (internal helper, no longer exposed through any public route)")
print("=" * 70)

conn = dbmod.get_db()
check("dad (has related claimed relatives) is eligible for family recovery", frc.eligible_family_tree(conn, dad["user_id"]))
check("stranger (no tree at all) is NOT eligible for family recovery", not frc.eligible_family_tree(conn, stranger["user_id"]))
conn.close()

print()
print("=" * 70)
print("A: available_methods_for_private_id() / GET /api/recovery/methods -- enumeration resistance")
print("=" * 70)
print("2026-11-14 security correction: this used to return otp_reset/family_recovery computed")
print("from the REAL account's own state, which let an attacker tell a real, eligible Private ID")
print("apart from an unknown one. It is now a FIXED response, independent of the input.")

conn = dbmod.get_db()
methods_dad = frc.available_methods_for_private_id(conn, DAD_PRIVATE)
methods_fake = frc.available_methods_for_private_id(conn, "000000000")
methods_stranger = frc.available_methods_for_private_id(conn, user_row(stranger["user_id"])["private_id_9digit"])
methods_empty = frc.available_methods_for_private_id(conn, "")
conn.close()
check("a real, eligible Private ID (dad: has phone/email-less account but a real Family Tree) gets the fixed response",
      methods_dad == {"otp_reset": True, "family_recovery": True, "admin_ticket": True})
check("a real but tree-ineligible Private ID (stranger) gets the IDENTICAL response -- no distinguishing bit",
      methods_stranger == methods_dad)
check("a non-existent Private ID gets the IDENTICAL response too -- existence itself is not revealed",
      methods_fake == methods_dad)
check("even an empty/malformed input gets the same fixed response (no error-shape leak either)",
      methods_empty == methods_dad)

reset_rate_limits()
logout()
route_results = []
for i in range(21):
    res = client.get(f"/api/recovery/methods?private_id={DAD_PRIVATE}")
    route_results.append((res.status_code, res.get_json()))
check("GET /api/recovery/methods returns the same fixed body for the first 20 calls",
      all(sc == 200 and body == {"otp_reset": True, "family_recovery": True, "admin_ticket": True} for sc, body in route_results[:20]))
check("the 21st call within 10 minutes is rate-limited (429) -- defense in depth now that the route carries no secret, still bounded",
      route_results[20][0] == 429)
res = client.get(f"/api/recovery/methods?private_id={user_row(stranger['user_id'])['private_id_9digit']}")
check("...and the rate limit is by caller IP, not by the Private ID queried (a different id while limited is ALSO 429)", res.status_code == 429)
reset_rate_limits()

print()
print("=" * 70)
print("Full lifecycle via the real HTTP routes: create -> inbox -> share Private ID")
print("=" * 70)

logout()
reset_rate_limits()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID1_NAME, "relationship": "father", "action": "private_id",
})
check("creating a valid request succeeds (201)", res.status_code == 201)
body = res.get_json()
tracking_code = body.get("tracking_code")
check("the response includes a tracking_code", bool(tracking_code))
check("the response includes an expires_at", bool(body.get("expires_at")))

res = client.get(f"/api/recovery/family/status?tracking_code={tracking_code}")
check("status-by-tracking-code for a fresh request reports pending", res.status_code == 200 and res.get_json()["status"] == "pending")
check("status response never includes the family member's identity", "family_member" not in res.get_json() and "name" not in res.get_json())

res = client.post("/api/recovery/family/reveal-private-id", json={"tracking_code": tracking_code})
check("revealing the Private ID before the family member decides anything is refused", res.status_code == 404)

login(dad["private_code"])
conn = dbmod.get_db()
msg_row = conn.execute(
    "SELECT id FROM qmail_messages WHERE to_user_id = ? AND message_type = 'family_recovery_request' ORDER BY id DESC LIMIT 1",
    (dad["user_id"],),
).fetchone()
conn.close()
check("a family_recovery_request Qmail message was delivered to dad's inbox", msg_row is not None)
request_id = None
if msg_row:
    conn = dbmod.get_db()
    req_row = conn.execute("SELECT id FROM family_recovery_requests WHERE qmail_message_id = ?", (msg_row["id"],)).fetchone()
    conn.close()
    request_id = req_row["id"] if req_row else None
check("the Qmail message links back to a real family_recovery_requests row", request_id is not None)

res = client.get(f"/api/qmail/family-recovery/{request_id}")
check("dad can read the request detail", res.status_code == 200)
detail = res.get_json()
check("the detail shows the requester's claimed name and verified relationship", detail["requester_claimed_name"] == KID1_NAME and detail["verified_relationship"] == "parent")
check("the detail is actionable (status pending, can_act)", detail["status"] == "pending" and detail["can_act"] is True)

logout()
login(kid2["private_code"])
res = client.get(f"/api/qmail/family-recovery/{request_id}")
check("a DIFFERENT real user (not the intended family member) cannot read someone else's request", res.status_code == 404)
res = client.post(f"/api/qmail/family-recovery/{request_id}/share-private-id")
check("...and cannot act on it either (share-private-id refused)", res.status_code == 404)

logout()
login(dad["private_code"])
res = client.post(f"/api/qmail/family-recovery/{request_id}/share-private-id")
check("dad shares kid1's Private ID", res.status_code == 200)

res = client.post(f"/api/qmail/family-recovery/{request_id}/share-private-id")
check("sharing a second time on the SAME (now completed) request is refused", res.status_code == 404)

logout()
res = client.post("/api/recovery/family/reveal-private-id", json={"tracking_code": tracking_code})
check("the requester can now reveal the Private ID via their tracking code", res.status_code == 200)
check("...and it's actually kid1's real Private ID", res.get_json().get("private_id") == KID1_PRIVATE)

res = client.post("/api/recovery/family/reveal-private-id", json={"tracking_code": "not-a-real-code"})
check("an unknown tracking code never reveals anything (404)", res.status_code == 404)

print()
print("=" * 70)
print("PIN-reset path: approve -> single-use completion -> replay prevention")
print("=" * 70)

res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID1_NAME, "relationship": "father", "action": "pin_reset",
})
check("a second, different-action request from the same requester is accepted (201)", res.status_code == 201)
pin_tracking_code = res.get_json()["tracking_code"]

login(dad["private_code"])
conn = dbmod.get_db()
pin_req_row = conn.execute(
    "SELECT id FROM family_recovery_requests WHERE tracking_code_hash = ?", (frc._hash(pin_tracking_code),)
).fetchone()
pin_request_id = pin_req_row["id"]
first_request_status = conn.execute("SELECT status FROM family_recovery_requests WHERE id = ?", (request_id,)).fetchone()["status"]
conn.close()
check("the earlier (private_id) completed request was not touched by this new one (supersession is per-pending-request only)", first_request_status == "completed")

res = client.post(f"/api/qmail/family-recovery/{pin_request_id}/approve-pin-reset")
check("dad approves the PIN reset", res.status_code == 200)

logout()
res = client.get(f"/api/recovery/family/status?tracking_code={pin_tracking_code}")
check("status now reports approved with pin_reset_ready", res.get_json()["status"] == "approved" and res.get_json().get("pin_reset_ready") is True)

res = client.post("/api/recovery/family/complete-pin-reset", json={"tracking_code": pin_tracking_code, "new_pin": "99999"})
check("the requester completes the PIN reset with a new PIN", res.status_code == 200)

res = client.post("/login", json={"private_id": KID1_PRIVATE, "pin": "99999"})
check("kid1 can now log in with the NEW PIN", res.status_code == 200)
logout()
res = client.post("/login", json={"private_id": KID1_PRIVATE, "pin": "12345"})
check("...and the OLD PIN no longer works", res.status_code != 200)

res = client.post("/api/recovery/family/complete-pin-reset", json={"tracking_code": pin_tracking_code, "new_pin": "11111"})
check("completing the SAME approved PIN reset a second time is refused (single-use, replay prevention)", res.status_code == 400)

res = client.post("/login", json={"private_id": KID1_PRIVATE, "pin": "99999"})
check("...and the PIN from the first completion is still the active one (replay attempt changed nothing)", res.status_code == 200)
logout()

print()
print("=" * 70)
print("One pending request per requester: a second request SUPERSEDES the first")
print("=" * 70)

reset_rate_limits()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID2_NAME, "relationship": "father", "action": "private_id",
})
check("kid2's first request is accepted", res.status_code == 201)
tc_a = res.get_json()["tracking_code"]

res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID2_NAME, "relationship": "father", "action": "private_id",
})
check("kid2's second request (same requester, still pending) is also accepted", res.status_code == 201)
tc_b = res.get_json()["tracking_code"]

res = client.get(f"/api/recovery/family/status?tracking_code={tc_a}")
check("the FIRST request is now superseded, not still pending", res.get_json()["status"] == "superseded")
res = client.get(f"/api/recovery/family/status?tracking_code={tc_b}")
check("the SECOND request is the live pending one", res.get_json()["status"] == "pending")

print()
print("=" * 70)
print("72-hour request expiry and 24-hour PIN-reset authorization expiry")
print("=" * 70)

reset_rate_limits()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID2_NAME, "relationship": "father", "action": "both",
})
tc_expiry = res.get_json()["tracking_code"]
conn = dbmod.get_db()
conn.execute(
    "UPDATE family_recovery_requests SET expires_at = '2000-01-01T00:00:00+00:00' WHERE tracking_code_hash = ?",
    (frc._hash(tc_expiry),),
)
conn.commit()
conn.close()
res = client.get(f"/api/recovery/family/status?tracking_code={tc_expiry}")
check("a request past its 72-hour expiry reports expired on next status check", res.get_json()["status"] == "expired")

login(dad["private_code"])
conn = dbmod.get_db()
expired_req = conn.execute("SELECT id FROM family_recovery_requests WHERE tracking_code_hash = ?", (frc._hash(tc_expiry),)).fetchone()
conn.close()
res = client.post(f"/api/qmail/family-recovery/{expired_req['id']}/share-private-id")
check("the family member can no longer act on an already-expired request", res.status_code == 404)
logout()

res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID2_NAME, "relationship": "father", "action": "pin_reset",
})
tc_auth_expiry = res.get_json()["tracking_code"]
login(dad["private_code"])
conn = dbmod.get_db()
auth_req = conn.execute("SELECT id FROM family_recovery_requests WHERE tracking_code_hash = ?", (frc._hash(tc_auth_expiry),)).fetchone()
conn.close()
client.post(f"/api/qmail/family-recovery/{auth_req['id']}/approve-pin-reset")
conn = dbmod.get_db()
conn.execute(
    "UPDATE family_recovery_requests SET pin_reset_approved_until = '2000-01-01T00:00:00+00:00' WHERE id = ?",
    (auth_req["id"],),
)
conn.commit()
conn.close()
logout()
res = client.get(f"/api/recovery/family/status?tracking_code={tc_auth_expiry}")
check("status reports the lapsed approval as expired, not a stale 'approved'", res.get_json()["status"] == "expired")
res = client.post("/api/recovery/family/complete-pin-reset", json={"tracking_code": tc_auth_expiry, "new_pin": "55555"})
check("completing a PIN reset whose 24-hour approval window has lapsed is refused", res.status_code == 400)

print()
print("=" * 70)
print("Rejection path")
print("=" * 70)

reset_rate_limits()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD_PRIVATE, "family_member_name": DAD_NAME,
    "requester_name": KID2_NAME, "relationship": "father", "action": "private_id",
})
tc_reject = res.get_json()["tracking_code"]
login(dad["private_code"])
conn = dbmod.get_db()
reject_req = conn.execute("SELECT id FROM family_recovery_requests WHERE tracking_code_hash = ?", (frc._hash(tc_reject),)).fetchone()
conn.close()
res = client.post(f"/api/qmail/family-recovery/{reject_req['id']}/reject")
check("dad rejects the request", res.status_code == 200)
logout()
res = client.get(f"/api/recovery/family/status?tracking_code={tc_reject}")
check("the requester sees the rejection via their tracking code", res.get_json()["status"] == "rejected")
res = client.post("/api/recovery/family/reveal-private-id", json={"tracking_code": tc_reject})
check("a rejected request never yields the Private ID", res.status_code == 404)

print()
print("=" * 70)
print("Rate limiting: 3 attempts / 24h by caller IP and by targeted family-member Private ID,")
print("counting FAILED attempts too")
print("=" * 70)

reset_rate_limits()
# A fresh family member+requester pair, isolated from every request fired above, so this
# section's own counter starts clean regardless of how many requests preceded it in this file.
dad2 = register("Dad2")
kid1b = register("Kid1b")
conn = dbmod.get_db()
n_dad2 = make_node(conn, dad2["user_id"])
n_kid1b = make_node(conn, kid1b["user_id"])
link_parent(conn, n_dad2, n_kid1b)
conn.commit()
conn.close()
DAD2_PRIVATE = user_row(dad2["user_id"])["private_id_9digit"]
DAD2_NAME = user_row(dad2["user_id"])["name"]
KID1B_NAME = user_row(kid1b["user_id"])["name"]

results = []
for i in range(4):
    # Deliberately a FAILING verification each time (wrong relationship CATEGORY -- dad2 is
    # actually kid1b's parent, not sibling) -- Part 8.3 requires failed attempts to still consume
    # the rate limit, to prevent unlimited probing.
    res = client.post("/api/recovery/family/request", json={
        "family_member_private_id": DAD2_PRIVATE, "family_member_name": DAD2_NAME,
        "requester_name": KID1B_NAME, "relationship": "brother", "action": "private_id",
    })
    results.append(res.status_code)
check("first 3 attempts against the same target each get a normal verification response (400, wrong relationship)",
      results[:3] == [400, 400, 400])
check("the 4th attempt within 24h is rate-limited (429), even though every prior attempt FAILED verification", results[3] == 429)

print()
print("=" * 70)
print("C: system-message identity -- never self-sent, never impersonates, correctly inboxed")
print("=" * 70)

reset_rate_limits()
dad3 = register("Dad3")
kid3 = register("Kid3")
conn = dbmod.get_db()
n_dad3 = make_node(conn, dad3["user_id"])
n_kid3 = make_node(conn, kid3["user_id"])
link_parent(conn, n_dad3, n_kid3)
conn.commit()
conn.close()
DAD3_PRIVATE = user_row(dad3["user_id"])["private_id_9digit"]
DAD3_NAME = user_row(dad3["user_id"])["name"]
KID3_NAME = user_row(kid3["user_id"])["name"]

logout()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD3_PRIVATE, "family_member_name": DAD3_NAME,
    "requester_name": KID3_NAME, "relationship": "father", "action": "private_id",
})
check("request for the identity test is created", res.status_code == 201)

login(dad3["private_code"])
res = client.get("/api/qmail/inbox")
check("GET /api/qmail/inbox succeeds", res.status_code == 200)
recovery_msgs = [m for m in res.get_json()["messages"] if m["message_type"] == "family_recovery_request"]
check("the recovery request appears in dad3's inbox", len(recovery_msgs) == 1)
check("...displayed as from 'Qumanity System', never dad3's own name", recovery_msgs and recovery_msgs[0]["from_name"] == "Qumanity System")
check("...with no from_user_id exposed (not a real, clickable member profile)", recovery_msgs and recovery_msgs[0]["from_user_id"] is None)

res = client.get("/api/qmail/sent")
check("GET /api/qmail/sent succeeds", res.status_code == 200)
sent_recovery = [m for m in res.get_json()["messages"] if m.get("subject", "").startswith("Family Recovery Request")]
check("the SAME message never appears in dad3's own Sent folder", len(sent_recovery) == 0)
logout()

print()
print("=" * 70)
print("E: a retired/removed account cannot participate in recovery, on either side")
print("=" * 70)

reset_rate_limits()
dad4 = register("Dad4")
kid4 = register("Kid4")
conn = dbmod.get_db()
n_dad4 = make_node(conn, dad4["user_id"])
n_kid4 = make_node(conn, kid4["user_id"])
link_parent(conn, n_dad4, n_kid4)
conn.commit()
conn.close()
DAD4_PRIVATE = user_row(dad4["user_id"])["private_id_9digit"]
DAD4_NAME = user_row(dad4["user_id"])["name"]
KID4_NAME = user_row(kid4["user_id"])["name"]

logout()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD4_PRIVATE, "family_member_name": DAD4_NAME,
    "requester_name": KID4_NAME, "relationship": "father", "action": "both",
})
check("request for the retirement test is created", res.status_code == 201)
tc_removed = res.get_json()["tracking_code"]

conn = dbmod.get_db()
removed_req = conn.execute("SELECT id FROM family_recovery_requests WHERE tracking_code_hash = ?", (frc._hash(tc_removed),)).fetchone()
conn.execute("UPDATE users SET is_removed = 1 WHERE id = ?", (kid4["user_id"],))
conn.commit()
conn.close()

login(dad4["private_code"])
res = client.post(f"/api/qmail/family-recovery/{removed_req['id']}/share-private-id")
check("the family member can no longer act on a request whose REQUESTER has since been retired", res.status_code == 404)
logout()

# Restore kid4 and approve normally so the PIN-reset-side exclusion can be tested on a request
# that genuinely reached 'approved' before the requester was retired.
conn = dbmod.get_db()
conn.execute("UPDATE users SET is_removed = 0 WHERE id = ?", (kid4["user_id"],))
conn.commit()
conn.close()
login(dad4["private_code"])
res = client.post(f"/api/qmail/family-recovery/{removed_req['id']}/approve-pin-reset")
check("dad4 approves the PIN reset while kid4 is still active", res.status_code == 200)
logout()
conn = dbmod.get_db()
conn.execute("UPDATE users SET is_removed = 1 WHERE id = ?", (kid4["user_id"],))
conn.commit()
conn.close()
res = client.post("/api/recovery/family/complete-pin-reset", json={"tracking_code": tc_removed, "new_pin": "22222"})
check("completing an APPROVED PIN reset for a now-retired requester is refused", res.status_code == 400)
res = client.post("/api/recovery/family/reveal-private-id", json={"tracking_code": tc_removed})
check("revealing a Private ID for a now-retired requester is refused too (never reached 'completed' here, so 404)", res.status_code == 404)
conn = dbmod.get_db()
conn.execute("UPDATE users SET is_removed = 0 WHERE id = ?", (kid4["user_id"],))
conn.commit()
conn.close()

print()
print("=" * 70)
print("B: duplicate/concurrent decisions on the same request are rejected, not double-applied")
print("=" * 70)

reset_rate_limits()
dad5 = register("Dad5")
kid5 = register("Kid5")
conn = dbmod.get_db()
n_dad5 = make_node(conn, dad5["user_id"])
n_kid5 = make_node(conn, kid5["user_id"])
link_parent(conn, n_dad5, n_kid5)
conn.commit()
conn.close()
DAD5_PRIVATE = user_row(dad5["user_id"])["private_id_9digit"]
DAD5_NAME = user_row(dad5["user_id"])["name"]
KID5_NAME = user_row(kid5["user_id"])["name"]

logout()
res = client.post("/api/recovery/family/request", json={
    "family_member_private_id": DAD5_PRIVATE, "family_member_name": DAD5_NAME,
    "requester_name": KID5_NAME, "relationship": "father", "action": "pin_reset",
})
tc_race = res.get_json()["tracking_code"]
conn = dbmod.get_db()
race_req = conn.execute("SELECT id FROM family_recovery_requests WHERE tracking_code_hash = ?", (frc._hash(tc_race),)).fetchone()
conn.close()

login(dad5["private_code"])
# Simulates two concurrent decision attempts on the SAME request: both READ a 'pending' row before
# either WRITE commits in a true race, but the status-flip UPDATE itself (`WHERE status =
# 'pending'`, checked via rowcount) is the guard -- calling approve_pin_reset() twice back-to-back
# exercises that exact guard, since the second call sees the row already moved out of 'pending'
# regardless of how close together the two calls happen.
import family_recovery_core as _frc_direct
conn = dbmod.get_db()
_frc_direct.approve_pin_reset(conn, race_req["id"], dad5["user_id"])
try:
    _frc_direct.approve_pin_reset(conn, race_req["id"], dad5["user_id"])
    check("a second approve_pin_reset() on an already-approved request is rejected, not double-applied", False)
except ValueError:
    check("a second approve_pin_reset() on an already-approved request is rejected, not double-applied", True)
conn.close()
logout()

res = client.post("/api/recovery/family/complete-pin-reset", json={"tracking_code": tc_race, "new_pin": "33333"})
check("the approved PIN reset still completes exactly once despite the earlier double-approve attempt", res.status_code == 200)
res = client.post("/api/recovery/family/complete-pin-reset", json={"tracking_code": tc_race, "new_pin": "44444"})
check("...and a second completion attempt is refused (the row is no longer 'approved')", res.status_code == 400)

print()
print("=" * 70)
print("F: qmail_core.auto_activate() no longer misclassifies a non-collision error as a collision")
print("=" * 70)

import qmail_core
import sqlite3 as _sqlite3

dad6 = register("Dad6")
conn = dbmod.get_db()
_real_insert_username = qmail_core._insert_username


def _raise_integrity_error(*a, **kw):
    raise _sqlite3.IntegrityError("UNIQUE constraint failed: users.qmail_username")


def _raise_other_error(*a, **kw):
    raise RuntimeError("disk I/O error (simulated, not a uniqueness collision)")


conn.execute("UPDATE users SET qmail_username = NULL WHERE id = ?", (dad6["user_id"],))
conn.execute("DELETE FROM qmail_addresses WHERE user_id = ?", (dad6["user_id"],))
conn.commit()
qmail_core._insert_username = _raise_integrity_error
try:
    result = qmail_core.auto_activate(conn, dad6["user_id"])
    # Every candidate "collides" (IntegrityError every time) -- auto_activate() should exhaust
    # MAX_USERNAME_ATTEMPTS and return None cleanly, never raise, never crash registration/login.
    check("a genuine sqlite3.IntegrityError on every attempt is treated as a collision and exhausts cleanly (returns None)", result is None)
except Exception:
    check("a genuine sqlite3.IntegrityError on every attempt is treated as a collision and exhausts cleanly (returns None)", False)
finally:
    qmail_core._insert_username = _real_insert_username

conn.execute("UPDATE users SET qmail_username = NULL WHERE id = ?", (dad6["user_id"],))
conn.execute("DELETE FROM qmail_addresses WHERE user_id = ?", (dad6["user_id"],))
conn.commit()
qmail_core._insert_username = _raise_other_error
try:
    qmail_core.auto_activate(conn, dad6["user_id"])
    check("a non-collision error (e.g. a real DB error) is NOT silently swallowed as a collision -- it propagates", False)
except RuntimeError:
    check("a non-collision error (e.g. a real DB error) is NOT silently swallowed as a collision -- it propagates", True)
except Exception:
    check("a non-collision error (e.g. a real DB error) is NOT silently swallowed as a collision -- it propagates", False)
finally:
    qmail_core._insert_username = _real_insert_username
conn.close()

# Confirm the outer app.py call site still protects registration/login even though auto_activate()
# itself now re-raises a non-collision error -- i.e. the fix doesn't just move the crash somewhere
# else. register() uses the real, unpatched auto_activate() (no monkeypatch active here), so a
# normal registration for a BRAND NEW user must still succeed end-to-end regardless.
dad7 = register("Dad7")
check("registration still succeeds end-to-end for a normal user after the error-handling fix (not a regression)", bool(dad7.get("user_id")))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
