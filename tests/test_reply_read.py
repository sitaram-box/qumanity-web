"""Verifies that a member can read the replies to their own council message and their own Admin
query (2026-10-18). Before this fix a reply raised the sender's unread count (notify_core's
'council' and 'query' kinds) but no route returned the reply itself, so a resident was told
there was a reply and had no way to read it.

Covers: the sender sees their original alongside each reply; the sender never sees the action
log (who viewed, replied or closed); any other member, a council head included, gets the same
404 as a missing message; opening the reply clears its unread count through the existing
chat_read_state mechanism; the same for an Admin query reply; and the /qmail page and the
notification menu are wired to the new routes.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_reply_read.py (not -I -- isolated mode hides this machine's Flask
install).
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import time

ROOT = "/Users/macmudgal/Desktop/Qumanity_DPG"
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import admin_queries_core  # noqa: E402
import db as dbmod  # noqa: E402
import elemental_core  # noqa: E402
import notify_core  # noqa: E402

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
VID = VILLAGE["village"]["id"]

_n = [0]


def register(name_prefix):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": VILLAGE["continent"], "country": VILLAGE["country"]},
        "present_location": VILLAGE,
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


def unread(user_id):
    conn = dbmod.get_db()
    s = notify_core.summary(conn, user_id)
    conn.close()
    return s


print("=" * 70)
print("Setup: a village with 5 real members, a seated council, the Founder, and one council message")
print("=" * 70)

members = [register("Villager") for _ in range(5)]
conn = dbmod.get_db()
elemental_core.recompute_location_elements(conn)
conn.close()
today = dt.date.today()
raw_exec(
    "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
    "nomination_end, voting_start, voting_end, status) VALUES (301, ?, 'Aries', 'Fire', 2026, ?, ?, ?, ?, 'closed')",
    (VID, (today - dt.timedelta(days=20)).isoformat(), (today - dt.timedelta(days=15)).isoformat(),
     (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
)
raw_exec(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
    "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Aries', 2026, ?, ?, 301, ?, ?)",
    (VID, members[0]["user_id"], members[1]["user_id"], today.isoformat(), (today + dt.timedelta(days=30)).isoformat()),
)
head = members[0]
other = members[2]

founder = register("Founder")
os.environ["QM_ADMIN_PRIVATE_IDS"] = founder["private_code"]

sender = register("Resident")
login(sender["private_code"])
client.post("/api/qmail/activate", json={"username": "residentone"})
res = client.post("/api/qmail/compose", json={
    "to": f"village-{VID}@qumanity.in", "subject": "Street light", "body": "The street light on lane 4 is out.",
})
check("resident's message to the council address was sent", res.status_code == 201)
message_id = raw("SELECT id FROM qpunch_queue_messages WHERE sender_id = ?", (sender["user_id"],))["id"]

print()
print("=" * 70)
print("1. Before any reply: the resident sees their original and no replies")
print("=" * 70)

res = client.get(f"/api/qmail/sent/council/{message_id}")
check("resident fetching their own council message -> 200", res.status_code == 200)
body = res.get_json()
check("the response carries the resident's original body", body["body"] == "The street light on lane 4 is out.")
check("the response names the council it went to", body["to_name"] == "Village Council")
check("the response has an empty replies list", body["replies"] == [])

res = client.get("/api/qmail/sent")
council_rows = [m for m in res.get_json()["messages"] if m.get("kind") == "council"]
check("the Sent list marks the council message as kind 'council'", len(council_rows) == 1 and council_rows[0]["id"] == message_id)

print()
print("=" * 70)
print("2. The council head views it and replies; the resident is notified")
print("=" * 70)

time.sleep(1.1)  # the fetch above set a read mark; timestamps are second-resolution
login(head["private_code"])
res = client.get(f"/api/admin/panel/council/{message_id}")
check("the council head can open the message in the Admin Panel", res.status_code == 200)
res = client.post(f"/api/admin/panel/council/{message_id}/reply", json={"message": "An electrician will fix it **tomorrow**."})
check("the council head's reply succeeds", res.status_code == 200)
check("the resident now has 1 unread council reply", unread(sender["user_id"])["unread_council"] == 1)

print()
print("=" * 70)
print("3. The resident reads the reply alongside their original, without the action log")
print("=" * 70)

login(sender["private_code"])
res = client.get(f"/api/qmail/sent/council/{message_id}")
check("resident fetching the thread -> 200", res.status_code == 200)
body = res.get_json()
text = res.get_data(as_text=True)
check("the original is still there", body["body"] == "The street light on lane 4 is out.")
check("exactly one reply is returned", len(body["replies"]) == 1)
check("the reply carries the council's text", body["replies"] and body["replies"][0]["message"] == "An electrician will fix it **tomorrow**.")
check("the reply carries when it arrived", body["replies"] and body["replies"][0].get("created_at"))
check("each reply holds only its text and time", body["replies"] and set(body["replies"][0]) == {"message", "created_at"})
check("no action log key in the response", "actions" not in body)
check("no actor id or actor name anywhere in the response", "actor_user_id" not in text and "actor_name" not in text)
check("the 'viewed' action is not exposed", "viewed" not in text)
check("the council head's name does not appear in the response", "Villager 1" not in text)
check("the message status is not exposed", "status" not in body)

print()
print("=" * 70)
print("4. Opening the reply cleared its unread count, and a later reply raises it again")
print("=" * 70)

check("after opening, the resident has 0 unread council replies", unread(sender["user_id"])["unread_council"] == 0)
mark = raw("SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'council' AND chat_id = ?",
           (sender["user_id"], message_id))
check("the read mark is the existing chat_read_state row with kind 'council'", mark is not None)

time.sleep(1.1)  # timestamps are second-resolution; a reply in the same second as the read counts as read
login(head["private_code"])
client.post(f"/api/admin/panel/council/{message_id}/reply", json={"message": "Update: the part has been ordered."})
client.post(f"/api/admin/panel/council/{message_id}/close", json={})
check("a second reply makes it unread again", unread(sender["user_id"])["unread_council"] == 1)
login(sender["private_code"])
res = client.get(f"/api/qmail/sent/council/{message_id}")
body = res.get_json()
check("both replies are returned, oldest first",
      [r["message"] for r in body["replies"]] == ["An electrician will fix it **tomorrow**.", "Update: the part has been ordered."])
check("the close action does not appear as a reply", len(body["replies"]) == 2)
check("opening it again clears the count", unread(sender["user_id"])["unread_council"] == 0)

print()
print("=" * 70)
print("5. The resident cannot reach the action log")
print("=" * 70)

res = client.get(f"/api/admin/panel/council/{message_id}")
check("the resident fetching the Admin Panel detail (with the log) -> 403", res.status_code == 403)
res = client.get("/api/admin/panel/feed")
check("the resident fetching the Admin Panel feed -> 403", res.status_code == 403)

print()
print("=" * 70)
print("6. Anyone other than the sender gets 404, the same as a missing message")
print("=" * 70)

login(other["private_code"])
before = raw("SELECT COUNT(*) AS n FROM chat_read_state")["n"]
res = client.get(f"/api/qmail/sent/council/{message_id}")
check("a different member of the same village -> 404", res.status_code == 404)
missing = client.get("/api/qmail/sent/council/999999")
check("a message id that does not exist -> 404", missing.status_code == 404)
check("the two 404 bodies are identical", res.get_data() == missing.get_data())
check("the rejected fetch wrote no read mark", raw("SELECT COUNT(*) AS n FROM chat_read_state")["n"] == before)
login(head["private_code"])
res = client.get(f"/api/qmail/sent/council/{message_id}")
check("the council head, through the sender's route -> 404 (heads use the Admin Panel)", res.status_code == 404)
login(founder["private_code"])
res = client.get(f"/api/qmail/sent/council/{message_id}")
check("the Founder, through the sender's route -> 404 (the Admin uses the Admin Panel)", res.status_code == 404)

print()
print("=" * 70)
print("7. An Admin query reply works the same way")
print("=" * 70)

# No route lets a member file a query yet (Doc 10), so the query is created directly, the way
# the route will when it is wired.
conn = dbmod.get_db()
query_id = admin_queries_core.create(conn, sender["user_id"], "karma", "Karma looks wrong", "My karma dropped by 10 overnight.")
conn.close()

login(sender["private_code"])
res = client.get(f"/api/queries/mine/{query_id}")
check("the asker fetching their own query -> 200 with no replies yet", res.status_code == 200 and res.get_json()["replies"] == [])

time.sleep(1.1)  # same reason as section 2
login(founder["private_code"])
res = client.post(f"/api/admin/queries/{query_id}/reply", json={"message": "Fixed: a vote was double-counted."})
check("the Founder's reply succeeds", res.status_code == 200)
check("the asker now has 1 unread query reply", unread(sender["user_id"])["unread_queries"] == 1)

login(sender["private_code"])
res = client.get(f"/api/queries/mine/{query_id}")
body = res.get_json()
check("the asker sees their original", body["body"] == "My karma dropped by 10 overnight.")
check("the asker sees the reply text", [r["message"] for r in body["replies"]] == ["Fixed: a vote was double-counted."])
check("each reply holds only its text and time", set(body["replies"][0]) == {"message", "created_at"})
check("the Founder's name does not appear in the response", "Founder" not in res.get_data(as_text=True))
check("opening it cleared the unread count", unread(sender["user_id"])["unread_queries"] == 0)
res = client.get(f"/api/admin/queries/{query_id}")
check("the asker fetching the Admin detail -> 403", res.status_code == 403)

login(other["private_code"])
res = client.get(f"/api/queries/mine/{query_id}")
missing = client.get("/api/queries/mine/999999")
check("a different member fetching the query -> 404", res.status_code == 404)
check("same body as a query that does not exist", res.get_data() == missing.get_data())

print()
print("=" * 70)
print("8. The /qmail page and the notification menu are wired to the new routes")
print("=" * 70)

qmail_js = open(os.path.join(ROOT, "static/js/qmail.js")).read()
dash_js = open(os.path.join(ROOT, "static/js/dash_extras.js")).read()
check("qmail.js fetches the council thread route", "/api/qmail/sent/council/" in qmail_js)
check("qmail.js fetches the query thread route", "/api/queries/mine/" in qmail_js)
check("qmail.js opens a council Sent item as a thread", 'item.kind === "council"' in qmail_js)
check("qmail.js opens /qmail#council-<id> and #query-<id>", "(council|query)-(\\d+)" in qmail_js)
check("the notification menu sends council and query replies to /qmail", '"/qmail#" + it.kind' in dash_js)
check("replies are rendered through the shared text renderer, not as HTML",
      "qmRenderFormattedText(r.message)" in qmail_js and "innerHTML = r." not in qmail_js)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL REPLY-READ TESTS PASSED")
