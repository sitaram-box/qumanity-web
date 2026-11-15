"""Verifies the Q-Card system's Stage 2 pieces (2026-11-15): q_card_core.issue_card()/
resolve_token(), the public GET /api/card/<token> resolve route, and the public
POST /api/card-login route -- which reuses app.py's verify_user_pin_and_login() (Stage 1)
unchanged for the actual PIN check, lockout, and sign-in.

Covers: a genuinely active card logging in with the correct PIN; a wrong PIN hitting the exact
same lockout behavior /login itself has (no second, divergent implementation); a revoked,
replaced, pending_payment, or malformed/random token all producing the IDENTICAL generic refusal
(enumeration-safety, measured, not just asserted); and that the two existing login-guard suites
are untouched by any of this.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure -- same conventions
as every other test file in this repo.

Run with: python3 tests/test_q_cards.py
"""
from __future__ import annotations

import os
import statistics
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
import q_card_core  # noqa: E402

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
ROHINI = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
_n = [0]


def register(name):
    _n[0] += 1
    payload = {
        "name": f"{name} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": ROHINI["continent"], "country": ROHINI["country"]},
        "present_location": ROHINI, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def logout():
    with client.session_transaction() as sess:
        sess.clear()


print("=" * 70)
print("issue_card() / resolve_token() -- the core primitives")
print("=" * 70)

alice = register("Alice CardHolder")
conn = dbmod.get_db()
q_card_core.ensure_tables(conn)
issued = q_card_core.issue_card(conn, alice["user_id"])
conn.commit()
conn.close()
check("issue_card() returns a card_display_id in the QC-###### shape", issued["card_display_id"].startswith("QC-") and issued["card_display_id"][3:].isdigit())
check("issue_card() returns a raw_token, shown once", bool(issued["raw_token"]))

conn = dbmod.get_db()
stored = conn.execute("SELECT token_hash, status, payment_status FROM q_cards WHERE card_display_id = ?", (issued["card_display_id"],)).fetchone()
conn.close()
check("the raw token is NEVER stored -- only its hash is", issued["raw_token"] != stored["token_hash"] and stored["token_hash"] == q_card_core._hash(issued["raw_token"]))
check("a non-free card starts 'pending_payment'/'unpaid', not active", stored["status"] == "pending_payment" and stored["payment_status"] == "unpaid")

conn = dbmod.get_db()
check("resolve_token() correctly refuses a PENDING_PAYMENT card (not yet active)", q_card_core.resolve_token(conn, issued["raw_token"]) is None)
conn.close()

alice_free = register("Alice Free")
conn = dbmod.get_db()
free_issued = q_card_core.issue_card(conn, alice_free["user_id"], free_reason="family")
conn.commit()
stored_free = conn.execute("SELECT status, payment_status, payment_method, free_reason FROM q_cards WHERE card_display_id = ?", (free_issued["card_display_id"],)).fetchone()
check("a free-issued card (free_reason given) starts 'active'/'free' immediately, no payment gate",
      stored_free["status"] == "active" and stored_free["payment_status"] == "free" and stored_free["payment_method"] == "free" and stored_free["free_reason"] == "family")
resolved = q_card_core.resolve_token(conn, free_issued["raw_token"])
check("resolve_token() succeeds for a genuinely active card, returning card_id/user_id/name",
      resolved is not None and resolved["user_id"] == alice_free["user_id"])
conn.close()

print()
print("=" * 70)
print("GET /api/card/<token> -- the resolve route")
print("=" * 70)

bob = register("Bob Scanner")
conn = dbmod.get_db()
bob_card = q_card_core.issue_card(conn, bob["user_id"], free_reason="admin")
conn.commit()
conn.close()

conn = dbmod.get_db()
bob_full_name = conn.execute("SELECT name FROM users WHERE id = ?", (bob["user_id"],)).fetchone()["name"]
conn.close()
res = client.get(f"/api/card/{bob_card['raw_token']}")
check("a genuinely active card's token resolves (200, ok=True)", res.status_code == 200 and res.get_json()["ok"] is True)
check("...and returns ONLY the first name, never the full name or any account identifier",
      res.get_json()["first_name"] == bob_full_name.split()[0] and "last_name" not in res.get_json() and "user_id" not in res.get_json() and "private_id" not in res.get_json())

print()
print("=" * 70)
print("POST /api/card-login -- active token, correct PIN -> login")
print("=" * 70)

res = client.post("/api/card-login", json={"token": bob_card["raw_token"], "pin": "12345"})
check("card-login with the correct PIN succeeds (200, status=success)", res.status_code == 200 and res.get_json().get("status") == "success")
res2 = client.get("/api/me")
check("the session is genuinely signed in as bob after card-login", res2.status_code == 200 and res2.get_json().get("name", "").startswith("Bob Scanner"))
logout()

print()
print("=" * 70)
print("POST /api/card-login -- active token, WRONG PIN -> the SAME lockout behavior as /login")
print("=" * 70)

carol = register("Carol Lockout")
conn = dbmod.get_db()
carol_card = q_card_core.issue_card(conn, carol["user_id"], free_reason="admin")
conn.commit()
conn.close()

results = []
for i in range(5):
    res = client.post("/api/card-login", json={"token": carol_card["raw_token"], "pin": "00000"})
    results.append((res.status_code, res.get_json()))
check("the first 5 wrong-PIN attempts all report the standard 'Invalid Private ID or PIN' 401 (same message /login itself uses -- no card-specific wording)",
      all(sc == 401 and body == {"error": "Invalid Private ID or PIN"} for sc, body in results))
res = client.post("/api/card-login", json={"token": carol_card["raw_token"], "pin": "00000"})
check("the 6th attempt is locked out (429), same threshold/message /login's own lockout uses",
      res.status_code == 429 and res.get_json() == {"error": "Too many wrong PINs. Try again in a few minutes."})
res = client.post("/api/card-login", json={"token": carol_card["raw_token"], "pin": "12345"})
check("...and the lockout blocks even the CORRECT PIN while active, exactly like /login's own lockout", res.status_code == 429)
logout()

print()
print("=" * 70)
print("Enumeration safety: revoked / replaced / pending_payment / malformed all refuse IDENTICALLY")
print("=" * 70)

dave = register("Dave Cases")
conn = dbmod.get_db()
dave_card = q_card_core.issue_card(conn, dave["user_id"], free_reason="admin")
dave_card_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (dave_card["card_display_id"],)).fetchone()["id"]
conn.execute("UPDATE q_cards SET status = 'revoked', revoked_at = ? WHERE id = ?", (q_card_core._now_iso(), dave_card_id))
conn.commit()
conn.close()

erin = register("Erin Cases")
conn = dbmod.get_db()
erin_old_card = q_card_core.issue_card(conn, erin["user_id"], free_reason="admin")
erin_old_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (erin_old_card["card_display_id"],)).fetchone()["id"]
erin_new_card = q_card_core.issue_card(conn, erin["user_id"], free_reason="admin")
erin_new_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (erin_new_card["card_display_id"],)).fetchone()["id"]
conn.execute("UPDATE q_cards SET status = 'replaced', replaced_by_card_id = ? WHERE id = ?", (erin_new_id, erin_old_id))
conn.commit()
conn.close()

frank = register("Frank Cases")
conn = dbmod.get_db()
frank_card = q_card_core.issue_card(conn, frank["user_id"])  # no free_reason -- stays pending_payment
conn.commit()
conn.close()

cases = {
    "revoked": dave_card["raw_token"],
    "replaced (old token, refused outright -- NOT forwarded to the active replacement)": erin_old_card["raw_token"],
    "pending_payment (never paid or marked free)": frank_card["raw_token"],
    "malformed/random (never issued at all)": "not-a-real-token-" + "x" * 20,
}
for label, token in cases.items():
    res_resolve = client.get(f"/api/card/{token}")
    res_login = client.post("/api/card-login", json={"token": token, "pin": "12345"})
    check(f"resolve route refuses a {label} token with the identical generic response (200, ok=False)",
          res_resolve.status_code == 200 and res_resolve.get_json() == {"ok": False})
    check(f"card-login refuses a {label} token with the identical generic response, not a PIN-specific error",
          res_login.status_code == 200 and res_login.get_json() == {"ok": False})

# Empty token is only meaningful through the POST body (an empty URL path SEGMENT isn't routable
# at all -- Flask's <token> converter never matches a zero-length segment, so GET /api/card/
# would be a routing-level 404 before this view function even runs, not a comparable case).
res_login_empty = client.post("/api/card-login", json={"token": "", "pin": "12345"})
check("an empty token in the login body refuses with the identical generic response too",
      res_login_empty.status_code == 200 and res_login_empty.get_json() == {"ok": False})

check("replaced token truly does NOT grant access to the replacement card -- confirmed the NEW token still works on its own",
      q_card_core.resolve_token(dbmod.get_db(), erin_new_card["raw_token"]) is not None)

print()
print("=" * 70)
print("Timing: a revoked/replaced/pending/malformed token resolves in statistically indistinguishable time")
print("=" * 70)

def _timed_resolve(token):
    t0 = time.perf_counter()
    client.get(f"/api/card/{token}")
    return time.perf_counter() - t0

samples = {label: [] for label in cases}
for _ in range(60):
    for label, token in cases.items():
        samples[label].append(_timed_resolve(token))
means = {label: statistics.mean(v) for label, v in samples.items()}
pooled_stdev = statistics.pstdev([t for v in samples.values() for t in v]) or 1e-9
max_gap = max(means.values()) - min(means.values())
print(f"  [INFO] per-case means (ms): " + ", ".join(f"{label}={means[label]*1000:.3f}" for label in cases))
print(f"  [INFO] max gap between cases: {max_gap*1000:.4f}ms, pooled stdev: {pooled_stdev*1000:.4f}ms")
check("the timing gap between every refused-token case is well within normal jitter (under 3 pooled standard deviations), not a measurable side-channel",
      max_gap / pooled_stdev < 3)

print()
print("=" * 70)
print("Regression: the two login-guard suites are untouched")
print("=" * 70)

import subprocess
for guard_file, expected in (("tests/test_app_token_auth.py", 25), ("tests/test_browser_session_auth.py", 72)):
    out = subprocess.run([sys.executable, guard_file], capture_output=True, text=True, cwd=ROOT)
    passed = out.stdout.count("[PASS]")
    check(f"{guard_file} still passes at {expected}/{expected} (re-run as its own fresh process, not edited)",
          out.returncode == 0 and passed == expected)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
