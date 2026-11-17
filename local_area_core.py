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


def list_local_areas(conn, village_id: str) -> list[dict]:
    """Every Local Area in a village, with its current active member count."""
    ensure_tables(conn)
    rows = conn.execute(
        """SELECT la.id, la.name, la.village_id, la.created_at,
                  (SELECT COUNT(*) FROM local_area_members m
                   WHERE m.local_area_id = la.id AND m.status = 'active') AS member_count
           FROM local_areas la WHERE la.village_id = ? ORDER BY la.name""",
        (village_id,),
    ).fetchall()
    return [dict(r) for r in rows]


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
