"""Verifies Qmail end to end (2026-10-18): username validation/normalization, cross-account_id
uniqueness, compose resolution (current / inside-forward-window / past-forward-window), the
Path B -> regenerate_account_id -> qmail_addresses hook, and the smart "To" field's
connected/unconnected scoping.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_qmail.py (not -I -- isolated mode hides this machine's Flask
install; see tests/test_account_id_sync.py's note on the same thing).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH

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
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
HARYANA = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/NS", "name": "North India State"}, "state": {"id": "NS.HR", "name": "Haryana"},
}
PUNJAB = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/NS", "name": "North India State"}, "state": {"id": "NS.PB", "name": "Punjab"},
}

_n = [0]


def register(name_prefix, present_location):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
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


def raw(sql, params=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def raw_exec(sql, params=()):
    conn = dbmod.get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def activate(username):
    return client.post("/api/qmail/activate", json={"username": username})


print("=" * 70)
print("Section 1: username validation and normalization")
print("=" * 70)

u1 = register("Alpha", ROHINI)
login(u1["private_code"])

res = activate("RohitDELHI1")
check("uppercase username accepted and normalized", res.status_code == 201)
row = raw("SELECT qmail_username FROM users WHERE id = ?", (u1["user_id"],))
check("stored lowercase ('rohitdelhi1')", row["qmail_username"] == "rohitdelhi1")

u2 = register("Beta", ROHINI)
login(u2["private_code"])
res = activate("short7x")
check("7-character username rejected", res.status_code == 400)

res = activate("sixteencharsxxxx")
check("16-character username rejected", res.status_code == 400)

res = activate("bad user@x")
check("illegal character (@, space) rejected", res.status_code == 400)
row = raw("SELECT qmail_username FROM users WHERE id = ?", (u2["user_id"],))
check("rejected attempts left qmail_username NULL", row["qmail_username"] is None)

print()
print("=" * 70)
print("Section 2: username uniqueness across DIFFERENT account_ids")
print("=" * 70)

u3 = register("Gamma", HARYANA)
login(u3["private_code"])
res = activate("sharedname01")
check("first claimant of 'sharedname01' succeeds", res.status_code == 201)

u4 = register("Delta", PUNJAB)  # different user, different location -> different account_id
login(u4["private_code"])
check("u3 and u4 have different account_id (sanity check)", u3["account_id"] != u4["account_id"])
res = activate("sharedname01")
check("second claimant with a DIFFERENT account_id is still rejected (the design's whole point)", res.status_code == 400)
row = raw("SELECT qmail_username FROM users WHERE id = ?", (u4["user_id"],))
check("u4's qmail_username stays NULL after the rejected claim", row["qmail_username"] is None)

print()
print("=" * 70)
print("Section 3: compose resolution -- current, inside window, past window")
print("=" * 70)

sender = register("Sender", ROHINI)
login(sender["private_code"])
activate("senderaccnt1")

recipient = register("Recip", ROHINI)
login(recipient["private_code"])
res = activate("recipientac1")
current_address = res.get_json()["address"]

login(sender["private_code"])
res = client.post("/api/qmail/compose", json={"to": current_address, "subject": "Hi", "body": "Test body 1"})
check("compose to CURRENT address delivered", res.status_code == 201)
row = raw("SELECT COUNT(*) AS n FROM qmail_messages WHERE to_user_id = ?", (recipient["user_id"],))
check("message actually landed in recipient's inbox", row["n"] == 1)

# Force the recipient's account_id to change via Path B, creating an is_current=0 row.
login(recipient["private_code"])
res = client.post("/api/dashboard/edit-request", json={"present_location": HARYANA, "reason": "moved"})
check("recipient's Path B edit-request accepted", res.status_code == 200)

login(sender["private_code"])
req_row = raw(
    "SELECT id FROM profile_change_requests WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
    (recipient["user_id"],),
)
# approve as admin
os.environ["QM_ADMIN_PRIVATE_IDS"] = sender["private_code"]
res = client.post(f"/api/admin/profile-changes/{req_row['id']}/decide", json={"approve": True})
check("admin approval of recipient's move succeeded", res.status_code == 200)

old_addr_row = raw(
    "SELECT full_address, forward_until FROM qmail_addresses WHERE user_id = ? AND is_current = 0 ORDER BY id DESC LIMIT 1",
    (recipient["user_id"],),
)
new_addr_row = raw(
    "SELECT full_address FROM qmail_addresses WHERE user_id = ? AND is_current = 1 ORDER BY id DESC LIMIT 1",
    (recipient["user_id"],),
)
check("old qmail_addresses row exists, is_current=0, forward_until set", old_addr_row is not None and old_addr_row["forward_until"])
check("new qmail_addresses row exists, is_current=1", new_addr_row is not None)
check("new current address differs from the old one", new_addr_row["full_address"] != old_addr_row["full_address"])

res = client.post("/api/qmail/compose", json={"to": old_addr_row["full_address"], "subject": "Hi again", "body": "Test body 2"})
check("compose to OLD address INSIDE the 30-day window delivered", res.status_code == 201)
row = raw(
    "SELECT COUNT(*) AS n FROM qmail_messages WHERE to_user_id = ? AND body = 'Test body 2'",
    (recipient["user_id"],),
)
check("that message resolved to the recipient's real user_id, not lost", row["n"] == 1)

# Boundary test: just inside the window.
just_inside = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2)).isoformat(timespec="seconds")
raw_exec("UPDATE qmail_addresses SET forward_until = ? WHERE full_address = ?", (just_inside, old_addr_row["full_address"]))
res = client.post("/api/qmail/compose", json={"to": old_addr_row["full_address"], "subject": "Boundary", "body": "just inside"})
check("compose to old address with forward_until 2s in the FUTURE: delivered (just inside)", res.status_code == 201)

# Boundary test: just outside the window.
just_outside = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=2)).isoformat(timespec="seconds")
raw_exec("UPDATE qmail_addresses SET forward_until = ? WHERE full_address = ?", (just_outside, old_addr_row["full_address"]))
res = client.post("/api/qmail/compose", json={"to": old_addr_row["full_address"], "subject": "Boundary", "body": "just outside"})
check("compose to old address with forward_until 2s in the PAST: rejected cleanly (just outside)", res.status_code == 404)

# Fully expired (original 30-day-ago style check too).
far_past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=5)).isoformat(timespec="seconds")
raw_exec("UPDATE qmail_addresses SET forward_until = ? WHERE full_address = ?", (far_past, old_addr_row["full_address"]))
res = client.post("/api/qmail/compose", json={"to": old_addr_row["full_address"], "subject": "Boundary", "body": "long expired"})
check("compose to an address expired 5 days ago: rejected cleanly", res.status_code == 404)

print()
print("=" * 70)
print("Section 4: /api/qmail/status reflects the banner condition")
print("=" * 70)

# Re-set forward_until back inside the window so the banner condition is live for this check.
live_window = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(timespec="seconds")
raw_exec("UPDATE qmail_addresses SET forward_until = ? WHERE full_address = ?", (live_window, old_addr_row["full_address"]))
login(recipient["private_code"])
res = client.get("/api/qmail/status")
status_body = res.get_json()
check("status route succeeds for the moved recipient", res.status_code == 200)
check("status shows activated=True", status_body.get("activated") is True)
check("status's 'changed' is populated (the banner condition)", status_body.get("changed") is not None)
check("status's current address matches the new current row", status_body.get("address") == new_addr_row["full_address"])

print()
print("=" * 70)
print("Section 5: smart 'To' field -- connected vs unconnected")
print("=" * 70)

asker = register("Asker", ROHINI)
login(asker["private_code"])
activate("askeraccount")

friend = register("Friend", ROHINI)
login(friend["private_code"])
friend_addr = activate("friendlyuser1").get_json()["address"]

stranger = register("Stranger", ROHINI)
login(stranger["private_code"])
activate("strangerperson")

# Wire up an approved Personal Group connection between asker and friend, directly (test setup,
# not what's under test -- mirrors how tests/test_post_kinds.py sets up state directly).
now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
conn = dbmod.get_db()
cur = conn.execute(
    "INSERT INTO personal_groups (owner_user_id, category, name, created_at) VALUES (?, 'friends', 'Test Friends', ?)",
    (asker["user_id"], now_iso),
)
group_id = cur.lastrowid
conn.execute(
    "INSERT INTO personal_group_members (group_id, user_id, status, invited_by, created_at) VALUES (?, ?, 'approved', ?, ?)",
    (group_id, friend["user_id"], asker["user_id"], now_iso),
)
conn.commit()
conn.close()

login(asker["private_code"])
res = client.get("/api/qmail/resolve-username?q=friendly")
matches = res.get_json()["matches"]
check("connected user (friend) appears in resolve-username", any(m["full_address"] == friend_addr for m in matches))

res = client.get("/api/qmail/resolve-username?q=stranger")
matches = res.get_json()["matches"]
check("unconnected user (stranger) does NOT appear in resolve-username", len(matches) == 0)

print()
print("=" * 70)
print("Section 6: resolve-public-id -- activated vs not")
print("=" * 70)

activated_member = register("Activated", ROHINI)
login(activated_member["private_code"])
activate("imactivated1")
activated_code = raw("SELECT search_code FROM account_ids WHERE user_id = ? AND is_current = 1", (activated_member["user_id"],))["search_code"]

not_activated_member = register("NotActivated", ROHINI)
not_activated_code = raw("SELECT search_code FROM account_ids WHERE user_id = ? AND is_current = 1", (not_activated_member["user_id"],))["search_code"]

login(asker["private_code"])
res = client.get(f"/api/qmail/resolve-public-id?code={activated_code}")
body = res.get_json()
check("resolve-public-id for an ACTIVATED member returns an address", res.status_code == 200 and body.get("activated") is True and body.get("address"))

res = client.get(f"/api/qmail/resolve-public-id?code={not_activated_code}")
body = res.get_json()
check("resolve-public-id for a NON-activated member: clean message, not 404", res.status_code == 200 and body.get("activated") is False)
check("that response has no address field claiming to be real", not body.get("address"))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
