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
import re

QMAIL_USERNAME_RE = re.compile(r"^[a-z0-9._-]{8,15}$")
FORWARD_WINDOW_DAYS = 30
DOMAIN = "qumanity.in"


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
    """Resolves a Qmail address to a user_id -- current addresses always resolve; an old
    (is_current=0) address resolves only while its forward_until is still in the future. Returns
    None if the address is unknown, or if it's old and its forward window has lapsed. The one
    place compose's `to` field (and nothing else) does its final lookup, so an old address can
    never be trusted past its 30-day window no matter which route is asking."""
    row = conn.execute(
        "SELECT user_id, is_current, forward_until FROM qmail_addresses WHERE full_address = ?",
        (full_address,),
    ).fetchone()
    if not row:
        return None
    if row["is_current"]:
        return row["user_id"]
    if row["forward_until"] and row["forward_until"] > _now():
        return row["user_id"]
    return None


def current_address(conn, user_id: int):
    """This user's current Qmail address, or None if they haven't activated (or, defensively,
    have no is_current=1 row for some other reason)."""
    row = conn.execute(
        "SELECT full_address FROM qmail_addresses WHERE user_id = ? AND is_current = 1", (user_id,)
    ).fetchone()
    return row["full_address"] if row else None
