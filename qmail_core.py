"""Qmail (2026-10-18): an internal-messaging identity layered on top of each member's Account ID.

Not a real mailbox. @qumanity.in is an addressing convention for messages that stay inside
Qumanity -- there is no inbound or outbound internet mail delivery anywhere in this system, and
the activation UI must say so plainly so no member expects outside mail to arrive here. A later
phase could add real inbound receiving through a chosen mail provider; this module doesn't do
that, and isn't built to make adding it later any harder, either.

An address is [qmail_username]-[account_id]@qumanity.in. The username (users.qmail_username) is
chosen once at activation, globally unique, and never changes. The account_id half changes
whenever social_core.regenerate_account_id() runs -- the one place (not duplicated here) that
mints a fresh qmail_addresses row for an activated user, keeping Qmail in sync with Account ID
the same way both present_location-change paths (app.py) now share that one function instead of
two divergent ones.
"""
from __future__ import annotations

import datetime as dt
import os
import re

QMAIL_USERNAME_RE = re.compile(r"^[a-z0-9._-]{8,15}$")
FORWARD_WINDOW_DAYS = 30
DOMAIN = "qumanity.in"

# Q-Punch council addresses (2026-10-18): a location, not a member, gets an address once its
# real member count crosses its level's threshold. village/tehsil thresholds are reachable with
# this project's current pilot-scale membership; state and above are not, today -- built anyway,
# since an unreachable threshold costs nothing (the location simply never gets a row).
QPUNCH_THRESHOLDS = {
    "village": 5,
    "tehsil": 10,
    "district": 100,
    "state": 1_000,
    "zone": 10_000,
    "country": 100_000,
    "continent": 1_000_000,
    "earth": 10_000_000,
}
# Only village has real elected data (village_council) -- same documented gap as
# reports_core.is_holder_council()/announcements_core.is_council_member(). A council address
# above village exists and is displayed (see docs/QMAIL.md) but resolve_address() never delivers
# to it. One constant, read by both resolve_address() (delivery) and the board-line renderer
# (display) -- not two independently-maintained gates that could drift apart.
QPUNCH_REACHABLE_LEVELS = {"village"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def validate_username(raw: str) -> str:
    """Lowercases and validates a candidate username: 8-15 characters, letters/numbers/'.'/'_'/'-'
    only -- narrower than a bare email RFC would technically allow, deliberately, since most of
    what's technically legal in a local-part behaves inconsistently across real mail clients and
    this address is meant to actually work everywhere it's shown. Raises ValueError (the route
    turns it into a 400) on any violation. Returns the normalized username on success. Does NOT
    check uniqueness -- that needs a DB connection, so it's activate()'s job."""
    normalized = (raw or "").strip().lower()
    if not QMAIL_USERNAME_RE.fullmatch(normalized):
        raise ValueError(
            "Username must be 8-15 characters: letters, numbers, dots, underscores or hyphens only."
        )
    return normalized


def build_full_address(username: str, account_id: str) -> str:
    return f"{username}-{account_id}@{DOMAIN}"


def activate(conn, user_id: int, raw_username: str) -> str:
    """Validates and claims `raw_username` for this user, mints their first qmail_addresses row at
    their current account_id. Raises ValueError if the username is malformed, already taken by
    ANY user (including, redundantly but safely, a second attempt by this same user with a
    different account_id -- the uniqueness check is on the username string alone, which is the
    whole point: two users can never share one, regardless of what their account_id happens to
    be), or this user has already activated (one-time; usernames don't change). Returns the new
    full address."""
    existing = conn.execute("SELECT qmail_username FROM users WHERE id = ?", (user_id,)).fetchone()
    if existing and existing["qmail_username"]:
        raise ValueError("Qmail is already activated for this account.")
    username = validate_username(raw_username)
    if conn.execute("SELECT 1 FROM users WHERE qmail_username = ?", (username,)).fetchone():
        raise ValueError("That username is already taken.")

    user = conn.execute("SELECT account_id FROM users WHERE id = ?", (user_id,)).fetchone()
    full_address = build_full_address(username, user["account_id"])
    conn.execute("UPDATE users SET qmail_username = ? WHERE id = ?", (username, user_id))
    conn.execute(
        "INSERT INTO qmail_addresses (user_id, account_id, full_address, is_current, created_at) "
        "VALUES (?, ?, ?, 1, ?)",
        (user_id, user["account_id"], full_address, _now()),
    )
    conn.commit()
    return full_address


def resolve_address(conn, full_address: str):
    """Resolves a Qmail address and tells the caller how to deliver to it -- not just who to.
    Returns one of:

      - None: the address is unknown outright, or known but not currently reachable (a Q-Punch
        address above village level -- see docs/QMAIL.md).
      - {"kind": "member", "user_ids": [user_id]}: a regular member address. Deliver by
        inserting into qmail_messages, same as always.
      - {"kind": "council", "level", "location_id", "user_ids": [...]}: a village council
        address. Deliver by inserting into qpunch_queue_messages INSTEAD -- never into
        qmail_messages, regardless of how many heads currently serve. user_ids is who currently
        holds the seat (both heads, or the admin fallback if it's empty) -- kept here for
        display/notification use, not for message fan-out: a council message has exactly one
        recipient, the location's shared queue, not each individual head.

    This is a real change from an earlier version of this function, which returned a bare
    list[int] for both kinds and left fan-out to the caller. That shape stopped making sense once
    a council message's storage requirement (docs/QMAIL.md) turned out to be "one row in a
    location-scoped queue table," not "one row per current head in qmail_messages" -- the kind
    tag exists so compose's routing decision has a single, explicit source instead of inferring
    it from whether the address happened to look like a council address.

    Checked in order: qpunch_addresses first, then qmail_addresses. Both are a single
    exact-string lookup against the stored full_address -- no parsing, no hyphen-splitting, no
    inference from the address's shape (see docs/QMAIL.md's note on why there is no username
    guard: resolve_address never parses an address, so there is no shape for a member's username
    to accidentally collide with). The one place compose's `to` field does its final lookup, so
    neither an old member address past its forward window nor a not-yet-reachable council address
    can ever be trusted no matter which route is asking."""
    qpunch_row = conn.execute(
        "SELECT level, location_id FROM qpunch_addresses WHERE full_address = ?", (full_address,)
    ).fetchone()
    if qpunch_row:
        if qpunch_row["level"] not in QPUNCH_REACHABLE_LEVELS:
            return None
        return {
            "kind": "council",
            "level": qpunch_row["level"],
            "location_id": qpunch_row["location_id"],
            "user_ids": _current_council_recipients(conn, qpunch_row["location_id"]),
        }

    row = conn.execute(
        "SELECT user_id, is_current, forward_until FROM qmail_addresses WHERE full_address = ?",
        (full_address,),
    ).fetchone()
    if not row:
        return None
    if row["is_current"]:
        return {"kind": "member", "user_ids": [row["user_id"]]}
    if row["forward_until"] and row["forward_until"] > _now():
        return {"kind": "member", "user_ids": [row["user_id"]]}
    return None


def _current_council_recipients(conn, village_id: str) -> list[int]:
    """Whoever currently holds this village's council seat -- both heads, if both are serving --
    or the admin fallback if the seat is empty (no election held yet, or between terms). Same
    precedent as reports_core.is_holder_council(): every level past village has no real elected
    data, but this is only ever reached for a village address (resolve_address already rejects
    every other level before calling this), so that gap doesn't apply here. Returns [] only if
    even the admin fallback can't resolve -- a prototype misconfiguration (QM_ADMIN_PRIVATE_IDS
    unset or stale), reported to the sender the same way an unknown address is."""
    today = dt.date.today().isoformat()
    row = conn.execute(
        """SELECT male_head_user_id, female_head_user_id FROM village_council
           WHERE village_id = ? AND leadership_start <= ? AND leadership_end >= ?
           ORDER BY year DESC LIMIT 1""",
        (village_id, today, today),
    ).fetchone()
    heads = [uid for uid in ((row["male_head_user_id"], row["female_head_user_id"]) if row else ()) if uid]
    if heads:
        return heads
    return _admin_fallback_user_ids(conn)


def _admin_fallback_user_ids(conn) -> list[int]:
    """The Founder/Admin's user id(s), by the same QM_ADMIN_PRIVATE_IDS env var app.py's own
    _is_admin() checks -- read directly here rather than through a session, since resolving a
    council address's recipient has nothing to do with who is currently logged in (the sender
    and the recipient are never the same request). Empty list if nothing is configured or no
    matching user exists."""
    allowed = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not allowed:
        return []
    placeholders = ",".join("?" for _ in allowed)
    rows = conn.execute(
        f"SELECT id FROM users WHERE private_id_9digit IN ({placeholders})", tuple(allowed)
    ).fetchall()
    return [r["id"] for r in rows]


def build_qpunch_address(level: str, location_id: str) -> str:
    return f"{level}-{location_id}@{DOMAIN}"


def sync_qpunch_addresses(conn, totals: dict) -> list:
    """Creates a qpunch_addresses row for every (location_id, location_type) in `totals` that has
    just crossed its level's QPUNCH_THRESHOLDS value and doesn't have one yet. Permanent once
    created -- never retired, never reactivated, regardless of what the count does afterward (see
    docs/QMAIL.md). `totals` is {(location_id, location_type): total_users}, the same keying
    elemental_core.recompute_location_elements() already tallies in. Returns the list of
    (level, location_id) pairs created, for the caller to report. Caller commits (or rolls back,
    for a dry run) -- this function only executes, so it shares that transaction."""
    created = []
    now = _now()
    for (location_id, location_type), total in totals.items():
        threshold = QPUNCH_THRESHOLDS.get(location_type)
        if threshold is None or total < threshold:
            continue
        if conn.execute(
            "SELECT 1 FROM qpunch_addresses WHERE level = ? AND location_id = ?",
            (location_type, location_id),
        ).fetchone():
            continue
        full_address = build_qpunch_address(location_type, location_id)
        conn.execute(
            "INSERT INTO qpunch_addresses (level, location_id, full_address, created_at) VALUES (?, ?, ?, ?)",
            (location_type, location_id, full_address, now),
        )
        created.append((location_type, location_id))
    return created


def current_address(conn, user_id: int):
    """This user's current Qmail address, or None if they haven't activated (or, defensively,
    have no is_current=1 row for some other reason)."""
    row = conn.execute(
        "SELECT full_address FROM qmail_addresses WHERE user_id = ? AND is_current = 1", (user_id,)
    ).fetchone()
    return row["full_address"] if row else None
