"""Verifies the 2026-11-12 Multi-View fixes: the Admin Queue's five-source feed (including the
newly-recognized Identity source), LBE's Location ID / Account ID resolution (POST
/api/admin/lbe/resolve), its scope enforcement for a council head vs. the Founder, and the
Part 6 audit log (POST /api/admin/lbe/log-event, admin_location_views).

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real migrations (same convention as tests/test_election_winner_tally.py
and tests/test_global_account.py), PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_lbe_admin_panel.py
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
os.environ["QM_DISABLE_SCHEDULER"] = "1"
os.environ["QM_ADMIN_PRIVATE_IDS"] = "719341677"  # the Founder's own real Private ID, per the owner's report

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import zodiac_core  # noqa: E402

FAILS = []


def _dob_for_current_sign() -> str:
    """A 1990 DOB landing inside whichever zodiac sign's window is active on the real day this
    test happens to run -- _viewable_locations_scope() gates a council head's Explorer access on
    THEIR OWN current zodiac month, so a hardcoded DOB would start silently failing the day the
    real calendar moved past it."""
    today = dt.date.today()
    md = (today.month, today.day)
    for z in zodiac_core.ZODIAC_RANGES:
        sm, sd = (int(p) for p in z["start"].split("-"))
        em, ed = (int(p) for p in z["end"].split("-"))
        in_range = (sm, sd) <= md <= (em, ed) if (sm, sd) <= (em, ed) else (md >= (sm, sd) or md <= (em, ed))
        if in_range:
            return dt.date(1990, sm, sd).isoformat()
    raise RuntimeError("Could not match today's date to any zodiac range")


COUNCIL_HEAD_DOB = _dob_for_current_sign()


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


ROHINI = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
OTHER_TEHSIL_VILLAGE = {**ROHINI, "tehsil": {"id": "CS.DL.3.5", "name": "Narela"}, "village": {"id": "CS.DL.3.5.1A", "name": "Narela Village"}}

conn = dbmod.get_db()
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.5.1A', 'CS.DL.3.5', 'Narela Village')")
conn.commit()
conn.close()

client = appmod.app.test_client()


def register(name, private_id_override=None, location=None, pin="12345", dob="1990-10-01"):
    payload = {
        "name": name, "gender": "male", "dob": dob, "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": pin,
        "birth_location": {k: (location or ROHINI)[k] for k in ("continent", "country", "zone", "state")},
        "present_location": location or ROHINI, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    uid = res.get_json()["user_id"]
    if private_id_override:
        conn2 = dbmod.get_db()
        conn2.execute("UPDATE users SET private_id_9digit = ? WHERE id = ?", (private_id_override, uid))
        conn2.commit()
        conn2.close()
    return uid


def login_as(uid):
    client.get("/logout")
    conn2 = dbmod.get_db()
    private_id = conn2.execute("SELECT private_id_9digit FROM users WHERE id = ?", (uid,)).fetchone()["private_id_9digit"]
    conn2.close()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return private_id


print("=" * 70)
print("1. Seed one real pending item in each of the five Admin Queue sources")
print("=" * 70)

admin_uid = register("Founder Test", private_id_override="719341677")
reporter_uid = register("Reporter Resident")
other_uid = register("Other Resident")

conn = dbmod.get_db()
now = dt.datetime.now(dt.timezone.utc).isoformat()
conn.execute(
    "INSERT INTO reports (user_id, location_id, location_level, body, status, sla_deadline, created_at) "
    "VALUES (?, 'CS.DL.3.4.1A', 'village', 'The hand-pump is broken.', 'open', ?, ?)",
    (str(reporter_uid), now, now),
)
conn.execute(
    "INSERT INTO id_recovery_requests (name, dob, mailing_address, status, created_at) "
    "VALUES ('Jane Claimant', '1985-05-05', '123 Main St', 'pending', ?)", (now,),
)
conn.execute(
    "INSERT INTO admin_queries (user_id, category, subject, body, status, created_at) "
    "VALUES (?, 'query', 'How do Qoins work?', 'Can you explain?', 'open', ?)", (reporter_uid, now),
)
conn.execute(
    "INSERT INTO qpunch_queue_messages (level, location_id, sender_id, subject, body, status, created_at) "
    "VALUES ('village', 'CS.DL.3.4.1A', ?, 'Streetlight out', 'Please fix.', 'open', ?)", (reporter_uid, now),
)
conn.commit()
conn.close()

# An identity-correction ticket -- profile_change_requests with request_type != 'edit'
appmod._ensure_profile_change_table(dbmod.get_db())
conn = dbmod.get_db()
conn.execute(
    "INSERT INTO profile_change_requests (user_id, fields_json, reason, status, created_at, request_type, location_level, location_id) "
    "VALUES (?, '{}', 'Birth time was wrong', 'pending', ?, 'birth_time_correction', 'village', 'CS.DL.3.4.1A')",
    (other_uid, now),
)
conn.commit()
conn.close()

print()
print("=" * 70)
print("2. Admin (global scope) sees all five sources in one feed")
print("=" * 70)

login_as(admin_uid)
scope_resp = client.get("/api/admin/viewable-locations").get_json()
check("Founder resolves to global scope (719341677 matches QM_ADMIN_PRIVATE_IDS)", scope_resp.get("scope") == "global")

feed = client.get("/api/admin/panel/feed").get_json()
sources_seen = {it["source"] for it in feed["items"]}
check("Feed is non-empty", len(feed["items"]) > 0)
check("Citizen Report appears", "report" in sources_seen)
check("ID Recovery appears", "id_recovery" in sources_seen)
check("Query appears", "query" in sources_seen)
check("Council Queue item appears", "council" in sources_seen)
check("Identity ticket appears", "identity" in sources_seen)
check("All five sources combined in one response", sources_seen == {"report", "id_recovery", "query", "council", "identity"})

print()
print("=" * 70)
print("3. A council head (location scope) never sees the three global-only sources")
print("=" * 70)

council_uid = register("Council Head", location=ROHINI, dob=COUNCIL_HEAD_DOB)
conn = dbmod.get_db()
today = dt.date.today()
cur = conn.execute(
    "INSERT INTO election_cycles (village_id, zodiac_sign, element, year, nomination_start, nomination_end, "
    "voting_start, voting_end, status) VALUES ('CS.DL.3.4.1A', 'Libra', 'Air', ?, ?, ?, ?, ?, 'closed')",
    (today.year, today.isoformat(), today.isoformat(), today.isoformat(), today.isoformat()),
)
cycle_id = cur.lastrowid
conn.execute(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, election_cycle_id, "
    "leadership_start, leadership_end) VALUES ('CS.DL.3.4.1A', 'Libra', ?, ?, ?, ?, ?)",
    (today.year, council_uid, cycle_id, (today - dt.timedelta(days=5)).isoformat(), (today + dt.timedelta(days=5)).isoformat()),
)
conn.commit()
conn.close()

login_as(council_uid)
council_scope = client.get("/api/admin/viewable-locations").get_json()
check("Currently-serving council head resolves to a 'limited' Explorer scope", council_scope.get("scope") == "limited")

council_feed = client.get("/api/admin/panel/feed").get_json()
council_sources = {it["source"] for it in council_feed["items"]}
check("Council head's feed has no 'report' source (global-only, by design)", "report" not in council_sources)
check("Council head's feed has no 'id_recovery' source (global-only, by design)", "id_recovery" not in council_sources)
check("Council head's feed has no 'query' source (global-only, by design)", "query" not in council_sources)
check("Council head's feed DOES include their own village's council queue", "council" in council_sources)

print()
print("=" * 70)
print("4. LBE resolve: Location ID (village, tehsil) and Account ID")
print("=" * 70)

login_as(admin_uid)
r = client.post("/api/admin/lbe/resolve", json={"query": "CS.DL.3.4.1A"})
body = r.get_json()
check("Village Location ID resolves: HTTP 200", r.status_code == 200)
check("Village Location ID resolves to level='village'", body.get("level") == "village")
check("Resolved chain's village id matches exactly, unchanged", body.get("chain", {}).get("village", {}).get("id") == "CS.DL.3.4.1A")
check("Resolved chain carries the real ancestor names (not invented)", body.get("chain", {}).get("state", {}).get("name") == "Delhi")

r2 = client.post("/api/admin/lbe/resolve", json={"query": "CS.DL.3.4"})
body2 = r2.get_json()
check("Tehsil Location ID resolves: HTTP 200, level='tehsil'", r2.status_code == 200 and body2.get("level") == "tehsil")

acct_id = dbmod.get_db().execute("SELECT account_id FROM account_ids WHERE user_id = ? AND is_current = 1", (reporter_uid,)).fetchone()["account_id"]
r3 = client.post("/api/admin/lbe/resolve", json={"query": acct_id})
body3 = r3.get_json()
check("A real Account ID resolves: HTTP 200", r3.status_code == 200)
check("Account ID resolves to that member's actual present village", body3.get("chain", {}).get("village", {}).get("id") == "CS.DL.3.4.1A")

r4 = client.post("/api/admin/lbe/resolve", json={"query": "NOT-A-REAL-ID-XYZ"})
check("An unknown id returns HTTP 404 with a clear error, not a silently-opened board", r4.status_code == 404 and "error" in r4.get_json())

r5 = client.post("/api/admin/lbe/resolve", json={"query": ""})
check("An empty query returns HTTP 400", r5.status_code == 400)

print()
print("=" * 70)
print("5. LBE resolve enforces the council head's own Tehsil scope")
print("=" * 70)

login_as(council_uid)
r6 = client.post("/api/admin/lbe/resolve", json={"query": "CS.DL.3.4.1A"})
check("Council head CAN resolve a village inside their own Tehsil", r6.status_code == 200)

outside_uid = register("Narela Resident", location=OTHER_TEHSIL_VILLAGE)
r7 = client.post("/api/admin/lbe/resolve", json={"query": "CS.DL.3.5.1A"})
check("Council head CANNOT resolve a village outside their own Tehsil: HTTP 403", r7.status_code == 403)

login_as(reporter_uid)
r8 = client.post("/api/admin/lbe/resolve", json={"query": "CS.DL.3.4.1A"})
check("An ordinary member (no Explorer scope at all) is rejected: HTTP 403", r8.status_code == 403)

client.get("/logout")
r9 = client.post("/api/admin/lbe/resolve", json={"query": "CS.DL.3.4.1A"})
check("A logged-out visitor is rejected (login_required): not HTTP 200", r9.status_code != 200)

print()
print("=" * 70)
print("6. Audit log (Part 6): BOARD_OPENED / BOARD_CLOSED")
print("=" * 70)

login_as(admin_uid)
log_open = client.post("/api/admin/lbe/log-event", json={
    "event": "BOARD_OPENED", "location_level": "village", "location_id": "CS.DL.3.4.1A",
    "location_name": "Rohini Sector 24", "source": "lbe_location_id",
})
check("BOARD_OPENED logs successfully: HTTP 200", log_open.status_code == 200)

log_close = client.post("/api/admin/lbe/log-event", json={
    "event": "BOARD_CLOSED", "location_level": "village", "location_id": "CS.DL.3.4.1A",
    "location_name": "Rohini Sector 24", "source": "lbe_location_id",
})
check("BOARD_CLOSED logs successfully: HTTP 200", log_close.status_code == 200)

conn = dbmod.get_db()
rows = conn.execute(
    "SELECT user_id, event, location_level, location_id, location_name, source, viewed_at FROM admin_location_views ORDER BY id"
).fetchall()
conn.close()
check("Exactly 2 rows were written (one open, one close)", len(rows) == 2)
check("Row 1 is BOARD_OPENED for the Founder's own user_id (never client-supplied)", rows[0]["event"] == "BOARD_OPENED" and rows[0]["user_id"] == admin_uid)
check("Row 2 is BOARD_CLOSED", rows[1]["event"] == "BOARD_CLOSED")
check("location_id recorded exactly as the canonical village id", rows[0]["location_id"] == "CS.DL.3.4.1A")
check("source recorded as 'lbe_location_id'", rows[0]["source"] == "lbe_location_id")
check("viewed_at is a server-generated, parseable UTC timestamp", dt.datetime.fromisoformat(rows[0]["viewed_at"]).tzinfo is not None)

bad_event = client.post("/api/admin/lbe/log-event", json={"event": "NOT_A_REAL_EVENT", "location_level": "village", "location_id": "CS.DL.3.4.1A"})
check("An invalid event name is rejected: HTTP 400", bad_event.status_code == 400)

login_as(council_uid)
log_open_outside = client.post("/api/admin/lbe/log-event", json={
    "event": "BOARD_OPENED", "location_level": "village", "location_id": "CS.DL.3.5.1A", "source": "lbe_location_id",
})
check("BOARD_OPENED for a village outside the council head's Tehsil is rejected: HTTP 403 (no fabricated log entry either)", log_open_outside.status_code == 403)

conn = dbmod.get_db()
count_after = conn.execute("SELECT COUNT(*) AS n FROM admin_location_views").fetchone()["n"]
conn.close()
check("The rejected out-of-scope open did not write a log row", count_after == 2)

client.get("/logout")
log_open_anon = client.post("/api/admin/lbe/log-event", json={
    "event": "BOARD_OPENED", "location_level": "village", "location_id": "CS.DL.3.4.1A", "source": "lbe_location_id",
})
check("A logged-out visitor cannot write an audit log row either", log_open_anon.status_code != 200)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
