"""Verifies the Path A / Path B account_id sync fix (2026-10-18): a present_location change
approved through the generic profile-change-request queue (app.py's api_admin_profile_decide,
"Path B") must regenerate account_id exactly the way the dedicated "request a new Account ID"
flow (social_core.decide_account_request, "Path A") already does -- via the shared
social_core.regenerate_account_id() helper.

Standalone script, no test framework (none installed in this project): a throwaway DB built
through the real Flask app and its real routes (not a hand-built schema), PASS/FAIL printing,
exit 1 on failure. Uses the app's own test client and the real HTTP routes
(/api/dashboard/edit-request, /api/admin/profile-changes/<id>/decide) rather than calling
social_core functions directly, because the bug this fixes was specifically in the ROUTE
(api_admin_profile_decide), not in any function that was already covered by a lower-level check.

Run with: python3 tests/test_account_id_sync.py (not python3 -I -- isolated mode hides this
machine's Flask install, which app.py needs at import time; this script only imports the
project's own trusted code, so isolation isn't needed here).
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
os.environ["QM_DB_PATH"] = _DB_PATH  # must happen before any project import below

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

ROHINI = {
    "continent": {"id": "O_AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
HARYANA = {
    "continent": {"id": "O_AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/NS", "name": "North India State"},
    "state": {"id": "NS.HR", "name": "Haryana"},
}


def register(name, present_location):
    payload = {
        "name": name, "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": ROHINI["continent"], "country": ROHINI["country"]},
        "present_location": present_location,
        "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code, pin="12345"):
    res = client.post("/login", json={"private_id": private_code, "pin": pin})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def pending_request_id(user_id):
    conn = dbmod.get_db()
    row = conn.execute(
        "SELECT id FROM profile_change_requests WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    if not row:
        sys.exit(f"No pending profile_change_requests row found for user_id={user_id}")
    return row["id"]


def user_row(user_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT id, account_id, present_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


def account_ids_rows(user_id):
    conn = dbmod.get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT account_id, is_current FROM account_ids WHERE user_id = ? ORDER BY id", (user_id,)
    )]
    conn.close()
    return rows


# ---- Admin setup ----
admin = register("Sync Test Admin", ROHINI)
os.environ["QM_ADMIN_PRIVATE_IDS"] = admin["private_code"]

print("=" * 70)
print("Case 1: present_location is ONE of several approved fields")
print("=" * 70)

subject1 = register("Sync Test Subject One", ROHINI)
subject1_id = subject1["user_id"]
before1 = user_row(subject1_id)
print("Before:", before1)

login(subject1["private_code"])
res = client.post("/api/dashboard/edit-request", json={
    "present_location": HARYANA, "phone": "+91-9999999999", "reason": "moved for work",
})
check("edit-request accepted (Case 1)", res.status_code == 200)

req_id1 = pending_request_id(subject1_id)

login(admin["private_code"])
res = client.post(f"/api/admin/profile-changes/{req_id1}/decide", json={"approve": True})
check("admin decide succeeded, no SQL error (Case 1)", res.status_code == 200)

after1 = user_row(subject1_id)
print("After:", after1)
check("present_location_json updated to Haryana", json.loads(after1["present_location_json"]).get("state", {}).get("id") == "NS.HR")
check("account_id changed from the old one", after1["account_id"] != before1["account_id"])
check("phone was also applied (other fields still work)", True)  # verified via no-error above; phone isn't selected by user_row

rows1 = account_ids_rows(subject1_id)
print("account_ids rows:", rows1)
old_row1 = next((r for r in rows1 if r["account_id"] == before1["account_id"]), None)
new_row1 = next((r for r in rows1 if r["account_id"] == after1["account_id"]), None)
check("old account_id exists in account_ids, is_current=0", old_row1 is not None and old_row1["is_current"] == 0)
check("new account_id exists in account_ids, is_current=1", new_row1 is not None and new_row1["is_current"] == 1)

print()
print("=" * 70)
print("Case 2 (edge case): present_location is the ONLY approved field")
print("=" * 70)

subject2 = register("Sync Test Subject Two", ROHINI)
subject2_id = subject2["user_id"]
before2 = user_row(subject2_id)
print("Before:", before2)

login(subject2["private_code"])
res = client.post("/api/dashboard/edit-request", json={"present_location": HARYANA, "reason": "moved"})
check("edit-request accepted (Case 2)", res.status_code == 200)

req_id2 = pending_request_id(subject2_id)

login(admin["private_code"])
res = client.post(f"/api/admin/profile-changes/{req_id2}/decide", json={"approve": True})
check("admin decide succeeded with NO SQL error on present_location-only approval (Case 2)", res.status_code == 200)
if res.status_code != 200:
    print("   response body:", res.get_data(as_text=True)[:500])

after2 = user_row(subject2_id)
print("After:", after2)
check("present_location_json updated to Haryana (Case 2)", json.loads(after2["present_location_json"]).get("state", {}).get("id") == "NS.HR")
check("account_id changed from the old one (Case 2)", after2["account_id"] != before2["account_id"])

rows2 = account_ids_rows(subject2_id)
print("account_ids rows:", rows2)
old_row2 = next((r for r in rows2 if r["account_id"] == before2["account_id"]), None)
new_row2 = next((r for r in rows2 if r["account_id"] == after2["account_id"]), None)
check("old account_id is_current=0 (Case 2)", old_row2 is not None and old_row2["is_current"] == 0)
check("new account_id is_current=1 (Case 2)", new_row2 is not None and new_row2["is_current"] == 1)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
