"""Verifies the Admin Panel's location-scoped feed branch for Q-Punch council heads
(2026-10-18): _is_admin_panel_user()'s scope descriptor, the dispatch between the global and
location handlers, the location handler's query (level/location_id from the scope only, never
from the client), the council detail/reply/close routes' own scope check (not just the feed's),
the qpunch_queue_actions writes on every touch, and the derived unread count via notify_core's
'council' kind.

This is the highest-risk change in the whole Q-Punch feature -- a route that served one audience
now serves two, and a scoping mistake here is a data leak, not a broken page. Its own file,
separate from tests/test_qpunch.py, per the explicit instruction that this gets its own diff, its
own tests and its own commit.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_admin_panel_council_scope.py (not -I -- isolated mode hides this
machine's Flask install).
"""
from __future__ import annotations

import datetime as dt
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
import elemental_core  # noqa: E402
import notify_core  # noqa: E402
import qmail_core  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

VILLAGE_A = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
VILLAGE_B = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1B", "name": "Rohini Sector 25"},
}
VID_A, VID_B = VILLAGE_A["village"]["id"], VILLAGE_B["village"]["id"]

_n = [0]


def register(name_prefix, present_location):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": VILLAGE_A["continent"], "country": VILLAGE_A["country"]},
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
    cur = conn.execute(sql, params)
    conn.commit()
    conn.close()
    return cur.lastrowid


def seat_council(village_id, male_id, female_id, cycle_id, start_offset, end_offset, sign, element, year):
    today = dt.date.today()
    raw_exec(
        "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
        "nomination_end, voting_start, voting_end, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed')",
        (cycle_id, village_id, sign, element, year,
         (today + dt.timedelta(days=start_offset - 20)).isoformat(), (today + dt.timedelta(days=start_offset - 15)).isoformat(),
         (today + dt.timedelta(days=start_offset - 10)).isoformat(), (today + dt.timedelta(days=start_offset - 1)).isoformat()),
    )
    raw_exec(
        "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
        "election_cycle_id, leadership_start, leadership_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (village_id, sign, year, male_id, female_id, cycle_id,
         (today + dt.timedelta(days=start_offset)).isoformat(), (today + dt.timedelta(days=end_offset)).isoformat()),
    )


print("=" * 70)
print("Setup: two villages, each with 5 real members and a seated council, one council message each")
print("=" * 70)

members_a = [register("VillagerA", VILLAGE_A) for _ in range(5)]
members_b = [register("VillagerB", VILLAGE_B) for _ in range(5)]
conn = dbmod.get_db()
elemental_core.recompute_location_elements(conn)
conn.close()
check("village A crossed threshold -> address exists",
      raw("SELECT 1 FROM qpunch_addresses WHERE level='village' AND location_id=?", (VID_A,)) is not None)
check("village B crossed threshold -> address exists",
      raw("SELECT 1 FROM qpunch_addresses WHERE level='village' AND location_id=?", (VID_B,)) is not None)

seat_council(VID_A, members_a[0]["user_id"], members_a[1]["user_id"], 201, 0, 30, "Aries", "Fire", 2026)
seat_council(VID_B, members_b[0]["user_id"], members_b[1]["user_id"], 202, 0, 30, "Aries", "Fire", 2026)

sender_a = register("AskerA", VILLAGE_A)
login(sender_a["private_code"])
client.post("/api/qmail/activate", json={"username": "askeravillage"})
res = client.post("/api/qmail/compose", json={"to": f"village-{VID_A}@qumanity.in", "subject": "Water supply", "body": "Water supply has been cut for two days."})
check("message composed to village A's council", res.status_code == 201)
message_a_id = raw("SELECT id FROM qpunch_queue_messages WHERE location_id=?", (VID_A,))["id"]

sender_b = register("AskerB", VILLAGE_B)
login(sender_b["private_code"])
client.post("/api/qmail/activate", json={"username": "askerbvillage"})
res = client.post("/api/qmail/compose", json={"to": f"village-{VID_B}@qumanity.in", "subject": "Road repair", "body": "The main road needs repair."})
check("message composed to village B's council", res.status_code == 201)
message_b_id = raw("SELECT id FROM qpunch_queue_messages WHERE location_id=?", (VID_B,))["id"]

print()
print("=" * 70)
print("1. A village A head's feed shows ONLY village A's queue -- absence checked on the body")
print("=" * 70)

login(members_a[0]["private_code"])  # head_a is a current male head of village A
res = client.get("/api/admin/panel/feed")
check("village A head's feed fetch succeeds (200, not 403)", res.status_code == 200)
items = res.get_json()["items"]
check("feed contains village A's own message", any(it["id"] == message_a_id and it["source"] == "council" for it in items))
check("feed contains ONLY source='council' items (no report/id_recovery/query at all)",
      all(it["source"] == "council" for it in items))
check("no item in the body has source == 'report'", not any(it.get("source") == "report" for it in items))
check("no item in the body has source == 'id_recovery'", not any(it.get("source") == "id_recovery" for it in items))
check("no item in the body has source == 'query'", not any(it.get("source") == "query" for it in items))
check("village B's message does NOT appear in village A head's feed",
      not any(it["id"] == message_b_id for it in items))

print()
print("=" * 70)
print("2. A village A head cannot reach village B's queue by message id -- detail, reply, close")
print("=" * 70)

res = client.get(f"/api/admin/panel/council/{message_b_id}")
check("village A head fetching village B's message by id -> 404, not the data", res.status_code == 404)
res = client.post(f"/api/admin/panel/council/{message_b_id}/reply", json={"message": "trying to reply across villages"})
check("village A head replying to village B's message -> 404, not accepted", res.status_code == 404)
res = client.post(f"/api/admin/panel/council/{message_b_id}/close", json={})
check("village A head closing village B's message -> 404, not accepted", res.status_code == 404)
leaked = raw("SELECT 1 FROM qpunch_queue_actions WHERE message_id = ? AND detail = 'trying to reply across villages'", (message_b_id,))
check("the cross-village reply attempt left NO action row on village B's message", leaked is None)

print()
print("=" * 70)
print("3. A village head hitting /api/admin/queries/* -> 403 (general queries stay global-only)")
print("=" * 70)

res = client.get("/api/admin/queries/1")
check("village A head fetching a member query -> 403", res.status_code == 403)
res = client.post("/api/admin/queries/1/reply", json={"message": "x"})
check("village A head replying to a member query -> 403", res.status_code == 403)
res = client.post("/api/admin/queries/1/close", json={})
check("village A head closing a member query -> 403", res.status_code == 403)

print()
print("=" * 70)
print("4. The Founder (global scope) sees all three existing sources plus every queue")
print("=" * 70)

admin_user = register("Founder", VILLAGE_A)
os.environ["QM_ADMIN_PRIVATE_IDS"] = admin_user["private_code"]
login(admin_user["private_code"])
res = client.get("/api/admin/panel/feed")
check("founder's feed fetch succeeds", res.status_code == 200)
founder_items = res.get_json()["items"]
founder_sources = {it["source"] for it in founder_items}
check("founder's feed includes village A's council message", any(it["id"] == message_a_id for it in founder_items))
check("founder's feed includes village B's council message", any(it["id"] == message_b_id for it in founder_items))
check("founder's feed source set is a subset of the four known kinds (no unexpected leak of shape)",
      founder_sources <= {"report", "id_recovery", "query", "council"})

res = client.get(f"/api/admin/panel/council/{message_a_id}")
check("founder CAN fetch village A's message directly (global scope sees any message)", res.status_code == 200)
res = client.get(f"/api/admin/panel/council/{message_b_id}")
check("founder CAN fetch village B's message directly too", res.status_code == 200)

print()
print("=" * 70)
print("5. A council reply writes a qpunch_queue_actions row and raises the asker's derived unread count")
print("=" * 70)

before_unread = notify_core.summary(dbmod.get_db(), sender_a["user_id"])
check("before any reply, the asker has 0 unread council items", before_unread["unread_council"] == 0)

res = client.post(f"/api/admin/panel/council/{message_a_id}/reply", json={"message": "We are dispatching a repair team today."})
check("founder's reply to village A's message succeeds", res.status_code == 200)
action_row = raw("SELECT * FROM qpunch_queue_actions WHERE message_id = ? AND action = 'replied'", (message_a_id,))
check("a 'replied' action row was written", action_row is not None)
check("the action row names the actual actor (the founder)", action_row and action_row["actor_user_id"] == admin_user["user_id"])
check("the action row carries the reply text in detail", action_row and action_row["detail"] == "We are dispatching a repair team today.")
check("the message's status moved to 'answered'", raw("SELECT status FROM qpunch_queue_messages WHERE id=?", (message_a_id,))["status"] == "answered")

after_unread = notify_core.summary(dbmod.get_db(), sender_a["user_id"])
check("after the reply, the asker's unread_council count is now 1", after_unread["unread_council"] == 1)
check("the reply also raised the asker's grand total", after_unread["total"] == before_unread["total"] + 1)

print()
print("=" * 70)
print("6. The sender's own /api/qmail/sent shows their message, never the reply or the action log")
print("=" * 70)

login(sender_a["private_code"])
res = client.get("/api/qmail/sent")
sent = res.get_json()["messages"]
council_sent = [m for m in sent if m.get("to_name") == "Village Council"]
check("sender's sent view shows exactly one council entry", len(council_sent) == 1)
check("that entry is the ORIGINAL message body, not the reply",
      council_sent and council_sent[0]["body"] == "Water supply has been cut for two days.")
check("the reply text never appears anywhere in the sender's own sent response",
      "dispatching a repair team" not in res.get_data(as_text=True))
check("the word 'actions' (the action log) never appears in the sender's own sent response",
      "actor_user_id" not in res.get_data(as_text=True))

print()
print("=" * 70)
print("7. An expired council term drops the head out of location scope entirely")
print("=" * 70)

today = dt.date.today()
raw_exec("UPDATE village_council SET leadership_end = ? WHERE village_id = ?",
         ((today - dt.timedelta(days=1)).isoformat(), VID_A))
login(members_a[0]["private_code"])
res = client.get("/api/admin/panel/feed")
check("village A head's term has expired -> feed fetch is now 403, not a stale location",
      res.status_code == 403)
res = client.get(f"/api/admin/panel/council/{message_a_id}")
check("same expired head fetching their own OLD village's message by id -> also 403 now",
      res.status_code == 403)

print()
print("=" * 70)
print("8. A newly-elected head sees the full open queue, including messages sent before the election")
print("=" * 70)

seat_council(VID_A, members_a[2]["user_id"], members_a[3]["user_id"], 203, 1, 30, "Taurus", "Earth", 2026)
# The new term starts TOMORROW in this fixture; move it to start today for the test.
raw_exec("UPDATE village_council SET leadership_start = ? WHERE village_id = ? AND zodiac_sign = 'Taurus'",
         (today.isoformat(), VID_A))
login(members_a[2]["private_code"])
res = client.get("/api/admin/panel/feed")
check("newly-elected head's feed fetch succeeds", res.status_code == 200)
new_head_items = res.get_json()["items"]
check("the newly-elected head sees the message sent before their own election (still open at the time)",
      any(it["id"] == message_a_id for it in new_head_items))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL ADMIN PANEL COUNCIL SCOPE TESTS PASSED")
