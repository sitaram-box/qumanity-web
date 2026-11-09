"""Browser-session authentication for retired accounts (2026-11-09 fix, app.py
_retired_session_guard()).

A retired account (users.is_removed = 1) can't sign in (/login filters is_removed = 0,
2026-10-28), and since 2026-11-09 its phone-app tokens are refused (_app_token_auth(), see
tests/test_app_token_auth.py). But a browser session signed in BEFORE retirement kept working:
login_required only checks that session["user_id"] is set, and several routes read
session["user_id"] without login_required at all -- notably assisted registration, which takes
the signed-in session as the new member's helper/referrer. Flask's session is a signed cookie
held by the browser, so it can't be revoked server-side; the account has to be re-checked on
every request.

Covers: (A) an active browser session is unchanged; (B) a retired account's existing session is
refused on /api/me, a board post (nothing written), another protected page and assisted
registration (not credited as helper), and stays refused on later requests and when the
pre-retirement cookie is replayed; (C) the session cookie left behind by a bearer-token request
can't be used instead of the refused token; (D) other members, logout and missing/forged
sessions behave as before.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes (same convention as tests/test_global_account.py),
PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_browser_session_auth.py (not -I)
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

# Registration verifies a real Village against india_villages; every throwaway DB starts with
# that table empty (same seed as tests/test_global_account.py).
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


INDIA_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def payload(name_prefix, **extra):
    _n[0] += 1
    body = {
        "name": f"{name_prefix} {_n[0]}", "gender": "female", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": INDIA_LOC, "present_location": INDIA_LOC, "assisted": False,
    }
    body.update(extra)
    return body


def create_member(name_prefix):
    """A real account through the real route; returns its body (private_code, user_id). Uses a
    throwaway client so the browser under test only gets its session from /login."""
    res = appmod.app.test_client().post("/api/auth/register", json=payload(name_prefix))
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED for {name_prefix}: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def browser_login(member):
    """A browser (cookie-keeping client) signed in through the normal /login form post."""
    b = appmod.app.test_client()
    res = b.post("/login", json={"private_id": member["private_code"], "pin": "12345"})
    if res.status_code != 200 or b.get_cookie("session") is None:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:300]}")
    return b


def to_login(res):
    """login_required's existing unauthenticated answer: a redirect to /login."""
    return res.status_code == 302 and "/login" in (res.headers.get("Location") or "")


def db_one(sql, args=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, args).fetchone()
    conn.close()
    return row


def post_count(user_id):
    return db_one("SELECT COUNT(*) FROM board_posts WHERE author_id = ?", (user_id,))[0]


def set_removed(user_id, value):
    conn = dbmod.get_db()
    conn.execute("UPDATE users SET is_removed = ? WHERE id = ?", (value, user_id))
    conn.commit()
    conn.close()


def assisted_register(client, name_prefix):
    """Assisted registration with NO helper Private ID/PIN: the route falls back to the signed-in
    session as the helper. Returns (status, new user's referred_by_user_id or None)."""
    res = client.post("/api/auth/register", json=payload(name_prefix, assisted=True))
    body = res.get_json() or {}
    ref = None
    if body.get("user_id"):
        ref = db_one("SELECT referred_by_user_id FROM users WHERE id = ?", (body["user_id"],))[0]
    return res.status_code, ref


print("=" * 70)
print("A. Active browser session: unchanged")
print("=" * 70)
alice = create_member("Active Browser")
a_browser = browser_login(alice)
r = a_browser.get("/api/me")
check("active session: /api/me -> 200 with that member's profile", r.status_code == 200 and (r.get_json() or {}).get("name") == "Active Browser 1")
r = a_browser.post("/api/board/post", json={"level": "village", "content": "Active browser post"})
check("active session: village board post -> 201 and the row exists", r.status_code == 201 and post_count(alice["user_id"]) == 1)
check("active session: /dashboard -> 200", a_browser.get("/dashboard").status_code == 200)
status, ref = assisted_register(a_browser, "Helped By Active")
check("active session: assisted registration credits the signed-in member as helper (201)",
      status == 201 and ref == alice["user_id"])

print()
print("=" * 70)
print("B. Retired browser session: refused, and stays refused")
print("=" * 70)
bob = create_member("Retired Browser")
b_browser = browser_login(bob)
check("before retirement: /api/me -> 200", b_browser.get("/api/me").status_code == 200)
pre_retirement_cookie = b_browser.get_cookie("session").value
posts_before = post_count(bob["user_id"])

set_removed(bob["user_id"], 1)

r = b_browser.get("/api/me")
check("retired, same session: /api/me -> redirect to /login (login_required's existing answer)", to_login(r))
check("...and the response carries no profile data", (r.get_json(silent=True) or {}).get("name") is None)
r = b_browser.post("/api/board/post", json={"level": "village", "content": "Posted after retirement"})
check("retired, same session: village board post refused", to_login(r))
check("...and no board post was created", post_count(bob["user_id"]) == posts_before)
check("retired, same session: /dashboard -> redirect to /login", to_login(b_browser.get("/dashboard")))
check("retired, same session: /api/notifications/summary -> redirect to /login", to_login(b_browser.get("/api/notifications/summary")))
check("later request on the same browser: /api/me still refused", to_login(b_browser.get("/api/me")))
status, ref = assisted_register(b_browser, "Helped By Retired")
check("retired, same session: assisted registration (no login_required) does NOT credit the retired member",
      ref != bob["user_id"])
# With the retired session refused, that request was anonymous, so (existing registration
# behaviour) the browser is now signed in as the brand-new member -- never as the retired one.
r = b_browser.get("/api/me")
check("...afterwards the browser is the new member, not the retired account",
      r.status_code == 200 and (r.get_json() or {}).get("name", "").startswith("Helped By Retired"))

replay = appmod.app.test_client()
replay.set_cookie("session", pre_retirement_cookie)
check("replaying the pre-retirement session cookie: /api/me refused", to_login(replay.get("/api/me")))
r = replay.post("/api/board/post", json={"level": "village", "content": "Replayed cookie post"})
check("replaying the pre-retirement session cookie: board post refused, nothing written",
      to_login(r) and post_count(bob["user_id"]) == posts_before)
r = b_browser.post("/login", json={"private_id": bob["private_code"], "pin": "12345"})
check("the retired account still cannot sign in again (existing 401)", r.status_code == 401)

print()
print("=" * 70)
print("C. Session cookie left behind by a bearer-token request")
print("=" * 70)
carol = create_member("Token Then Cookie")
tok = appmod.app.test_client(use_cookies=False).post(
    "/login", json={"private_id": carol["private_code"], "pin": "12345", "client": "app"}).get_json()["token"]
c_client = appmod.app.test_client()  # keeps cookies, like a device's shared cookie store
r = c_client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
check("bearer request -> 200", r.status_code == 200)
check("...and the server left a session cookie behind", c_client.get_cookie("session") is not None)
r = c_client.get("/api/me")
check("control: before retirement that cookie alone signs in (so this test exercises a real path)", r.status_code == 200)
c_posts = post_count(carol["user_id"])

set_removed(carol["user_id"], 1)

r = c_client.get("/api/me", headers={"Authorization": f"Bearer {tok}"})
check("retired: old bearer token -> 401", r.status_code == 401)
check("retired: the left-behind cookie without the token -> /api/me refused", to_login(c_client.get("/api/me")))
r = c_client.post("/api/board/post", json={"level": "village", "content": "Cookie-only post"})
check("retired: the left-behind cookie -> board post refused, nothing written",
      to_login(r) and post_count(carol["user_id"]) == c_posts)
status, ref = assisted_register(c_client, "Helped By Leftover Cookie")
check("retired: the left-behind cookie is not credited as an assisted-registration helper", ref != carol["user_id"])

print()
print("=" * 70)
print("D. Controls")
print("=" * 70)
check("another member's active browser session is unaffected (/api/me -> 200)", a_browser.get("/api/me").status_code == 200)
r = a_browser.get("/logout")
check("logout: redirects to /login (unchanged)", to_login(r))
check("after logout: /api/me -> redirect to /login (unchanged)", to_login(a_browser.get("/api/me")))
a_again = browser_login(alice)
check("an active member can sign in again after logout (/api/me -> 200)", a_again.get("/api/me").status_code == 200)
check("no session at all: /api/me -> redirect to /login (unchanged)", to_login(appmod.app.test_client().get("/api/me")))
forged = appmod.app.test_client()
forged.set_cookie("session", "not-a-signed-session")
check("forged/unsigned session cookie: /api/me -> redirect to /login (unchanged)", to_login(forged.get("/api/me")))
check("public page with a retired session still loads (/about -> 200)", b_browser.get("/about").status_code == 200)

print()
print("=" * 70)
print("E. Retired account's saved browser cookie x every kind of Authorization header")
print("=" * 70)
# _retired_session_guard() skips requests whose header starts with "Bearer " -- safe only because
# _app_token_auth() runs first (registration order) with the SAME test and either answers 401
# (Flask then runs neither the guard nor the route) or replaces session["user_id"] with the
# token's own, verified-active user. This matrix proves no Authorization header lets a retired
# account's cookie through. Policy it pins down: a bearer header is the request's only credential
# (a good one wins over the cookie, a bad one is 401 whatever the cookie says); any other header
# is ignored and the cookie is checked by the guard.
from unittest import mock  # noqa: E402
import time as _time  # noqa: E402

dave = create_member("Matrix Retired")
erin = create_member("Matrix Active")
_app = appmod.app.test_client(use_cookies=False)
dave_tok = _app.post("/login", json={"private_id": dave["private_code"], "pin": "12345", "client": "app"}).get_json()["token"]
erin_tok = _app.post("/login", json={"private_id": erin["private_code"], "pin": "12345", "client": "app"}).get_json()["token"]
dave_hash = db_one("SELECT pin_hash FROM users WHERE id = ?", (dave["user_id"],))[0]
with mock.patch("itsdangerous.timed.time.time", return_value=_time.time() - (appmod.APP_TOKEN_DAYS + 1) * 86400):
    dave_expired = appmod._issue_app_token(dave["user_id"], dave_hash)
ghost_tok = appmod._issue_app_token(999999, "x" * 40)
dave_cookie = browser_login(dave).get_cookie("session").value

set_removed(dave["user_id"], 1)

HEADERS = [
    ("no Authorization header", None),
    ("retired account's own old valid token", f"Bearer {dave_tok}"),
    ("invalid token", "Bearer not-a-real-token"),
    ("malformed: 'Bearer ' with nothing after it", "Bearer "),
    ("malformed: bare 'Bearer' (no space)", "Bearer"),
    ("malformed: lowercase 'bearer <retired token>'", f"bearer {dave_tok}"),
    ("non-bearer scheme: 'Basic ...'", "Basic ZGF2ZToxMjM0NQ=="),
    ("expired token (retired account's, 31 days old)", f"Bearer {dave_expired}"),
    ("validly signed token for an unknown user", f"Bearer {ghost_tok}"),
    ("valid token of ACTIVE account Erin", f"Bearer {erin_tok}"),
]
NAMES = {dave["user_id"]: "retired account", erin["user_id"]: "Erin (active)"}
rows = []
for label, header in HEADERS:
    def fresh():
        c = appmod.app.test_client()
        c.set_cookie("session", dave_cookie)  # the retired account's real pre-retirement cookie
        return c
    h = {"Authorization": header} if header is not None else {}
    d0, e0 = post_count(dave["user_id"]), post_count(erin["user_id"])

    me = fresh().get("/api/me", headers=h)
    me_who = (me.get_json(silent=True) or {}).get("name") if me.status_code == 200 else None
    wr = fresh().post("/api/board/post", headers=h, json={"level": "village", "content": f"matrix: {label}"})
    d1, e1 = post_count(dave["user_id"]), post_count(erin["user_id"])
    wr_who = "retired account" if d1 > d0 else ("Erin (active)" if e1 > e0 else "nobody")
    ar = fresh().post("/api/auth/register", headers=h, json=payload("Matrix Helped", assisted=True))
    new_id = (ar.get_json(silent=True) or {}).get("user_id")
    ref = db_one("SELECT referred_by_user_id FROM users WHERE id = ?", (new_id,))[0] if new_id else None
    ar_who = NAMES.get(ref, "nobody") if ref else "nobody"
    rows.append((label, me.status_code, me_who or "-", wr.status_code, wr_who, ar.status_code, ar_who))

    check(f"[{label}] /api/me is never served as the retired account", not (me_who or "").startswith("Matrix Retired"))
    check(f"[{label}] board post is never written as the retired account", d1 == d0)
    check(f"[{label}] assisted registration never credits the retired account", ref != dave["user_id"])
    if header is not None and header.startswith("Bearer ") and "Erin" not in label:
        check(f"[{label}] bad bearer token -> 401 on all three, nothing written",
              me.status_code == 401 and wr.status_code == 401 and ar.status_code == 401 and e1 == e0 and not new_id)
    elif "Erin" in label:
        check(f"[{label}] the token's own active account is used (/api/me = Erin, post by Erin, Erin credited)",
              me.status_code == 200 and (me_who or "").startswith("Matrix Active") and wr_who == "Erin (active)" and ar_who == "Erin (active)")
    else:
        check(f"[{label}] not a bearer token: the cookie is checked and refused (/api/me and post -> redirect to /login)",
              to_login(me) and to_login(wr))

f_active = create_member("Matrix Control")
fb = browser_login(f_active)
r = fb.get("/api/me")
check("control: an active account's browser session without any header -> 200 as that member",
      r.status_code == 200 and (r.get_json() or {}).get("name", "").startswith("Matrix Control"))

print()
print(f"  {'Authorization header (cookie = retired account)':50} | /api/me      | board post        | assisted registration")
for label, ms, mw, ws, ww, as_, aw in rows:
    print(f"  {label:50} | {ms} {mw[:9]:9} | {ws} by {ww[:12]:12} | {as_} credits {aw}")

print()
print("=" * 70)
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s)")
    for f in FAILS:
        print(f"  - {f}")
    try:
        os.remove(_DB_PATH)
    except OSError:
        pass
    sys.exit(1)
print("ALL PASSED")
try:
    os.remove(_DB_PATH)
except OSError:
    pass
