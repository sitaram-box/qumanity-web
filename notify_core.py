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
    if kind not in ("private", "group"):
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

    def is_unread(r):
        return bool(r["last_msg"]) and (not r["last_read"] or r["last_msg"] > r["last_read"])

    unread_private = sum(1 for r in private_rows if is_unread(r))
    unread_groups = sum(1 for r in group_rows if is_unread(r))
    pending_requests = conn.execute(
        "SELECT COUNT(*) FROM people_requests WHERE to_user_id = ? AND status IN ('pending', 'waiting')", (user_id,)
    ).fetchone()[0]

    return {
        "unread_chats": unread_private + unread_groups,
        "unread_private": unread_private,
        "unread_groups": unread_groups,
        "pending_requests": pending_requests,
        "total": unread_private + unread_groups + pending_requests,
    }
