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

import datetime as dt
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
import election_core  # noqa: E402
import family_core  # noqa: E402
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


def register(name, gender="male"):
    _n[0] += 1
    payload = {
        "name": f"{name} {_n[0]}", "gender": gender, "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        # Birth location now stops at State (2026-11-19) for a Sub-continent country.
        "birth_location": {k: ROHINI[k] for k in ("continent", "country", "zone", "state")},
        "present_location": ROHINI, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def logout():
    with client.session_transaction() as sess:
        sess.clear()


def login(private_code):
    res = client.post("/login", json={"private_id": private_code, "pin": "12345"})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


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


def activate(payload):
    res = client.post("/api/family/activate", json=payload)
    if res.status_code != 201:
        sys.exit(f"ACTIVATE FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def marry(payload):
    res = client.post("/api/family/marry", json=payload)
    if res.status_code != 201:
        sys.exit(f"MARRY FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def approve_join(approver_private_code, requester_user_id):
    login(approver_private_code)
    res = client.get("/api/people/inbox")
    req = next(r for r in res.get_json()["requests"]
               if r["kind"] == "family_group_join" and r["from_user_id"] == requester_user_id)
    res2 = client.post(f"/api/people/inbox/{req['id']}/decide", json={"decision": "accept"})
    if res2.status_code != 200:
        sys.exit(f"APPROVE FAILED: {res2.status_code} {res2.get_data(as_text=True)[:300]}")


def self_node_id(user_id):
    return raw("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,))["id"]


def placeholder_node_id(display_name):
    return raw("SELECT id FROM family_nodes WHERE display_name = ? AND claimed_user_id IS NULL", (display_name,))["id"]


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
print("Stage 3 setup: the 8-member worked example (Pardeep+Neelam / Rohit+Sakshi / Mohit+Radha),")
print("built through the real Family Tree routes, plus a married-daughter and a cousin negative case")
print("=" * 70)

pardeep = register("Pardeep Sharma")
login(pardeep["private_code"])
activate({"father": {"name": "PP Father", "action": "create"}, "mother": {"name": "PP Mother", "action": "create"}, "relationship": "married"})
pardeep_marry = marry({"spouse": {"name": "Neelam Placeholder", "action": "create"}})
root_group_id = pardeep_marry["marital_group_id"]
pardeep_node = self_node_id(pardeep["user_id"])
neelam_slot = placeholder_node_id("Neelam Placeholder")

neelam = register("Neelam Real", gender="female")
login(neelam["private_code"])
activate({"father": {"name": "Neelam Father", "action": "create"}, "mother": {"name": "Neelam Mother", "action": "create"}, "relationship": "married"})
marry({"spouse": {"name": "Neelam Placeholder", "action": "join", "group_id": root_group_id, "matched_node_id": neelam_slot}})

rohit = register("Rohit Real")
login(rohit["private_code"])
activate({"father": {"name": "Pardeep Sharma", "action": "join", "group_id": root_group_id, "matched_node_id": pardeep_node},
          "mother": {"name": "Rohit Mother Placeholder", "action": "create"}, "relationship": "married"})
approve_join(pardeep["private_code"], rohit["user_id"])
login(rohit["private_code"])
rohit_node = self_node_id(rohit["user_id"])
rohit_marry = marry({"spouse": {"name": "Sakshi Placeholder", "action": "create"}})
rohit_marital_id = rohit_marry["marital_group_id"]
sakshi_slot = placeholder_node_id("Sakshi Placeholder")
check("Rohit+Sakshi's unit auto-links husband_parent_group_id to the root (Pardeep+Neelam) -- the Cascade",
      raw("SELECT husband_parent_group_id FROM family_groups WHERE id = ?", (rohit_marital_id,))["husband_parent_group_id"] == root_group_id)

sakshi = register("Sakshi Real", gender="female")
login(sakshi["private_code"])
activate({"father": {"name": "Sakshi Father", "action": "create"}, "mother": {"name": "Sakshi Mother", "action": "create"}, "relationship": "married"})
marry({"spouse": {"name": "Sakshi Placeholder", "action": "join", "group_id": rohit_marital_id, "matched_node_id": sakshi_slot}})

shivanya = register("Shivanya Real", gender="female")
login(shivanya["private_code"])
activate({"father": {"name": "Rohit Real", "action": "join", "group_id": rohit_marital_id, "matched_node_id": rohit_node},
          "mother": {"name": "Shivanya Mother Placeholder", "action": "create"}, "relationship": "single"})
approve_join(rohit["private_code"], shivanya["user_id"])

shivank = register("Shivank Real")
login(shivank["private_code"])
activate({"father": {"name": "Rohit Real", "action": "join", "group_id": rohit_marital_id, "matched_node_id": rohit_node},
          "mother": {"name": "Shivank Mother Placeholder", "action": "create"}, "relationship": "single"})
approve_join(rohit["private_code"], shivank["user_id"])

mohit = register("Mohit Real")
login(mohit["private_code"])
activate({"father": {"name": "Pardeep Sharma", "action": "join", "group_id": root_group_id, "matched_node_id": pardeep_node},
          "mother": {"name": "Mohit Mother Placeholder", "action": "create"}, "relationship": "married"})
approve_join(pardeep["private_code"], mohit["user_id"])
login(mohit["private_code"])
mohit_marry = marry({"spouse": {"name": "Radha Placeholder", "action": "create"}})
mohit_marital_id = mohit_marry["marital_group_id"]
radha_slot = placeholder_node_id("Radha Placeholder")

radha = register("Radha Real", gender="female")
login(radha["private_code"])
activate({"father": {"name": "Radha Father", "action": "create"}, "mother": {"name": "Radha Mother", "action": "create"}, "relationship": "married"})
marry({"spouse": {"name": "Radha Placeholder", "action": "join", "group_id": mohit_marital_id, "matched_node_id": radha_slot}})

check("recursive_member_count(root) == 8 -- the exact worked example, built through the real routes this time",
      family_core.recursive_member_count(dbmod.get_db(), root_group_id) == 8)

# Negative case A: Divya, Pardeep's DAUGHTER, who then MARRIES OUT -- a naive tree walk (anyone ever
# linked parent/child to root_group_id) would still find her; the cascade rules must not.
divya = register("Divya Real", gender="female")
login(divya["private_code"])
activate({"father": {"name": "Pardeep Sharma", "action": "join", "group_id": root_group_id, "matched_node_id": pardeep_node},
          "mother": {"name": "Divya Mother Placeholder", "action": "create"}, "relationship": "married"})
approve_join(pardeep["private_code"], divya["user_id"])
login(divya["private_code"])
divya_marry = marry({"spouse": {"name": "Divya Husband Placeholder", "action": "create"}})
divya_marital_id = divya_marry["marital_group_id"]
check("Divya's own married unit's wife_parent_group_id correctly points back to the root (she WAS his daughter)",
      raw("SELECT wife_parent_group_id FROM family_groups WHERE id = ?", (divya_marital_id,))["wife_parent_group_id"] == root_group_id)

# Negative case B: Carl, a cousin -- an entirely disconnected tree, never linked to Pardeep's at all.
carl = register("Cousin Carl")
login(carl["private_code"])
activate({"father": {"name": "Carl Father", "action": "create"}, "mother": {"name": "Carl Mother", "action": "create"}, "relationship": "single"})
logout()

print()
print("=" * 70)
print("Stage 3: family_core.recursive_member_node_ids() matches recursive_member_count() exactly")
print("=" * 70)

conn = dbmod.get_db()
for label, gid in (("root (Pardeep+Neelam)", root_group_id), ("Rohit+Sakshi", rohit_marital_id), ("Mohit+Radha", mohit_marital_id)):
    check(f"len(recursive_member_node_ids({label})) == recursive_member_count({label}) -- the two can never drift apart",
          len(family_core.recursive_member_node_ids(conn, gid)) == family_core.recursive_member_count(conn, gid))
conn.close()

print()
print("=" * 70)
print("Stage 3: free_eligibility() -- the 8-member worked example (admin/family), plus the two negative cases")
print("=" * 70)

os.environ["QM_ADMIN_PRIVATE_IDS"] = pardeep["private_code"]

conn = dbmod.get_db()
check("Pardeep (root founder) -- eligible as 'admin' (Rule 1 takes precedence over Rule 2)",
      q_card_core.free_eligibility(conn, pardeep["user_id"]) == "admin")
for label, person in (
    ("Neelam (spouse of the root)", neelam), ("Rohit (son)", rohit),
    ("Sakshi (Rohit's wife, in-law by marriage to a son)", sakshi),
    ("Shivanya (Rohit's unmarried daughter)", shivanya), ("Shivank (Rohit's unmarried son)", shivank),
    ("Mohit (son)", mohit), ("Radha (Mohit's wife, in-law by marriage to a son)", radha),
):
    check(f"{label} -- eligible as 'family'", q_card_core.free_eligibility(conn, person["user_id"]) == "family")
check("Divya (a MARRIED daughter who left on marriage) -- NOT eligible (None) -- proves the cascade rule, not a naive walk",
      q_card_core.free_eligibility(conn, divya["user_id"]) is None)
check("Carl (a cousin, entirely disconnected from the tree) -- NOT eligible (None)",
      q_card_core.free_eligibility(conn, carl["user_id"]) is None)
conn.close()

print()
print("=" * 70)
print("Stage 3: council eligibility -- a seated pilot-village council head, reusing announcements_core.is_council_member()")
print("=" * 70)

council_chair = register("Council Chair")
_today = dt.date.today()
raw_exec(
    "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, nomination_end, "
    "voting_start, voting_end, status) VALUES (9001, ?, 'Libra', 'Air', 2026, ?, ?, ?, ?, 'closed')",
    (election_core.PILOT_VILLAGE_ID, (_today - dt.timedelta(days=40)).isoformat(), (_today - dt.timedelta(days=35)).isoformat(),
     (_today - dt.timedelta(days=30)).isoformat(), (_today - dt.timedelta(days=20)).isoformat()),
)
raw_exec(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
    "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Libra', 2026, ?, NULL, 9001, ?, ?)",
    (election_core.PILOT_VILLAGE_ID, council_chair["user_id"], (_today - dt.timedelta(days=10)).isoformat(),
     (_today + dt.timedelta(days=355)).isoformat()),
)
conn = dbmod.get_db()
check("a seated pilot-village council chair -- eligible as 'council' (not Admin, not family)",
      q_card_core.free_eligibility(conn, council_chair["user_id"]) == "council")
conn.close()

print()
print("=" * 70)
print("Stage 3: admin actions -- mark_paid, mark_free (all three categories + refusal), mark_delivered, revoke, replace")
print("=" * 70)

conn = dbmod.get_db()
paid_card = q_card_core.issue_card(conn, carl["user_id"])
paid_card_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (paid_card["card_display_id"],)).fetchone()["id"]
conn.close()
conn = dbmod.get_db()
q_card_core.mark_paid(conn, paid_card_id, "upi_static", "UPI-REF-001")
conn.close()
row = raw("SELECT status, payment_status, payment_method, payment_reference FROM q_cards WHERE id = ?", (paid_card_id,))
check("mark_paid: pending_payment -> active, payment_status -> paid, method/reference recorded",
      row["status"] == "active" and row["payment_status"] == "paid" and row["payment_method"] == "upi_static"
      and row["payment_reference"] == "UPI-REF-001")

conn = dbmod.get_db()
try:
    q_card_core.mark_paid(conn, paid_card_id, "cash", None)
    check("mark_paid on an already-active card is refused (no transition out of 'active')", False)
except ValueError as e:
    check("mark_paid on an already-active card is refused (no transition out of 'active')", "pending_payment" in str(e))
conn.close()

conn = dbmod.get_db()
try:
    q_card_core.mark_paid(conn, paid_card_id, "bitcoin", None)
    check("mark_paid with an illegal payment method is refused", False)
except ValueError:
    check("mark_paid with an illegal payment method is refused", True)
conn.close()

for label, person, expected_reason in (
    ("Pardeep (admin)", pardeep, "admin"),
    ("Rohit (family)", rohit, "family"),
    ("Council Chair (council)", council_chair, "council"),
):
    conn = dbmod.get_db()
    card = q_card_core.issue_card(conn, person["user_id"])
    card_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (card["card_display_id"],)).fetchone()["id"]
    conn.close()
    conn = dbmod.get_db()
    reason = q_card_core.mark_free(conn, card_id)
    conn.close()
    row = raw("SELECT status, payment_status, free_reason FROM q_cards WHERE id = ?", (card_id,))
    check(f"mark_free on {label}: status -> active, free_reason == '{expected_reason}' (derived, never admin-supplied)",
          reason == expected_reason and row["status"] == "active" and row["payment_status"] == "free"
          and row["free_reason"] == expected_reason)

conn = dbmod.get_db()
non_eligible_card = q_card_core.issue_card(conn, divya["user_id"])
non_eligible_card_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (non_eligible_card["card_display_id"],)).fetchone()["id"]
conn.close()
conn = dbmod.get_db()
try:
    q_card_core.mark_free(conn, non_eligible_card_id)
    check("mark_free on a non-eligible user (Divya) is refused outright", False)
except ValueError:
    check("mark_free on a non-eligible user (Divya) is refused outright", True)
conn.close()
row = raw("SELECT status, free_reason FROM q_cards WHERE id = ?", (non_eligible_card_id,))
check("...and the card's status/free_reason are genuinely unchanged after the refusal",
      row["status"] == "pending_payment" and row["free_reason"] is None)

conn = dbmod.get_db()
q_card_core.mark_delivered(conn, paid_card_id)
conn.close()
row = raw("SELECT delivered_at FROM q_cards WHERE id = ?", (paid_card_id,))
check("mark_delivered writes delivered_at", bool(row["delivered_at"]))
_first_delivered_at = row["delivered_at"]
conn = dbmod.get_db()
q_card_core.mark_delivered(conn, paid_card_id)
conn.close()
row = raw("SELECT delivered_at FROM q_cards WHERE id = ?", (paid_card_id,))
check("mark_delivered on an already-delivered card is a no-op -- delivered_at unchanged", row["delivered_at"] == _first_delivered_at)

conn = dbmod.get_db()
q_card_core.revoke(conn, paid_card_id)
conn.close()
row = raw("SELECT status, revoked_at FROM q_cards WHERE id = ?", (paid_card_id,))
check("revoke: active -> revoked, revoked_at populated", row["status"] == "revoked" and bool(row["revoked_at"]))
_first_revoked_at = row["revoked_at"]
conn = dbmod.get_db()
q_card_core.revoke(conn, paid_card_id)
conn.close()
row = raw("SELECT status, revoked_at FROM q_cards WHERE id = ?", (paid_card_id,))
check("revoke on an already-revoked card is a no-op -- no second write to revoked_at", row["revoked_at"] == _first_revoked_at)

conn = dbmod.get_db()
replace_card = q_card_core.issue_card(conn, sakshi["user_id"])
replace_card_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (replace_card["card_display_id"],)).fetchone()["id"]
q_card_core.mark_paid(conn, replace_card_id, "cash", None)
conn.close()
conn = dbmod.get_db()
new_card = q_card_core.replace(conn, replace_card_id)
conn.close()
old_row = raw("SELECT status, revoked_at, replaced_by_card_id FROM q_cards WHERE id = ?", (replace_card_id,))
new_row_id = raw("SELECT id FROM q_cards WHERE card_display_id = ?", (new_card["card_display_id"],))["id"]
check("replace: the old row -> status='replaced', revoked_at populated, replaced_by_card_id points at the new row",
      old_row["status"] == "replaced" and bool(old_row["revoked_at"]) and old_row["replaced_by_card_id"] == new_row_id)
new_row = raw("SELECT status FROM q_cards WHERE id = ?", (new_row_id,))
check("...and the new row starts fresh at 'pending_payment' -- even though the old card was PAID, the replacement is NOT auto-granted",
      new_row["status"] == "pending_payment")
conn = dbmod.get_db()
check("the OLD token is refused at resolve (Option A) -- never forwarded to the replacement",
      q_card_core.resolve_token(conn, replace_card["raw_token"]) is None)
check("...and the NEW token, still 'pending_payment' itself, is correctly refused too (not auto-active)",
      q_card_core.resolve_token(conn, new_card["raw_token"]) is None)
q_card_core.mark_free(conn, new_row_id)  # sakshi is family-eligible -- give the new card its own activation
conn.close()
check("...and once the NEW card is itself activated, its OWN token works independently",
      q_card_core.resolve_token(dbmod.get_db(), new_card["raw_token"]) is not None)

conn = dbmod.get_db()
try:
    q_card_core.revoke(conn, replace_card_id)
    check("revoke on a 'replaced' card is refused (no transition out of 'replaced')", False)
except ValueError:
    check("revoke on a 'replaced' card is refused (no transition out of 'replaced')", True)
conn.close()

conn = dbmod.get_db()
try:
    q_card_core.replace(conn, replace_card_id)
    check("replace on an already-'replaced' card is refused (no transition out of 'replaced')", False)
except ValueError:
    check("replace on an already-'replaced' card is refused (no transition out of 'replaced')", True)
conn.close()

conn = dbmod.get_db()
try:
    q_card_core._set_status(conn, paid_card_id, "cancelled")
    check("_set_status refuses a fifth, illegal status string", False)
except ValueError:
    check("_set_status refuses a fifth, illegal status string ('cancelled')", True)
conn.close()

conn = dbmod.get_db()
pending_list = q_card_core.list_pending(conn)
conn.close()
check("list_pending() returns only pending_payment cards", all(c["status"] == "pending_payment" for c in pending_list))
check("list_pending() includes the still-unpaid non_eligible_card (Divya's)", any(c["id"] == non_eligible_card_id for c in pending_list))
check("list_pending() excludes the now-active paid_card", not any(c["id"] == paid_card_id for c in pending_list))

print()
print("=" * 70)
print("Stage 3: admin ROUTES are gated by _is_admin() (403 for a non-admin, success for the real Admin)")
print("=" * 70)

conn = dbmod.get_db()
route_card = q_card_core.issue_card(conn, carl["user_id"])
route_card_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (route_card["card_display_id"],)).fetchone()["id"]
conn.close()

login(carl["private_code"])
res = client.post(f"/api/admin/q-cards/{route_card_id}/mark-paid", json={"method": "cash"})
check("a non-admin hitting the mark-paid route gets 403", res.status_code == 403)

login(pardeep["private_code"])
res = client.post(f"/api/admin/q-cards/{route_card_id}/mark-paid", json={"method": "cash"})
check("the real Admin hitting the mark-paid route succeeds (200)", res.status_code == 200 and res.get_json() == {"status": "ok"})

res = client.get("/api/admin/q-cards/pending")
check("the Admin's pending-list route returns a list", res.status_code == 200 and isinstance(res.get_json()["cards"], list))
logout()

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
