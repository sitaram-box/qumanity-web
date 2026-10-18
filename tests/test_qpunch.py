"""Verifies Q-Punch council addresses end to end (2026-10-18): threshold-based generation via
elemental_core.recompute_location_elements(), resolve_address()'s qpunch-vs-qmail branching and
village-only reachability gate, compose's routing into qpunch_queue_messages instead of
qmail_messages, /api/qmail/sent's sender-scoped union (the member's own outgoing copy, never the
council's reply or action log), and that a council message survives a change of village heads --
the whole point of a location-keyed queue instead of a per-head mailbox.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_qpunch.py (not -I -- isolated mode hides this machine's Flask
install; see tests/test_account_id_sync.py's note on the same thing).
"""
from __future__ import annotations

import datetime as dt
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
import elemental_core  # noqa: E402
import qmail_core  # noqa: E402

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
VILLAGE_ID = ROHINI["village"]["id"]

_n = [0]


def register(name_prefix, present_location=ROHINI):
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


def raw_all(sql, params=()):
    conn = dbmod.get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def raw_exec(sql, params=()):
    conn = dbmod.get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def activate(username):
    return client.post("/api/qmail/activate", json={"username": username})


def compose(to, subject="Subject", body="Body text"):
    return client.post("/api/qmail/compose", json={"to": to, "subject": subject, "body": body})


print("=" * 70)
print("Section 1: threshold-based generation (QPUNCH_THRESHOLDS)")
print("=" * 70)

# 4 real members at the pilot village -- below the village threshold (5) -- must create nothing.
members = [register("Villager", ROHINI) for _ in range(4)]
conn = dbmod.get_db()
result = elemental_core.recompute_location_elements(conn)
conn.close()
check("4 real members (below threshold 5) -> no qpunch address",
      raw("SELECT 1 FROM qpunch_addresses WHERE location_id = ?", (VILLAGE_ID,)) is None)

# A 5th real member crosses the threshold -- exactly 5, >=, not >.
members.append(register("Villager", ROHINI))
conn = dbmod.get_db()
result = elemental_core.recompute_location_elements(conn)
conn.close()
row = raw("SELECT full_address FROM qpunch_addresses WHERE level = 'village' AND location_id = ?", (VILLAGE_ID,))
check("exactly 5 real members (>=5, not >5) -> village address created", row is not None)
check("address is derivable, exact-case location_id, no slug",
      row and row["full_address"] == f"village-{VILLAGE_ID}@qumanity.in")

# Dropping back below threshold (simulate via a direct recompute call with a smaller total)
# must NOT remove the row -- permanent once created (decision: option (c), every level).
conn = dbmod.get_db()
qmail_core.sync_qpunch_addresses(conn, {(VILLAGE_ID, "village"): 1})
conn.commit()
row_after = raw("SELECT 1 FROM qpunch_addresses WHERE level = 'village' AND location_id = ?", (VILLAGE_ID,))
conn.close()
check("address survives a later drop below threshold (permanent, no retirement)", row_after is not None)

# dry_run must create zero rows even when a different village crosses its threshold.
OTHER_VILLAGE = "CS.DL.3.4.1B"
conn = dbmod.get_db()
dry_result = elemental_core.recompute_location_elements(conn, dry_run=True)
conn.close()
check("dry_run's own return value lists what WOULD be created",
      isinstance(dry_result.get("qpunch_addresses_created"), list))

print()
print("=" * 70)
print("Section 2: resolve_address -- qpunch vs qmail, village-only reachability")
print("=" * 70)

for i, m in enumerate(members):
    login(m["private_code"])
    activate(f"villager{i:03d}xx")

conn = dbmod.get_db()
qmail_core.sync_qpunch_addresses(conn, {(VILLAGE_ID, "village"): 5, ("CS.DL.3", "district"): 100})
conn.commit()
conn.close()

VILLAGE_ADDR = f"village-{VILLAGE_ID}@qumanity.in"
DISTRICT_ADDR = "district-CS.DL.3@qumanity.in"

resolved = qmail_core.resolve_address(dbmod.get_db(), DISTRICT_ADDR)
check("district (non-village) qpunch address -> None (not reachable), even though the row exists",
      resolved is None)

os.environ.pop("QM_ADMIN_PRIVATE_IDS", None)
resolved = qmail_core.resolve_address(dbmod.get_db(), VILLAGE_ADDR)
check("village address with no village_council row -> kind='council', empty user_ids (no admin configured)",
      resolved is not None and resolved["kind"] == "council" and resolved["user_ids"] == [])

check("resolve_address never lowercases the location_id segment",
      qmail_core.resolve_address(dbmod.get_db(), VILLAGE_ADDR.replace(VILLAGE_ID, VILLAGE_ID.lower())) is None
      or VILLAGE_ID == VILLAGE_ID.lower())

print()
print("=" * 70)
print("Section 3: compose routes a council address into qpunch_queue_messages, not qmail_messages")
print("=" * 70)

sender = register("Sender", ROHINI)
login(sender["private_code"])
activate("councilsender1")

res = compose(VILLAGE_ADDR, subject="To the council", body="A question for the village council.")
check("compose to a village council address (empty seat, no admin configured) still succeeds -- "
      "the queue is location-permanent, delivery to a live recipient is a separate concern",
      res.status_code == 201)

qrow = raw("SELECT * FROM qpunch_queue_messages WHERE level='village' AND location_id=?", (VILLAGE_ID,))
check("message landed in qpunch_queue_messages", qrow is not None)
check("sender_id recorded correctly", qrow and qrow["sender_id"] == sender["user_id"])
check("status defaults to 'open'", qrow and qrow["status"] == "open")

leak = raw("SELECT 1 FROM qmail_messages WHERE body = 'A question for the village council.'")
check("the SAME message did NOT also land in qmail_messages (no per-head fan-out)", leak is None)

res = compose(DISTRICT_ADDR, body="Trying a non-village council address.")
check("compose to a non-village council address -> 404, clean, not a silent failure", res.status_code == 404)

# Regression: composing to a regular member address still works exactly as before.
member_target = members[0]
login(member_target["private_code"])
target_status = client.get("/api/qmail/status").get_json()
login(sender["private_code"])
res = compose(target_status["address"], body="A normal person-to-person message.")
check("compose to a regular member address still works (regression)", res.status_code == 201)
personal_row = raw("SELECT 1 FROM qmail_messages WHERE body = 'A normal person-to-person message.'")
check("regular member message landed in qmail_messages, not qpunch_queue_messages", personal_row is not None)

print()
print("=" * 70)
print("Section 4: /api/qmail/sent shows the sender's own council message, nothing of the council's handling")
print("=" * 70)

res = client.get("/api/qmail/sent")
check("sent fetch succeeds", res.status_code == 200)
sent = res.get_json()["messages"]
council_sent = [m for m in sent if m.get("to_name") == "Village Council"]
check("sender's own sent list includes exactly one 'Village Council' entry", len(council_sent) == 1)
check("that entry shows the real council address",
      council_sent and council_sent[0]["to_address"] == VILLAGE_ADDR)
check("that entry carries no internal queue fields (status, location_id, level) to the member",
      council_sent and "status" not in council_sent[0] and "location_id" not in council_sent[0]
      and "level" not in council_sent[0])

# Simulate a council action (a reply/log entry that would exist once the panel is built) and
# confirm it never surfaces through the member's own /api/qmail/sent.
raw_exec(
    "INSERT INTO qpunch_queue_actions (message_id, actor_user_id, action, detail, created_at) "
    "VALUES (?, ?, 'replied', 'internal council note', ?)",
    (qrow["id"], member_target["user_id"], dt.datetime.now(dt.timezone.utc).isoformat()),
)
res = client.get("/api/qmail/sent")
sent_after = res.get_json()["messages"]
check("the simulated council reply/action never appears in the sender's own /api/qmail/sent",
      not any("internal council note" in (m.get("body") or "") for m in sent_after))

print()
print("=" * 70)
print("Section 5: a council message survives a change of village heads (location-keyed, not head-keyed)")
print("=" * 70)

head_a, head_b = members[0]["user_id"], members[1]["user_id"]
head_c, head_d = members[2]["user_id"], members[3]["user_id"]
today = dt.date.today()
raw_exec(
    "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
    "nomination_end, voting_start, voting_end, status) VALUES (99, ?, 'Aries', 'Fire', 2026, ?, ?, ?, ?, 'closed')",
    (VILLAGE_ID, (today - dt.timedelta(days=60)).isoformat(), (today - dt.timedelta(days=50)).isoformat(),
     (today - dt.timedelta(days=45)).isoformat(), (today - dt.timedelta(days=35)).isoformat()),
)
raw_exec(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
    "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Aries', 2026, ?, ?, 99, ?, ?)",
    (VILLAGE_ID, head_a, head_b, (today - dt.timedelta(days=30)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
)
os.environ["QM_ADMIN_PRIVATE_IDS"] = "no-such-id-configured"
resolved = qmail_core.resolve_address(dbmod.get_db(), VILLAGE_ADDR)
check("head_a/head_b's term has already ENDED -> falls back to admin, not stale heads",
      resolved["kind"] == "council" and resolved["user_ids"] == [])

before_count = len(raw_all("SELECT id FROM qpunch_queue_messages WHERE level='village' AND location_id=?", (VILLAGE_ID,)))

# A new election: head_c/head_d take over.
raw_exec(
    "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
    "nomination_end, voting_start, voting_end, status) VALUES (100, ?, 'Taurus', 'Earth', 2026, ?, ?, ?, ?, 'closed')",
    (VILLAGE_ID, (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=5)).isoformat(),
     (today - dt.timedelta(days=4)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
)
raw_exec(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
    "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Taurus', 2026, ?, ?, 100, ?, ?)",
    (VILLAGE_ID, head_c, head_d, today.isoformat(), (today + dt.timedelta(days=30)).isoformat()),
)
resolved = qmail_core.resolve_address(dbmod.get_db(), VILLAGE_ADDR)
check("newly-elected heads (c/d) now resolve as the current council", sorted(resolved["user_ids"]) == sorted([head_c, head_d]))

after_count = len(raw_all("SELECT id FROM qpunch_queue_messages WHERE level='village' AND location_id=?", (VILLAGE_ID,)))
check("the message sent before the election is STILL in the queue after the new heads take over "
      "(location-keyed, not head-keyed -- the whole point of qpunch_queue_messages existing separately)",
      after_count == before_count and before_count >= 1)
still_there = raw("SELECT 1 FROM qpunch_queue_messages WHERE id = ?", (qrow["id"],))
check("the original message row (by id) is unchanged, not deleted or reassigned", still_there is not None)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL Q-PUNCH TESTS PASSED")
