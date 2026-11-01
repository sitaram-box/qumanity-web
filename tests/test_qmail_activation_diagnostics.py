"""Covers the two QMail activation negative scenarios tests/test_qmail.py didn't already have
(2026-11-01, see docs/production/email_qmail_diagnostic_audit.md): an unauthenticated activation
attempt, and the SAME user calling activate twice (as opposed to test_qmail.py's Section 2, which
covers a DIFFERENT user trying someone else's already-taken username). Also confirms the new
diagnostic print() lines from qmail_core.activate()/app.py's api_qmail_activate() actually appear,
in the right order, for one real activation run through the Flask test client.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure -- same conventions
as tests/test_qmail.py.

Run with: python3 tests/test_qmail_activation_diagnostics.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH

import app as appmod  # noqa: E402

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

_n = [0]


def register():
    _n[0] += 1
    payload = {
        "name": f"DiagTester {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": ROHINI["continent"], "country": ROHINI["country"]},
        "present_location": ROHINI, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code):
    res = client.post("/login", json={"private_id": private_code, "pin": "12345"})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


print("=" * 70)
print("Section 1: unauthenticated activation attempt")
print("=" * 70)

with client.session_transaction() as sess:
    sess.clear()
res = client.post("/api/qmail/activate", json={"username": "shouldnotwork1"})
check("unauthenticated POST /api/qmail/activate does not succeed (no 201)", res.status_code != 201)
check("...specifically a redirect (login_required), not a server error", res.status_code in (301, 302))

print()
print("=" * 70)
print("Section 2: the SAME user activating twice")
print("=" * 70)

u = register()
login(u["private_code"])
res1 = client.post("/api/qmail/activate", json={"username": "firstattempt1"})
check("first activation by this user succeeds (201)", res1.status_code == 201)

res2 = client.post("/api/qmail/activate", json={"username": "secondattempt"})
check("a second activation attempt by the SAME user is rejected (400, not 201)", res2.status_code == 400)
check("the rejection message says already activated", "already activated" in (res2.get_json() or {}).get("error", "").lower())

conn = appmod.get_db()
row = conn.execute("SELECT qmail_username FROM users WHERE id = ?", (u["user_id"],)).fetchone()
check("the ORIGINAL username from the first attempt is still what's stored (not overwritten)", row["qmail_username"] == "firstattempt1")
count_row = conn.execute("SELECT COUNT(*) AS n FROM qmail_addresses WHERE user_id = ?", (u["user_id"],)).fetchone()
check("the rejected second attempt left no second qmail_addresses row behind", count_row["n"] == 1)
conn.close()

print()
print("=" * 70)
print("Section 3: diagnostic log lines appear, in order, for a real activation")
print("=" * 70)

u2 = register()
login(u2["private_code"])

buf = io.StringIO()
old_stdout = sys.stdout
sys.stdout = buf
try:
    res3 = client.post("/api/qmail/activate", json={"username": "logcheckuser"})
finally:
    sys.stdout = old_stdout
lines = buf.getvalue().splitlines()

check("activation itself still succeeds while logging is active", res3.status_code == 201)

EXPECTED_EVENTS = [
    "QMAIL_ACTIVATION_REQUEST_RECEIVED",
    "QMAIL_ACTIVATION_FUNCTION_ENTERED",
    "QMAIL_ADDRESS_GENERATION_STARTED",
    "QMAIL_ADDRESS_GENERATION_COMPLETED",
    "QMAIL_ADDRESS_INSERT_ATTEMPT",
    "QMAIL_DATABASE_COMMIT_SUCCESS",
    "QMAIL_ACTIVATION_COMPLETED",
]
seen_positions = []
for event in EXPECTED_EVENTS:
    matches = [i for i, l in enumerate(lines) if event in l]
    check(f"log contains {event}", len(matches) == 1)
    if matches:
        seen_positions.append(matches[0])
check("all seven events appear in the documented stage order", seen_positions == sorted(seen_positions))
check("the activated user_id appears in these log lines, not a Private ID or PIN",
      all(str(u2["user_id"]) in l for l in lines if any(ev in l for ev in EXPECTED_EVENTS)))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
