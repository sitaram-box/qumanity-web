"""Verifies the avatar-sweep backend plumbing (2026-10-20): every listing query the frontend's
new window.QMAvatar.render() depends on (static/js/avatar.js) must carry user_id/gender/
profile_picture_url for its author(s) -- Group Chat messages (social_core.group_messages, a
subgroup's board_core.chat_messages), private 1:1 chats (social_core.my_chats/chat_messages),
Collective Board posts/comments/stars (board_core.list/feed), and Admin Panel query replies
(admin_queries_core.replies_for). Qmail inbox/sent are covered separately in
tests/test_qmail_attachments.py (already exercises /api/qmail/inbox).

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure. Follows
the same pattern as tests/test_family_tree.py.

Run with: python3 tests/test_avatar_sweep.py (not -I -- isolated mode hides this machine's Flask
install).
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

_n = [0]


def register(name_prefix, gender="male"):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": gender, "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A, "present_location": VILLAGE_A, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code, pin="12345"):
    res = client.post("/login", json={"private_id": private_code, "pin": pin})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def logout():
    client.post("/logout")


print("=" * 70)
print("1. Personal (Friend/Business/Custom) group chat: group_messages() carries avatar data")
print("=" * 70)

alice = register("Alice Avatar", gender="female")
bob = register("Bob Avatar", gender="male")
login(alice["private_code"])
res = client.post("/api/people/groups/create", json={"category": "custom", "name": "Avatar Test Friends"})
check("group created", res.status_code == 201)
group_id = res.get_json()["id"]
res = client.post(f"/api/people/groups/{group_id}/messages", json={"text": "hello from alice"})
check("message sent", res.status_code in (200, 201))

res = client.get(f"/api/people/groups/{group_id}/messages")
body = res.get_json()
msg = body["messages"][-1]
check("group message carries user_id/gender for the author", msg.get("user_id") == alice["user_id"] and msg.get("gender") == "female")
check("profile_picture_url key is present (null, since no picture uploaded)", "profile_picture_url" in msg and msg["profile_picture_url"] is None)
member = next(m for m in body["members"] if m["user_id"] == alice["user_id"])
check("the members list also carries user_id/gender/profile_picture_url per member",
      member.get("gender") == "female" and "profile_picture_url" in member)

print()
print("=" * 70)
print("2. Private 1:1 chat: my_chats()/chat_messages() carry the OTHER party's avatar data")
print("=" * 70)

res = client.post("/api/people/message", json={"user_id": bob["user_id"], "text": "hi bob"})
check("message request sent", res.status_code == 201)

logout()
login(bob["private_code"])
res = client.get("/api/people/inbox")
req = next(r for r in res.get_json()["requests"] if r["kind"] == "message")
res = client.post(f"/api/people/inbox/{req['id']}/decide", json={"decision": "accept"})
check("bob accepts alice's message request, opening a private chat", res.status_code == 200)

res = client.get("/api/people/chats")
chats = res.get_json()["chats"]
check("bob's chat list shows alice with her avatar data", any(
    c["with_user_id"] == alice["user_id"] and c["with_gender"] == "female" and "with_profile_picture_url" in c for c in chats))
chat_id = next(c["chat_id"] for c in chats if c["with_user_id"] == alice["user_id"])

res = client.get(f"/api/people/chats/{chat_id}")
chat_detail = res.get_json()
check("chat_messages() carries the OTHER party's (alice's) avatar data",
      chat_detail.get("with_user_id") == alice["user_id"] and chat_detail.get("with_gender") == "female"
      and "with_profile_picture_url" in chat_detail)

print()
print("=" * 70)
print("3. Collective Board: post/comment/star rows carry avatar data")
print("=" * 70)

logout()
login(alice["private_code"])  # bob is still logged in from section 2 -- back to a known poster
res = client.post("/api/board/post", json={"content": "An avatar-bearing test post", "level": "village"})
check("board post created", res.status_code == 201)
res = client.get("/api/board/village")
board = res.get_json()
post = next(p for p in board["posts"] if p["content"] == "An avatar-bearing test post")
check("board post carries author_id/author_gender", post.get("author_id") == alice["user_id"] and post.get("author_gender") == "female")
check("author_profile_picture_url key present (null, no picture)", "author_profile_picture_url" in post and post["author_profile_picture_url"] is None)

print()
print("=" * 70)
print("4. Admin query replies: admin_queries_core.replies_for() carries the reply author's avatar data")
print("=" * 70)

import admin_queries_core  # noqa: E402
import db as dbmod  # noqa: E402

conn = dbmod.get_db()
admin_queries_core.ensure_tables(conn)
now = "2026-10-20T00:00:00+00:00"
cur = conn.execute(
    "INSERT INTO admin_queries (user_id, category, subject, body, status, created_at) VALUES (?, 'general', 'Test subject', 'Test body', 'open', ?)",
    (bob["user_id"], now),
)
query_id = cur.lastrowid
conn.commit()
admin_queries_core.reply(conn, alice["user_id"], query_id, "A reply from alice")
conn.close()

conn = dbmod.get_db()
replies = admin_queries_core.replies_for(conn, query_id)
conn.close()
check("the reply carries the replier's gender", replies[0].get("author_gender") == "female")
check("the reply carries a profile_picture_url key (null, no picture)", "author_profile_picture_url" in replies[0] and replies[0]["author_profile_picture_url"] is None)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
