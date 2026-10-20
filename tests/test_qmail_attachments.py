"""Verifies Qmail attachments and the mailbox/council-detail data contract (2026-10-18):
server-side size enforcement (both the Flask-wide cap and the precise per-attachment check),
attachment-serve access control (sender/recipient for a member message, sender-or-panel-scope for
a council message -- a village head cannot fetch another village's attachment), that the server
never mangles a message body (the safety property the client-side renderer depends on), and that
this pass's deliberate scope boundary -- no sent_as_level columns, reply-only council compose --
actually holds, not just was intended.

A note on scope: whether a <script> tag renders as inert text and a javascript: link never
becomes clickable are DOM-rendering properties of static/js/dashboard.js's qmRenderFormattedText()
and dash_extras.js's mailbox code. This project has no browser-automation test framework (no
Selenium/Playwright/jsdom installed, and adding one for this alone would be a new dependency this
pass deliberately avoids elsewhere). Those two properties were verified directly in a live browser
this session: a <script>alert(1)</script> subject and body rendered as literal escaped text with
zero console output (no alert fired), **bold**/_italic_/[text](url) rendered as real <b>/<i>/<a>
elements, and a [label](javascript:alert(2)) attempt rendered "label" as plain text with no <a>
element at all (confirmed via the accessibility tree: no "link" role). What THIS suite covers
instead is the part that doesn't need a browser: the server returns a message body completely
unmodified (no stripping, no escaping, no truncation) -- the contract the client-side renderer is
built against -- and that attachment access control holds at the HTTP layer regardless of what the
client would have rendered.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_qmail_attachments.py (not -I -- isolated mode hides this machine's
Flask install).
"""
from __future__ import annotations

import io
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
        "present_location": present_location, "assisted": False,
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
    conn.execute(sql, params)
    conn.commit()
    conn.close()


print("=" * 70)
print("Section 1: the sent_as_level scope boundary -- genuinely absent, not just undocumented")
print("=" * 70)

cols = {r["name"] for r in dbmod.get_db().execute("PRAGMA table_info(qmail_messages)")}
check("qmail_messages has NO sent_as_level column", "sent_as_level" not in cols)
check("qmail_messages has NO sent_as_location_id column", "sent_as_location_id" not in cols)
import inspect  # noqa: E402
compose_src = inspect.getsource(appmod.api_qmail_compose)
check("api_qmail_compose's own source never references sent_as_level",
      "sent_as_level" not in compose_src and "sent_as_location_id" not in compose_src)
reply_src = inspect.getsource(appmod.api_admin_panel_council_reply)
check("the council reply route's own source never references sent_as_level",
      "sent_as_level" not in reply_src and "sent_as_location_id" not in reply_src)

print()
print("=" * 70)
print("Section 2: size enforcement -- the global cap AND the precise per-attachment check, independently")
print("=" * 70)

u1 = register("AttachSender", VILLAGE_A)
login(u1["private_code"])
client.post("/api/qmail/activate", json={"username": "attachsender1"})
u2 = register("AttachTarget", VILLAGE_A)
login(u2["private_code"])
client.post("/api/qmail/activate", json={"username": "attachtarget1"})
status2 = client.get("/api/qmail/status").get_json()

login(u1["private_code"])

small = io.BytesIO(b"small attachment bytes")
res = client.post("/api/qmail/compose", data={
    "to": status2["address"], "subject": "ok", "body": "see attached",
    "attachment": (small, "note.txt"),
}, content_type="multipart/form-data")
check("an attachment well under the cap is accepted (201)", res.status_code == 201)

# Exercises qmail_core.save_attachment's OWN check directly, independent of HTTP transport --
# the thing this project's own code is responsible for, regardless of what any web server or
# proxy in front of it would also enforce.
conn = dbmod.get_db()
try:
    qmail_core.save_attachment(conn, "member", 999999, u1["user_id"], "big.bin", "application/octet-stream",
                                b"x" * (qmail_core.MAX_ATTACHMENT_BYTES + 1))
    check("save_attachment rejects data one byte over MAX_ATTACHMENT_BYTES", False)
except ValueError as e:
    check("save_attachment rejects data one byte over MAX_ATTACHMENT_BYTES", "MB limit" in str(e))
finally:
    conn.close()

# Exercises the SAME check through the real HTTP route, with a payload sized to land UNDER
# Flask's app-wide MAX_CONTENT_LENGTH but OVER qmail_core's own per-attachment cap -- proving the
# precise check fires on its own, not merely riding on the blunter global one.
mid = io.BytesIO(b"y" * (qmail_core.MAX_ATTACHMENT_BYTES + 200 * 1024))
res = client.post("/api/qmail/compose", data={
    "to": status2["address"], "subject": "too big", "body": "see attached",
    "attachment": (mid, "mid.bin"),
}, content_type="multipart/form-data")
check("an attachment over the 2 MB cap, but under Flask's own wider request-body cap, "
      "is still rejected (413) by qmail_core's own explicit byte-length check",
      res.status_code == 413)
check("the rejected compose did not leave a partial qmail_messages row behind (rollback worked)",
      raw("SELECT COUNT(*) c FROM qmail_messages WHERE subject = 'too big'")["c"] == 0)
check("the rejected compose did not leave an orphaned attachment row either",
      raw("SELECT COUNT(*) c FROM qmail_attachments WHERE filename = 'mid.bin'")["c"] == 0)

print()
print("=" * 70)
print("Section 3: attachment serve route -- access control for a member message")
print("=" * 70)

login(u2["private_code"])
res = client.get("/api/qmail/inbox")
inbox_msg = res.get_json()["messages"][0]
check("inbox rows carry from_user_id/from_gender for the avatar sweep (2026-10-20)",
      inbox_msg.get("from_user_id") is not None and inbox_msg.get("from_gender") == "male")
check("from_profile_picture_url is null when the sender has no picture uploaded",
      inbox_msg.get("from_profile_picture_url") is None)
att_id_member = inbox_msg["attachments"][0]["id"]
res = client.get(f"/api/qmail/attachments/{att_id_member}")
check("the recipient CAN fetch the attachment on their own received message", res.status_code == 200)
check("the served bytes match what was uploaded", res.data == b"small attachment bytes")

login(u1["private_code"])
res = client.get(f"/api/qmail/attachments/{att_id_member}")
check("the original sender CAN also fetch it (sender or recipient, either side)", res.status_code == 200)

u3 = register("Outsider", VILLAGE_A)
login(u3["private_code"])
res = client.get(f"/api/qmail/attachments/{att_id_member}")
check("an unrelated third member (neither sender nor recipient) gets 404, not the bytes",
      res.status_code == 404)

print()
print("=" * 70)
print("Section 4: attachment serve route -- a village head cannot fetch another village's attachment")
print("=" * 70)

members_a = [register("VA", VILLAGE_A) for _ in range(5)]
members_b = [register("VB", VILLAGE_B) for _ in range(5)]
conn = dbmod.get_db()
elemental_core.recompute_location_elements(conn)
conn.close()

import datetime as dt  # noqa: E402
today = dt.date.today()
raw_exec(
    "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
    "nomination_end, voting_start, voting_end, status) VALUES (401, ?, 'Aries', 'Fire', 2026, ?, ?, ?, ?, 'closed')",
    (VID_A, (today - dt.timedelta(days=20)).isoformat(), (today - dt.timedelta(days=15)).isoformat(),
     (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
)
raw_exec(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
    "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Aries', 2026, ?, ?, 401, ?, ?)",
    (VID_A, members_a[0]["user_id"], members_a[1]["user_id"], today.isoformat(), (today + dt.timedelta(days=30)).isoformat()),
)
raw_exec(
    "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
    "nomination_end, voting_start, voting_end, status) VALUES (402, ?, 'Aries', 'Fire', 2026, ?, ?, ?, ?, 'closed')",
    (VID_B, (today - dt.timedelta(days=20)).isoformat(), (today - dt.timedelta(days=15)).isoformat(),
     (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
)
raw_exec(
    "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
    "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Aries', 2026, ?, ?, 402, ?, ?)",
    (VID_B, members_b[0]["user_id"], members_b[1]["user_id"], today.isoformat(), (today + dt.timedelta(days=30)).isoformat()),
)

sender_a = register("AskerA", VILLAGE_A)
login(sender_a["private_code"])
client.post("/api/qmail/activate", json={"username": "askeravillagea1"})
small2 = io.BytesIO(b"village A's attached photo bytes")
res = client.post("/api/qmail/compose", data={
    "to": f"village-{VID_A}@qumanity.in", "subject": "Pothole", "body": "See photo.",
    "attachment": (small2, "pothole.jpg"),
}, content_type="multipart/form-data")
check("compose with attachment to village A's council succeeds", res.status_code == 201)
att_id_council = raw("SELECT id FROM qmail_attachments WHERE filename = 'pothole.jpg'")["id"]

login(members_a[0]["private_code"])  # village A's own head
res = client.get(f"/api/qmail/attachments/{att_id_council}")
check("village A's own head CAN fetch the attachment on their own village's message", res.status_code == 200)

login(members_b[0]["private_code"])  # village B's head -- a different location's scope entirely
res = client.get(f"/api/qmail/attachments/{att_id_council}")
check("village B's head CANNOT fetch village A's attachment -- 404, not the bytes, not a 403",
      res.status_code == 404)

login(sender_a["private_code"])
res = client.get(f"/api/qmail/attachments/{att_id_council}")
check("the original sender can still fetch their own attachment regardless of panel scope",
      res.status_code == 200)

print()
print("=" * 70)
print("Section 5: the server never mangles a message body -- the contract the client renderer depends on")
print("=" * 70)

tricky_body = "Does **this** render? <script>alert(1)</script> and [bad](javascript:alert(2)) and [ok](https://example.com)."
login(u1["private_code"])
res = client.post("/api/qmail/compose", json={"to": status2["address"], "subject": "tricky", "body": tricky_body})
check("compose with a markup/script/javascript-link body succeeds (no server-side rejection)", res.status_code == 201)
login(u2["private_code"])
res = client.get("/api/qmail/inbox")
stored = [m for m in res.get_json()["messages"] if m["subject"] == "tricky"][0]
check("the body comes back from the API byte-for-byte identical to what was sent -- "
      "no server-side escaping, stripping or truncation for the client renderer to fight against",
      stored["body"] == tricky_body)

print()
print("=" * 70)
print("Section 6: file-type allowlist on upload, and download-only serving")
print("=" * 70)

login(u1["private_code"])


def compose_with(filename, data, content_type):
    return client.post("/api/qmail/compose", data={
        "to": status2["address"], "subject": f"type-{filename}", "body": "type check",
        "attachment": (io.BytesIO(data), filename, content_type),
    }, content_type="multipart/form-data")


svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
res = compose_with("drawing.svg", svg, "image/svg+xml")
check("an .svg upload is rejected at save time with a clean 400", res.status_code == 400)
res = compose_with("page.html", b"<script>alert(1)</script>", "text/html")
check("an .html upload is rejected with 400", res.status_code == 400)
res = compose_with("trick.png", b"<script>alert(1)</script>", "text/html")
check("a .png name declared as text/html is rejected with 400 (extension and type disagree)",
      res.status_code == 400)
check("no rejected file entered the database, and no message was left behind either",
      raw("SELECT COUNT(*) c FROM qmail_attachments WHERE filename IN ('drawing.svg', 'page.html', 'trick.png')")["c"] == 0
      and raw("SELECT COUNT(*) c FROM qmail_messages WHERE subject IN "
              "('type-drawing.svg', 'type-page.html', 'type-trick.png')")["c"] == 0)

png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
res = compose_with("photo.png", png, "image/png")
check("a .png upload declared as image/png succeeds (201)", res.status_code == 201)
png_id = raw("SELECT id FROM qmail_attachments WHERE filename = 'photo.png'")["id"]
login(u2["private_code"])
res = client.get(f"/api/qmail/attachments/{png_id}")
check("the .png is served (200) with its bytes intact", res.status_code == 200 and res.data == png)
check("it is served with Content-Disposition: attachment, not inline",
      res.headers.get("Content-Disposition", "").startswith("attachment"))
check("it is served with X-Content-Type-Options: nosniff",
      res.headers.get("X-Content-Type-Options") == "nosniff")
check("it is served as image/png", res.mimetype == "image/png")

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL QMAIL ATTACHMENT / DATA-CONTRACT TESTS PASSED")
