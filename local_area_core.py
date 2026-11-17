"""Local Areas (2026-11-18): sub-divisions WITHIN a village -- a membership/identity layer only,
like a neighborhood WhatsApp group. They carry no Collective Board of their own; posting, voting
and Qoins all still happen on the Village board exactly as before (Decision 2 of this feature's
approved architecture). A village's Q-Punch Nayak/Nayika (or the Founder, as the universal
fallback every admin-gated action in this codebase already has) creates and administers Local
Areas; the Mentor role is a documented NO-OP here -- it doesn't exist anywhere in this codebase yet
(still [DESIGN GOAL] in the white paper's own Key Features table), so it is deliberately left out
of every permission check below rather than half-wired against a role with no real data behind it.
Wire it in alongside Nayak/Nayika once Mentor itself is built.

Membership rules (Decision-locked, not open questions):
  - A user is in at most ONE Local Area at a time (status='active' in local_area_members).
  - The FIRST join is free (join_local_area()) -- a user with no local_area_members row at all yet.
  - Every join after that (moving to a different Local Area, or rejoining one left earlier) is a
    hard lock: it must go through request_move()/decide_move_request(), approved by the village's
    Nayak/Nayika or the Founder, never self-service.
  - leave_local_area() drops a member back to "no Local Area" (the general Village group, which
    needs no code here -- it's just the absence of an active row), but does NOT clear the lock:
    their very next join attempt still needs request_move(), same as any other post-first-join
    move. There is no "free re-join."

Local Areas are scoped under a village_id (a leaf of the existing 8-level geography), never a new
level of their own -- a straight foreign key to the same village location_id strings the rest of
the codebase already uses (board_core.py's group_id, users.present_location_json's village.id),
not a new geography table.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

import announcements_core

SCHEMA = """
CREATE TABLE IF NOT EXISTS local_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (village_id, name)
);
CREATE INDEX IF NOT EXISTS idx_local_areas_village ON local_areas(village_id);

CREATE TABLE IF NOT EXISTS local_area_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_area_id INTEGER NOT NULL REFERENCES local_areas(id),
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    joined_at TEXT NOT NULL,
    left_at TEXT,
    UNIQUE (user_id, local_area_id)
);
CREATE INDEX IF NOT EXISTS idx_local_area_members_user ON local_area_members(user_id, status);
CREATE INDEX IF NOT EXISTS idx_local_area_members_area ON local_area_members(local_area_id, status);

CREATE TABLE IF NOT EXISTS local_area_move_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    from_local_area_id INTEGER,
    to_local_area_id INTEGER NOT NULL,
    village_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    decided_by_user_id INTEGER,
    requested_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_local_area_move_requests_user ON local_area_move_requests(user_id, status);
CREATE INDEX IF NOT EXISTS idx_local_area_move_requests_village ON local_area_move_requests(village_id, status);

CREATE TABLE IF NOT EXISTS local_area_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_area_id INTEGER NOT NULL REFERENCES local_areas(id),
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_local_area_messages_area ON local_area_messages(local_area_id, id);
"""


def ensure_tables(conn) -> None:
    """Defensive mirror of migrations/043_local_areas.py, same self-healing convention every
    *_core.py module in this codebase follows -- a throwaway test DB (or a database a migration
    hasn't reached yet) self-heals instead of crashing on a missing table."""
    conn.executescript(SCHEMA)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _is_village_admin(conn, user_id: int, village_id: str, is_admin: bool) -> bool:
    """Founder (is_admin, passed in by the Flask route -- app.py's own _is_admin(), same pattern
    announcements_core.can_publish_announcement() already uses for this exact distinction) or the
    village's current Q-Punch Nayak/Nayika (announcements_core.is_council_member(), reused rather
    than reimplemented). Mentor is NOT checked here -- see this module's own docstring."""
    return bool(is_admin) or announcements_core.is_council_member(conn, user_id, village_id, "village")


def create_local_area(conn, user_id: int, village_id: str, name: str, is_admin: bool) -> int:
    """Only the village's Nayak/Nayika or the Founder may create a Local Area (Rule 1). Raises
    ValueError for a blank name or a duplicate name within the same village (local_areas' own
    UNIQUE(village_id, name) -- caught and re-raised as a clear message, not a raw IntegrityError)."""
    ensure_tables(conn)
    name = (name or "").strip()
    if not name:
        raise ValueError("A name is required")
    if not _is_village_admin(conn, user_id, village_id, is_admin):
        raise PermissionError("Only the Village Q-Punch (Nayak/Nayika) or the Founder can create a Local Area")
    try:
        cur = conn.execute(
            "INSERT INTO local_areas (village_id, name, created_by_user_id, created_at) VALUES (?, ?, ?, ?)",
            (village_id, name, user_id, _now()),
        )
    except sqlite3.IntegrityError:
        raise ValueError("A Local Area with this name already exists in this village")
    conn.commit()
    return cur.lastrowid


def list_local_areas(conn, user_id: int, village_id: str, is_admin: bool) -> dict:
    """Every Local Area in a village, with its current active member count, PLUS (2026-11-18, the
    Phone App's own gaps) three fields the caller can't otherwise derive from the list alone:
    my_local_area_id/my_pending_move_to are reported once at the top level, not repeated on every
    row, since each is a single fact about the CALLER, not about any one Local Area; can_manage is
    the same Founder-or-Nayak/Nayika check create_local_area()/decide_move_request() already
    enforce, surfaced here so the app knows whether to show admin actions at all before the user
    even tries one and gets a 403."""
    ensure_tables(conn)
    rows = conn.execute(
        """SELECT la.id, la.name, la.village_id, la.created_at,
                  (SELECT COUNT(*) FROM local_area_members m
                   WHERE m.local_area_id = la.id AND m.status = 'active') AS member_count
           FROM local_areas la WHERE la.village_id = ? ORDER BY la.name""",
        (village_id,),
    ).fetchall()
    mine = conn.execute(
        "SELECT local_area_id FROM local_area_members WHERE user_id = ? AND status = 'active'", (user_id,)
    ).fetchone()
    pending = conn.execute(
        "SELECT to_local_area_id FROM local_area_move_requests WHERE user_id = ? AND status = 'pending'", (user_id,)
    ).fetchone()
    return {
        "local_areas": [dict(r) for r in rows],
        "my_local_area_id": mine["local_area_id"] if mine else None,
        "my_pending_move_to": pending["to_local_area_id"] if pending else None,
        "can_manage": _is_village_admin(conn, user_id, village_id, is_admin),
    }


def members_of(conn, local_area_id: int) -> list[dict]:
    """The Local Area's own member list, for its group page."""
    ensure_tables(conn)
    if not conn.execute("SELECT 1 FROM local_areas WHERE id = ?", (local_area_id,)).fetchone():
        raise LookupError("Local Area not found")
    rows = conn.execute(
        """SELECT m.user_id, m.joined_at, u.name
           FROM local_area_members m JOIN users u ON u.id = m.user_id
           WHERE m.local_area_id = ? AND m.status = 'active' ORDER BY m.joined_at""",
        (local_area_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_pending_move_requests(conn, user_id: int, village_id: str, is_admin: bool) -> list[dict]:
    """Every pending move request in a village, for the admin's own approve/deny screen
    (2026-11-18, the Phone App's own gap) -- gated by the SAME can_manage check list_local_areas()
    already reports, re-verified here rather than trusted from the client."""
    ensure_tables(conn)
    if not _is_village_admin(conn, user_id, village_id, is_admin):
        raise PermissionError("Only the Village Q-Punch (Nayak/Nayika) or the Founder can view pending move requests")
    rows = conn.execute(
        """SELECT r.id, r.user_id, u.name AS user_name,
                  r.from_local_area_id, fla.name AS from_name,
                  r.to_local_area_id, tla.name AS to_name, r.requested_at
           FROM local_area_move_requests r
           JOIN users u ON u.id = r.user_id
           LEFT JOIN local_areas fla ON fla.id = r.from_local_area_id
           JOIN local_areas tla ON tla.id = r.to_local_area_id
           WHERE r.village_id = ? AND r.status = 'pending'
           ORDER BY r.requested_at""",
        (village_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Local Area chat (2026-11-18, replacing the older Village sub-group chat for this purpose):
# its own dedicated message table, not a reuse of board_core's subgroups/board_messages -- a Local
# Area isn't a subgroup (different creation gate, different membership model, no join-approval
# queue of its own), and overloading one id column to mean two different things would need its own
# discriminator column for no real benefit. Mirrors board_core.py's chat SHAPE (same message dict
# fields, same is_admin-always-can-chat override), not its storage. ----

def _can_chat(conn, user_id: int, local_area_id: int, village_id: str, is_admin: bool) -> bool:
    if _is_village_admin(conn, user_id, village_id, is_admin):
        return True
    return bool(conn.execute(
        "SELECT 1 FROM local_area_members WHERE local_area_id = ? AND user_id = ? AND status = 'active'",
        (local_area_id, user_id),
    ).fetchone())


def chat_messages(conn, user_id: int, local_area_id: int, is_admin: bool) -> dict:
    """The last 100 messages, oldest first (board_core.chat_messages()'s own convention). Only a
    currently-ACTIVE member of THIS Local Area may read it -- someone who left, or who's active in
    a different one, is refused the same as a stranger, matching Rule 4's "returns them to just the
    general Village group" (no Local Area chat access at all, not read-only access to their old one)."""
    ensure_tables(conn)
    local_area = conn.execute("SELECT id, name, village_id FROM local_areas WHERE id = ?", (local_area_id,)).fetchone()
    if not local_area:
        raise LookupError("Local Area not found")
    if not _can_chat(conn, user_id, local_area_id, local_area["village_id"], is_admin):
        raise PermissionError("Only members of this Local Area can read its chat")
    rows = list(reversed(conn.execute(
        """SELECT m.id, m.text, m.created_at, m.user_id, u.name, u.gender, u.account_id,
                  u.profile_picture IS NOT NULL AS has_picture
           FROM local_area_messages m JOIN users u ON u.id = m.user_id
           WHERE m.local_area_id = ? ORDER BY m.id DESC LIMIT 100""",
        (local_area_id,),
    ).fetchall()))
    return {
        "id": local_area["id"], "name": local_area["name"],
        "messages": [
            {"id": r["id"], "who": r["name"], "user_id": r["user_id"], "gender": r["gender"],
             "profile_picture_url": f"/api/users/{r['user_id']}/profile-picture" if r["has_picture"] else None,
             "account_id": r["account_id"], "mine": r["user_id"] == user_id,
             "text": r["text"], "at": r["created_at"]}
            for r in rows
        ],
    }


def send_message(conn, user_id: int, local_area_id: int, text: str, is_admin: bool) -> None:
    """Same membership gate as chat_messages() -- a left member or an outsider cannot post either."""
    ensure_tables(conn)
    local_area = conn.execute("SELECT village_id FROM local_areas WHERE id = ?", (local_area_id,)).fetchone()
    if not local_area:
        raise LookupError("Local Area not found")
    if not _can_chat(conn, user_id, local_area_id, local_area["village_id"], is_admin):
        raise PermissionError("Only members of this Local Area can send messages in its chat")
    text = (text or "").strip()
    if not text or len(text) > 1000:
        raise ValueError("Write a message (up to 1000 characters)")
    conn.execute(
        "INSERT INTO local_area_messages (local_area_id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
        (local_area_id, user_id, text, _now()),
    )
    conn.commit()


def _present_village_id(present_location: dict) -> str | None:
    return (present_location.get("village") or {}).get("id")


def join_local_area(conn, user_id: int, local_area_id: int, present_location: dict) -> dict:
    """The FIRST, free join (Rule 2/3) -- a user with no local_area_members row at all yet, for a
    Local Area in the village they currently, actually live in (Rule 5). Every join after this one
    is a hard lock: refused here with a clear message pointing at request_move() instead."""
    ensure_tables(conn)
    local_area = conn.execute("SELECT village_id FROM local_areas WHERE id = ?", (local_area_id,)).fetchone()
    if not local_area:
        raise LookupError("Local Area not found")
    present_village_id = _present_village_id(present_location)
    if not present_village_id or present_village_id != local_area["village_id"]:
        raise ValueError("You can only join a Local Area in the village you currently live in")
    if conn.execute("SELECT 1 FROM local_area_members WHERE user_id = ? AND status = 'active'", (user_id,)).fetchone():
        raise ValueError("You're already in a Local Area — use Request Move to change it")
    if conn.execute("SELECT 1 FROM local_area_members WHERE user_id = ?", (user_id,)).fetchone():
        raise ValueError("You've been in a Local Area before — joining again needs the Village Q-Punch's approval; use Request Move instead")
    conn.execute(
        "INSERT INTO local_area_members (local_area_id, user_id, status, joined_at) VALUES (?, ?, 'active', ?)",
        (local_area_id, user_id, _now()),
    )
    conn.commit()
    return {"local_area_id": local_area_id}


def request_move(conn, user_id: int, to_local_area_id: int, present_location: dict) -> dict:
    """Queues a move request (Rule 3) -- covers both "moving from one Local Area to another" and
    "rejoining after a leave," since leave_local_area() never clears the lock. Idempotent on an
    exact duplicate pending request, same reusing-not-rejecting style as family_core.
    request_join_group()."""
    ensure_tables(conn)
    to_local_area = conn.execute("SELECT village_id FROM local_areas WHERE id = ?", (to_local_area_id,)).fetchone()
    if not to_local_area:
        raise LookupError("Local Area not found")
    present_village_id = _present_village_id(present_location)
    if not present_village_id or present_village_id != to_local_area["village_id"]:
        raise ValueError("You can only move to a Local Area in the village you currently live in")
    current = conn.execute(
        "SELECT local_area_id FROM local_area_members WHERE user_id = ? AND status = 'active'", (user_id,)
    ).fetchone()
    from_local_area_id = current["local_area_id"] if current else None
    if from_local_area_id == to_local_area_id:
        raise ValueError("You're already in this Local Area")
    existing = conn.execute(
        "SELECT id FROM local_area_move_requests WHERE user_id = ? AND to_local_area_id = ? AND status = 'pending'",
        (user_id, to_local_area_id),
    ).fetchone()
    if existing:
        return {"request_id": existing["id"], "status": "already_pending"}
    cur = conn.execute(
        """INSERT INTO local_area_move_requests
           (user_id, from_local_area_id, to_local_area_id, village_id, status, requested_at)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (user_id, from_local_area_id, to_local_area_id, to_local_area["village_id"], _now()),
    )
    conn.commit()
    return {"request_id": cur.lastrowid, "status": "created"}


def decide_move_request(conn, admin_user_id: int, request_id: int, decision: str, is_admin: bool) -> None:
    """The village's Nayak/Nayika or the Founder approves or denies a pending move request (Rule 3).
    On approval: the old active membership (if any) moves to 'left', and the target Local Area
    membership is (re)activated -- the same ON CONFLICT re-activation local_area_members' own
    UNIQUE(user_id, local_area_id) is built for, since a user rejoining a Local Area they were once
    a member of hits the same row a second time, not a fresh insert."""
    ensure_tables(conn)
    if decision not in ("approve", "deny"):
        raise ValueError("Unknown decision")
    req = conn.execute("SELECT * FROM local_area_move_requests WHERE id = ?", (request_id,)).fetchone()
    if not req:
        raise LookupError("Request not found")
    if req["status"] != "pending":
        raise ValueError("This request has already been decided")
    if not _is_village_admin(conn, admin_user_id, req["village_id"], is_admin):
        raise PermissionError("Only the Village Q-Punch (Nayak/Nayika) or the Founder can decide this")
    if decision == "approve":
        if req["from_local_area_id"]:
            conn.execute(
                "UPDATE local_area_members SET status = 'left', left_at = ? "
                "WHERE local_area_id = ? AND user_id = ? AND status = 'active'",
                (_now(), req["from_local_area_id"], req["user_id"]),
            )
        conn.execute(
            """INSERT INTO local_area_members (local_area_id, user_id, status, joined_at)
               VALUES (?, ?, 'active', ?)
               ON CONFLICT(user_id, local_area_id) DO UPDATE SET status = 'active', joined_at = excluded.joined_at, left_at = NULL""",
            (req["to_local_area_id"], req["user_id"], _now()),
        )
    conn.execute(
        "UPDATE local_area_move_requests SET status = ?, decided_by_user_id = ?, decided_at = ? WHERE id = ?",
        ("approved" if decision == "approve" else "denied", admin_user_id, _now(), request_id),
    )
    conn.commit()


def leave_local_area(conn, user_id: int) -> None:
    """Drops the member back to "no Local Area" (Rule 4) -- the general Village group needs no
    action here, since it's simply the absence of an active row. Does NOT clear the lock: their
    membership row stays in the table (status='left'), so their next join attempt still finds it
    and is refused by join_local_area() in favour of request_move()."""
    ensure_tables(conn)
    row = conn.execute("SELECT local_area_id FROM local_area_members WHERE user_id = ? AND status = 'active'", (user_id,)).fetchone()
    if not row:
        raise ValueError("You're not currently in a Local Area")
    conn.execute(
        "UPDATE local_area_members SET status = 'left', left_at = ? WHERE user_id = ? AND status = 'active'",
        (_now(), user_id),
    )
    conn.commit()
