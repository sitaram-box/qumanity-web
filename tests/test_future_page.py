"""Covers the /future route (2026-11-08): the Qumanity 3D Future Vision Experience page itself --
that it's public, makes no database write just by being viewed, references its own real static
assets, and renders the correct final-scene CTA for an anonymous visitor vs. a signed-in member.

This file does not exercise static/js/future.js's own Three.js/GSAP runtime behavior (scene
choreography, WebGL fallback, reduced-motion handling) -- that is only meaningfully testable in a
real browser and was verified separately. It tests everything the Flask route itself controls.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, same conventions as every other test file in this project
(see tests/test_qmap.py for the closest sibling).

Run with: python3 tests/test_future_page.py (not -I)
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

# 2026-11-08 (Phase 1 corrective task): registration now verifies a real (non-provisional)
# Village against india_villages, the same way profile-change already does -- every throwaway
# test DB starts with that table empty, so any test registering a real village through the real
# /api/auth/register route must seed its row here first (same pattern as
# tests/test_global_account.py's section 16/18).
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

VILLAGE_LOC = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}


def register_and_login():
    payload = {
        "name": "Future Tester", "gender": "female", "dob": "1992-03-10", "tob": "09:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_LOC, "present_location": VILLAGE_LOC, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:300]}")
    body = res.get_json()
    login_res = client.post("/login", json={"private_id": body["private_code"], "pin": "12345"})
    if login_res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {login_res.status_code} {login_res.get_data(as_text=True)[:300]}")


def table_count(table):
    conn = dbmod.get_db()
    try:
        return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    finally:
        conn.close()


print("=" * 70)
print("1. Anonymous visitor")
print("=" * 70)
client.get("/logout")
users_before = table_count("users")
res = client.get("/future")
check("GET /future returns 200 for an anonymous visitor (no login required)", res.status_code == 200)
html = res.get_data(as_text=True)
check("does not require authentication (no redirect to /login)", res.status_code != 302)
check("merely viewing the page creates no new user row", table_count("users") == users_before)
check("the world is fragmented. (Scene 1 text) is present", "The world is fragmented." in html)
check("there is a thread that connects us all. (Scene 2 text) is present", "there is a thread that connects us all." in html)
check("imagine 2126. no borders. every voice is heard. (Scene 3 text) is present", "Imagine 2126. No borders. Every voice is heard." in html)
check("you are the architect. register to begin. (Scene 4 text) is present", "You are the architect. Register to begin." in html)
check("the Skip control is present", "Skip — Go to Login" in html)
check("an anonymous visitor sees the Register to Begin CTA", "Register to Begin" in html)
check("an anonymous visitor does NOT see the authenticated-only Dashboard CTA", "Enter Your Dashboard" not in html)
check("references its own future.css", "css/future.css" in html)
check("references its own future.js", "js/future.js" in html)
check("references GSAP from the pinned CDN version", "gsap@3.12.5" in html)
check("does not load Three.js in the page itself (future.js lazy-loads it)",
      '<script src="https://unpkg.com/three@' not in html)
check("the Skip link points at the real /login route", 'href="/login"' in html or "QMF_LOGIN_URL" in html)
check("the Register CTA points at the real /register route", '/register' in html)
check("references the real, existing earth_texture.png asset (not a new/invented texture)",
      "images/earth_texture.png" in html)
check("no Marquee reference reappears on this new page", "_poems_marquee" not in html and "marquee" not in html.lower())
check("no religion-specific identity symbol reappears on this new page", "qm-identity-symbol" not in html)

print()
print("=" * 70)
print("2. Signed-in member")
print("=" * 70)
register_and_login()
res2 = client.get("/future")
check("GET /future returns 200 for a signed-in member too", res2.status_code == 200)
html2 = res2.get_data(as_text=True)
check("a signed-in member sees the Enter Your Dashboard CTA instead", "Enter Your Dashboard" in html2)
check("a signed-in member does NOT see the Register to Begin CTA", "Register to Begin" not in html2)
check("the Dashboard CTA points at the real /dashboard route", "/dashboard" in html2)
client.get("/logout")

print()
print("=" * 70)
print("3. No new routes beyond the one page route")
print("=" * 70)
check("POST to /future is not a defined method (GET-only page route)",
      client.post("/future").status_code == 405)
check("the static assets referenced actually exist on disk and are served",
      client.get("/static/css/future.css").status_code == 200
      and client.get("/static/js/future.js").status_code == 200)

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks PASSED.")
