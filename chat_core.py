"""Unified Chat Architecture, Phase 2 Step 1 (2026-11-24): the read-side aggregator across
Qumanity's existing messaging systems (private 1:1 chats, Personal Groups, Family Tree unit chats,
Village/Local Area/Governance Channel chats), the generalized Governance Channel creation rules,
and the dual Account ID logic for temporary cross-location access.

This is deliberately a NEW, thin module sitting ABOVE the existing ones -- not a rewrite of any of
them. Six messaging systems already exist, each with its own table shape and permission model
(private_chats/personal_groups in social_core.py, family_group_members in family_core.py,
subgroups in board_core.py, local_areas in local_area_core.py); migrating them into one unified
storage schema would be a large, risky rewrite touching every existing route and the mobile
client at once, for what is actually a DISPLAY problem, not a storage one. list_my_conversations()
below is the one new thing that actually needs building: a normalized read across all of them.

Governance Channel creation (2026-11-24 Phase 2 decision):
  - Village level: only the village's Q-Punch Nayak/Nayika or the Founder may create one, exactly
    like local_area_core.create_local_area()'s own rule -- reused here (see can_create_channel()),
    not reimplemented. No vote needed; a village already has an elected authority for this.
  - Tehsil and above: there is no elected authority at these levels yet anywhere in this codebase
    (announcements_core.is_council_member() itself returns False above village -- "every other
    level has no elected-council data model yet"). Creating a channel there instead requires an
    already-PASSED People's Vote (election_core.initiate_people_vote()/cast_people_vote()/
    tally_people_vote() -- the Upper House's own existing, generic "ask the population anything"
    power) at that EXACT (level, location_id). subgroups.created_via_vote_id records which vote
    authorized which channel, both as an audit trail and to stop the same passed vote being spent
    on a second channel.

Dual Account ID (2026-11-24 Phase 2 decision): a user's single, permanent Account ID
(users.account_id / social_core.account_ids, one CURRENT row at a time) is a MOVE record -- it
must never be repurposed for a temporary, simultaneous second identity. Temporary cross-location
access is instead its own table (temporary_location_access) with its own minted, independently
unique account_id string, resolved at read time by account_id_for_context() -- home account_id
unless an ACTIVE temporary grant exists for that exact (location_level, location_id), in which
case the foreign one. Wiring this resolver into how a Governance Channel message's account_id is
actually DISPLAYED (board_core.chat_messages() currently always joins live to the sender's home
users.account_id) is deliberately left for the Step 2/3 UI work, once a channel's chat route
actually has a location context to resolve against -- not done here, to avoid board_core.py
importing this module (it already needs to be importable FROM board_core-adjacent routes, and
board_core.py must not import chat_core.py back, or the two modules import each other).

Presence (2026-11-24): users.last_seen_at is touched on every authenticated request (a new
app.py after_request hook) -- computed-live status (Green/Yellow/Grey), never a separately stored
status column, matching this codebase's own repeated "compute live, never trust a stale snapshot"
convention (account_core.account_access_type(), family_core._node_dob(), dormancy checks all work
this way). users.presence_override is the one piece that CAN'T be computed live -- Red/Busy is a
user-DECLARED state, not activity-derived.
"""
from __future__ import annotations

import datetime as dt
import json

import announcements_core
import board_core
import id_generator
import local_area_core

PRESENCE_GREEN_MINUTES = 2
PRESENCE_YELLOW_MINUTES = 15
PRESENCE_BUSY_HOURS = 4  # how long a user-set "Busy" override lasts before it's treated as expired

SCHEMA = """
CREATE TABLE IF NOT EXISTS temporary_location_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    location_level TEXT NOT NULL,
    location_id TEXT NOT NULL,
    foreign_account_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | active | revoked | expired
    requested_at TEXT NOT NULL,
    decided_by_user_id INTEGER,
    decided_at TEXT,
    expires_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_temp_access_user ON temporary_location_access(user_id, status);
-- At most one pending-or-active grant per (user, location) -- a second request waits for the
-- first to resolve rather than queueing a duplicate.
CREATE UNIQUE INDEX IF NOT EXISTS idx_temp_access_one_live ON temporary_location_access(user_id, location_level, location_id)
    WHERE status IN ('pending', 'active');
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "last_seen_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")
    if "presence_override" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN presence_override TEXT")  # NULL | 'busy'
    if "presence_override_at" not in user_cols:
        # When the override was SET, so it can auto-expire (PRESENCE_BUSY_HOURS) -- without this,
        # a "Busy" a user forgot to clear would stay Red forever, defeating the whole point of a
        # computed-live status.
        conn.execute("ALTER TABLE users ADD COLUMN presence_override_at TEXT")
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def touch_presence(conn, user_id: int) -> None:
    """Called from the after_request hook on every authenticated request -- the one write this
    whole feature costs. Never raises; presence is advisory, never allowed to break a real
    request."""
    conn.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (_now(), user_id))
    conn.commit()


def set_presence_override(conn, user_id: int, busy: bool) -> None:
    """The one presence state that can't be computed live -- the user explicitly declaring
    themselves Busy (or clearing it). Auto-expires after PRESENCE_BUSY_HOURS -- see
    presence_status()'s own handling of a stale override."""
    conn.execute(
        "UPDATE users SET presence_override = ?, presence_override_at = ? WHERE id = ?",
        ("busy" if busy else None, _now() if busy else None, user_id),
    )
    conn.commit()


def presence_status(conn, user_id: int, now: dt.datetime | None = None) -> str:
    """'green' | 'yellow' | 'grey' | 'red'. Computed live from last_seen_at/presence_override --
    never a stored status column, see this module's own docstring on why. `now` is injectable
    (defaults to the real current time) purely for deterministic testing -- the same convention
    election_core.py's own today= parameters already use throughout this codebase, rather than a
    test having to sleep for real minutes."""
    row = conn.execute("SELECT last_seen_at, presence_override, presence_override_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return "grey"
    now = now or dt.datetime.now(dt.timezone.utc)
    if row["presence_override"] == "busy" and row["presence_override_at"]:
        set_at = dt.datetime.fromisoformat(row["presence_override_at"])
        if (now - set_at) < dt.timedelta(hours=PRESENCE_BUSY_HOURS):
            return "red"
    if not row["last_seen_at"]:
        return "grey"
    last_seen = dt.datetime.fromisoformat(row["last_seen_at"])
    age = now - last_seen
    if age < dt.timedelta(minutes=PRESENCE_GREEN_MINUTES):
        return "green"
    if age < dt.timedelta(minutes=PRESENCE_YELLOW_MINUTES):
        return "yellow"
    return "grey"


def presence_batch(conn, user_ids: list[int], now: dt.datetime | None = None) -> dict[int, str]:
    """presence_status() for several users at once -- the Members panel's own need (Step 2 UI),
    one call instead of one per row."""
    return {uid: presence_status(conn, uid, now=now) for uid in user_ids}


# ---- Dual Account ID: temporary cross-location access ----

def _mint_foreign_account_id(conn, user_row, foreign_location: dict) -> str:
    """A fresh, independently-unique account_id string for a temporary foreign context -- built
    the exact same way id_generator.generate_account_id() builds a real one (same format, same
    element/age/gender codes), but checked for uniqueness against BOTH users.account_id/
    account_ids.account_id (via generate_account_id()'s own check) AND this module's own
    temporary_location_access.foreign_account_id, since id_generator has no way to know about this
    new table. Collisions are already astronomically rare after the first check; retried (not
    looped indefinitely) on the vanishingly unlikely second-table collision."""
    import zodiac_core
    tropical = zodiac_core.get_zodiac_sign(dt.date.fromisoformat(user_row["dob"]))
    element = tropical["element"] if tropical else "Fire"
    for _ in range(5):
        candidate = id_generator.generate_account_id(
            conn, user_row["name"], user_row["gender"], dt.date.fromisoformat(user_row["dob"]),
            dt.time.fromisoformat(user_row["tob"]), element, foreign_location,
        )
        if not conn.execute(
            "SELECT 1 FROM temporary_location_access WHERE foreign_account_id = ?", (candidate,)
        ).fetchone():
            return candidate
    raise RuntimeError("Could not generate a unique foreign Account ID")


def _can_approve_temporary_access(conn, user_id: int, location_level: str, location_id: str, is_admin: bool) -> bool:
    """The Founder, always; at Village level, also that village's own Q-Punch Nayak/Nayika
    (announcements_core.is_council_member(), same reuse local_area_core._is_village_admin()
    already established). No elected authority exists above Village yet anywhere in this
    codebase, so only the Founder can approve temporary access there for now -- the same
    real limitation can_create_channel() below documents for channel creation."""
    if is_admin:
        return True
    if location_level == "village":
        return announcements_core.is_council_member(conn, user_id, location_id, "village")
    return False


def _present_temp_access(row) -> dict:
    """The internal-only PENDING-... placeholder (see request_temporary_access()'s own comment on
    why the column can't just be NULL while pending) is never a real Account ID and must never
    reach a client as if it were one -- masked to None here, the one place every row this module
    returns to a caller passes through."""
    d = dict(row)
    if d["status"] == "pending":
        d["foreign_account_id"] = None
    return d


def request_temporary_access(conn, user_id: int, location_level: str, location_id: str) -> dict:
    """Queues a request for temporary access to a location the user doesn't live in -- e.g. "I
    work there virtually." Starts 'pending'; nothing is minted or usable until an admin approves
    it (decide_temporary_access()). Idempotent-on-retry: an existing pending/active request for
    the same (user, location) is returned as-is rather than raising, the same style
    request_join_group()/request_join() already use elsewhere in this codebase."""
    if location_level not in board_core.LEVELS:
        raise ValueError("Unknown location level")
    existing = conn.execute(
        "SELECT * FROM temporary_location_access WHERE user_id = ? AND location_level = ? AND location_id = ? "
        "AND status IN ('pending', 'active')",
        (user_id, location_level, location_id),
    ).fetchone()
    if existing:
        return _present_temp_access(existing)
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user_row:
        raise LookupError("User not found")
    cur = conn.execute(
        "INSERT INTO temporary_location_access (user_id, location_level, location_id, foreign_account_id, status, requested_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (user_id, location_level, location_id, f"PENDING-{user_id}-{_now()}", _now()),
    )
    # foreign_account_id is a real, globally-unique column (UNIQUE constraint) and must hold SOME
    # value even while pending -- the placeholder above is overwritten with the real, properly
    # generated id_generator-shaped code only once approved (decide_temporary_access()), since
    # minting the real one requires deciding it's actually being granted. _present_temp_access()
    # masks it back to None for any caller in the meantime.
    conn.commit()
    return _present_temp_access(conn.execute("SELECT * FROM temporary_location_access WHERE id = ?", (cur.lastrowid,)).fetchone())


def decide_temporary_access(conn, admin_user_id: int, request_id: int, approve: bool, is_admin: bool,
                             location_name: dict | None = None) -> None:
    """Approves or revokes-before-use a pending temporary-access request. location_name (the
    foreign location's own full dict, e.g. {"continent":..., "country":..., ..., "village":...})
    is required to approve -- the caller (the admin's own UI) already has it on screen; this
    module has no independent source of "what is location_id called"."""
    req = conn.execute("SELECT * FROM temporary_location_access WHERE id = ?", (request_id,)).fetchone()
    if not req:
        raise LookupError("Request not found")
    if not _can_approve_temporary_access(conn, admin_user_id, req["location_level"], req["location_id"], is_admin):
        raise PermissionError("Only an admin of this location can decide temporary access")
    if req["status"] != "pending":
        raise ValueError("This request has already been decided")
    if not approve:
        conn.execute(
            "UPDATE temporary_location_access SET status = 'revoked', decided_by_user_id = ?, decided_at = ? WHERE id = ?",
            (admin_user_id, _now(), request_id),
        )
        conn.commit()
        return
    if not location_name:
        raise ValueError("The foreign location's own name/chain is required to approve")
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (req["user_id"],)).fetchone()
    foreign_account_id = _mint_foreign_account_id(conn, user_row, location_name)
    conn.execute(
        "UPDATE temporary_location_access SET status = 'active', foreign_account_id = ?, decided_by_user_id = ?, decided_at = ? WHERE id = ?",
        (foreign_account_id, admin_user_id, _now(), request_id),
    )
    conn.commit()


def my_temporary_access(conn, user_id: int) -> list[dict]:
    return [_present_temp_access(r) for r in conn.execute(
        "SELECT * FROM temporary_location_access WHERE user_id = ? ORDER BY requested_at DESC", (user_id,)
    )]


def account_id_for_context(conn, user_id: int, location_level: str | None = None, location_id: str | None = None) -> str:
    """The Account ID a user's action should be attributed to RIGHT NOW: their home
    users.account_id, UNLESS they hold an ACTIVE temporary-access grant for this exact
    (location_level, location_id), in which case the foreign one minted for it. Passing no
    location (location_level=None) always returns the home account_id -- there is no "foreign"
    concept outside a specific Governance Channel's own location context."""
    if location_level and location_id:
        grant = conn.execute(
            "SELECT foreign_account_id FROM temporary_location_access "
            "WHERE user_id = ? AND location_level = ? AND location_id = ? AND status = 'active'",
            (user_id, location_level, location_id),
        ).fetchone()
        if grant:
            return grant["foreign_account_id"]
    row = conn.execute("SELECT account_id FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["account_id"] if row else None


# ---- Governance Channel creation rules ----

def can_administer_channel(conn, user_id: int, sg_id: int, is_admin: bool) -> bool:
    """Who may approve a join request (or otherwise administer) an EXISTING channel -- the same
    authority as creating one at Village level (Nayak/Nayika or Founder); the Founder only above
    Village, since no elected authority exists there yet (the same honest limit
    _can_approve_temporary_access() above already documents for temporary access). Replaces the
    bare _is_admin()-only gate api_subgroup_decide() used before this generalization -- which was
    never actually "council members," despite its own error message, just the Founder."""
    g = board_core._subgroup(conn, sg_id)
    if g["location_level"] == "village":
        return local_area_core._is_village_admin(conn, user_id, g["location_id"], is_admin)
    return bool(is_admin)


def can_create_channel(conn, user_id: int, location_level: str, location_id: str, is_admin: bool) -> bool:
    """Village: the Founder or that village's Q-Punch Nayak/Nayika (reusing
    local_area_core._is_village_admin()'s exact check, not reimplemented). Tehsil and above:
    the Founder, or ANY resident of that location once a People's Vote there has passed -- see
    create_channel(), which is what actually verifies and consumes the specific passed vote;
    this function only answers "is it even worth trying" for a UI's own "+New Channel" button."""
    if location_level == "village":
        return local_area_core._is_village_admin(conn, user_id, location_id, is_admin)
    if is_admin:
        return True
    user_row = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user_row:
        return False
    present_location = json.loads(user_row["present_location_json"] or "{}")
    return board_core._residency_matches(present_location, location_level, location_id)


def create_channel(conn, user_id: int, location_level: str, location_id: str, name: str, description: str,
                    is_admin: bool, admin_label: str | None = None, people_vote_id: int | None = None) -> int:
    """Village: creates immediately once can_create_channel() passes -- no vote needed, an
    elected Nayak/Nayika (or the Founder) already carries that authority. Tehsil and above:
    people_vote_id is REQUIRED and must reference a People's Vote that (a) exists, (b) is at this
    EXACT (location_level, location_id), (c) has status='passed', and (d) has not already been
    spent on a different channel (subgroups.created_via_vote_id) -- each passed vote authorizes
    exactly one channel, never a standing blank cheque for more."""
    if location_level == "village":
        if not local_area_core._is_village_admin(conn, user_id, location_id, is_admin):
            raise PermissionError("Only the Village Q-Punch (Nayak/Nayika) or the Founder can create a Governance Channel")
        return board_core.create_subgroup(conn, user_id, location_id, location_level, name, description, admin_label)

    if not can_create_channel(conn, user_id, location_level, location_id, is_admin):
        raise PermissionError(f"Only a resident of this {board_core.LEVEL_LABEL[location_level].lower()} can create a Governance Channel here")
    if not people_vote_id:
        raise ValueError("Creating a channel above Village level requires a passed People's Vote")
    vote = conn.execute("SELECT * FROM qpunch_people_votes WHERE id = ?", (people_vote_id,)).fetchone()
    if not vote:
        raise LookupError("People's Vote not found")
    if vote["level"] != location_level or vote["location_id"] != location_id:
        raise ValueError("That People's Vote was not called for this location")
    if vote["status"] != "passed":
        raise ValueError("That People's Vote has not passed")
    if conn.execute("SELECT 1 FROM subgroups WHERE created_via_vote_id = ?", (people_vote_id,)).fetchone():
        raise ValueError("That People's Vote has already been used to create a channel")
    return board_core.create_subgroup(conn, user_id, location_id, location_level, name, description, admin_label, created_via_vote_id=people_vote_id)


# ---- The aggregator ----

def _last_message_at(conn, table: str, id_column: str, group_id: int) -> str | None:
    row = conn.execute(f"SELECT created_at FROM {table} WHERE {id_column} = ? ORDER BY id DESC LIMIT 1", (group_id,)).fetchone()
    return row["created_at"] if row else None


def list_my_conversations(conn, user_id: int) -> list[dict]:
    """Every conversation this user belongs to, across all six existing messaging systems,
    normalized to {kind, id, title, pane, location_id, location_level, last_message_at,
    unread_count}. `pane` is the one new classifier the Teams-style UI needs:
      - 'private': private_chats, personal_groups (any category -- Family/Friends/Business/
        Custom), family_group_members.
      - 'channel': subgroups (Village or Tehsil+), local_areas.
    unread_count is NOT computed here yet -- no per-user "last read" timestamp exists anywhere in
    this codebase today (confirmed by grep across every messaging table); that is real, separate
    schema work for Step 2, not silently invented here. Always 0 for now, an honest placeholder a
    UI can already build the unread/All tabs around once it exists."""
    out = []

    for r in conn.execute(
        """SELECT c.id, CASE WHEN c.user_lo = ? THEN c.user_hi ELSE c.user_lo END AS other_id, c.name
           FROM private_chats c WHERE c.user_lo = ? OR c.user_hi = ?""", (user_id, user_id, user_id)
    ):
        other = conn.execute("SELECT name FROM users WHERE id = ?", (r["other_id"],)).fetchone()
        out.append({
            "kind": "private", "id": r["id"], "title": r["name"] or (other["name"] if other else "Unknown"),
            "pane": "private", "location_id": None, "location_level": None,
            # other_user_id (2026-11-24, Step 2): the one piece of extra context a 1:1 row needs
            # beyond every other conversation kind -- a Teams-style list shows THIS specific
            # person's presence dot next to the row, which a Governance Channel has no single
            # equivalent of (see chat.js's own presence-dot logic, Private pane only).
            "other_user_id": r["other_id"],
            "last_message_at": _last_message_at(conn, "private_messages", "chat_id", r["id"]), "unread_count": 0,
        })

    for r in conn.execute(
        """SELECT pg.id, pg.name FROM personal_groups pg WHERE pg.owner_user_id = ?
           UNION
           SELECT pg.id, pg.name FROM personal_group_members pm JOIN personal_groups pg ON pg.id = pm.group_id
           WHERE pm.user_id = ? AND pm.status = 'approved'""", (user_id, user_id)
    ):
        out.append({
            "kind": "group", "id": r["id"], "title": r["name"], "pane": "private",
            "location_id": None, "location_level": None,
            "last_message_at": _last_message_at(conn, "personal_messages", "group_id", r["id"]), "unread_count": 0,
        })

    for r in conn.execute(
        """SELECT fg.id, fg.name FROM family_group_members m JOIN family_groups fg ON fg.id = m.group_id
           WHERE m.user_id = ? AND m.status = 'approved'""", (user_id,)
    ):
        out.append({
            "kind": "family", "id": r["id"], "title": r["name"], "pane": "private",
            "location_id": None, "location_level": None,
            "last_message_at": _last_message_at(conn, "family_group_messages", "group_id", r["id"]), "unread_count": 0,
        })

    for r in conn.execute(
        """SELECT g.id, g.name, g.location_id, g.location_level FROM subgroup_members m
           JOIN subgroups g ON g.id = m.subgroup_id WHERE m.user_id = ? AND m.status = 'approved'""", (user_id,)
    ):
        out.append({
            "kind": "sub", "id": r["id"], "title": r["name"], "pane": "channel",
            "location_id": r["location_id"], "location_level": r["location_level"],
            "last_message_at": _last_message_at(conn, "board_messages", "subgroup_id", r["id"]), "unread_count": 0,
        })

    for r in conn.execute(
        """SELECT la.id, la.name, la.village_id FROM local_area_members m
           JOIN local_areas la ON la.id = m.local_area_id WHERE m.user_id = ? AND m.status = 'active'""", (user_id,)
    ):
        out.append({
            "kind": "local", "id": r["id"], "title": r["name"], "pane": "channel",
            "location_id": r["village_id"], "location_level": "village",
            "last_message_at": _last_message_at(conn, "local_area_messages", "local_area_id", r["id"]), "unread_count": 0,
        })

    out.sort(key=lambda c: c["last_message_at"] or "", reverse=True)
    return out


# ---- Karma badge (Governance pane only, Step 2 UI) ----

def recent_karma_for(conn, user_ids: list[int], since: str) -> dict[int, dict]:
    """For the Governance pane's '+Karma' badge: the most recent POSITIVE karma_entries row for
    each of user_ids at or after `since` (an ISO timestamp), if any. This is deliberately the ONLY
    way Karma ever touches chat -- surfacing an event that was ALREADY earned elsewhere (a rated
    business transaction, or a Collective Board post freezing positively -- karma_core.py's own
    module docstring is explicit these are the only two sources), never a new trigger. Sending a
    chat message never awards Karma, here or anywhere else in this codebase.

    This is a correlation, not a precise link: karma_entries has no column tying a row to a
    specific chat message (no such relationship exists in the schema, and inventing one is out of
    scope for this pass) -- the badge means "this person earned Karma recently," not "this exact
    message earned it." The caller must keep that distinction visible in the UI (e.g. a tooltip
    with the real reason/timestamp), never present it as if the message itself was rewarded."""
    if not user_ids:
        return {}
    import karma_core
    karma_core.ensure_tables(conn)
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"""SELECT user_id, points, reason, created_at FROM karma_entries
            WHERE user_id IN ({placeholders}) AND points > 0 AND created_at >= ?
            ORDER BY id DESC""",
        (*user_ids, since),
    ).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["user_id"], {"points": r["points"], "reason": r["reason"], "at": r["created_at"]})
    return out
