"""Verifies the identity-correction ticket architecture (2026-10-19): identity_core.py's three
new ticket types layered onto profile_change_requests, the village-council scope boundary
api_admin_profile_decide and api_admin_profile_changes now enforce, the Admin Panel feed's new
'identity' source, the "I don't remember my exact birth time" registration flag, and -- the one
fact this whole feature leans on -- that regenerating private_id_9digit never touches account_id
or Qmail.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure. Follows
the same pattern as tests/test_account_id_sync.py and tests/test_admin_panel_council_scope.py.

Run with: python3 tests/test_identity_correction.py (not -I -- isolated mode hides this
machine's Flask install).
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = "/Users/macmudgal/Desktop/Qumanity_DPG"
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
VILLAGE_B = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1B", "name": "Rohini Sector 25"},
}
VID_A, VID_B = VILLAGE_A["village"]["id"], VILLAGE_B["village"]["id"]

_n = [0]


def register(name_prefix, birth_location, present_location=None, tob="06:00", tob_unknown=False):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": birth_location, "present_location": present_location or birth_location,
        "assisted": False,
    }
    if tob_unknown:
        payload["tob_unknown"] = True
    else:
        payload["tob"] = tob
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


def raw(sql, params=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def raw_exec(sql, params=()):
    conn = dbmod.get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    conn.close()
    return cur.lastrowid


def user_row(user_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row)


def seat_council(village_id, male_id, female_id, cycle_id):
    import datetime as dt
    today = dt.date.today()
    raw_exec(
        "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
        "nomination_end, voting_start, voting_end, status) VALUES (?, ?, 'Aries', 'Fire', 2026, ?, ?, ?, ?, 'closed')",
        (cycle_id, village_id,
         (today - dt.timedelta(days=20)).isoformat(), (today - dt.timedelta(days=15)).isoformat(),
         (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
    )
    raw_exec(
        "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
        "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Aries', 2026, ?, ?, ?, ?, ?)",
        (village_id, male_id, female_id, cycle_id, today.isoformat(), (today + dt.timedelta(days=30)).isoformat()),
    )


print("=" * 70)
print("Setup: Admin, a seated Village A council, and a subject born in Village A")
print("=" * 70)

admin = register("Admin", VILLAGE_B)
os.environ["QM_ADMIN_PRIVATE_IDS"] = admin["private_code"]

head_m = register("HeadM", VILLAGE_A)
head_f = register("HeadF", VILLAGE_A)
seat_council(VID_A, head_m["user_id"], head_f["user_id"], 301)

# Subject's PRESENT location is deliberately Village B -- the ticket must route by BIRTH
# location (Village A), not present location, proving the two are independent.
subject = register("Subject", VILLAGE_A, present_location=VILLAGE_B)
subject_id = subject["user_id"]
before = user_row(subject_id)

print()
print("=" * 70)
print("1. The subject submits all three ticket types, plus one plain self-service edit")
print("=" * 70)

login(subject["private_code"])

res = client.post("/api/dashboard/identity-request", json={"request_type": "id_change_b", "reason": "my ID is compromised"})
check("id_change_b ticket queued", res.status_code == 200 and res.get_json().get("status") == "queued")
req_b = res.get_json()["request_id"]

res = client.post("/api/dashboard/identity-request", json={
    "request_type": "id_change_a", "birth_location": VILLAGE_B, "reason": "wrong village at registration",
})
check("id_change_a ticket queued", res.status_code == 200)
req_a = res.get_json()["request_id"]

res = client.post("/api/dashboard/identity-request", json={"request_type": "birth_time_correction", "tob": "14:45:00", "reason": "found my birth certificate"})
check("birth_time_correction ticket queued", res.status_code == 200)
req_t = res.get_json()["request_id"]

res = client.post("/api/dashboard/identity-request", json={"request_type": "nonsense"})
check("an unknown request_type is rejected with 400", res.status_code == 400)

res = client.post("/api/dashboard/edit-request", json={"phone": "+91-8888888888", "dob": "1990-06-15", "reason": "unrelated edit"})
check("plain self-service edit ticket queued", res.status_code == 200)
req_edit = raw("SELECT id FROM profile_change_requests WHERE request_type = 'edit' ORDER BY id DESC LIMIT 1")["id"]

for rid, label in ((req_b, "id_change_b"), (req_a, "id_change_a"), (req_t, "birth_time_correction")):
    row = raw("SELECT location_level, location_id, request_type FROM profile_change_requests WHERE id = ?", (rid,))
    check(f"{label} ticket is scoped to Village A (the subject's BIRTH village, not present)",
          row["location_level"] == "village" and row["location_id"] == VID_A)

print()
print("=" * 70)
print("2. A Village A council head sees only the three new tickets, never the plain edit")
print("=" * 70)

login(head_m["private_code"])
res = client.get("/api/admin/profile-changes")
check("head's profile-changes listing succeeds", res.status_code == 200)
seen_ids = {r["id"] for r in res.get_json()["requests"]}
check("head sees id_change_b", req_b in seen_ids)
check("head sees id_change_a", req_a in seen_ids)
check("head sees birth_time_correction", req_t in seen_ids)
check("head does NOT see the plain edit ticket", req_edit not in seen_ids)

res = client.get("/api/admin/panel/feed")
check("head's panel feed succeeds", res.status_code == 200)
feed_items = res.get_json()["items"]
identity_items = [it for it in feed_items if it["source"] == "identity"]
check("head's panel feed carries exactly the 3 identity tickets", {it["id"] for it in identity_items} == {req_b, req_a, req_t})
check("every identity item in the head's feed is tagged with Village A", all(it["location"] == f"Village {VID_A}" for it in identity_items))

res = client.post(f"/api/admin/profile-changes/{req_edit}/decide", json={"approve": True})
check("head deciding the plain edit ticket -> 404, not applied (outside council authority)", res.status_code == 404)
check("the plain edit ticket is still pending after the head's attempt",
      raw("SELECT status FROM profile_change_requests WHERE id = ?", (req_edit,))["status"] == "pending")

print()
print("=" * 70)
print("3. Head approves id_change_b: private_id_9digit changes, account_id/Qmail do not")
print("=" * 70)

res = client.post(f"/api/admin/profile-changes/{req_b}/decide", json={"approve": True})
check("head approves id_change_b", res.status_code == 200)
after_b = user_row(subject_id)
check("private_id_9digit changed", after_b["private_id_9digit"] != before["private_id_9digit"])
check("account_id is UNCHANGED (private_id_9digit carries no location/account relationship)",
      after_b["account_id"] == before["account_id"])
check("birth_location is UNCHANGED (id_change_b never touches location)",
      after_b["birth_location_json"] == before["birth_location_json"])

print()
print("=" * 70)
print("4. Head approves id_change_a: birth_location moves, zodiac/kundali recompute, ID re-rolls again")
print("=" * 70)

res = client.post(f"/api/admin/profile-changes/{req_a}/decide", json={"approve": True})
check("head approves id_change_a", res.status_code == 200)
after_a = user_row(subject_id)
check("birth_location_json now reflects Village B", "CS.DL.3.4.1B" in after_a["birth_location_json"])
check("private_id_9digit changed again from the id_change_b value",
      after_a["private_id_9digit"] != after_b["private_id_9digit"])
check("account_id is STILL unchanged (present_location was never part of this ticket)",
      after_a["account_id"] == before["account_id"])
zodiac_after = raw("SELECT * FROM user_zodiac WHERE user_id = ?", (subject_id,))
check("user_zodiac row still exists after the recompute", zodiac_after is not None)

print()
print("=" * 70)
print("5. Head approves birth_time_correction: tob updates, birth_time_known flips to 1")
print("=" * 70)

res = client.post(f"/api/admin/profile-changes/{req_t}/decide", json={"approve": True})
check("head approves birth_time_correction", res.status_code == 200)
after_t = user_row(subject_id)
check("tob updated to the corrected time", after_t["tob"] == "14:45:00")
check("birth_time_known is 1 after an approved correction", after_t["birth_time_known"] == 1)

print()
print("=" * 70)
print("6. Admin (global scope) can still decide the plain edit ticket a village head could not")
print("=" * 70)

login(admin["private_code"])
res = client.post(f"/api/admin/profile-changes/{req_edit}/decide", json={"approve": True})
check("admin approves the plain edit ticket", res.status_code == 200)
check("the plain edit ticket is now approved", raw("SELECT status FROM profile_change_requests WHERE id = ?", (req_edit,))["status"] == "approved")

print()
print("=" * 70)
print("7. Attachment upload + scoped serve route")
print("=" * 70)

logout()
other = register("Unrelated", VILLAGE_B)
# A FRESH subject, still born in (and never moved out of) Village A -- subject_id's own birth
# village moved to Village B in section 4, so a new ticket from THEM would now (correctly) scope
# to Village B instead, which has no seated council in this test and would make this check
# meaningless.
subject2 = register("Subject2", VILLAGE_A, present_location=VILLAGE_B)
login(subject2["private_code"])

import base64
png_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 64  # not a valid PNG decode-wise, just bytes with the right magic/extension
res = client.post("/api/dashboard/identity-request", json={
    "request_type": "id_change_b", "reason": "compromised again, with proof",
    "attachment": {"filename": "proof.png", "content_type": "image/png", "data": base64.b64encode(png_bytes).decode()},
})
check("ticket with an attachment queued", res.status_code == 200)
req_with_attachment = res.get_json()["request_id"]
att_row = raw("SELECT id FROM profile_change_attachments WHERE request_id = ?", (req_with_attachment,))
check("attachment row was written", att_row is not None)
att_id = att_row["id"]

res = client.get(f"/api/admin/profile-changes/{req_with_attachment}/attachments/{att_id}")
check("the submitter themself can fetch their own attachment", res.status_code == 200)

login(head_m["private_code"])
res = client.get(f"/api/admin/profile-changes/{req_with_attachment}/attachments/{att_id}")
check("Village A's head (in scope) can fetch the attachment", res.status_code == 200)

login(other["private_code"])
res = client.get(f"/api/admin/profile-changes/{req_with_attachment}/attachments/{att_id}")
check("an unrelated member gets 404, not the file", res.status_code == 404)

print()
print("=" * 70)
print("8. Registration's \"I don't remember my exact birth time\" flag")
print("=" * 70)

logout()
unknown_tob_user = register("ForgotTime", VILLAGE_A, tob_unknown=True)
row = user_row(unknown_tob_user["user_id"])
check("tob defaulted to noon", row["tob"] == "12:00:00")
check("birth_time_known is 0", row["birth_time_known"] == 0)

known_tob_user = register("KnowsTime", VILLAGE_A, tob="09:15")
row2 = user_row(known_tob_user["user_id"])
check("a normal registration keeps birth_time_known = 1", row2["birth_time_known"] == 1)
check("a normal registration's tob is untouched", row2["tob"] == "09:15")

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
