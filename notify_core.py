"""Notification badge (2026-09-28): a small, honest count of what a user hasn't looked at yet --
unread Personal-timeline chats (private one-to-one + group), and pending people-requests waiting
on their decision. Village/sub-group board chat and Collective Board posts are public/location
feeds rather than addressed to one person, so they are not counted here.

Read state is a simple per-(user, chat) high-water mark: a chat becomes "read" the moment its
screen calls mark_read(); a chat is "unread" whenever it has a message newer than that mark (or
no mark at all yet). Nothing here changes the messages themselves -- it is purely a derived count.
"""
from __future__ import annotations

import datetime as dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_read_state (
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,       -- 'private' (private_chats.id) or 'group' (personal_groups.id)
    chat_id INTEGER NOT NULL,
    last_read_at TEXT NOT NULL,
    PRIMARY KEY (user_id, kind, chat_id)
);
"""


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    # Same format as social_core._now() -- messages' created_at is this exact ISO shape, and SQLite
    # has no real datetime type, so last_read_at must be byte-for-byte comparable to it (a mix of
    # this format and SQLite's own CURRENT_TIMESTAMP, e.g., would sort wrong: "2026-09-28 …" <
    # "2026-09-28T…" for every timestamp, always, because ' ' sorts before 'T').
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def mark_read(conn, user_id: int, kind: str, chat_id: int) -> None:
    if kind not in ("private", "group", "query", "council"):
        # 'query' = admin_queries.id (2026-10-18, Admin Panel replies)
        # 'council' = qpunch_queue_messages.id (2026-10-18, Q-Punch council replies)
        raise ValueError("Unknown chat kind")
    ensure_tables(conn)
    conn.execute(
        """INSERT INTO chat_read_state (user_id, kind, chat_id, last_read_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, kind, chat_id) DO UPDATE SET last_read_at = excluded.last_read_at""",
        (user_id, kind, chat_id, _now()),
    )
    conn.commit()


def summary(conn, user_id: int) -> dict:
    ensure_tables(conn)

    private_rows = conn.execute(
        """SELECT c.id AS chat_id,
                  (SELECT MAX(created_at) FROM private_messages WHERE chat_id = c.id) AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'private' AND chat_id = c.id) AS last_read
           FROM private_chats c WHERE c.user_lo = ? OR c.user_hi = ?""",
        (user_id, user_id, user_id),
    ).fetchall()

    group_rows = conn.execute(
        """SELECT pg.id AS chat_id,
                  (SELECT MAX(created_at) FROM personal_messages WHERE group_id = pg.id) AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'group' AND chat_id = pg.id) AS last_read
           FROM personal_groups pg
           WHERE pg.owner_user_id = ?
              OR pg.id IN (SELECT group_id FROM personal_group_members WHERE user_id = ? AND status = 'approved')""",
        (user_id, user_id, user_id),
    ).fetchall()

    # Admin Panel reply (2026-10-18): unread means a reply NEWER than the asker's last-read mark
    # -- not "the query itself is still open", since an unanswered query has nothing new to read
    # yet. chat_id here is admin_queries.id, same high-water-mark pattern as private/group above.
    query_rows = conn.execute(
        """SELECT q.id AS chat_id,
                  (SELECT MAX(created_at) FROM admin_query_replies WHERE query_id = q.id) AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'query' AND chat_id = q.id) AS last_read
           FROM admin_queries q WHERE q.user_id = ?""",
        (user_id, user_id),
    ).fetchall()

    # Q-Punch council reply (2026-10-18): same high-water-mark pattern as 'query' above, with
    # qpunch_queue_actions' 'replied' rows standing in for admin_query_replies -- unread means a
    # reply NEWER than the sender's last-read mark, not "the message is still open". chat_id is
    # qpunch_queue_messages.id; scoped to q.sender_id, the same person this module's union is
    # always about -- the council's OTHER handling (viewed/closed actions) never counts here.
    council_rows = conn.execute(
        """SELECT q.id AS chat_id,
                  (SELECT MAX(created_at) FROM qpunch_queue_actions WHERE message_id = q.id AND action = 'replied') AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'council' AND chat_id = q.id) AS last_read
           FROM qpunch_queue_messages q WHERE q.sender_id = ?""",
        (user_id, user_id),
    ).fetchall()

    def is_unread(r):
        return bool(r["last_msg"]) and (not r["last_read"] or r["last_msg"] > r["last_read"])

    unread_private = sum(1 for r in private_rows if is_unread(r))
    unread_groups = sum(1 for r in group_rows if is_unread(r))
    unread_queries = sum(1 for r in query_rows if is_unread(r))
    unread_council = sum(1 for r in council_rows if is_unread(r))
    pending_requests = conn.execute(
        "SELECT COUNT(*) FROM people_requests WHERE to_user_id = ? AND status IN ('pending', 'waiting')", (user_id,)
    ).fetchone()[0]

    return {
        "unread_chats": unread_private + unread_groups,
        "unread_private": unread_private,
        "unread_groups": unread_groups,
        "unread_queries": unread_queries,
        "unread_council": unread_council,
        "pending_requests": pending_requests,
        "total": unread_private + unread_groups + pending_requests + unread_queries + unread_council,
    }


def recent_items(conn, user_id: int, limit: int = 5) -> list[dict]:
    """The `limit` most recent unread items across private chats, group chats and pending
    people-requests, newest first -- the same three sources `summary()` counts, just surfaced
    as titled rows instead of a number. Title convention matches `my_chats()`/`my_groups()`
    elsewhere (the chat's own name if set, else the other person's/group's name -- no
    hide_identity masking here, same as the rest of the Personal tab)."""
    ensure_tables(conn)

    private_rows = conn.execute(
        """SELECT c.id AS chat_id, c.name AS chat_name,
                  CASE WHEN c.user_lo = ? THEN c.user_hi ELSE c.user_lo END AS other_id,
                  (SELECT MAX(created_at) FROM private_messages WHERE chat_id = c.id) AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'private' AND chat_id = c.id) AS last_read
           FROM private_chats c WHERE c.user_lo = ? OR c.user_hi = ?""",
        (user_id, user_id, user_id, user_id),
    ).fetchall()

    group_rows = conn.execute(
        """SELECT pg.id AS chat_id, pg.name AS chat_name,
                  (SELECT MAX(created_at) FROM personal_messages WHERE group_id = pg.id) AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'group' AND chat_id = pg.id) AS last_read
           FROM personal_groups pg
           WHERE pg.owner_user_id = ?
              OR pg.id IN (SELECT group_id FROM personal_group_members WHERE user_id = ? AND status = 'approved')""",
        (user_id, user_id, user_id),
    ).fetchall()

    query_rows = conn.execute(
        """SELECT q.id AS chat_id, q.subject AS chat_name,
                  (SELECT MAX(created_at) FROM admin_query_replies WHERE query_id = q.id) AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'query' AND chat_id = q.id) AS last_read
           FROM admin_queries q WHERE q.user_id = ?""",
        (user_id, user_id),
    ).fetchall()

    council_rows = conn.execute(
        """SELECT q.id AS chat_id, q.subject AS chat_name,
                  (SELECT MAX(created_at) FROM qpunch_queue_actions WHERE message_id = q.id AND action = 'replied') AS last_msg,
                  (SELECT last_read_at FROM chat_read_state WHERE user_id = ? AND kind = 'council' AND chat_id = q.id) AS last_read
           FROM qpunch_queue_messages q WHERE q.sender_id = ?""",
        (user_id, user_id),
    ).fetchall()

    def is_unread(r):
        return bool(r["last_msg"]) and (not r["last_read"] or r["last_msg"] > r["last_read"])

    items = []
    for r in private_rows:
        if not is_unread(r):
            continue
        other = conn.execute("SELECT name FROM users WHERE id = ?", (r["other_id"],)).fetchone()
        other_name = other["name"] if other else "Unknown"
        items.append({
            "kind": "private", "id": r["chat_id"], "title": r["chat_name"] or other_name,
            "created_at": r["last_msg"], "meta": {"with": other_name},
        })
    for r in group_rows:
        if not is_unread(r):
            continue
        items.append({
            "kind": "group", "id": r["chat_id"], "title": r["chat_name"],
            "created_at": r["last_msg"], "meta": {},
        })
    for r in query_rows:
        if not is_unread(r):
            continue
        items.append({
            "kind": "query", "id": r["chat_id"], "title": r["chat_name"],
            "created_at": r["last_msg"], "meta": {},
        })
    for r in council_rows:
        if not is_unread(r):
            continue
        items.append({
            "kind": "council", "id": r["chat_id"], "title": r["chat_name"],
            "created_at": r["last_msg"], "meta": {},
        })
    for r in conn.execute(
        """SELECT pr.id, pr.created_at, pr.first_message, u.name AS from_name
           FROM people_requests pr JOIN users u ON u.id = pr.from_user_id
           WHERE pr.to_user_id = ? AND pr.status IN ('pending', 'waiting')""",
        (user_id,),
    ):
        items.append({
            "kind": "request", "id": r["id"], "title": r["from_name"],
            "created_at": r["created_at"], "meta": {"first_message": r["first_message"]},
        })

    items.sort(key=lambda it: it["created_at"] or "", reverse=True)
    return items[:limit]
