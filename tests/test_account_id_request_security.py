"""Covers the C1 security correction (2026-11-08): the account-ID-request flow ("Path A" --
social_core.request_new_account() / decide_account_request(), reached via
POST /api/people/account-ids/request and POST /api/admin/account-ids/<id>/decide) now applies
the SAME present_location validation and Global/Public account-boundary lock as the existing
profile-change-request flow ("Path B" -- app.py's api_dashboard_edit_request /
api_admin_profile_decide), via the shared account_core.validate_present_location_change().

Before this fix, Path A's only check was a bare truthiness test
(`present_location.get("village") or present_location.get("state")`) -- an independent
adversarial pre-merge audit demonstrated this let a Global Account queue a fabricated
Public/India village present_location and, once an admin approved it, cross the Global<->Public
account boundary and resolve to the real pilot village under election_core._present_village_id().

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes where the scenario calls for it, direct
social_core calls where it doesn't, PASS/FAIL printing, exit 1 on failure (same convention as
tests/test_global_account.py and tests/test_account_id_sync.py).

Run with: python3 tests/test_account_id_request_security.py (not -I)
"""
from __future__ import annotations

import json
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
import social_core  # noqa: E402

# Every throwaway test DB starts with india_villages empty -- seed the two real villages this
# file's fixtures need: Rohini Sector 24 (the real pilot village, under Delhi/Bawana) and
# Bombooflat (a second, genuinely different Indian village, under Andaman/Port Blair), both
# correctly parented so a "legitimate move between two real villages" test has something true to
# exercise, and a "real village, wrong stated parent" test has something to catch.
_seed_conn = appmod.get_db()
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.AN.1.1.1', 'CS.AN.1.1', 'Bombooflat')")
_seed_conn.commit()
_seed_conn.close()

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def expect_rejected(label, fn):
    """Calls fn() expecting it to raise ValueError (the convention request_new_account() and
    decide_account_request() both use for a rejected submission/approval); fails the check if it
    does not raise, or raises something else."""
    try:
        fn()
        check(label, False)
    except ValueError:
        check(label, True)
    except Exception as e:  # noqa: BLE001 -- a non-ValueError failure is still a FAIL, just labelled
        check(f"{label} (raised {type(e).__name__} instead of ValueError: {e})", False)


client = appmod.app.test_client()

JAPAN_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_JPN", "code": "JPN", "name": "Japan"},
}
# Rohini Sector 24 -- the real pilot village (election_core.PILOT_VILLAGE_ID).
INDIA_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
# Bombooflat -- a second, genuinely different, fully self-consistent Indian village (Andaman and
# Nicobar Islands / Port Blair tehsil), used for a legitimate same-classification move.
ANDAMAN_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.AN", "name": "Andaman and Nicobar Islands"},
    "district": {"id": "CS.AN.1", "name": "Andaman and Nicobar Islands"},
    "tehsil": {"id": "CS.AN.1.1", "name": "Port Blair"},
    "village": {"id": "CS.AN.1.1.1", "name": "Bombooflat"},
}

_n = [0]


def register(name_prefix, present_location):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "female", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": present_location, "present_location": present_location,
        "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED for {name_prefix}: {res.status_code} {res.get_data(as_text=True)[:500]}")
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


def account_snapshot(user_id):
    row = user_row(user_id)
    return {
        "account_id": row["account_id"],
        "present_location_json": row["present_location_json"],
        "classification": appmod.account_access_type(json.loads(row["present_location_json"])),
    }


def pending_request_row(user_id):
    conn = dbmod.get_db()
    row = conn.execute(
        "SELECT * FROM account_id_requests WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def insert_forged_request(user_id, present_location, reason="forged, bypassing request_new_account()"):
    """Simulates a pending account_id_requests row that reached 'pending' status WITHOUT going
    through request_new_account()'s own validation -- e.g. a pre-fix row, or any future bug in the
    submission route. Approval must independently refuse this on its own (defense in depth)."""
    conn = dbmod.get_db()
    social_core.ensure_account_request_table(conn)
    cur = conn.execute(
        "INSERT INTO account_id_requests (user_id, present_location_json, created_at) VALUES (?, ?, datetime('now'))",
        (user_id, json.dumps(present_location)),
    )
    conn.commit()
    request_id = cur.lastrowid
    conn.close()
    return request_id


# ---- Setup ----
admin = register("Security Test Admin", INDIA_LOC)
os.environ["QM_ADMIN_PRIVATE_IDS"] = admin["private_code"]
admin_id = admin["user_id"]

japan = register("Security Test Global", JAPAN_LOC)
japan_id = japan["user_id"]

india_a = register("Security Test Public A", INDIA_LOC)
india_a_id = india_a["user_id"]

print("=" * 70)
print("A. Submission-time validation (social_core.request_new_account(), direct calls)")
print("=" * 70)

conn = dbmod.get_db()
japan_before = account_snapshot(japan_id)
expect_rejected(
    "A1. A Global Account (Japan) submitting a complete India/Rohini Sector 24 present_location "
    "is REJECTED at submission -- the exact original exploit payload",
    lambda: social_core.request_new_account(conn, japan_id, INDIA_LOC),
)

expect_rejected(
    "A2a. A Public Account submitting a non-dict present_location ('not-a-location') is REJECTED, "
    "not silently accepted or a crash",
    lambda: social_core.request_new_account(conn, india_a_id, "not-a-location"),
)
malformed = dict(INDIA_LOC)
malformed["district"] = "CS.DL.3"  # a plain string instead of {"id": "CS.DL.3"}
expect_rejected(
    "A2b. A Public Account submitting a malformed sub-field (district as a bare string, not an "
    "object) is REJECTED, not a 500",
    lambda: social_core.request_new_account(conn, india_a_id, malformed),
)

mismatched_village = dict(INDIA_LOC)  # Delhi/Bawana zone+state+district+tehsil, Andaman's REAL village
mismatched_village["village"] = {"id": "CS.AN.1.1.1", "name": "Bombooflat"}
expect_rejected(
    "A3. A Public Account submitting a real village (Bombooflat) whose real parent tehsil "
    "(Port Blair) disagrees with the rest of the submitted chain (Bawana/Delhi) is REJECTED",
    lambda: social_core.request_new_account(conn, india_a_id, mismatched_village),
)
conn.close()

japan_after = account_snapshot(japan_id)
check("A5. The rejected Japan->India submission did not mutate the Global Account's account_id, "
      "present_location_json, or classification at all", japan_after == japan_before)
check("A5b. The rejected submissions queued NO account_id_requests row for Japan",
      pending_request_row(japan_id) is None)
check("A5c. The rejected submissions queued NO account_id_requests row for the Public account either",
      pending_request_row(india_a_id) is None)

print()
print("=" * 70)
print("B. Submission + approval of a LEGITIMATE request (regression: the fix must not block real moves)")
print("=" * 70)

india_mover = register("Security Test Mover", INDIA_LOC)
india_mover_id = india_mover["user_id"]
mover_before = account_snapshot(india_mover_id)
conn = dbmod.get_db()
social_core.request_new_account(conn, india_mover_id, ANDAMAN_LOC)  # Rohini -> Bombooflat, same classification
conn.close()
mover_request = pending_request_row(india_mover_id)
check("B4. A legitimate, same-classification move (Rohini -> Bombooflat, both real, both Public) "
      "is ACCEPTED at submission and queued", mover_request is not None)

approval_raised = False
try:
    conn = dbmod.get_db()
    social_core.decide_account_request(conn, admin_id, mover_request["id"], True)
    conn.close()
except ValueError:
    approval_raised = True
mover_after = account_snapshot(india_mover_id)
check("B9. The admin's approval of a valid, consistent request succeeds without error",
      not approval_raised)
check("B9b. The approved present_location_json now reflects the new (Andaman) location",
      json.loads(mover_after["present_location_json"]) == ANDAMAN_LOC)
check("B9c. The account stays 'public' after a legitimate same-classification move",
      mover_after["classification"] == "public")
check("B9d. account_id was regenerated for the new location (changed from the pre-approval value)",
      mover_after["account_id"] != mover_before["account_id"])
conn = dbmod.get_db()
mover_req_row = conn.execute("SELECT status FROM account_id_requests WHERE id = ?", (mover_request["id"],)).fetchone()
conn.close()
check("B9e. The approved request's own status is now 'approved'", mover_req_row["status"] == "approved")

print()
print("=" * 70)
print("C. Approval-time revalidation (state changes AFTER a valid submission, BEFORE approval)")
print("=" * 70)

india_switcher = register("Security Test Switcher", INDIA_LOC)
switcher_id = india_switcher["user_id"]
conn = dbmod.get_db()
social_core.request_new_account(conn, switcher_id, ANDAMAN_LOC)  # valid AT SUBMISSION TIME: public -> public
conn.close()
switcher_request = pending_request_row(switcher_id)
check("C-setup. The switcher's Rohini -> Bombooflat request is accepted at submission (both Public)",
      switcher_request is not None)

# The user's account state now changes WHILE the request is pending -- e.g. some other approved
# change. Applied directly, the way any other real mutation of present_location_json would land.
conn = dbmod.get_db()
conn.execute("UPDATE users SET present_location_json = ? WHERE id = ?", (json.dumps(JAPAN_LOC), switcher_id))
conn.commit()
conn.close()
switcher_before_decide = account_snapshot(switcher_id)
check("C-setup2. The switcher's account is now classified 'global' (their state changed since "
      "they submitted the still-pending Rohini->Bombooflat, public-only request)",
      switcher_before_decide["classification"] == "global")

expect_rejected(
    "C6. Approving the now-stale request (still 'public' Andaman target, but the account is now "
    "'global') is REJECTED -- approval revalidates against CURRENT state, not the state at "
    "submission time",
    lambda: social_core.decide_account_request(dbmod.get_db(), admin_id, switcher_request["id"], True),
)
switcher_after_decide = account_snapshot(switcher_id)
check("C10a. The switcher's account_id/present_location_json/classification are UNCHANGED by the "
      "rejected approval", switcher_after_decide == switcher_before_decide)
conn = dbmod.get_db()
switcher_req_row = conn.execute("SELECT status FROM account_id_requests WHERE id = ?", (switcher_request["id"],)).fetchone()
conn.close()
check("C10b. The request's own status is still 'pending' -- not silently approved or auto-rejected",
      switcher_req_row["status"] == "pending")

print()
print("=" * 70)
print("D. Approval-time defense in depth (a forged/bypassed pending row -- not through request_new_account())")
print("=" * 70)

japan2 = register("Security Test Global Two", JAPAN_LOC)
japan2_id = japan2["user_id"]
japan2_before = account_snapshot(japan2_id)
forged_request_id = insert_forged_request(japan2_id, INDIA_LOC)  # bypasses request_new_account() entirely

expect_rejected(
    "D7. Approving a forged pending request (inserted directly, bypassing submission validation) "
    "that would flip a Global Account to Public via a fabricated India/Rohini Sector 24 location "
    "is REJECTED at approval time too -- defense in depth, not reliant on submission alone",
    lambda: social_core.decide_account_request(dbmod.get_db(), admin_id, forged_request_id, True),
)
japan2_after = account_snapshot(japan2_id)
check("D10. The forged approval attempt left the Global Account's account_id/present_location_json/"
      "classification completely unchanged", japan2_after == japan2_before)
conn = dbmod.get_db()
forged_row = conn.execute("SELECT status FROM account_id_requests WHERE id = ?", (forged_request_id,)).fetchone()
village_id_after = appmod.election_core._present_village_id(user_row(japan2_id))
conn.close()
check("D10b. The forged request's status is still 'pending'", forged_row["status"] == "pending")
check("D13. The Global Account acquired NO Q-Punch village eligibility through this path "
      "(_present_village_id() is still None) -- independently of any age/zodiac/voting-cycle "
      "state, since the rejection happens at the location/boundary check, before eligibility is "
      "ever considered", village_id_after is None)

india_d = register("Security Test Public D", INDIA_LOC)
india_d_id = india_d["user_id"]
bad_ancestry_request_id = insert_forged_request(india_d_id, mismatched_village)  # stays Public, but ancestry is forged
expect_rejected(
    "D8. Approving a forged pending request with an internally inconsistent ancestry chain "
    "(real village, wrong stated parent) -- same classification throughout, so only the "
    "ancestry check can catch it -- is REJECTED at approval",
    lambda: social_core.decide_account_request(dbmod.get_db(), admin_id, bad_ancestry_request_id, True),
)

print()
print("=" * 70)
print("E. The real HTTP routes (POST /api/people/account-ids/request, "
      "POST /api/admin/account-ids/<id>/decide) -- the critical bypass scenario, reproduced exactly")
print("=" * 70)

japan3 = register("Security Test Global Three", JAPAN_LOC)
japan3_id = japan3["user_id"]
japan3_before = account_snapshot(japan3_id)

login(japan3["private_code"])
submit_resp = client.post("/api/people/account-ids/request", json={"present_location": INDIA_LOC})
check("E11. The real POST /api/people/account-ids/request route REJECTS (400) a Global Account's "
      "exact-original-exploit India/Rohini Sector 24 payload", submit_resp.status_code == 400)
logout()
check("E11b. No account_id_requests row was ever queued through the real route",
      pending_request_row(japan3_id) is None)

# To exercise the real admin-decide route's own defense-in-depth (not just the direct function
# call already proven in section D), force a pending row into existence the way a pre-fix bug or
# stale data could have, then hit the real HTTP admin route.
japan3_forged_id = insert_forged_request(japan3_id, INDIA_LOC)
login(admin["private_code"])
decide_resp = client.post(f"/api/admin/account-ids/{japan3_forged_id}/decide", json={"approve": True})
check("E12. The real POST /api/admin/account-ids/<id>/decide route REJECTS (400) approval of that "
      "forged pending request -- the original exploit's admin-approval step, exactly as the "
      "earlier audit executed it, no longer succeeds", decide_resp.status_code == 400)
logout()

japan3_after = account_snapshot(japan3_id)
check("E13. The Global Account's account_id/present_location_json/classification are "
      "COMPLETELY UNCHANGED after the full exploit attempt (real submission route + real admin "
      "decide route)", japan3_after == japan3_before)
check("E13b. classification is still 'global' -- the Global<->Public boundary never flipped",
      japan3_after["classification"] == "global")
village_id_e = appmod.election_core._present_village_id(user_row(japan3_id))
check("E13c. _present_village_id() is still None for this account -- no Q-Punch village "
      "eligibility was ever acquired, checked independently of age/zodiac/voting-cycle state",
      village_id_e is None)

print()
print("=" * 70)
print("F. Path B (the profile-change-request flow) regression -- unaffected by this fix")
print("=" * 70)

login(india_a["private_code"])
cross_boundary = client.post("/api/dashboard/edit-request", json={"present_location": JAPAN_LOC, "reason": "x"})
check("F14a. Path B's own Public->Global boundary rejection still works unchanged (400)",
      cross_boundary.status_code == 400)
good_edit = client.post("/api/dashboard/edit-request", json={"present_location": INDIA_LOC, "reason": "x"})
check("F14b. Path B's own legitimate, same-classification edit still works unchanged (200)",
      good_edit.status_code == 200)
logout()

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks PASSED.")
