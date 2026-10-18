"""Verifies Qmail drafts (2026-10-18): ownership scoping (a second user gets 404, not 403, on a
draft that isn't theirs -- the same shape qpunch_queue's own scoping invariants use), that a
draft's body round-trips unmodified, and that sending from a draft deletes it on success but
leaves it fully intact if the send fails partway through (the attachment size check, specifically
-- the one real failure mode compose can hit after the draft would otherwise be consumed).

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_qmail_drafts.py (not -I -- isolated mode hides this machine's Flask
install).
"""
from __future__ import annotations

import io
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
import qmail_core  # noqa: E402

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
_n = [0]


def register(name_prefix):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": {"continent": VILLAGE["continent"], "country": VILLAGE["country"]},
        "present_location": VILLAGE, "assisted": False,
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


print("=" * 70)
print("Section 1: ownership -- a saved draft appears for its owner only")
print("=" * 70)

u1 = register("DraftOwner")
login(u1["private_code"])
client.post("/api/qmail/activate", json={"username": "draftowner1"})
u2 = register("DraftTarget")
login(u2["private_code"])
client.post("/api/qmail/activate", json={"username": "drafttarget1"})
status2 = client.get("/api/qmail/status").get_json()

login(u1["private_code"])
tricky_body = "Draft with **markup**, a <script>alert(1)</script> and a link: [x](https://example.com)."
res = client.post("/api/qmail/drafts", json={"to": status2["address"], "subject": "Draft one", "body": tricky_body})
check("creating a draft succeeds (201)", res.status_code == 201)
draft_id = res.get_json()["id"]
check("creation returns a real id", isinstance(draft_id, int) and draft_id > 0)

res = client.get("/api/qmail/drafts")
check("owner's draft list fetch succeeds", res.status_code == 200)
owned = res.get_json()["drafts"]
check("owner's draft list contains exactly the one draft just created",
      len(owned) == 1 and owned[0]["id"] == draft_id)
check("the body round-trips byte-for-byte unmodified -- same contract as messages",
      owned[0]["body"] == tricky_body)
check("the subject round-trips unmodified too", owned[0]["subject"] == "Draft one")

login(u2["private_code"])
res = client.get("/api/qmail/drafts")
check("a different user's draft list is empty -- u1's draft never leaks across accounts",
      res.get_json()["drafts"] == [])

print()
print("=" * 70)
print("Section 2: a second user cannot read, update or delete the first user's draft -- 404, not 403")
print("=" * 70)

res = client.post(f"/api/qmail/drafts/{draft_id}", json={"to": "x", "subject": "hijacked", "body": "hijacked"})
check("u2 updating u1's draft by id -> 404, not accepted", res.status_code == 404)
check("u1's draft subject is unchanged after u2's attempted update",
      raw("SELECT subject FROM qmail_drafts WHERE id = ?", (draft_id,))["subject"] == "Draft one")

res = client.post(f"/api/qmail/drafts/{draft_id}/delete")
check("u2 deleting u1's draft by id -> 404, not accepted", res.status_code == 404)
check("u1's draft still exists in the database after u2's attempted delete",
      raw("SELECT 1 FROM qmail_drafts WHERE id = ?", (draft_id,)) is not None)

# "Read" isn't a per-id GET in this design (the list already returns full bodies, see
# qmail_core.drafts_for's own docstring) -- the read-scoping check is that u2's own list, proven
# empty above, never includes u1's draft. Confirmed again here for a second draft, after u1 has
# since been proven to still own the first one.
login(u1["private_code"])
res = client.post("/api/qmail/drafts", json={"to": status2["address"], "subject": "Draft two", "body": "second"})
draft_id_2 = res.get_json()["id"]
login(u2["private_code"])
res = client.get("/api/qmail/drafts")
check("u2's own draft list still never includes either of u1's drafts",
      all(d["id"] not in (draft_id, draft_id_2) for d in res.get_json()["drafts"]))

print()
print("=" * 70)
print("Section 3: sending from a draft deletes it on success, leaves it intact on failure")
print("=" * 70)

login(u1["private_code"])
res = client.post("/api/qmail/drafts", json={"to": status2["address"], "subject": "To send", "body": "will be sent"})
send_draft_id = res.get_json()["id"]
check("draft-to-send exists before the compose call",
      raw("SELECT 1 FROM qmail_drafts WHERE id = ?", (send_draft_id,)) is not None)

# Failure case FIRST, against this same draft -- an oversized attachment, the one real compose
# failure mode that happens after the message row would otherwise already be written.
big = io.BytesIO(b"z" * (qmail_core.MAX_ATTACHMENT_BYTES + 1024))
res = client.post("/api/qmail/compose", data={
    "to": status2["address"], "subject": "To send", "body": "will be sent",
    "draft_id": str(send_draft_id), "attachment": (big, "big.bin"),
}, content_type="multipart/form-data")
check("compose with an oversized attachment fails (413)", res.status_code == 413)
check("the draft is STILL THERE after the failed send -- nothing lost on a failed attempt",
      raw("SELECT 1 FROM qmail_drafts WHERE id = ?", (send_draft_id,)) is not None)
check("no message row was created by the failed send either",
      raw("SELECT COUNT(*) c FROM qmail_messages WHERE subject = 'To send'")["c"] == 0)

# Now the real, successful send from the same draft.
res = client.post("/api/qmail/compose", json={
    "to": status2["address"], "subject": "To send", "body": "will be sent", "draft_id": send_draft_id,
})
check("the real send (no attachment) succeeds", res.status_code == 201)
check("the draft is GONE after a successful send",
      raw("SELECT 1 FROM qmail_drafts WHERE id = ?", (send_draft_id,)) is None)
check("the message itself was actually delivered",
      raw("SELECT 1 FROM qmail_messages WHERE subject = 'To send' AND body = 'will be sent'") is not None)

print()
print("=" * 70)
print("Section 4: the delete route works for a member cleaning up their own draft")
print("=" * 70)

res = client.post(f"/api/qmail/drafts/{draft_id_2}/delete")
check("u1 deleting their own second draft succeeds", res.status_code == 200)
check("that draft is actually gone", raw("SELECT 1 FROM qmail_drafts WHERE id = ?", (draft_id_2,)) is None)
res = client.get("/api/qmail/drafts")
check("u1's remaining draft list contains only the original first draft",
      [d["id"] for d in res.get_json()["drafts"]] == [draft_id])

print()
print("=" * 70)
print("Section 5: a missing or malformed body returns a clean 400, never a 500")
print("=" * 70)

count_before = raw("SELECT COUNT(*) c FROM qmail_drafts")["c"]

res = client.post("/api/qmail/drafts")
check("no request body at all -> 400, not a crash", res.status_code == 400)

res = client.post("/api/qmail/drafts", json=[1, 2, 3])
check("a JSON array instead of an object -> 400, not an unhandled AttributeError 500 "
      "(request.get_json() happily returns a non-dict without raising -- .get() on that is what crashed)",
      res.status_code == 400)

res = client.post("/api/qmail/drafts", json={})
check("an empty JSON object -> 400, nothing worth saving", res.status_code == 400)

res = client.post("/api/qmail/drafts", data="{not valid json", content_type="application/json")
check("genuinely malformed JSON text -> 400, not a crash", res.status_code == 400)

check("none of the four rejected requests above created a row",
      raw("SELECT COUNT(*) c FROM qmail_drafts")["c"] == count_before)

res = client.post("/api/qmail/drafts", json={"subject": "just a subject, nothing else"})
check("a minimal but genuinely valid draft (one non-empty field) still succeeds (201)",
      res.status_code == 201)
check("the one genuinely valid request DID create exactly one row",
      raw("SELECT COUNT(*) c FROM qmail_drafts")["c"] == count_before + 1)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} FAILURE(S):")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("ALL QMAIL DRAFT TESTS PASSED")
