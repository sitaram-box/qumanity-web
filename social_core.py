"""Personal timeline: Family / Friends / Business / two Custom group chats, private one-to-one chats,
friend-style requests, and the 12-digit public search code people use to find each other.

Every "present location stay" a user has ever had keeps its own Account ID forever (see
`account_ids`); the newest one is `is_current`. Each Account ID gets its own 12-digit search code,
generated once and never reused. The Public profile shows only the CURRENT one.
"""
from __future__ import annotations

import datetime as dt
import secrets

import cycle_middleware
import notify_core

CATEGORIES = ("private", "family", "friends", "business", "custom")  # "private" has no groups of its own -- it's the 1:1 chat list
GROUP_CATEGORIES = ("family", "friends", "business", "custom")
# Family/Friends/Business are pre-defined only -- 2026-09-28: create_group() now only accepts
# 'custom' (the single "+" icon on the Personal timeline); a custom group can still be MOVED into
# any category afterwards (move_group()). Spouse-Family dropped from the defaults for now (kept in
# a comment, not deleted, since docs/personal_timeline_and_social.md ties it to a user's future
# relationship-status field once that's wired up here too).
DEFAULT_FAMILY_GROUPS = ("Paternal", "Maternal")  # was ("Paternal", "Maternal", "Spouse-Family")
DEFAULT_FRIENDS_GROUP = "All Friends"  # was "Friends"
ADMIN_BUSINESS_GROUP = "Qumanity Team"
MAX_MESSAGE_CHARS = 1000

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    account_id TEXT NOT NULL UNIQUE,
    search_code TEXT NOT NULL UNIQUE,
    present_location_json TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_ids_user ON account_ids(user_id);

CREATE TABLE IF NOT EXISTS personal_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    category TEXT NOT NULL,         -- family | friends | business | custom (see GROUP_CATEGORIES)
    name TEXT NOT NULL,
    business_name TEXT, business_sector TEXT, business_services TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_personal_groups_owner ON personal_groups(owner_user_id, category);
CREATE TABLE IF NOT EXISTS personal_group_members (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'approved',  -- invites land 'approved' only once accepted
    invited_by INTEGER,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
);
CREATE TABLE IF NOT EXISTS personal_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_personal_messages ON personal_messages(group_id, id);

CREATE TABLE IF NOT EXISTS people_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,             -- message | group
    group_id INTEGER,               -- set when kind = group
    first_message TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | declined | waiting
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_people_requests_to ON people_requests(to_user_id, status);

CREATE TABLE IF NOT EXISTS private_chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_lo INTEGER NOT NULL, user_hi INTEGER NOT NULL,
    name TEXT,                                    -- optional; falls back to the other person's name
    user_lo_status TEXT NOT NULL DEFAULT 'active', -- active | left -- both users are admins (2026-09-28)
    user_hi_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    UNIQUE (user_lo, user_hi)
);
CREATE TABLE IF NOT EXISTS private_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_private_messages ON private_messages(chat_id, id);
"""


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(private_chats)")}
    for col, ddl in (("name", "TEXT"), ("user_lo_status", "TEXT NOT NULL DEFAULT 'active'"), ("user_hi_status", "TEXT NOT NULL DEFAULT 'active'")):
        if col not in cols:
            conn.execute(f"ALTER TABLE private_chats ADD COLUMN {col} {ddl}")
    conn.commit()


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _new_code(conn):
    for _ in range(200):
        code = f"{secrets.randbelow(10**12):012d}"
        if not conn.execute("SELECT 1 FROM account_ids WHERE search_code = ?", (code,)).fetchone():
            return code
    raise RuntimeError("Could not generate a unique 12-digit search code")


def backfill_account_ids(conn):
    """One row per user for their current Account ID, run once at startup for users who pre-date this table."""
    ensure_tables(conn)
    for u in conn.execute("SELECT id, account_id, present_location_json FROM users WHERE account_id IS NOT NULL"):
        if conn.execute("SELECT 1 FROM account_ids WHERE user_id = ? AND account_id = ?", (u["id"], u["account_id"])).fetchone():
            continue
        conn.execute(
            "INSERT INTO account_ids (user_id, account_id, search_code, present_location_json, is_current, created_at, cycle_id) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (u["id"], u["account_id"], _new_code(conn), u["present_location_json"], _now(), cycle_middleware.get_active_cycle_id(conn)),
        )
    conn.commit()


def record_new_account_id(conn, user_id, account_id, present_location):
    """Called when a user's present location changes and a fresh Account ID is minted (future 'move' flow).
    Every earlier Account ID is kept forever, just marked no-longer-current."""
    import json
    conn.execute("UPDATE account_ids SET is_current = 0 WHERE user_id = ?", (user_id,))
    conn.execute(
        "INSERT INTO account_ids (user_id, account_id, search_code, present_location_json, is_current, created_at, cycle_id) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (user_id, account_id, _new_code(conn), json.dumps(present_location), _now(), cycle_middleware.get_active_cycle_id(conn)),
    )
    conn.commit()


def regenerate_account_id(conn, user_id, present_location: dict) -> str:
    """Regenerates a user's account_id for a new present_location, updates users.account_id +
    users.present_location_json, and records the change in account_ids (record_new_account_id
    marks every prior row is_current=0 and inserts the new one as is_current=1). Returns the new
    account_id. The one place both the dedicated 'request a new Account ID' flow
    (decide_account_request) and the generic profile-change-request queue
    (app.py's api_admin_profile_decide) regenerate an account_id -- so present_location can
    never change without account_id changing with it again."""
    import json
    import id_generator
    u = conn.execute("SELECT name, gender, dob, tob FROM users WHERE id = ?", (user_id,)).fetchone()
    zodiac = conn.execute("SELECT sun_element FROM user_zodiac WHERE user_id = ?", (user_id,)).fetchone()
    dob = dt.date.fromisoformat(u["dob"])
    tob = dt.time.fromisoformat(u["tob"])
    new_account_id = id_generator.generate_account_id(conn, u["name"], u["gender"], dob, tob, zodiac["sun_element"], present_location)
    record_new_account_id(conn, user_id, new_account_id, present_location)
    conn.execute("UPDATE users SET account_id = ?, present_location_json = ? WHERE id = ?",
                 (new_account_id, json.dumps(present_location), user_id))
    conn.commit()

    # Qmail (2026-10-18): the one choke point both account_id-change paths funnel through, so
    # Qmail addressing can never develop the same two-path divergence bug that was just fixed for
    # account_id itself. A no-op for a user who has never activated Qmail.
    qmail_user = conn.execute("SELECT qmail_username FROM users WHERE id = ?", (user_id,)).fetchone()
    if qmail_user and qmail_user["qmail_username"]:
        import qmail_core
        full_address = qmail_core.build_full_address(qmail_user["qmail_username"], new_account_id)
        forward_until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=qmail_core.FORWARD_WINDOW_DAYS)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE qmail_addresses SET is_current = 0, forward_until = ? WHERE user_id = ? AND is_current = 1",
            (forward_until, user_id),
        )
        conn.execute(
            "INSERT INTO qmail_addresses (user_id, account_id, full_address, is_current, created_at) VALUES (?, ?, ?, 1, ?)",
            (user_id, new_account_id, full_address, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()

    return new_account_id


def connected_user_ids(conn, user_id) -> set:
    """Every person this user is connected to: every Personal Group (any category, approved
    membership, both directions -- groups they own and groups they've been approved into) plus
    every private chat where their own side hasn't been left. No existing function already
    returns this flat a list across every connection type (my_groups returns per-category groups
    with member counts, my_chats only covers 1:1 chats) -- built fresh here for Qmail's smart "To"
    field (app.py's /api/qmail/resolve-username), which must never suggest a disconnected user."""
    ids = set()

    for r in conn.execute(
        """SELECT pgm.user_id FROM personal_groups pg
           JOIN personal_group_members pgm ON pgm.group_id = pg.id
           WHERE pg.owner_user_id = ? AND pgm.status = 'approved'""", (user_id,)):
        ids.add(r["user_id"])

    for r in conn.execute(
        """SELECT pg.owner_user_id AS other_id FROM personal_group_members pgm
           JOIN personal_groups pg ON pg.id = pgm.group_id
           WHERE pgm.user_id = ? AND pgm.status = 'approved'""", (user_id,)):
        ids.add(r["other_id"])

    for r in conn.execute(
        """SELECT pgm2.user_id AS other_id FROM personal_group_members pgm
           JOIN personal_group_members pgm2 ON pgm2.group_id = pgm.group_id
           WHERE pgm.user_id = ? AND pgm.status = 'approved' AND pgm2.status = 'approved'""", (user_id,)):
        ids.add(r["other_id"])

    for r in conn.execute(
        """SELECT CASE WHEN user_lo = ? THEN user_hi ELSE user_lo END AS other_id,
                  CASE WHEN user_lo = ? THEN user_lo_status ELSE user_hi_status END AS my_status
           FROM private_chats WHERE user_lo = ? OR user_hi = ?""",
        (user_id, user_id, user_id, user_id)):
        if r["my_status"] == "active":
            ids.add(r["other_id"])

    ids.discard(user_id)
    return ids


def my_account_history(conn, user_id):
    return [dict(r) for r in conn.execute(
        "SELECT id, account_id, search_code, present_location_json, is_current, created_at FROM account_ids WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,))]


def my_search_code(conn, user_id):
    row = conn.execute("SELECT search_code FROM account_ids WHERE user_id = ? AND is_current = 1", (user_id,)).fetchone()
    return row["search_code"] if row else None


# ---- Identity masking: for an account with users.hide_identity set (the Founder's own, as of
# 2026-10-04), a stranger never sees the real name or any location finer than State -- only Gender,
# Age-Category and Zodiac Sun-Element, plus their Account ID as the thing to actually contact them
# by. Their own Family group members, and their own authored Collective Board posts, are exempt --
# see is_family_member() and board_core.py (board posts were never routed through this module, so
# they're unaffected by design, not by an explicit carve-out here). ----

def _is_hidden(conn, user_id) -> bool:
    row = conn.execute("SELECT hide_identity FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and row["hide_identity"])


def is_family_member(conn, owner_user_id, viewer_user_id) -> bool:
    """True if viewer_user_id belongs to one of owner_user_id's OWN "family" category groups --
    the one relationship that still sees a hidden-identity account's real name."""
    if viewer_user_id == owner_user_id:
        return True
    row = conn.execute(
        """SELECT 1 FROM personal_group_members m
           JOIN personal_groups g ON g.id = m.group_id
           WHERE g.owner_user_id = ? AND g.category = 'family' AND m.user_id = ? AND m.status = 'approved'""",
        (owner_user_id, viewer_user_id),
    ).fetchone()
    return bool(row)


def _capped_location(location_json: str) -> dict:
    import json
    loc = json.loads(location_json)
    return {k: loc[k] for k in ("continent", "country", "zone", "state") if k in loc}


def display_identity(conn, user_id, viewer_user_id=None) -> dict:
    """{name, place, hidden, gender, age_category, sun_element} for showing someone else's
    identity to `viewer_user_id` (None = no viewer / not logged in, treated as a stranger).
    When the target isn't hidden, or the viewer is their own Family, this is just their real
    name + present village/country. When hidden and the viewer doesn't qualify: name is replaced
    by their Account ID, place is capped at State, and age_category/sun_element are filled in
    (gender was already shown everywhere this is used) -- the exact fields the Founder's own
    privacy request asked to keep visible."""
    import json
    u = conn.execute("SELECT id, name, gender, present_location_json, account_id, hide_identity, dob FROM users WHERE id = ?", (user_id,)).fetchone()
    if not u:
        return None
    hidden = bool(u["hide_identity"]) and not is_family_member(conn, user_id, viewer_user_id)
    loc = json.loads(u["present_location_json"])
    if not hidden:
        village = (loc.get("village") or {}).get("name") or (loc.get("country") or {}).get("name")
        return {"name": u["name"], "place": village, "hidden": False}
    capped = _capped_location(u["present_location_json"])
    place = (capped.get("state") or capped.get("country") or capped.get("continent") or {}).get("name") or "Earth"
    import id_generator
    age_category = {"A1": "Balak", "A2": "Yuvak", "A3": "Vridh", "A4": "Mentor"}[id_generator.age_code(dt.date.fromisoformat(u["dob"]))]
    z = conn.execute("SELECT sun_element FROM user_zodiac WHERE user_id = ?", (user_id,)).fetchone()
    return {
        "name": u["account_id"], "place": place, "hidden": True,
        "age_category": age_category, "sun_element": z["sun_element"] if z else None,
    }


def find_person(conn, query, viewer_user_id=None):
    """Search by 12-digit search code or by a readable Account ID string. Returns a public-safe profile or None.
    Never returns the private (9-digit) ID, email or phone -- matches the village-member-list privacy scoping.
    A hide_identity account (see display_identity()) never gives up its real name or village/
    tehsil/district here, no matter who's searching -- the Account ID itself becomes the "name"."""
    query = (query or "").strip()
    if not query:
        return None
    if query.isdigit() and len(query) == 12:
        row = conn.execute(
            "SELECT user_id, account_id FROM account_ids WHERE search_code = ? AND is_current = 1", (query,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT user_id, account_id FROM account_ids WHERE account_id = ? AND is_current = 1", (query.upper(),)
        ).fetchone()
    if not row:
        return None
    u = conn.execute("SELECT id, gender FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    if not u:
        return None
    identity = display_identity(conn, u["id"], viewer_user_id)
    result = {"user_id": u["id"], "name": identity["name"], "gender": u["gender"], "place": identity["place"], "account_id": row["account_id"]}
    if identity["hidden"]:
        result["age_category"] = identity["age_category"]
        result["sun_element"] = identity["sun_element"]
    return result


# ---- Personal groups: Private (1:1, no groups) / Family / Friends / Business / Custom ----
# Family starts with 2 default groups (Paternal, Maternal), Friends with 1 ("All Friends"),
# Business with none (except "Qumanity Team" for the Founder/admin). New groups are always Custom
# (create_group()); move_group() re-files a Custom group into Family/Friends/Business afterwards.

def migrate_group_defaults(conn):
    """One-time, conservative cleanup for accounts created before the 2026-09-28 default change:
    renames an untouched default "Friends" group to "All Friends", and drops an untouched, empty
    default "Spouse-Family" group. Never touches a group a user has renamed, added members to, or
    exchanged messages in -- this only removes/renames rows nobody has actually used."""
    conn.execute("UPDATE personal_groups SET name = ? WHERE category = 'friends' AND name = 'Friends'", (DEFAULT_FRIENDS_GROUP,))
    untouched_spouse = conn.execute(
        """SELECT id FROM personal_groups WHERE category = 'family' AND name = 'Spouse-Family'
           AND id NOT IN (SELECT DISTINCT group_id FROM personal_messages)
           AND id NOT IN (SELECT DISTINCT group_id FROM personal_group_members)"""
    ).fetchall()
    for row in untouched_spouse:
        conn.execute("DELETE FROM personal_groups WHERE id = ?", (row["id"],))
    conn.commit()


def ensure_defaults(conn, owner_user_id, is_admin=False):
    """Creates the standard starter groups the first time this user's Personal tab is opened. Safe to
    call every time -- does nothing once they already exist."""
    have = {r["category"] for r in conn.execute("SELECT DISTINCT category FROM personal_groups WHERE owner_user_id=?", (owner_user_id,))}
    if "family" not in have:
        for name in DEFAULT_FAMILY_GROUPS:
            _insert_group(conn, owner_user_id, "family", name)
    if "friends" not in have:
        _insert_group(conn, owner_user_id, "friends", DEFAULT_FRIENDS_GROUP)
    if is_admin and "business" not in have:
        _insert_group(conn, owner_user_id, "business", ADMIN_BUSINESS_GROUP)
    conn.commit()


def _insert_group(conn, owner_user_id, category, name, business_name=None, business_sector=None, business_services=None):
    conn.execute(
        "INSERT INTO personal_groups (owner_user_id, category, name, business_name, business_sector, business_services, created_at, cycle_id) VALUES (?,?,?,?,?,?,?,?)",
        (owner_user_id, category, name, business_name, business_sector, business_services, _now(), cycle_middleware.get_active_cycle_id(conn)),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def create_group(conn, owner_user_id, category, name, description=None):
    """A brand-new group is always Custom (the single "+" icon on the Personal timeline,
    2026-09-28) -- Family/Friends/Business are pre-defined or auto-created, never created directly.
    Move it afterwards with move_group() once it exists."""
    if category != "custom":
        raise ValueError("New groups are created as Custom, then moved into Family / Friends / Business if you like")
    name = (name or "").strip()
    if not 2 <= len(name) <= 60:
        raise ValueError("Give the group a name (2-60 characters)")
    gid = _insert_group(conn, owner_user_id, "custom", name)
    conn.commit()
    return gid


def move_group(conn, owner_user_id, group_id, category):
    """Re-file one of the owner's own groups into a different category (e.g. a brand-new group moved into Family)."""
    if category not in GROUP_CATEGORIES:
        raise ValueError("Unknown group category")
    g = group_by_id(conn, group_id)
    if g["owner_user_id"] != owner_user_id:
        raise PermissionError("Only the group's owner can move it")
    conn.execute("UPDATE personal_groups SET category=? WHERE id=?", (category, group_id))
    conn.commit()


def my_groups(conn, user_id, is_admin=False):
    """{"family": {...}, "friends": {...}, "business": {...}, "custom": {...}}, each with the groups the
    user owns in that category plus every group of that category someone else has approved them into."""
    ensure_defaults(conn, user_id, is_admin)
    out = {}
    for cat in GROUP_CATEGORIES:
        owned = []
        for g in conn.execute("SELECT * FROM personal_groups WHERE owner_user_id=? AND category=? ORDER BY id", (user_id, cat)):
            n = conn.execute("SELECT COUNT(*) FROM personal_group_members WHERE group_id=? AND status='approved'", (g["id"],)).fetchone()[0]
            owned.append({"id": g["id"], "category": cat, "name": g["name"], "mine": True, "members": n + 1,
                         "business_name": g["business_name"], "business_sector": g["business_sector"], "business_services": g["business_services"]})
        joined = [dict(r, mine=False) for r in conn.execute(
            """SELECT pg.id, pg.category, pg.name, u.name AS owner_name,
                      (SELECT COUNT(*) FROM personal_group_members m2 WHERE m2.group_id = pg.id AND m2.status = 'approved') + 1 AS members
               FROM personal_group_members pm JOIN personal_groups pg ON pg.id = pm.group_id JOIN users u ON u.id = pg.owner_user_id
               WHERE pm.user_id = ? AND pm.status = 'approved' AND pg.category = ?""", (user_id, cat))]
        out[cat] = {"owned": owned, "joined": joined}
    return out


def set_business_profile(conn, owner_user_id, group_id, name, sector, services):
    g = group_by_id(conn, group_id)
    if g["owner_user_id"] != owner_user_id or g["category"] != "business":
        raise PermissionError("Not your business group")
    conn.execute("UPDATE personal_groups SET business_name=?, business_sector=?, business_services=? WHERE id=?",
                 ((name or "").strip()[:120], (sector or "").strip()[:120], (services or "").strip()[:500], group_id))
    conn.commit()


def rename_group(conn, owner_user_id, group_id, name):
    g = group_by_id(conn, group_id)
    if g["owner_user_id"] != owner_user_id:
        raise PermissionError("Not your group")
    name = (name or "").strip()
    if not 2 <= len(name) <= 60:
        raise ValueError("Give the group a name (2-60 characters)")
    conn.execute("UPDATE personal_groups SET name=? WHERE id=?", (name, group_id))
    conn.commit()


def group_by_id(conn, group_id):
    row = conn.execute("SELECT * FROM personal_groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise LookupError("Group not found")
    return row


def _is_member(conn, group, user_id):
    if group["owner_user_id"] == user_id:
        return True
    return bool(conn.execute("SELECT 1 FROM personal_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'", (group["id"], user_id)).fetchone())


def group_messages(conn, user_id, group_id):
    import reactions_core
    g = group_by_id(conn, group_id)
    if not _is_member(conn, g, user_id):
        raise PermissionError("You are not a member of this group")
    rows = list(reversed(conn.execute(
        "SELECT m.id, m.text, m.created_at, m.user_id, u.name, u.account_id FROM personal_messages m JOIN users u ON u.id = m.user_id "
        "WHERE m.group_id = ? ORDER BY m.id DESC LIMIT 200", (group_id,)).fetchall()))
    members = [{"name": u2["name"], "you": u2["id"] == user_id} for u2 in conn.execute(
        """SELECT u.id, u.name FROM personal_group_members m JOIN users u ON u.id = m.user_id WHERE m.group_id = ? AND m.status = 'approved'
           UNION SELECT u.id, u.name FROM users u WHERE u.id = ?""", (group_id, g["owner_user_id"]))]
    reactions = reactions_core.counts_for(conn, "personal", [r["id"] for r in rows], user_id)
    return {"id": g["id"], "category": g["category"], "name": g["name"], "is_owner": g["owner_user_id"] == user_id, "members": members,
            "business": {"name": g["business_name"], "sector": g["business_sector"], "services": g["business_services"]} if g["category"] == "business" else None,
            "messages": [{"id": r["id"], "who": r["name"], "account_id": r["account_id"], "mine": r["user_id"] == user_id,
                         "text": r["text"], "at": r["created_at"], "reactions": reactions[r["id"]]} for r in rows]}


def send_group_message(conn, user_id, group_id, text):
    g = group_by_id(conn, group_id)
    if not _is_member(conn, g, user_id):
        raise PermissionError("You are not a member of this group")
    text = (text or "").strip()
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Write a message (up to {MAX_MESSAGE_CHARS} characters)")
    conn.execute("INSERT INTO personal_messages (group_id, user_id, text, created_at, cycle_id) VALUES (?, ?, ?, ?, ?)",
                (group_id, user_id, text, _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


# ---- Requests: a one-time message, or an invite into one of the sender's groups ----

def send_message_request(conn, from_user_id, to_user_id, text):
    if from_user_id == to_user_id:
        raise ValueError("You can't message yourself")
    if existing_chat(conn, from_user_id, to_user_id):
        raise ValueError("You already have a private chat with this person")
    if conn.execute("SELECT 1 FROM people_requests WHERE from_user_id=? AND to_user_id=? AND kind='message' AND status='pending'",
                     (from_user_id, to_user_id)).fetchone():
        raise ValueError("You already have a message request waiting with this person")
    text = (text or "").strip()
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Write your message (up to {MAX_MESSAGE_CHARS} characters)")
    conn.execute("INSERT INTO people_requests (from_user_id, to_user_id, kind, first_message, created_at, cycle_id) VALUES (?, ?, 'message', ?, ?, ?)",
                 (from_user_id, to_user_id, text, _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def send_group_invite(conn, owner_user_id, group_id, to_user_id):
    g = group_by_id(conn, group_id)
    if g["owner_user_id"] != owner_user_id:
        raise PermissionError("Only the group's owner can invite members")
    if owner_user_id == to_user_id:
        raise ValueError("You can't invite yourself")
    if _is_member(conn, g, to_user_id):
        raise ValueError("They are already a member of this group")
    if conn.execute("SELECT 1 FROM people_requests WHERE from_user_id=? AND to_user_id=? AND group_id=? AND kind='group' AND status='pending'",
                     (owner_user_id, to_user_id, g["id"])).fetchone():
        raise ValueError("An invitation is already waiting for them")
    conn.execute("INSERT INTO people_requests (from_user_id, to_user_id, kind, group_id, created_at, cycle_id) VALUES (?, ?, 'group', ?, ?, ?)",
                 (owner_user_id, to_user_id, g["id"], _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def inbox(conn, user_id):
    # r.group_id is overloaded: a personal_groups.id for kind='group', a private_chats.id for
    # kind='rejoin' (see request_rejoin()) -- each JOIN is gated by kind so the two id spaces (both
    # autoincrement from 1) can never cross-match into the wrong row.
    rows = conn.execute(
        """SELECT r.id, r.kind, r.first_message, r.created_at, r.status, r.from_user_id, u.name AS from_name,
                  pg.name AS group_name, pg.category AS group_category, pc.name AS chat_name
           FROM people_requests r JOIN users u ON u.id = r.from_user_id
           LEFT JOIN personal_groups pg ON pg.id = r.group_id AND r.kind = 'group'
           LEFT JOIN private_chats pc ON pc.id = r.group_id AND r.kind = 'rejoin'
           WHERE r.to_user_id = ? AND r.status IN ('pending', 'waiting') ORDER BY r.id DESC""", (user_id,)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        if _is_hidden(conn, r["from_user_id"]) and not is_family_member(conn, r["from_user_id"], user_id):
            identity = display_identity(conn, r["from_user_id"], user_id)
            item["from_name"] = identity["name"]
        out.append(item)
    return out


def existing_chat(conn, a, b):
    lo, hi = sorted((a, b))
    return conn.execute("SELECT id FROM private_chats WHERE user_lo = ? AND user_hi = ?", (lo, hi)).fetchone()


def _open_chat(conn, a, b):
    row = existing_chat(conn, a, b)
    if row:
        return row["id"]
    lo, hi = sorted((a, b))
    cur = conn.execute("INSERT INTO private_chats (user_lo, user_hi, created_at, cycle_id) VALUES (?, ?, ?, ?)",
                      (lo, hi, _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()
    return cur.lastrowid


def decide_request(conn, user_id, request_id, decision):
    """decision: 'accept' | 'decline' | 'waiting'."""
    r = conn.execute("SELECT * FROM people_requests WHERE id = ? AND to_user_id = ?", (request_id, user_id)).fetchone()
    if not r:
        raise LookupError("Request not found")
    if decision == "waiting":
        conn.execute("UPDATE people_requests SET status='waiting' WHERE id=?", (request_id,))
        conn.commit()
        return {"status": "waiting"}
    if decision not in ("accept", "decline"):
        raise ValueError("decision must be accept, decline or waiting")
    status = "accepted" if decision == "accept" else "declined"
    conn.execute("UPDATE people_requests SET status=?, decided_at=? WHERE id=?", (status, _now(), request_id))
    if decision == "accept":
        if r["kind"] == "message":
            chat_id = _open_chat(conn, r["from_user_id"], r["to_user_id"])
            conn.execute("INSERT INTO private_messages (chat_id, user_id, text, created_at, cycle_id) VALUES (?, ?, ?, ?, ?)",
                         (chat_id, r["from_user_id"], r["first_message"], r["created_at"], cycle_middleware.get_active_cycle_id(conn)))
            # The sender already knows what they wrote -- their own first message shouldn't show as
            # an unread notification for them once the recipient accepts.
            notify_core.mark_read(conn, r["from_user_id"], "private", chat_id)
        elif r["kind"] == "group":
            conn.execute("INSERT OR REPLACE INTO personal_group_members (group_id, user_id, status, invited_by, created_at, cycle_id) VALUES (?, ?, 'approved', ?, ?, ?)",
                         (r["group_id"], user_id, r["from_user_id"], _now(), cycle_middleware.get_active_cycle_id(conn)))
        elif r["kind"] == "rejoin":
            # group_id holds the private_chats id here (see request_rejoin()); `user_id` is deciding
            # on THEIR OWN chat (they never left it), so the rejoining member is r["from_user_id"].
            chat = conn.execute("SELECT * FROM private_chats WHERE id = ?", (r["group_id"],)).fetchone()
            if chat:
                conn.execute(f"UPDATE private_chats SET {_my_status_col(chat, r['from_user_id'])} = 'active' WHERE id = ?", (chat["id"],))
    conn.commit()
    return {"status": status}


# ---- Private Groups (2026-09-28): a 1:1 chat opened by an accepted message request. Both users
# are admins -- either can rename it or remove themselves ("leave"). Leaving keeps the chat and its
# history visible (read-only) but blocks sending or seeing new messages until the OTHER user
# approves a rejoin request (reuses people_requests, kind='rejoin', group_id repurposed to hold the
# chat id -- decide_request() below handles it distinctly from a personal_groups invite).

def _my_status_col(row, user_id):
    return "user_lo_status" if row["user_lo"] == user_id else "user_hi_status"


def _other_status_col(row, user_id):
    return "user_hi_status" if row["user_lo"] == user_id else "user_lo_status"


def my_chats(conn, user_id):
    rows = conn.execute(
        """SELECT c.*, CASE WHEN c.user_lo = ? THEN c.user_hi ELSE c.user_lo END AS other_id
           FROM private_chats c WHERE c.user_lo = ? OR c.user_hi = ?""", (user_id, user_id, user_id)).fetchall()
    out = []
    for r in rows:
        other = conn.execute("SELECT name FROM users WHERE id = ?", (r["other_id"],)).fetchone()
        other_name = other["name"] if other else "Unknown"
        last = conn.execute("SELECT text, created_at FROM private_messages WHERE chat_id = ? ORDER BY id DESC LIMIT 1", (r["id"],)).fetchone()
        out.append({
            "chat_id": r["id"], "name": r["name"] or other_name, "with": other_name,
            "left": r[_my_status_col(r, user_id)] == "left",
            "last": last["text"] if last else None, "at": last["created_at"] if last else None,
        })
    return out


def chat_messages(conn, user_id, chat_id):
    row = conn.execute("SELECT * FROM private_chats WHERE id = ?", (chat_id,)).fetchone()
    if not row or user_id not in (row["user_lo"], row["user_hi"]):
        raise PermissionError("Not your chat")
    other_id = row["user_hi"] if row["user_lo"] == user_id else row["user_lo"]
    other = conn.execute("SELECT name, account_id FROM users WHERE id = ?", (other_id,)).fetchone()
    other_name = other["name"] if other else "Unknown"
    left = row[_my_status_col(row, user_id)] == "left"
    # Visible while left (history stays readable) -- only sending and seeing NEW messages is blocked.
    msgs = conn.execute("SELECT text, created_at, user_id FROM private_messages WHERE chat_id = ? ORDER BY id", (chat_id,)).fetchall()
    return {
        "name": row["name"] or other_name, "with": other_name,
        "is_owner": True,  # both members are admins
        "left": left, "other_left": row[_other_status_col(row, user_id)] == "left",
        "other_account_id": other["account_id"] if other else None,
        "messages": [{"mine": m["user_id"] == user_id, "text": m["text"], "at": m["created_at"]} for m in msgs],
    }


def send_chat_message(conn, user_id, chat_id, text):
    row = conn.execute("SELECT * FROM private_chats WHERE id = ?", (chat_id,)).fetchone()
    if not row or user_id not in (row["user_lo"], row["user_hi"]):
        raise PermissionError("Not your chat")
    if row[_my_status_col(row, user_id)] == "left":
        raise PermissionError("You left this chat -- ask the other member to let you back in")
    text = (text or "").strip()
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ValueError(f"Write a message (up to {MAX_MESSAGE_CHARS} characters)")
    conn.execute("INSERT INTO private_messages (chat_id, user_id, text, created_at, cycle_id) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, text, _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def rename_chat(conn, user_id, chat_id, name):
    row = conn.execute("SELECT * FROM private_chats WHERE id = ?", (chat_id,)).fetchone()
    if not row or user_id not in (row["user_lo"], row["user_hi"]):
        raise PermissionError("Not your chat")
    name = (name or "").strip()
    if not 2 <= len(name) <= 60:
        raise ValueError("Give the chat a name (2-60 characters)")
    conn.execute("UPDATE private_chats SET name = ? WHERE id = ?", (name, chat_id))
    conn.commit()


def leave_chat(conn, user_id, chat_id):
    row = conn.execute("SELECT * FROM private_chats WHERE id = ?", (chat_id,)).fetchone()
    if not row or user_id not in (row["user_lo"], row["user_hi"]):
        raise PermissionError("Not your chat")
    conn.execute(f"UPDATE private_chats SET {_my_status_col(row, user_id)} = 'left' WHERE id = ?", (chat_id,))
    conn.commit()


def request_rejoin(conn, user_id, chat_id):
    row = conn.execute("SELECT * FROM private_chats WHERE id = ?", (chat_id,)).fetchone()
    if not row or user_id not in (row["user_lo"], row["user_hi"]):
        raise PermissionError("Not your chat")
    if row[_my_status_col(row, user_id)] != "left":
        raise ValueError("You're already in this chat")
    other_id = row["user_hi"] if row["user_lo"] == user_id else row["user_lo"]
    if conn.execute("SELECT 1 FROM people_requests WHERE from_user_id=? AND to_user_id=? AND kind='rejoin' AND group_id=? AND status='pending'",
                     (user_id, other_id, chat_id)).fetchone():
        raise ValueError("A rejoin request is already waiting")
    conn.execute("INSERT INTO people_requests (from_user_id, to_user_id, kind, group_id, created_at, cycle_id) VALUES (?, ?, 'rejoin', ?, ?, ?)",
                 (user_id, other_id, chat_id, _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


# ---- Switching between a user's Account IDs (only one is ever "current"/active) ----

def switch_account(conn, user_id, account_row_id):
    """Makes one of the user's past Account IDs current again. Updates users.account_id and
    users.present_location_json to match, so every present-location page (Public timeline, board,
    stats) reflects the switch immediately. Global timeline is unaffected -- it never depended on
    the present location."""
    row = conn.execute("SELECT * FROM account_ids WHERE id=? AND user_id=?", (account_row_id, user_id)).fetchone()
    if not row:
        raise LookupError("That Account ID isn't yours")
    conn.execute("UPDATE account_ids SET is_current=0 WHERE user_id=?", (user_id,))
    conn.execute("UPDATE account_ids SET is_current=1 WHERE id=?", (account_row_id,))
    conn.execute("UPDATE users SET account_id=?, present_location_json=? WHERE id=?", (row["account_id"], row["present_location_json"], user_id))
    conn.commit()


ACCOUNT_REQUEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS account_id_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    present_location_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
    decided_by INTEGER, decided_at TEXT,
    created_at TEXT NOT NULL
);
"""


def ensure_account_request_table(conn):
    conn.executescript(ACCOUNT_REQUEST_SCHEMA)
    conn.commit()


def request_new_account(conn, user_id, present_location):
    """A user who has moved asks for a new Account ID at their new present location. Manual council
    review for now (the founder's spec also wants this triggered automatically by a local shop's
    payment approval -- that needs a commerce/shop module that doesn't exist yet, so it's deferred;
    see docs/personal_timeline_and_social.md)."""
    ensure_account_request_table(conn)
    if not (present_location.get("village") or present_location.get("state")):
        raise ValueError("Choose at least a state for your new present location")
    if conn.execute("SELECT 1 FROM account_id_requests WHERE user_id=? AND status='pending'", (user_id,)).fetchone():
        raise ValueError("You already have a request waiting for the council")
    conn.execute("INSERT INTO account_id_requests (user_id, present_location_json, created_at, cycle_id) VALUES (?,?,?,?)",
                 (user_id, __import__("json").dumps(present_location), _now(), cycle_middleware.get_active_cycle_id(conn)))
    conn.commit()


def my_account_requests(conn, user_id):
    """The user's own new-Account-ID requests (newest first), so the app can show "waiting for approval"."""
    ensure_account_request_table(conn)
    return [dict(r) for r in conn.execute(
        "SELECT id, present_location_json, status, created_at, decided_at FROM account_id_requests WHERE user_id=? ORDER BY id DESC LIMIT 5",
        (user_id,))]


def list_account_requests(conn):
    ensure_account_request_table(conn)
    return [dict(r) for r in conn.execute(
        "SELECT r.*, u.name FROM account_id_requests r JOIN users u ON u.id=r.user_id WHERE r.status='pending' ORDER BY r.id")]


def decide_account_request(conn, admin_id, request_id, approve):
    import json as _json
    ensure_account_request_table(conn)
    row = conn.execute("SELECT * FROM account_id_requests WHERE id=? AND status='pending'", (request_id,)).fetchone()
    if not row:
        raise LookupError("Request not found")
    conn.execute("UPDATE account_id_requests SET status=?, decided_by=?, decided_at=? WHERE id=?",
                 ("approved" if approve else "rejected", admin_id, _now(), request_id))
    if approve:
        present = _json.loads(row["present_location_json"])
        regenerate_account_id(conn, row["user_id"], present)
    conn.commit()
