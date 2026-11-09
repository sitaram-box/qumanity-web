"""Phone-app bearer-token authentication (app.py _app_token_auth()), including the 2026-11-09
retired-account fix.

The phone app (Desktop/Qumanity_App) signs every request with "Authorization: Bearer <token>"
instead of a browser cookie. _app_token_auth() runs before every request and, for a good token,
signs the request in as that member. Since 2026-10-28 a retired account (users.is_removed = 1)
can't sign in (/login filters is_removed = 0), but until 2026-11-09 a token issued BEFORE the
account was retired kept working until it expired (30 days): /api/me answered 200 and board posts
were created. Found by the phone app's contract checker (Qumanity_App/tools/website-check).

Covers: an active account's token works; the same token is refused (401, same generic message as
any bad token) once the account is retired, on /api/me, a board post and a profile write, with
nothing written; and the existing rejections still hold (malformed, tampered, expired, unknown
user, old token after a PIN change).

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes (same convention as tests/test_global_account.py),
PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_app_token_auth.py (not -I)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from unittest import mock

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


# No cookie jar: like the phone app's API calls, only the bearer token can sign a request in, so a
# leftover browser session from registration can never make a check pass by accident.
client = appmod.app.test_client(use_cookies=False)

INDIA_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
GENERIC_401 = {"error": "Please sign in again"}

_n = [0]


def register_app(name_prefix, pin="12345"):
    """Registers through the real route exactly as the app does (client=app) and returns the body."""
    _n[0] += 1
    res = client.post("/api/auth/register", json={
        "name": f"{name_prefix} {_n[0]}", "gender": "female", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": pin,
        "birth_location": INDIA_LOC, "present_location": INDIA_LOC, "assisted": False, "client": "app",
    })
    if res.status_code != 201 or not (res.get_json() or {}).get("token"):
        sys.exit(f"REGISTER FAILED for {name_prefix}: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def post_count(user_id):
    conn = dbmod.get_db()
    n = conn.execute("SELECT COUNT(*) FROM board_posts WHERE author_id = ?", (user_id,)).fetchone()[0]
    conn.close()
    return n


def daily_language(user_id):
    conn = dbmod.get_db()
    v = conn.execute("SELECT daily_language FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    conn.close()
    return v


def set_removed(user_id, value):
    conn = dbmod.get_db()
    conn.execute("UPDATE users SET is_removed = ? WHERE id = ?", (value, user_id))
    conn.commit()
    conn.close()


print("=" * 70)
print("1. Active account: its app token signs requests in")
print("=" * 70)
active = register_app("Active Member")
r = client.get("/api/me", headers=bearer(active["token"]))
check("active account, valid token: /api/me -> 200", r.status_code == 200)
check("...and it is that member's own profile", (r.get_json() or {}).get("name") == "Active Member 1")
r = client.post("/api/board/post", headers=bearer(active["token"]), json={"level": "village", "content": "Active member's post"})
check("active account, valid token: village board post -> 201", r.status_code == 201)
check("...and the post row exists", post_count(active["user_id"]) == 1)
r = client.post("/api/user/languages", headers=bearer(active["token"]), json={"daily": "Hindi"})
check("active account, valid token: POST /api/user/languages {daily: Hindi} -> 200 and saved",
      r.status_code == 200 and daily_language(active["user_id"]) == "Hindi")
r = client.get("/api/me")
check("no token and no cookie: /api/me is not served (existing login_required redirect)", r.status_code in (302, 401))

print()
print("=" * 70)
print("2. Retired account: the token it was issued BEFORE retirement is refused")
print("=" * 70)
retired = register_app("Retired Member")
rid, rtok = retired["user_id"], retired["token"]
r = client.get("/api/me", headers=bearer(rtok))
check("before retirement the token works (/api/me -> 200)", r.status_code == 200)
r = client.post("/api/board/post", headers=bearer(rtok), json={"level": "village", "content": "Posted before retirement"})
check("before retirement a village post works (201)", r.status_code == 201)
lang_before = daily_language(rid)
posts_before = post_count(rid)

set_removed(rid, 1)

r = client.get("/api/me", headers=bearer(rtok))
check("retired account, same token: /api/me -> 401", r.status_code == 401)
check("...with the same generic message as any bad token (no hint the account exists or was retired)",
      r.get_json() == GENERIC_401)
r = client.post("/api/board/post", headers=bearer(rtok), json={"level": "village", "content": "Posted AFTER retirement"})
check("retired account, same token: village board post -> 401", r.status_code == 401)
check("...and no board post was created", post_count(rid) == posts_before)
r = client.post("/api/user/languages", headers=bearer(rtok), json={"daily": "Hindi"})
check("retired account, same token: POST /api/user/languages (profile write) -> 401", r.status_code == 401)
check("...and the profile was not changed (the same write an active member just made)", lang_before is None and daily_language(rid) is None)
r = client.get("/api/notifications/summary", headers=bearer(rtok))
check("retired account, same token: GET /api/notifications/summary -> 401", r.status_code == 401)
r = client.post("/login", json={"private_id": retired["private_code"], "pin": "12345", "client": "app"})
check("retired account cannot get a new token through /login either (existing 401)", r.status_code == 401 and not (r.get_json() or {}).get("token"))
r = client.get("/api/me", headers=bearer(active["token"]))
check("another member's active token is unaffected (/api/me -> 200)", r.status_code == 200)

print()
print("=" * 70)
print("3. Existing rejections still hold")
print("=" * 70)
r = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
check("malformed token -> 401 with the generic message", r.status_code == 401 and r.get_json() == GENERIC_401)
tampered = active["token"][:-2] + ("AA" if not active["token"].endswith("AA") else "BB")
r = client.get("/api/me", headers=bearer(tampered))
check("tampered signature -> 401", r.status_code == 401)

conn = dbmod.get_db()
active_pin_hash = conn.execute("SELECT pin_hash FROM users WHERE id = ?", (active["user_id"],)).fetchone()["pin_hash"]
conn.close()
# A token signed 31 days ago (APP_TOKEN_DAYS = 30): itsdangerous stamps tokens with time.time().
with mock.patch("itsdangerous.timed.time.time", return_value=time.time() - (appmod.APP_TOKEN_DAYS + 1) * 86400):
    expired = appmod._issue_app_token(active["user_id"], active_pin_hash)
r = client.get("/api/me", headers=bearer(expired))
check("expired token (31 days old) for an ACTIVE account -> 401", r.status_code == 401 and r.get_json() == GENERIC_401)
fresh = appmod._issue_app_token(active["user_id"], active_pin_hash)
check("control: a freshly issued token for the same account -> 200",
      client.get("/api/me", headers=bearer(fresh)).status_code == 200)

ghost = appmod._issue_app_token(999999, "x" * 40)
r = client.get("/api/me", headers=bearer(ghost))
check("validly signed token for a user id that doesn't exist -> 401", r.status_code == 401)

pin_user = register_app("Pin Change Member")
old_tok = pin_user["token"]
r = client.post("/api/user/pin", headers=bearer(old_tok), json={"current_pin": "12345", "new_pin": "Ab#12", "client": "app"})
new_tok = (r.get_json() or {}).get("token")
check("PIN change through the app returns a new token", r.status_code == 200 and new_tok)
check("old token after the PIN change -> 401 (unchanged behaviour)", client.get("/api/me", headers=bearer(old_tok)).status_code == 401)
check("new token after the PIN change -> 200", client.get("/api/me", headers=bearer(new_tok)).status_code == 200)

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
