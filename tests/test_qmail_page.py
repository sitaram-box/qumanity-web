"""Verifies the /qmail route itself (2026-10-18): it's login-gated like every other page route,
it sends an unactivated member back to the dashboard (where the activation UI actually lives)
rather than rendering a broken mailbox shell, and it renders successfully once Qmail is
activated. This is real route-behavior testing via the Flask test client -- not a browser test,
but genuinely regression-testable without one, unlike the DOM-rendering properties documented as
a known gap in docs/QMAIL.md and tests/test_qmail_format_extraction.py.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_qmail_page.py (not -I -- isolated mode hides this machine's Flask
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

import app as appmod  # noqa: E402

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


def register(name_prefix):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": VILLAGE["continent"], "country": VILLAGE["country"]},
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


print("=" * 70)
print("/qmail is login-gated, same as every other page route")
print("=" * 70)

res = client.get("/qmail", follow_redirects=False)
check("an anonymous request to /qmail redirects (not a 200, no session at all)",
      res.status_code in (301, 302))
check("the redirect target is the login page", "/login" in res.headers.get("Location", ""))

print()
print("=" * 70)
print("An unactivated member is sent back to the dashboard, not a broken mailbox shell")
print("=" * 70)

u1 = register("PageTester")
login(u1["private_code"])
res = client.get("/qmail", follow_redirects=False)
check("an activated-but-not-yet-Qmail member hitting /qmail redirects", res.status_code in (301, 302))
check("...specifically back to the dashboard, where #qm-qmail-card's activation UI lives",
      "/dashboard" in res.headers.get("Location", ""))

print()
print("=" * 70)
print("Once Qmail is activated, /qmail renders successfully")
print("=" * 70)

client.post("/api/qmail/activate", json={"username": "pagetester1"})
res = client.get("/qmail")
check("an activated member's /qmail request succeeds (200)", res.status_code == 200)
body = res.get_data(as_text=True)
check("the rendered page includes the member's own name in the header", "PageTester" in body)
check("the rendered page includes the three folder buttons (Inbox/Sent/Drafts)",
      'data-folder="inbox"' in body and 'data-folder="sent"' in body and 'data-folder="drafts"' in body)
check("the rendered page includes the compose overlay shell", "qmail-compose-overlay" in body)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL /qmail ROUTE TESTS PASSED")
