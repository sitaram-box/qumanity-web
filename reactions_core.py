"""Shared message reactions -- Agree / Disagree / Read -- for group chats (village sub-groups and
Personal groups), and (2026-10-17) for Council Update board posts (scope 'board_post', message_id
= the board_posts.id) -- a council update is never voted on, so Agree/Disagree is the only signal
a member can leave on one; rendered as thumbs up/down in static/js/board.js, which hardcodes its
own emoji rather than importing this module's EMOJI dict (EMOJI is otherwise unused). Reactions
are deliberately separate from post voting (+1/0/-1): they never change a score or elevate
anything, they just show how many of a group's members have weighed in or seen a message/post.
One reaction per person per item; picking a new one replaces the old, and it can be cleared.

Every function here is intentionally scope-agnostic -- the only place 'board_post' is enforced as
a valid scope (alongside 'subgroup'/'personal') is the route whitelist in app.py's
api_set_reaction(), plus one additional check there specific to 'board_post': the target id must
actually be a council_update post, since that's the only post_kind that ever displays reactions.
"""
from __future__ import annotations

import cycle_middleware

KINDS = ("agree", "disagree", "read")
EMOJI = {"agree": "\U0001F44D", "disagree": "\U0001F44E", "read": "\U0001F441️"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS message_reactions (
    scope TEXT NOT NULL,        -- 'subgroup' (board_messages) | 'personal' (personal_messages) | 'board_post' (council_update board_posts, 2026-10-17)
    message_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    reaction TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (scope, message_id, user_id)
);
"""


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def set_reaction(conn, scope, message_id, user_id, reaction):
    """reaction is one of KINDS, or None/"" to clear the user's reaction."""
    ensure_tables(conn)
    if not reaction:
        conn.execute("DELETE FROM message_reactions WHERE scope=? AND message_id=? AND user_id=?", (scope, message_id, user_id))
    else:
        if reaction not in KINDS:
            raise ValueError("Unknown reaction")
        import datetime as dt
        conn.execute(
            "INSERT INTO message_reactions (scope, message_id, user_id, reaction, created_at, cycle_id) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(scope, message_id, user_id) DO UPDATE SET reaction=excluded.reaction, created_at=excluded.created_at, cycle_id=excluded.cycle_id",
            (scope, message_id, user_id, reaction, dt.datetime.now(dt.timezone.utc).isoformat(), cycle_middleware.get_active_cycle_id(conn)),
        )
    conn.commit()


def counts_for(conn, scope, message_ids, viewer_id):
    """{message_id: {"agree": n, "disagree": n, "read": n, "mine": <kind>|None}} for a batch of messages."""
    ensure_tables(conn)
    out = {mid: {"agree": 0, "disagree": 0, "read": 0, "mine": None} for mid in message_ids}
    if not message_ids:
        return out
    qmarks = ",".join("?" * len(message_ids))
    for r in conn.execute(f"SELECT message_id, user_id, reaction FROM message_reactions WHERE scope=? AND message_id IN ({qmarks})",
                          (scope, *message_ids)):
        out[r["message_id"]][r["reaction"]] += 1
        if r["user_id"] == viewer_id:
            out[r["message_id"]]["mine"] = r["reaction"]
    return out
