"""Family Tree: the Nuclear Family Node architecture (2026-10-20 restructure).

A `family_groups` row is now a NUCLEAR FAMILY UNIT (a marriage), not a generic container -- the
tree is built out of marriage pairs, not individual people. `family_nodes` stays exactly what it
was: a person reference (claimed or empty, is_deceased-aware). A unit names its two founders
directly (husband_node_id, wife_node_id); the "lineage vs marital" split from the previous pass
dissolves, since activate_timeline()'s "parents' group" and marry_timeline()'s "my own group" are
now literally the same operation (find-or-create a couple-unit) applied to different pairs.

  - family_nodes / family_parent_links: unchanged. A node is a person; a parent_link is a raw
    genealogical fact (X is a parent of Y), independent of which unit currently organizes the tree.
  - family_spouse_links: DEPRECATED, no longer written by new code (kept, historical rows only --
    a marriage is now the unit itself: family_groups.husband_node_id/wife_node_id). tree_for_group()
    synthesizes an equivalent spouse-link entry from a unit's own founder pair, so the (unchanged
    this pass) D3 frontend's spouse-connector still renders for marriages created under the new model.
  - family_groups: now a unit. husband_node_id/wife_node_id are its two founders (one may be an
    empty, not-yet-claimed node). husband_parent_group_id/wife_parent_group_id each point at the
    founder's OWN birth unit, if the tree already knows it -- a unit can have 0, 1 or 2 parent
    units, which is exactly why this was never renderable as a single d3.tree() hierarchy across
    multiple generations: a married couple has two ancestries, almost always two separate,
    unrelated families, meeting only at this one marriage. The D3 side's answer (approved) is to
    render one unit's own immediate neighborhood at a time -- see GET .../neighborhood.
  - family_group_members: a unit's own chat roster -- "just the parents and their children," per
    spec. is_admin is no longer derived from a spouse edge; it's set directly from being a founder
    (husband_node_id/wife_node_id) at creation, or granted the moment an empty founder slot is
    claimed (see link_node_to_user()). A join-request from anyone else is always a plain member,
    never admin -- founders are the only admins, full stop.
  - family_group_nodes: still needed for UNMARRIED children -- a couple's kids who haven't founded
    their own unit are individual family_nodes rows tracked here, not units themselves. Married
    children show up instead as their OWN family_groups row, linked back via
    husband_parent_group_id/wife_parent_group_id.

Dormancy (computed live, never stored, same house style as _node_display_name()/_node_dob()
refusing to trust a stale snapshot once a node is claimed): a unit is dormant once NEITHER founder
slot is a filled, alive node. Admin authority for a dormant unit's own chat doesn't move -- a
founder's own admin row is historical fact -- but authority to act on the unit's CHILD units
(rename/link/mark-deceased reaching a dormant ancestor) passes up through EITHER parent-group
chain, deliberately with no patrilineal/matrilineal default: any reachable active ancestor on
either side is an equally valid authority. See _is_admin_of_group().

One schema addition beyond the four columns on family_groups: people_requests.target_node_id.
Needed because the old admin-derivation-via-spouse_links this module's PREVIOUS pass built has no
source of truth left to derive from once family_spouse_links is deprecated -- a spousal join now
means "let me claim this unit's still-empty founder slot," which is a *request to be linked*
(self-initiated, approval-gated), not the admin-initiated, instant link_node_to_user(). Recording
which node the requester means to become, on the request itself, is the explicit, simple way to
thread that through social_core.decide_request()'s existing accept flow without re-deriving intent
from an edge table that no longer exists for new marriages.

Real-world family structure (2026-10-26): the paragraph above still describes the generic
self-service join (a parent/grandparent placeholder a child's activation wizard matched, still
approval-gated via request_join_group()/decide_request()). A MARRIAGE is no longer this -- the
founder's ruling is that a declared mutual fact between two people doesn't need a third party's
sign-off, unlike every other join here. marry_timeline()'s two founder-slot-claiming branches call
_claim_founder_slot() directly instead (the exact same re-pointing mechanics add_member()'s accept
branch already used, just invoked synchronously instead of behind an approval queue), and the
other founder gets a courtesy notification (_notify_marriage()), never a blocking request. Active
unit membership (family_group_members -- never the tree itself) is now a live-computed function of
the tree shape and marital status, not a one-off grant made at the moment a wizard runs -- see
_sync_family_membership(), called at the end of activate_timeline(), every marry_timeline() exit
path, add_member()'s founder-slot claim, and link_node_to_user().
"""
from __future__ import annotations

import datetime as dt
import json
import re

import cycle_middleware

SCHEMA = """
CREATE TABLE IF NOT EXISTS family_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claimed_user_id INTEGER,              -- NULL = empty/unclaimed
    created_by_user_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,           -- authoritative while empty; once claimed, users.name wins (see _node_display_name)
    gender TEXT,
    dob_approx TEXT,                      -- only meaningful while empty; once claimed, users.dob wins (see _node_dob)
    status TEXT NOT NULL DEFAULT 'empty', -- empty | claimed
    is_deceased INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    claimed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_family_nodes_claimed_user ON family_nodes(claimed_user_id) WHERE claimed_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_family_nodes_created_by ON family_nodes(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_family_nodes_display_name ON family_nodes(display_name);

CREATE TABLE IF NOT EXISTS family_parent_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_node_id INTEGER NOT NULL,
    child_node_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', -- active | deceased -- describes the PARENT, not the edge
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (parent_node_id, child_node_id)
);
CREATE INDEX IF NOT EXISTS idx_family_parent_links_child ON family_parent_links(child_node_id);
CREATE INDEX IF NOT EXISTS idx_family_parent_links_parent ON family_parent_links(parent_node_id);

-- Deprecated (2026-10-20): kept for historical rows only. A marriage is now the unit itself
-- (family_groups.husband_node_id/wife_node_id); see this module's docstring.
CREATE TABLE IF NOT EXISTS family_spouse_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_lo_id INTEGER NOT NULL,
    node_hi_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active', -- active | separated | deceased
    created_by_user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (node_lo_id, node_hi_id)
);
CREATE INDEX IF NOT EXISTS idx_family_spouse_links_lo ON family_spouse_links(node_lo_id);
CREATE INDEX IF NOT EXISTS idx_family_spouse_links_hi ON family_spouse_links(node_hi_id);

CREATE TABLE IF NOT EXISTS family_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_by_user_id INTEGER NOT NULL,   -- historical/audit only -- NOT the permission-check column
    kind TEXT NOT NULL DEFAULT 'unit',     -- historical ('lineage'|'marital') on old rows; always 'unit' going forward
    husband_node_id INTEGER,               -- FK family_nodes -- one of this unit's two founders
    wife_node_id INTEGER,                  -- FK family_nodes -- the other founder
    husband_parent_group_id INTEGER,       -- FK family_groups -- husband's OWN birth unit, if known
    wife_parent_group_id INTEGER,          -- FK family_groups -- wife's OWN birth unit, if known
    marriage_status TEXT NOT NULL DEFAULT 'active',  -- active | separated | dissolved (no mutator route built yet)
    eldest_node_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_family_groups_creator ON family_groups(created_by_user_id);

CREATE TABLE IF NOT EXISTS family_group_members (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'approved',  -- approved | left | pending (re-invited after leaving/removal)
    is_admin INTEGER NOT NULL DEFAULT 0,
    invited_by INTEGER,
    created_at TEXT NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS family_group_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_family_group_messages ON family_group_messages(group_id, id);

CREATE TABLE IF NOT EXISTS family_group_nodes (
    group_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    added_by_user_id INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (group_id, node_id)
);
"""

MAX_MESSAGE_CHARS = 1000
MAX_NODE_NAME_CHARS = 80  # matches the registration/activation forms' own name-field limit


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)

    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "timeline_activated_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN timeline_activated_at TEXT")

    node_cols = {r["name"] for r in conn.execute("PRAGMA table_info(family_nodes)")}
    if "is_deceased" not in node_cols:
        conn.execute("ALTER TABLE family_nodes ADD COLUMN is_deceased INTEGER NOT NULL DEFAULT 0")

    member_cols = {r["name"] for r in conn.execute("PRAGMA table_info(family_group_members)")}
    if "is_admin" not in member_cols:
        conn.execute("ALTER TABLE family_group_members ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    group_cols = {r["name"] for r in conn.execute("PRAGMA table_info(family_groups)")}
    if "owner_user_id" in group_cols and "created_by_user_id" not in group_cols:
        conn.execute("ALTER TABLE family_groups RENAME COLUMN owner_user_id TO created_by_user_id")
        group_cols = {r["name"] for r in conn.execute("PRAGMA table_info(family_groups)")}
    if "kind" not in group_cols:
        conn.execute("ALTER TABLE family_groups ADD COLUMN kind TEXT NOT NULL DEFAULT 'unit'")
    for col, ddl in (
        ("husband_node_id", "INTEGER"), ("wife_node_id", "INTEGER"),
        ("husband_parent_group_id", "INTEGER"), ("wife_parent_group_id", "INTEGER"),
        ("marriage_status", "TEXT NOT NULL DEFAULT 'active'"),
    ):
        if col not in group_cols:
            conn.execute(f"ALTER TABLE family_groups ADD COLUMN {col} {ddl}")
    # Indexed here, not in SCHEMA's CREATE TABLE block -- on an already-existing family_groups
    # table, CREATE TABLE IF NOT EXISTS is a no-op, so an index on these columns would run before
    # the ALTERs above ever add them.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_family_groups_husband_parent ON family_groups(husband_parent_group_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_family_groups_wife_parent ON family_groups(wife_parent_group_id)")

    # people_requests is social_core.py's own table -- this is the same lazy, defensive
    # cross-module ALTER pattern identity_core.py already uses on `users` (a table db/schema.sql
    # owns). Needed because the spouse-join request now means "let me claim this specific empty
    # founder node," and family_spouse_links -- the OLD way to derive that intent -- is deprecated.
    pr_cols = {r["name"] for r in conn.execute("PRAGMA table_info(people_requests)")}
    if pr_cols and "target_node_id" not in pr_cols:
        conn.execute("ALTER TABLE people_requests ADD COLUMN target_node_id INTEGER")

    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---- Node helpers: a claimed node's name/dob always resolve live from `users`, never from the
# node's own (possibly stale) snapshot columns, which only matter while the node is still empty ----

def _node_display_name(conn, node_id: int):
    row = conn.execute("SELECT claimed_user_id, display_name FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    if not row:
        return None
    if row["claimed_user_id"]:
        u = conn.execute("SELECT name FROM users WHERE id = ?", (row["claimed_user_id"],)).fetchone()
        return u["name"] if u else row["display_name"]
    return row["display_name"]


def _node_dob(conn, node_id: int):
    row = conn.execute("SELECT claimed_user_id, dob_approx FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    if not row:
        return None
    if row["claimed_user_id"]:
        u = conn.execute("SELECT dob FROM users WHERE id = ?", (row["claimed_user_id"],)).fetchone()
        return u["dob"] if u else None
    return row["dob_approx"]


def _node_is_deceased(conn, node_id: int) -> bool:
    row = conn.execute("SELECT is_deceased FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    return bool(row and row["is_deceased"])


def _claimed_user_for_node(conn, node_id):
    if not node_id:
        return None
    row = conn.execute("SELECT claimed_user_id FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    return row["claimed_user_id"] if row else None


def create_node(conn, created_by_user_id: int, display_name: str, gender=None, dob_approx=None,
                 claimed_user_id=None, is_deceased=False) -> int:
    display_name = (display_name or "").strip()
    if not display_name:
        raise ValueError("A name is required")
    now = _now()
    cur = conn.execute(
        """INSERT INTO family_nodes (claimed_user_id, created_by_user_id, display_name, gender, dob_approx,
                                      status, is_deceased, created_at, claimed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (claimed_user_id, created_by_user_id, display_name, gender, dob_approx,
         "claimed" if claimed_user_id else "empty", 1 if is_deceased else 0,
         now, now if claimed_user_id else None),
    )
    return cur.lastrowid


# ---- Dormancy and admin authority (2026-10-20): a unit is dormant once NEITHER founder slot is a
# filled, alive node -- computed live, never stored. Authority to act on a dormant unit's own
# descendant units passes up through EITHER parent-group chain -- deliberately no default side. ----

def _group_is_dormant(conn, group_id) -> bool:
    row = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        return False

    def alive(node_id):
        if not node_id:
            return False
        n = conn.execute("SELECT is_deceased FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
        return bool(n) and not n["is_deceased"]

    return not (alive(row["husband_node_id"]) or alive(row["wife_node_id"]))


def _founder_alive_match(conn, user_id: int, group_id: int) -> bool:
    """True if user_id IS one of this group's two founders, and that founder is currently alive."""
    row = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        return False
    for node_id in (row["husband_node_id"], row["wife_node_id"]):
        if not node_id:
            continue
        n = conn.execute("SELECT claimed_user_id, is_deceased FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
        if n and n["claimed_user_id"] == user_id and not n["is_deceased"]:
            return True
    return False


def _is_admin_of_group(conn, user_id: int, group_id: int, _visited=None) -> bool:
    """True if user_id currently has administrative authority over group_id: a living founder (or,
    failing that, any approved is_admin=1 membership row -- the same check, generalized) of this
    unit if it's still active; if the unit has gone dormant (both founders deceased), authority is
    inherited from ANY reachable active ancestor on EITHER the husband's or the wife's parent-group
    chain -- no patrilineal/matrilineal default. _visited guards a pathological cycle."""
    _visited = _visited if _visited is not None else set()
    if group_id in _visited:
        return False
    _visited.add(group_id)

    if _founder_alive_match(conn, user_id, group_id):
        return True
    if not _group_is_dormant(conn, group_id):
        return bool(conn.execute(
            "SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ? AND is_admin = 1 AND status = 'approved'",
            (group_id, user_id),
        ).fetchone())

    row = conn.execute(
        "SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (group_id,)
    ).fetchone()
    if not row:
        return False
    return any(
        pid and _is_admin_of_group(conn, user_id, pid, _visited)
        for pid in (row["husband_parent_group_id"], row["wife_parent_group_id"])
    )


def _is_admin_of_node_group(conn, user_id: int, node_id: int) -> bool:
    """True if user_id has administrative authority (see _is_admin_of_group, including dormant
    ancestor succession) over AT LEAST ONE unit this node belongs to -- the shared check
    mark_deceased()/rename_node()/link_node_to_user() all need. A node can be in more than one
    unit; any one of them being admin-accessible is enough."""
    group_ids = [r["group_id"] for r in conn.execute("SELECT group_id FROM family_group_nodes WHERE node_id = ?", (node_id,))]
    return any(_is_admin_of_group(conn, user_id, gid) for gid in group_ids)


def mark_deceased(conn, user_id: int, node_id: int, is_deceased: bool = True) -> None:
    """Toggles a node's deceased flag. Any admin (including one who inherited authority from a
    dormant ancestor unit) of a group this node belongs to may do this -- purely a tree-display
    attribute, never touching the real users row or that account's login capability even for a
    claimed node (a real, separate, far more sensitive admin action)."""
    if not conn.execute("SELECT 1 FROM family_nodes WHERE id = ?", (node_id,)).fetchone():
        raise LookupError("Node not found")
    if not _is_admin_of_node_group(conn, user_id, node_id):
        raise PermissionError("Only an admin of a group this person belongs to can change this")
    conn.execute("UPDATE family_nodes SET is_deceased = ? WHERE id = ?", (1 if is_deceased else 0, node_id))
    conn.commit()


def rename_node(conn, user_id: int, node_id: int, new_name) -> None:
    """Renames an EMPTY node's display name -- never a claimed one. A claimed node's visible name
    always comes live from users.name (see _node_display_name()), so renaming the snapshot column
    here would silently do nothing visible -- refusing outright is less confusing than a no-op.
    Any admin of a group this node belongs to may do this."""
    row = conn.execute("SELECT claimed_user_id FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    if not row:
        raise LookupError("Node not found")
    if row["claimed_user_id"]:
        raise ValueError("This person has a real Qumanity account -- their name can only be changed on their own profile")
    if not _is_admin_of_node_group(conn, user_id, node_id):
        raise PermissionError("Only an admin of a group this person belongs to can change this")
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("A name is required")
    if len(new_name) > MAX_NODE_NAME_CHARS:
        raise ValueError(f"Name is too long (max {MAX_NODE_NAME_CHARS} characters)")
    conn.execute("UPDATE family_nodes SET display_name = ? WHERE id = ?", (new_name, node_id))
    conn.commit()


def _resolve_target_user_id(conn, raw) -> int:
    """Accepts the 12-digit Public Search ID only -- spaces and dashes are stripped before
    matching, so '4060 2408 5969' and '4060-2408-5969' both normalize to the same 12 digits (a
    real bug this fixed, 2026-10-20: the previous version had NO path for a search code at all --
    an all-digit string was treated as a raw family_nodes/users primary key, which a real 12-digit
    code never is, so every correctly-typed Public ID was silently rejected as 'not found').
    Looked up the same way social_core.find_person() resolves one, via account_ids.search_code
    (is_current=1 -- a user's search code can change, e.g. after a present-location switch; only
    their CURRENT one is live). Raises ValueError if it isn't a valid 12-digit code or doesn't
    resolve to a real user -- never leaks which case failed, same as every other identity lookup
    in this project."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) != 12:
        raise ValueError("Enter a 12-digit Public ID")
    row = conn.execute(
        "SELECT user_id FROM account_ids WHERE search_code = ? AND is_current = 1", (digits,)
    ).fetchone()
    if not row:
        raise ValueError("No member found with that Public ID")
    return row["user_id"]


def _grant_founder_admin_if_applicable(conn, node_id: int, newly_claimed_user_id: int) -> None:
    """If node_id is a FOUNDER slot (husband_node_id or wife_node_id) of any unit, the newly-linked
    real person becomes that unit's co-admin immediately -- the natural consequence of founder
    status, not a new privilege being smuggled in via linking. A node that's just a plain
    child-member of a unit grants nothing extra here."""
    for g in conn.execute("SELECT id FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?", (node_id, node_id)):
        conn.execute(
            """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at)
               VALUES (?, ?, 'approved', 1, NULL, ?)
               ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved', is_admin = 1""",
            (g["id"], newly_claimed_user_id, _now()),
        )


def _repoint_founder_slot(conn, group_id: int, old_node_id: int, new_node_id: int) -> None:
    """Swaps which node fills ONE unit's husband_node_id/wife_node_id -- just that column.
    family_group_nodes and family_parent_links are handled uniformly by _swap_node_references(),
    called alongside this, never by this function, so the two compose instead of overlapping."""
    group = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        return
    slot_col = "husband_node_id" if group["husband_node_id"] == old_node_id else "wife_node_id"
    conn.execute(f"UPDATE family_groups SET {slot_col} = ? WHERE id = ?", (new_node_id, group_id))


def _swap_node_references(conn, old_node_id: int, new_node_id: int, acted_by_user_id: int) -> None:
    """Re-points every family_group_nodes and family_parent_links row that references an
    unclaimed placeholder node to a real person's own existing node instead -- needed whenever
    that real person already has a node elsewhere, so the placeholder can never be claimed
    directly (family_nodes.claimed_user_id is globally unique). Row-by-row INSERT-then-DELETE,
    not a bulk UPDATE: a row that would collide with one new_node_id already has (either table's
    own UNIQUE constraint) is silently skipped (INSERT OR IGNORE) rather than crashing the whole
    swap. Global, not scoped to one group -- a placeholder being linked may already carry its own
    family_parent_links (e.g. a father placeholder linked as a parent during activate_timeline()),
    and those must move too, not just the founder-slot column a caller may separately update via
    _repoint_founder_slot(). The placeholder node itself is left in the database afterwards, just
    unreferenced by anything."""
    for row in conn.execute("SELECT group_id, added_by_user_id FROM family_group_nodes WHERE node_id = ?", (old_node_id,)).fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
            (row["group_id"], new_node_id, row["added_by_user_id"], _now()),
        )
    conn.execute("DELETE FROM family_group_nodes WHERE node_id = ?", (old_node_id,))

    for row in conn.execute("SELECT child_node_id, created_by_user_id FROM family_parent_links WHERE parent_node_id = ?", (old_node_id,)).fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO family_parent_links (parent_node_id, child_node_id, created_by_user_id, created_at) VALUES (?, ?, ?, ?)",
            (new_node_id, row["child_node_id"], row["created_by_user_id"], _now()),
        )
    for row in conn.execute("SELECT parent_node_id, created_by_user_id FROM family_parent_links WHERE child_node_id = ?", (old_node_id,)).fetchall():
        conn.execute(
            "INSERT OR IGNORE INTO family_parent_links (parent_node_id, child_node_id, created_by_user_id, created_at) VALUES (?, ?, ?, ?)",
            (row["parent_node_id"], new_node_id, row["created_by_user_id"], _now()),
        )
    conn.execute("DELETE FROM family_parent_links WHERE parent_node_id = ? OR child_node_id = ?", (old_node_id, old_node_id))


def _claim_founder_slot(conn, target_node_id: int, user_id: int) -> None:
    """Instantly claims an unclaimed founder-slot placeholder (target_node_id) as user_id's own
    self-node -- re-points whichever unit's husband_node_id/wife_node_id column holds it, swaps
    every other reference to the placeholder onto the real node, and grants founder-admin. Shared
    by add_member()'s approval-gated 'claim this slot' accept branch and marry_timeline()'s
    automatic, unapproved marriage-join path (2026-10-26 ruling: marriage is a declared mutual
    fact, not a claim needing a third party's sign-off, unlike every other join in this module --
    see this module's docstring). Caller's responsibility: confirm target_node_id is actually
    still unclaimed before calling."""
    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if not self_node:
        raise ValueError("Activate your Family Timeline before joining a Family Group")
    group = conn.execute(
        "SELECT id FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?", (target_node_id, target_node_id)
    ).fetchone()
    if group:
        _repoint_founder_slot(conn, group["id"], target_node_id, self_node["id"])
    _swap_node_references(conn, target_node_id, self_node["id"], user_id)
    _grant_founder_admin_if_applicable(conn, self_node["id"], user_id)


def link_node_to_user(conn, user_id: int, node_id: int, target) -> None:
    """Links an EMPTY node to a real user -- an admin unilaterally identifying who this person
    really is. If that node is a unit's founder slot, the newly-linked person becomes that unit's
    co-admin (see _grant_founder_admin_if_applicable); otherwise this deliberately does NOT touch
    family_group_members at all -- adding a stranger into a group's chat without their own
    request/consent would reverse the join-then-approve model used everywhere else in this
    project. The linked person can still separately request to join if they want to.

    Only ever claims a node that is still empty -- a placeholder someone else already claimed
    stays refused outright, same as before.

    2026-10-25: a target who ALREADY has their own self-node elsewhere (they registered and
    activated independently, e.g. a parent who joined Qumanity before their child's activation
    wizard tried to link them) is no longer blocked with "already has their own profile node
    elsewhere". family_nodes.claimed_user_id staying globally unique means the placeholder can
    never be claimed a second time, so instead every reference to the placeholder is re-pointed
    to the target's own real node -- the exact mechanism the spousal-join flow (add_member()'s
    target_node_id path) already uses for the identical situation one role over. A founder-slot
    placeholder (husband_node_id/wife_node_id of some unit) also re-points that column and grants
    founder-admin, same as any fresh founder claim; a plain child-member placeholder only needs
    _swap_node_references(). This does NOT attempt to unify the viewer's and the target's own
    separate units into one tree beyond that -- a deliberately separate, harder decision. The
    target is sent the same courtesy ping notify_to_activate() already sends for any other
    identity match; this is never consent-gated, consistent with every other admin-initiated link
    in this module."""
    row = conn.execute("SELECT claimed_user_id FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    if not row:
        raise LookupError("Node not found")
    if row["claimed_user_id"]:
        raise ValueError("This node is already linked to a member")
    if not _is_admin_of_node_group(conn, user_id, node_id):
        raise PermissionError("Only an admin of a group this person belongs to can change this")
    target_user_id = _resolve_target_user_id(conn, target)

    existing_self_node = conn.execute(
        "SELECT id FROM family_nodes WHERE claimed_user_id = ?", (target_user_id,)
    ).fetchone()
    if existing_self_node:
        real_node_id = existing_self_node["id"]
        founder_groups = conn.execute(
            "SELECT id FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?", (node_id, node_id)
        ).fetchall()
        for g in founder_groups:
            _repoint_founder_slot(conn, g["id"], node_id, real_node_id)
        _swap_node_references(conn, node_id, real_node_id, user_id)
        if founder_groups:
            _grant_founder_admin_if_applicable(conn, real_node_id, target_user_id)
        notify_to_activate(conn, user_id, target_user_id)
        _sync_family_membership(conn, target_user_id)
        conn.commit()
        return

    conn.execute(
        "UPDATE family_nodes SET claimed_user_id = ?, status = 'claimed', claimed_at = ? WHERE id = ?",
        (target_user_id, _now(), node_id),
    )
    _grant_founder_admin_if_applicable(conn, node_id, target_user_id)
    _sync_family_membership(conn, target_user_id)
    conn.commit()


def link_parent(conn, parent_node_id: int, child_node_id: int, created_by_user_id: int) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO family_parent_links (parent_node_id, child_node_id, created_by_user_id, created_at)
           VALUES (?, ?, ?, ?)""",
        (parent_node_id, child_node_id, created_by_user_id, _now()),
    )


# ---- Naming (2026-10-20): '[HusbandCode]-[WifeCode]-[Surname] Family', both founders
# contributing -- not just whichever is eldest-and-alive, the old _group_name_from() rule this
# replaces. _pick_unit_eldest() below is a SEPARATE, still-needed concept (it picks which founder
# fills family_groups.eldest_node_id, unused by naming) and is untouched. ----

def _split_name_parts(full_name: str, explicit_middle: str = None) -> tuple:
    """(first, middle, last) tokens from a free-text name. `explicit_middle` -- a claimed user's
    own users.middle_name -- wins outright when given; otherwise any tokens strictly between the
    first and last word of `full_name` fill that role, so a name typed as one string ("A P J
    Abdul Kalam") still yields a sensible middle ("P J Abdul") without ever touching a dedicated
    middle-name field -- the only form an unclaimed placeholder node's name can take at all,
    since family_nodes has no middle_name column of its own."""
    tokens = (full_name or "").split()
    if not tokens:
        return "", "", ""
    first = tokens[0]
    last = tokens[-1] if len(tokens) > 1 else ""
    middle = (explicit_middle or "").strip() or " ".join(tokens[1:-1])
    return first, middle, last


def _name_parts_for_node(conn, node_id) -> tuple:
    """(first, middle, last) for a family_nodes.id -- live from `users` (name + middle_name) once
    claimed, same live-resolution rule as _node_display_name(); an unclaimed placeholder has no
    middle_name column at all, so its Middle comes purely from _split_name_parts()'s
    between-tokens fallback on its single display_name string."""
    if not node_id:
        return "", "", ""
    row = conn.execute("SELECT claimed_user_id, display_name FROM family_nodes WHERE id = ?", (node_id,)).fetchone()
    if not row:
        return "", "", ""
    if row["claimed_user_id"]:
        u = conn.execute("SELECT name, middle_name FROM users WHERE id = ?", (row["claimed_user_id"],)).fetchone()
        if u:
            return _split_name_parts(u["name"], u["middle_name"])
    return _split_name_parts(row["display_name"])


def _name_code(first: str, middle: str, last: str, fallback_last: str = "") -> str:
    """The 4-letter per-founder code, verified against the founder's own worked examples:
      "A"/"P J Abdul"/"Kalam" -> APAM | "Vishal"/-/"Kumar" -> VIAR
      "Sakshi"/no last (fallback="Kumar") -> SAAR (the "crucial rule": no surname of her own
      borrows the husband's) | "Amit"/no last/no fallback -> AMIT (self-pads from its own pool)

    `pool` is First+Middle run together (spaces stripped); its first 2 characters are the code's
    initials (First's own letters first, reaching into Middle only once First alone is shorter
    than 2 characters). The last 2 characters come from Last's own last 2 letters, or --  only
    when this side has no last name at all -- fallback_last's, or, failing both, the NEXT 2
    characters of the same pool (indices [2:4]), so a bare single name still yields a stable
    4-character code from itself alone. A pool/last shorter than 2 characters yields a shorter-
    than-4 code rather than padding with anything invented."""
    pool = (first or "") + (middle or "").replace(" ", "")
    initials = pool[:2].upper()
    effective_last = last or fallback_last
    tail = (effective_last[-2:] if effective_last else pool[2:4]).upper()
    return initials + tail


def _group_name_from_couple(conn, husband_node_id, wife_node_id) -> str:
    """'[HusbandCode]-[WifeCode]-[Surname] Family'. Surname is the husband's last name, or the
    wife's if he has none, or omitted entirely if neither does. When both have a last name and
    they DIFFER, the surname is '[HusbandLast] & [WifeLast]' rather than picking one silently.
    Falls back to 'Family Group' if neither founder is known yet (mirrors the old function's
    behavior for a not-yet-fully-formed unit)."""
    h_first, h_middle, h_last = _name_parts_for_node(conn, husband_node_id)
    w_first, w_middle, w_last = _name_parts_for_node(conn, wife_node_id)
    if not h_first and not w_first:
        return "Family Group"

    h_code = _name_code(h_first, h_middle, h_last) if h_first else ""
    w_code = _name_code(w_first, w_middle, w_last, fallback_last=h_last) if w_first else ""
    codes = "-".join(c for c in (h_code, w_code) if c)

    if h_last and w_last:
        surname = h_last if h_last.lower() == w_last.lower() else f"{h_last} & {w_last}"
    else:
        surname = h_last or w_last
    return f"{codes}-{surname} Family" if surname else f"{codes} Family"


def _pick_unit_eldest(conn, husband_node_id, wife_node_id):
    """Only ALIVE candidates are eligible (an admin must be alive); among those, earliest DOB
    wins. Falls back to earliest family_nodes.created_at if nobody is alive (shouldn't normally
    happen -- whoever is CREATING this unit must themselves be alive) so this never returns None
    for a unit with at least one founder."""
    candidates = [nid for nid in (husband_node_id, wife_node_id) if nid]
    alive = []
    for nid in candidates:
        if _node_is_deceased(conn, nid):
            continue
        alive.append((_node_dob(conn, nid) or "9999-99-99", nid))
    if alive:
        alive.sort()
        return alive[0][1]
    if not candidates:
        return None
    dated = []
    for nid in candidates:
        row = conn.execute("SELECT created_at FROM family_nodes WHERE id = ?", (nid,)).fetchone()
        dated.append((row["created_at"] if row else "", nid))
    dated.sort()
    return dated[0][1]


def _generate_unit_name(conn, husband_node_id, wife_node_id):
    eldest_id = _pick_unit_eldest(conn, husband_node_id, wife_node_id)
    name = _group_name_from_couple(conn, husband_node_id, wife_node_id)
    return name, eldest_id


VALID_MARRIAGE_STATUSES = ("active", "separated", "dissolved")


def create_group(conn, created_by_user_id: int, name: str, eldest_node_id, husband_node_id, wife_node_id,
                  member_node_ids, husband_parent_group_id=None, wife_parent_group_id=None,
                  marriage_status: str = "active") -> int:
    """The low-level mechanics: inserts the unit row, then grants family_group_nodes (tree
    visibility) and -- for whichever of husband/wife/member_node_ids is CURRENTLY a real, claimed
    user -- family_group_members (chat access), is_admin=1 for the two founders. An unclaimed
    founder slot grants admin automatically once link_node_to_user() later claims it.

    marriage_status (2026-10-20): active | separated | dissolved -- the tree's own record of this
    unit's marriage, independent of users.relationship_status (a different, 3-value legacy enum --
    see activate_timeline()'s own relationship-sync, which is deliberately a separate mapping for a
    separate column). A widowed founder's unit stays 'active' -- the SURVIVING founder is still
    alive, it's their deceased spouse's own is_deceased flag that records the loss, not this column.

    The creator is ALSO always granted is_admin=1, additive to (not a replacement for) founder
    admin -- practically necessary the moment a unit is first founded with one or both slots still
    unclaimed placeholders (e.g. a child activating with parents who haven't registered yet):
    without this, nobody could rename a typo'd placeholder or link it once that person signs up,
    since neither slot has a real admin yet. Mirrors the pre-restructure model, which granted the
    creator admin unconditionally."""
    if marriage_status not in VALID_MARRIAGE_STATUSES:
        raise ValueError("Unknown marriage status")
    cur = conn.execute(
        """INSERT INTO family_groups (name, created_by_user_id, kind, husband_node_id, wife_node_id,
                                       husband_parent_group_id, wife_parent_group_id, marriage_status,
                                       eldest_node_id, created_at)
           VALUES (?, ?, 'unit', ?, ?, ?, ?, ?, ?, ?)""",
        (name, created_by_user_id, husband_node_id, wife_node_id,
         husband_parent_group_id, wife_parent_group_id, marriage_status, eldest_node_id, _now()),
    )
    group_id = cur.lastrowid

    conn.execute(
        """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at)
           VALUES (?, ?, 'approved', 1, NULL, ?)
           ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved', is_admin = 1""",
        (group_id, created_by_user_id, _now()),
    )

    founder_ids = {husband_node_id, wife_node_id}
    all_node_ids = {nid for nid in (founder_ids | set(member_node_ids or [])) if nid}
    for nid in all_node_ids:
        conn.execute(
            "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
            (group_id, nid, created_by_user_id, _now()),
        )
        member_user_id = _claimed_user_for_node(conn, nid)
        if member_user_id:
            conn.execute(
                """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at)
                   VALUES (?, ?, 'approved', ?, NULL, ?)
                   ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved', is_admin = MAX(is_admin, excluded.is_admin)""",
                (group_id, member_user_id, 1 if nid in founder_ids else 0, _now()),
            )
    return group_id


def _find_or_create_couple_group(conn, created_by_user_id: int, husband_node_id, wife_node_id,
                                  member_node_ids=None, husband_parent_group_id=None, wife_parent_group_id=None,
                                  marriage_status: str = "active"):
    """Finds an existing unit already founded by this exact pair, or by EITHER side alone (that
    side may already have been entered into a unit from someone else's earlier activation/
    marriage -- e.g. a sibling who activated first), or creates a new one. If both sides
    independently match two DIFFERENT existing units, the husband's side wins -- a documented,
    simplifying tie-break for a genuine data conflict that would need a human to resolve properly
    anyway, not a silent guess dressed up as correct. Returns (group_id, created: bool).

    marriage_status is only used when a NEW unit is created here -- an EXISTING unit's own recorded
    status is never overwritten just because someone else's activation/marriage call happens to
    reuse it (e.g. activate_timeline()'s own parents'-unit lookup always passes the 'active'
    default, regardless of the activating child's own relationship status).

    Deliberately does NOT add member_node_ids to an EXISTING unit found here -- if the caller
    reached it via a 'join' action on a slot, request_join_group() already queued a request to its
    owner inside _resolve_slot(); the requester's own node is only ever added once that request is
    approved (see add_member()), never bypassed here."""
    member_node_ids = member_node_ids or []
    existing = conn.execute(
        """SELECT id FROM family_groups
           WHERE (husband_node_id = ? AND wife_node_id = ?) OR husband_node_id = ? OR wife_node_id = ?
           ORDER BY (husband_node_id = ? AND wife_node_id = ?) DESC, id ASC LIMIT 1""",
        (husband_node_id, wife_node_id, husband_node_id, wife_node_id, husband_node_id, wife_node_id),
    ).fetchone()
    if existing:
        return existing["id"], False
    name, eldest_id = _generate_unit_name(conn, husband_node_id, wife_node_id)
    group_id = create_group(conn, created_by_user_id, name, eldest_id, husband_node_id, wife_node_id,
                             member_node_ids, husband_parent_group_id, wife_parent_group_id, marriage_status)
    return group_id, True


def _find_parents_group_for_node(conn, node_id):
    """The unit where node_id is a plain CHILD-member (not a founder) -- that person's own birth
    unit, if the tree already knows it. None if they haven't been entered as anyone's child yet."""
    if not node_id:
        return None
    row = conn.execute(
        """SELECT fgn.group_id FROM family_group_nodes fgn JOIN family_groups fg ON fg.id = fgn.group_id
           WHERE fgn.node_id = ?
             AND (fg.husband_node_id IS NULL OR fg.husband_node_id != ?)
             AND (fg.wife_node_id IS NULL OR fg.wife_node_id != ?)
           ORDER BY fgn.added_at LIMIT 1""",
        (node_id, node_id, node_id),
    ).fetchone()
    return row["group_id"] if row else None


def add_member(conn, group_id: int, user_id: int, invited_by=None, target_node_id=None) -> None:
    """Approves user_id into the group's chat membership as a PLAIN member (never admin -- only a
    unit's two named founders are ever admins, granted directly at creation or the moment an empty
    founder slot is claimed; see create_group()/link_node_to_user()).

    target_node_id (2026-10-20): set when this request was a self-service "let me claim this
    specific empty founder slot as me" (see request_join_group()'s target_node_id and
    social_core.decide_request()'s family_group_join branch). Request_join_group() only ever
    accepts this request from a user who has ALREADY activated -- so user_id already has their
    OWN self-node, and family_nodes.claimed_user_id is globally unique (one node per real person,
    not just per group). Claiming the placeholder node directly would collide with that. Instead,
    this re-points the GROUP's founder slot at the joiner's own existing self-node (swapping out
    the placeholder, which stays in the DB, just no longer referenced by anything -- see
    _claim_founder_slot(), shared with link_node_to_user()'s identical 2026-10-25 case and
    marry_timeline()'s automatic marriage-join) and grants founder-admin -- the approval itself IS the authorization a
    third-party admin-initiated link_node_to_user() would otherwise need."""
    if target_node_id:
        node = conn.execute("SELECT claimed_user_id FROM family_nodes WHERE id = ?", (target_node_id,)).fetchone()
        self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
        if node and not node["claimed_user_id"] and self_node:
            _claim_founder_slot(conn, target_node_id, user_id)
            _sync_family_membership(conn, user_id)
            return

    conn.execute(
        """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at) VALUES (?, ?, 'approved', 0, ?, ?)
           ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved'""",
        (group_id, user_id, invited_by, _now()),
    )
    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if self_node:
        conn.execute(
            "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
            (group_id, self_node["id"], user_id, _now()),
        )


def request_join_group(conn, user_id: int, group_id: int, target_node_id=None) -> int:
    """Queues a join request for the group's FOUNDING creator to approve (not every current
    co-admin -- a known simplification) -- via the same people_requests table social_core.py
    already uses for group invites/rejoins (kind='family_group_join', group_id repurposed to hold
    family_groups.id, same overloading convention 'rejoin' already uses for private_chats.id).
    target_node_id (optional): this request is specifically "let me claim this empty founder
    slot," not just "let me join as a plain member" -- see add_member(). social_core.decide_request()
    has the matching accept-side branch. Returns the new request's id.

    2026-10-26 (the rejoin rule): a user whose status here is 'left' CANNOT self-request back in
    -- rejoin after a leave or a removal is admin-initiated only (see invite_to_group()); this
    keeps that a deliberate decision by the group's admin, not something the ex-member can just
    undo themselves. A user who was never a member at all is unaffected."""
    if not conn.execute("SELECT 1 FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone():
        raise ValueError("Activate your Family Timeline before joining a Family Group")
    group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise LookupError("Family Group not found")
    if group["created_by_user_id"] == user_id:
        raise ValueError("You already own this group")
    existing = conn.execute(
        "SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (group_id, user_id)
    ).fetchone()
    if existing and existing["status"] == "approved":
        raise ValueError("You are already a member of this group")
    if existing and existing["status"] == "left":
        raise ValueError("You previously left this group — ask an admin to invite you back")
    if conn.execute(
        "SELECT 1 FROM people_requests WHERE from_user_id=? AND to_user_id=? AND kind='family_group_join' AND group_id=? AND status='pending'",
        (user_id, group["created_by_user_id"], group_id),
    ).fetchone():
        raise ValueError("A join request is already waiting")
    cur = conn.execute(
        "INSERT INTO people_requests (from_user_id, to_user_id, kind, group_id, target_node_id, created_at, cycle_id) VALUES (?, ?, 'family_group_join', ?, ?, ?, ?)",
        (user_id, group["created_by_user_id"], group_id, target_node_id, _now(), cycle_middleware.get_active_cycle_id(conn)),
    )
    return cur.lastrowid


def invite_to_group(conn, admin_user_id: int, group_id: int, target_user_id: int) -> int:
    """An admin invites a specific real user to join this unit as a plain member -- the
    admin-initiated counterpart to request_join_group()'s self-initiated "let me join." Takes an
    already-resolved target_user_id, not a raw Public ID: the caller (the frontend's "Add Member
    by Public ID" box) always resolves the ID via /api/people/search first, so the admin confirms
    a real name/avatar before inviting -- matching social_core.send_group_invite()'s own
    signature exactly, not link_node_to_user()'s (which takes a raw Public ID because it has no
    separate confirm-first search step). Queues a people_requests row (kind='family_group_invite')
    the target must accept; nothing is APPROVED until they do, the same join-then-approve model
    as every other group invite in this project.

    2026-10-26 (the rejoin rule): if the target previously left (or was removed from) this group,
    their family_group_members row moves from 'left' to 'pending' right here, at invite time --
    not silently left at 'left' until they accept. 'pending' is a visibility marker only (a
    re-invite is in flight); add_member()'s own accept-time upsert already overwrites ANY prior
    status with 'approved', so this needs no change there. A target with NO row yet (never a
    member before) is untouched -- still no family_group_members row until they accept, same as
    today. Returns the new request's id."""
    if not _is_admin_of_group(conn, admin_user_id, group_id):
        raise PermissionError("Only an admin of this group can invite members")
    group = conn.execute("SELECT 1 FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise LookupError("Family Group not found")
    if not conn.execute("SELECT 1 FROM users WHERE id = ?", (target_user_id,)).fetchone():
        raise LookupError("Member not found")
    if target_user_id == admin_user_id:
        raise ValueError("You can't invite yourself")
    if conn.execute(
        "SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'",
        (group_id, target_user_id),
    ).fetchone():
        raise ValueError("They are already a member of this group")
    if conn.execute(
        "SELECT 1 FROM people_requests WHERE from_user_id = ? AND to_user_id = ? AND group_id = ? AND kind = 'family_group_invite' AND status = 'pending'",
        (admin_user_id, target_user_id, group_id),
    ).fetchone():
        raise ValueError("An invitation is already waiting for them")
    conn.execute(
        "UPDATE family_group_members SET status = 'pending' WHERE group_id = ? AND user_id = ? AND status = 'left'",
        (group_id, target_user_id),
    )
    cur = conn.execute(
        "INSERT INTO people_requests (from_user_id, to_user_id, kind, group_id, created_at, cycle_id) VALUES (?, ?, 'family_group_invite', ?, ?, ?)",
        (admin_user_id, target_user_id, group_id, _now(), cycle_middleware.get_active_cycle_id(conn)),
    )
    return cur.lastrowid


def group_members_for(conn, viewer_user_id: int, group_id: int):
    """The full approved member list for a unit's own Members modal: user_id, name, gender,
    age_group, present_location, profile_picture_url, is_admin, role, you -- every admin (founders
    and creator-admins alike) before plain members, alphabetical within each. Name/present_location
    are masked for a hide_identity member
    exactly like everywhere else a stranger might see them (social_core.member_display_row() ->
    display_identity()). `role` ('founder'|'admin'|'member', 2026-10-27) is the honest label --
    is_admin alone can't tell a unit's actual husband/wife apart from its creator-admin (see
    create_group()'s own additive creator grant), which rendered a plain child as "Admin" in their
    parents' unit. None if the group doesn't exist or the viewer isn't an approved member, same
    404-not-403 convention as neighborhood_for_group()/tree_for_group()."""
    import social_core
    group = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        return None
    member_row = conn.execute(
        "SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'",
        (group_id, viewer_user_id),
    ).fetchone()
    if not member_row:
        return None
    founder_node_ids = {nid for nid in (group["husband_node_id"], group["wife_node_id"]) if nid}
    rows = conn.execute(
        """SELECT u.id, u.name, m.is_admin, fn.id AS node_id
           FROM family_group_members m JOIN users u ON u.id = m.user_id
           LEFT JOIN family_nodes fn ON fn.claimed_user_id = u.id
           WHERE m.group_id = ? AND m.status = 'approved' ORDER BY m.is_admin DESC, u.name""",
        (group_id,),
    ).fetchall()
    return [
        social_core.member_display_row(
            conn, r["id"], viewer_user_id, bool(r["is_admin"]), is_founder=r["node_id"] in founder_node_ids,
        )
        for r in rows
    ]


def _classify_membership(conn, self_node_id: int, group_id: int) -> str:
    """'founder' | 'birth' | 'other' -- how self_node_id relates to group_id, the single
    classification leave_group()/remove_member() both key their rules off (2026-10-26, the three
    real-world exit rules). 'other' covers an in-laws unit, a grandparent unit, or any other plain
    membership not earned by birth -- those carry no special exit restriction at all."""
    group = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if group and self_node_id in (group["husband_node_id"], group["wife_node_id"]):
        return "founder"
    if _find_parents_group_for_node(conn, self_node_id) == group_id:
        return "birth"
    return "other"


def leave_group(conn, user_id: int, group_id: int) -> None:
    """Leaves a unit's chat membership (status='left', never a hard delete -- same convention as
    social_core.leave_chat()). Three real-world exit rules (2026-10-26), keyed off
    _classify_membership():
      - FOUNDER: never allowed -- it's the unit their marriage literally founded, not something
        they joined and could unjoin from. The only people who can never leave at all.
      - BIRTH unit: blocked if the user's own node has a parent OR a child who is still an
        approved member of THIS SAME unit -- leaving would otherwise orphan an active family
        relationship inside the very group meant to represent it. While unmarried this is
        effectively always true (their parents are definitionally active in their own birth
        unit), which is exactly how "cannot leave while unmarried" falls out of this check without
        a separate marriage test. Once married, _sync_family_membership() has already auto-left
        this membership UNLESS it's a creator-admin row (deliberately preserved, see that
        function) -- a married creator-admin may still choose to leave by hand; nothing locks them
        in beyond the founder rule above.
      - Anything else (in-laws unit, grandparent unit, ...): always allowed, no check at all --
        this is the fix for the real bug this same check used to cause: a wife auto-joined to her
        in-laws' unit, whose own child was LATER also auto-joined there as a grandchild, could not
        voluntarily leave her in-laws' unit, because the old unscoped check saw her child as an
        "active relative in this same group" and blocked her -- even though this was never her
        birth unit at all."""
    member_row = conn.execute(
        "SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'",
        (group_id, user_id),
    ).fetchone()
    if not member_row:
        raise LookupError("You are not a member of this group")

    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if self_node:
        classification = _classify_membership(conn, self_node["id"], group_id)
        if classification == "founder":
            raise ValueError("You cannot leave your own family group.")
        if classification == "birth":
            blocking = conn.execute(
                """SELECT 1 FROM family_parent_links fpl
                   JOIN family_nodes fn ON fn.id = (CASE WHEN fpl.parent_node_id = ? THEN fpl.child_node_id ELSE fpl.parent_node_id END)
                   JOIN family_group_members fgm ON fgm.user_id = fn.claimed_user_id AND fgm.group_id = ?
                   WHERE (fpl.parent_node_id = ? OR fpl.child_node_id = ?) AND fgm.status = 'approved'""",
                (self_node["id"], group_id, self_node["id"], self_node["id"]),
            ).fetchone()
            if blocking:
                raise ValueError("You cannot leave this group because your parents/children are active members.")

    conn.execute("UPDATE family_group_members SET status = 'left' WHERE group_id = ? AND user_id = ?", (group_id, user_id))
    conn.commit()


def remove_member(conn, admin_user_id: int, group_id: int, target_user_id: int) -> None:
    """Admin-initiated removal (2026-10-26, the in-laws-unit "the father-in-law can remove her"
    rule, generalized): sets the target's membership to 'left', same column, same convention as a
    voluntary leave_group(). Deliberately NOT scoped to in-laws units only -- _is_admin_of_group()
    is checked generically, so a birth unit's admin can remove a plain (non-founder) member too
    (e.g. a father removing an adult son's active chat membership); the son's node stays in the
    tree, only his active membership is revoked. A FOUNDER can never be removed -- removing one
    isn't a membership action, it's dissolving the marriage, out of scope here, same boundary
    leave_group() draws for the founder themselves."""
    if not _is_admin_of_group(conn, admin_user_id, group_id):
        raise PermissionError("Only an admin of this group can remove members")
    if target_user_id == admin_user_id:
        raise ValueError("Use Leave Group to remove yourself")
    target_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (target_user_id,)).fetchone()
    if target_node and _classify_membership(conn, target_node["id"], group_id) == "founder":
        raise ValueError("A founder cannot be removed from their own family group.")
    if not conn.execute(
        "SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'", (group_id, target_user_id)
    ).fetchone():
        raise LookupError("That member isn't in this group")
    conn.execute("UPDATE family_group_members SET status = 'left' WHERE group_id = ? AND user_id = ?", (group_id, target_user_id))
    conn.commit()


# ---- Family unit chat (2026-10-26): the unit's own message board, readable and writable by its
# APPROVED members only -- the same roster the Members list shows (family_group_members). Anyone
# who left or was removed loses both at once. Non-members get the scoped 404 used throughout this
# module, never a 403 that would confirm the unit exists. ----

FAMILY_MESSAGE_MAX_CHARS = 4000


def _is_approved_member(conn, group_id: int, user_id: int) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'",
        (group_id, user_id),
    ).fetchone())


def family_messages(conn, viewer_user_id: int, group_id: int):
    """The unit's last 200 messages, oldest first, plus its member list -- the same shape as a
    personal group's /messages (social_core.group_messages) so one chat screen can show both.
    None if the unit doesn't exist or the viewer isn't an approved member."""
    import social_core
    group = conn.execute("SELECT id, name FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group or not _is_approved_member(conn, group_id, viewer_user_id):
        return None
    rows = list(reversed(conn.execute(
        """SELECT m.id, m.user_id, m.text, m.created_at FROM family_group_messages m
           WHERE m.group_id = ? ORDER BY m.id DESC LIMIT 200""", (group_id,)).fetchall()))
    who = {}
    for r in rows:
        if r["user_id"] not in who:
            ident = social_core.display_identity(conn, r["user_id"], viewer_user_id) or {}
            who[r["user_id"]] = ident
    return {
        "id": group["id"], "name": group["name"], "is_admin": _is_admin_of_group(conn, viewer_user_id, group_id),
        "members": group_members_for(conn, viewer_user_id, group_id),
        "messages": [{
            "id": r["id"], "user_id": r["user_id"], "mine": r["user_id"] == viewer_user_id,
            "who": who[r["user_id"]].get("name") or "Member", "gender": who[r["user_id"]].get("gender"),
            "profile_picture_url": _profile_picture_url(r["user_id"]) if who[r["user_id"]].get("has_picture") and not who[r["user_id"]].get("hidden") else None,
            "text": r["text"], "at": r["created_at"],
        } for r in rows],
    }


def post_family_message(conn, user_id: int, group_id: int, text: str) -> int:
    """Approved members only (LookupError -> 404 otherwise, same as reading). Returns the new id."""
    if not conn.execute("SELECT 1 FROM family_groups WHERE id = ?", (group_id,)).fetchone() or not _is_approved_member(conn, group_id, user_id):
        raise LookupError("Family Group not found")
    text = (text or "").strip()
    if not text or len(text) > FAMILY_MESSAGE_MAX_CHARS:
        raise ValueError(f"Write a message (up to {FAMILY_MESSAGE_MAX_CHARS} characters)")
    cur = conn.execute("INSERT INTO family_group_messages (group_id, user_id, text, created_at) VALUES (?, ?, ?, ?)",
                       (group_id, user_id, text, _now()))
    conn.commit()
    return cur.lastrowid


def notify_to_activate(conn, from_user_id: int, to_user_id: int) -> None:
    """A courtesy nudge, not a claim -- reuses social_core's own plain message-request, same as any
    other first contact. Never links anything on its own; the recipient still has to show up and
    activate for real, same as every other identity match in this project being confirm-only."""
    import social_core
    text = "Hi! I think we might be related, and I'm building our Family Tree on Qumanity. Want to connect?"
    try:
        social_core.send_message_request(conn, from_user_id, to_user_id, text)
    except ValueError:
        pass  # already connected, or a request is already pending -- the ping isn't the point, the node still gets created


def _notify_marriage(conn, new_spouse_user_id: int, other_founder_user_id: int) -> None:
    """Tells the OTHER founder their spouse just auto-joined their unit -- informational only,
    never gates the join itself (2026-10-26 ruling: marriage is automatic, see this module's
    docstring and marry_timeline()'s instant-join branches). Same plain-message-request mechanism
    notify_to_activate() already established for every other identity-match courtesy ping here."""
    import social_core
    name = conn.execute("SELECT name FROM users WHERE id = ?", (new_spouse_user_id,)).fetchone()["name"]
    text = f"{name} has joined your family unit as your spouse."
    try:
        social_core.send_message_request(conn, new_spouse_user_id, other_founder_user_id, text)
    except ValueError:
        pass  # already connected, or a request is already pending -- the notification isn't the point, the join already happened


# ---- Search: the three-way suggestion logic (Section A of the approved architecture) ----

def search_suggestions(conn, viewer_user_id: int, name: str) -> list[dict]:
    name = (name or "").strip()
    if len(name) < 2:
        return []
    pattern = f"%{name}%"
    results = []
    seen_groups = {r["group_id"] for r in conn.execute(
        "SELECT group_id FROM family_group_members WHERE user_id = ? AND status = 'approved'", (viewer_user_id,)
    )}

    for r in conn.execute(
        """SELECT DISTINCT fgn.group_id, fg.name AS group_name, fg.kind AS group_kind, fn.id AS node_id,
                  COALESCE(u.name, fn.display_name) AS matched_name
           FROM family_nodes fn
           JOIN family_group_nodes fgn ON fgn.node_id = fn.id
           JOIN family_groups fg ON fg.id = fgn.group_id
           LEFT JOIN users u ON u.id = fn.claimed_user_id
           WHERE COALESCE(u.name, fn.display_name) LIKE ? COLLATE NOCASE""",
        (pattern,),
    ):
        if r["group_id"] in seen_groups:
            continue
        seen_groups.add(r["group_id"])
        member_count = conn.execute(
            "SELECT COUNT(*) FROM family_group_members WHERE group_id = ? AND status = 'approved'", (r["group_id"],)
        ).fetchone()[0]
        founders = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (r["group_id"],)).fetchone()
        role = "husband" if founders["husband_node_id"] == r["node_id"] else "wife" if founders["wife_node_id"] == r["node_id"] else "child"
        partner_node_id = founders["wife_node_id"] if role == "husband" else founders["husband_node_id"] if role == "wife" else None
        results.append({
            "type": "group", "group_id": r["group_id"], "group_name": r["group_name"], "group_kind": r["group_kind"],
            "matched_node_id": r["node_id"], "matched_name": r["matched_name"], "member_count": member_count,
            # 2026-10-26: units can share a name (e.g. a person's parents' unit and their own), so
            # say who founded each one, and how the matched person sits in it. A spouse may only
            # join a unit the matched person FOUNDED, into the partner slot nobody has claimed yet.
            "husband_name": _node_display_name(conn, founders["husband_node_id"]) if founders["husband_node_id"] else None,
            "wife_name": _node_display_name(conn, founders["wife_node_id"]) if founders["wife_node_id"] else None,
            "matched_role": role,
            "partner_slot_open": role != "child" and (partner_node_id is None or not _claimed_user_for_node(conn, partner_node_id)),
        })

    for r in conn.execute(
        """SELECT id, name, gender, profile_picture IS NOT NULL AS has_picture FROM users
           WHERE name LIKE ? COLLATE NOCASE AND timeline_activated_at IS NULL AND id != ?""",
        (pattern, viewer_user_id),
    ):
        results.append({
            "type": "unactivated_user", "user_id": r["id"], "name": r["name"], "gender": r["gender"],
            "profile_picture_url": _profile_picture_url(r["id"]) if r["has_picture"] else None,
        })

    # 2026-10-20: real, ALREADY-ACTIVATED members nearby, by name -- a third, different discovery
    # path from the two above (which only ever surface existing family_nodes placeholders, or
    # users who haven't activated at all). This is for "I don't know which of my relatives already
    # has a Qumanity account -- help me find them by name and roughly where they live," distinct
    # from the Activation wizard's own father/mother/spouse/child slot-matching. hide_identity
    # users are excluded outright (not masked) unless already an established family_member --
    # consistent with is_family_member()'s own "the one relationship that still sees a hidden
    # identity's real name" rule, which doesn't apply here since searcher and candidate aren't yet
    # connected (that's the whole point of this search).
    import social_core
    viewer_row = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (viewer_user_id,)).fetchone()
    viewer_location = json.loads(viewer_row["present_location_json"] or "{}") if viewer_row and viewer_row["present_location_json"] else {}
    viewer_district_id = (viewer_location.get("district") or {}).get("id")
    viewer_tehsil_id = (viewer_location.get("tehsil") or {}).get("id")

    if viewer_district_id:
        my_group_ids = {r["group_id"] for r in conn.execute(
            "SELECT group_id FROM family_group_members WHERE user_id = ? AND status = 'approved'", (viewer_user_id,)
        )}
        for r in conn.execute(
            """SELECT id, name, gender, hide_identity, present_location_json, profile_picture IS NOT NULL AS has_picture
               FROM users WHERE name LIKE ? COLLATE NOCASE AND id != ? AND timeline_activated_at IS NOT NULL
                 AND is_demo = 0 AND is_removed = 0""",
            (pattern, viewer_user_id),
        ):
            if r["hide_identity"] and not social_core.is_family_member(conn, r["id"], viewer_user_id):
                continue
            candidate_location = json.loads(r["present_location_json"] or "{}") if r["present_location_json"] else {}
            candidate_district_id = (candidate_location.get("district") or {}).get("id")
            if candidate_district_id != viewer_district_id:
                continue
            candidate_tehsil_id = (candidate_location.get("tehsil") or {}).get("id")
            candidate_group_rows = conn.execute(
                """SELECT fgm.group_id, (fg.husband_node_id IS NOT NULL AND fn.claimed_user_id = ?)
                          OR (fg.wife_node_id IS NOT NULL AND fn2.claimed_user_id = ?) AS is_founder
                   FROM family_group_members fgm JOIN family_groups fg ON fg.id = fgm.group_id
                   LEFT JOIN family_nodes fn ON fn.id = fg.husband_node_id
                   LEFT JOIN family_nodes fn2 ON fn2.id = fg.wife_node_id
                   WHERE fgm.user_id = ? AND fgm.status = 'approved' ORDER BY is_founder DESC""",
                (r["id"], r["id"], r["id"]),
            ).fetchall()
            if not candidate_group_rows:
                continue  # activated but belongs to no unit yet (shouldn't normally happen) -- nothing to join
            candidate_group_ids = {g["group_id"] for g in candidate_group_rows}
            mutual_group_ids = my_group_ids & candidate_group_ids
            mutual_group_name = None
            if mutual_group_ids:
                mutual_row = conn.execute(
                    "SELECT name FROM family_groups WHERE id = ?", (next(iter(mutual_group_ids)),)
                ).fetchone()
                mutual_group_name = mutual_row["name"] if mutual_row else None
            # The join-request target: the candidate's own founded unit if they have one (most
            # relevant for "let's connect our families"), else whichever unit they're first found
            # in -- candidate_group_rows is already ordered founder-first.
            target_group_id = candidate_group_rows[0]["group_id"]
            target_group_name = conn.execute("SELECT name FROM family_groups WHERE id = ?", (target_group_id,)).fetchone()["name"]
            results.append({
                "type": "real_user", "user_id": r["id"], "name": r["name"], "gender": r["gender"],
                "profile_picture_url": _profile_picture_url(r["id"]) if r["has_picture"] else None,
                "location": _location_display_brief(candidate_location),
                "same_tehsil": candidate_tehsil_id is not None and candidate_tehsil_id == viewer_tehsil_id,
                "mutual_group_name": mutual_group_name,
                "group_id": target_group_id, "group_name": target_group_name,
            })

    if not results:
        results.append({"type": "none"})
    return results


def _profile_picture_url(user_id: int) -> str:
    """The one URL form every caller uses for a user's profile picture -- never built ad hoc,
    so a path change only happens here. Unconditional: the serving route itself (GET
    /api/users/<id>/profile-picture) is what enforces the hide_identity gate, returning 404 for a
    viewer who isn't family -- an <img> tag just shows nothing on a 404, no different from any
    other broken-image fallback already needed for "no picture uploaded" at all."""
    return f"/api/users/{user_id}/profile-picture"


def _location_display_brief(location: dict) -> str:
    """'Village, Tehsil, District' (whatever levels are present) -- display-only, for a search
    result card; never the full chain, and never used for anything access-control related."""
    parts = [location.get(level, {}).get("name") for level in ("village", "tehsil", "district")]
    return ", ".join(p for p in parts if p)


# ---- Relation slot resolution: shared by activate_timeline() (father/mother) and
# marry_timeline() (spouse/children) ----

VALID_NODE_GENDERS = ("male", "female", "both")  # same 3 values registration offers (templates/register.html) -- never a different vocabulary for the same concept


def _resolve_gender(entry: dict, default_gender):
    """entry.get("gender") wins when the caller supplied one (the wizard's own explicit Son/
    Daughter/Child selection for a child slot) -- default_gender is only a role-based fallback
    (activate_timeline() passes 'male' for father, 'female' for mother; nothing else does)."""
    gender = entry.get("gender") or default_gender
    if gender is not None and gender not in VALID_NODE_GENDERS:
        raise ValueError("Unknown gender")
    return gender


def _resolve_slot(conn, user_id: int, entry: dict, fresh_node_ids: list, results: dict, label: str, default_gender=None):
    """One relation entry -- {"name", "action": "create"|"join"|"notify", "is_deceased"?, "gender"?,
    ...}. Returns the family_nodes.id this entry ends up representing (always non-None once a name
    was given -- 'notify' still creates a normal empty node; the ping is a side effect, not a
    different structural outcome, so parent/child linking works uniformly either way)."""
    if not entry or not (entry.get("name") or "").strip():
        return None
    action = entry.get("action", "create")
    name = entry["name"].strip()
    gender = _resolve_gender(entry, default_gender)

    if action == "join":
        group_id, matched_node_id = entry.get("group_id"), entry.get("matched_node_id")
        if not group_id or not matched_node_id:
            raise ValueError(f"Missing group/node to join for {label}")
        request_join_group(conn, user_id, group_id)
        results["joined_requests"].append({"label": label, "name": name, "group_id": group_id})
        return matched_node_id

    if action == "notify":
        target_user_id = entry.get("user_id")
        if target_user_id:
            notify_to_activate(conn, user_id, target_user_id)
            results["notified"].append({"label": label, "name": name, "user_id": target_user_id})
            existing_self_node = conn.execute(
                "SELECT id FROM family_nodes WHERE claimed_user_id = ?", (target_user_id,)
            ).fetchone()
            if existing_self_node:
                results["created_node_ids"].append({"label": label, "node_id": existing_self_node["id"], "name": name, "linked_existing": True})
                return existing_self_node["id"]
        node_id = create_node(conn, user_id, name, gender=gender)
        fresh_node_ids.append(node_id)
        results["created_node_ids"].append({"label": label, "node_id": node_id, "name": name})
        return node_id

    node_id = create_node(conn, user_id, name, gender=gender, is_deceased=bool(entry.get("is_deceased")))
    fresh_node_ids.append(node_id)
    results["created_node_ids"].append({"label": label, "node_id": node_id, "name": name, "is_deceased": bool(entry.get("is_deceased"))})
    return node_id


# ---- Activation: father + mother -> find-or-create THEIR couple-unit, with the activating user
# added as one of its (unmarried) child-members. ----

# The Activation wizard's own 5-way relationship question (2026-10-20) -> users.relationship_status,
# a separate, older, 3-value enum (app.py's RELATIONSHIP_STATUSES) read elsewhere for Qoins/Kundali
# eligibility. Deliberately a different mapping from marriage_status (family_groups' own, richer
# 3-value enum, set by marry_timeline()) -- same wizard answer, two different destination columns
# with two different vocabularies, not one shared value reused twice.
_RELATIONSHIP_TO_PROFILE_STATUS = {
    "single": "single",
    "married": "married",
    "separated": "divorced_widowed",
    "divorced": "divorced_widowed",
    "widowed": "divorced_widowed",
}


def _link_known_parents_group(conn, user_id: int, child_node_id: int, group_id: int, side_column: str,
                               father_entry, mother_entry, results: dict, father_label: str, mother_label: str):
    """Shared by activate_timeline() (linking the user's own parents' unit to grandparents' units)
    and marry_timeline() (linking the user's own unit to the spouse's parents' unit) -- resolves an
    optional (father, mother) pair into a couple-unit with child_node_id as their child-member, and
    fills side_column ('husband_parent_group_id' | 'wife_parent_group_id') on group_id ONLY if it's
    currently unset -- never overwrites an already-known link (e.g. a sibling who activated earlier
    and already supplied this same grandparent pair). Returns the grandparents'/spouse-parents' own
    group_id, or None if neither entry had a name."""
    assert side_column in ("husband_parent_group_id", "wife_parent_group_id")
    if not father_entry and not mother_entry:
        return None
    father_id = _resolve_slot(conn, user_id, father_entry or {}, [], results, father_label, default_gender="male")
    mother_id = _resolve_slot(conn, user_id, mother_entry or {}, [], results, mother_label, default_gender="female")
    if not father_id and not mother_id:
        return None
    known_group_id, _ = _find_or_create_couple_group(
        conn, user_id, husband_node_id=father_id, wife_node_id=mother_id, member_node_ids=[child_node_id],
    )
    current = conn.execute(f"SELECT {side_column} FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if current and not current[side_column]:
        conn.execute(f"UPDATE family_groups SET {side_column} = ? WHERE id = ?", (known_group_id, group_id))
    return known_group_id


# ---- Explicit tree growth (2026-10-20): the D3 neighborhood view's own "+Add" buttons, for
# growing the tree by hand instead of only through the Activation/Marriage wizards. ----

def add_parents_to_group(conn, user_id: int, group_id: int, side: str, father_entry, mother_entry) -> dict:
    """The '+ Add Father's/Mother's Family' (husband side) / '+ Add Mother's Family' (wife side)
    button: a thin wrapper around _link_known_parents_group(), the exact same mechanism the
    wizards use one generation at a time -- one code path for "known at activation" and "added
    later by hand," not two. Raises ValueError if that side already has a parents' unit (additive
    only, never an overwrite) or if the side's founder slot isn't filled yet, and PermissionError
    if user_id isn't an admin of group_id."""
    if side not in ("husband", "wife"):
        raise ValueError("Unknown side")
    if not _is_admin_of_group(conn, user_id, group_id):
        raise PermissionError("Only an admin of this group can grow the tree here")
    group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise LookupError("Family Group not found")
    side_column = "husband_parent_group_id" if side == "husband" else "wife_parent_group_id"
    founder_node_id = group["husband_node_id"] if side == "husband" else group["wife_node_id"]
    if not founder_node_id:
        raise ValueError("That side's founder isn't known yet")
    if group[side_column]:
        raise ValueError("This side's family is already added")
    if not (father_entry and (father_entry.get("name") or "").strip()) and \
       not (mother_entry and (mother_entry.get("name") or "").strip()):
        raise ValueError("Enter at least one parent's name")
    results = {"joined_requests": [], "notified": [], "created_node_ids": []}
    parent_group_id = _link_known_parents_group(
        conn, user_id, founder_node_id, group_id, side_column,
        father_entry, mother_entry, results, "father", "mother",
    )
    conn.commit()
    results["parent_group_id"] = parent_group_id
    return results


def add_child_to_group(conn, user_id: int, group_id: int, name: str, gender=None) -> dict:
    """The '+ Add Child' AND '+ Add Sibling' buttons -- one primitive, not two: both create a plain,
    unclaimed family_nodes placeholder and link it as a child-member of group_id's two founders.
    'Add Child' passes the viewer's own unit as group_id; 'Add Sibling' (an in-law -- structurally a
    child of the SPOUSE'S parents' unit, not a peer of the viewer) passes THAT unit's group_id
    instead. Unclaimed, so this only grants family_group_nodes (tree visibility), never
    family_group_members (chat access) -- nobody has consented to anything, same as every other
    freshly-created placeholder elsewhere in this module."""
    if not _is_admin_of_group(conn, user_id, group_id):
        raise PermissionError("Only an admin of this group can grow the tree here")
    group = conn.execute("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise LookupError("Family Group not found")
    name = (name or "").strip()
    if not name:
        raise ValueError("A name is required")
    if gender is not None and gender not in VALID_NODE_GENDERS:
        raise ValueError("Unknown gender")
    node_id = create_node(conn, user_id, name, gender=gender)
    for parent_node_id in (group["husband_node_id"], group["wife_node_id"]):
        if parent_node_id:
            link_parent(conn, parent_node_id, node_id, user_id)
    conn.execute(
        "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
        (group_id, node_id, user_id, _now()),
    )
    conn.commit()
    return {"node_id": node_id, "name": name}


# ---- Real-world family membership (2026-10-26): which units a person should ACTIVELY belong to
# (family_group_members) is now a live-computed function of the tree shape + marital status, same
# "computed live, never stored" philosophy this module already uses for dormancy -- not a set of
# one-off grants hand-threaded into each mutation. See _sync_family_membership(). ----

def _sync_family_membership(conn, user_id: int) -> None:
    """Recomputes and applies this person's correct set of ACTIVE family unit memberships from the
    tree's current shape -- the single place that decides "which units does X actively belong to,"
    called at the end of activate_timeline(), marry_timeline() (all three of its exit paths),
    add_member()'s founder-slot claim, and link_node_to_user() -- every point a person's node
    identity or marital status can change. Idempotent and safe to call repeatedly; never demotes an
    existing admin, never touches the TREE itself (family_group_nodes/family_parent_links) -- only
    chat membership (family_group_members) moves.

    Bounded to exactly the three rules the founder has signed off on (2026-10-26), not a general
    recursive walk of arbitrary tree depth:
      1. FOUNDER units (any unit where this person is husband_node_id/wife_node_id) -> admin
         member. Re-confirms _grant_founder_admin_if_applicable()'s own grant; harmless to repeat.
      2. BIRTH unit (_find_parents_group_for_node() -- the unit where this person is a plain
         child-member) -> plain member, UNLESS rule 1 found at least one founder unit (they've
         founded their own marital unit, i.e. they're married), in which case this membership
         moves to 'left' instead. Marriage_status of a past/dissolved marriage isn't distinguished
         here -- once you've founded any unit, your birth-unit chat has moved, full stop; reverting
         that on a later divorce isn't handled and would need a separate pass.
      3. GRANDPARENT units -- the birth unit's OWN husband_parent_group_id/wife_parent_group_id,
         one generation further up -- same member-or-left rule as #2, for the same reason (a
         married person has moved out of their whole birth lineage's active chats, not just their
         parents' own unit).
      4. IN-LAWS, patrilocal only (2026-10-26 ruling -- matches this schema's existing
         husband/wife-shaped columns and this project's real-world context; not configurable): if
         this person is the WIFE founder of an ACTIVE marital unit, that unit's
         husband_parent_group_id (her father-in-law's unit) -> plain member. Nothing extra for a
         husband founder -- he's already a member of that same unit from his own birth/activation.
    """
    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if not self_node:
        return
    node_id = self_node["id"]

    def _ensure_member(group_id) -> None:
        if not group_id:
            return
        conn.execute(
            """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at)
               VALUES (?, ?, 'approved', 0, NULL, ?)
               ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved'""",
            (group_id, user_id, _now()),
        )

    def _ensure_left(group_id) -> None:
        if not group_id:
            return
        # is_admin = 0 guard is load-bearing: a birth unit's own creator (e.g. the activating user,
        # when their parents hadn't registered yet) is ALSO unconditionally admin there per
        # create_group()'s creator-admin grant, additive to founder-admin -- a real administrative
        # role, not a side effect of being a plain child-member. Marrying moves plain CHILD
        # membership out; it must never silently strip an unrelated admin grant on the same row.
        conn.execute(
            "UPDATE family_group_members SET status = 'left' WHERE group_id = ? AND user_id = ? AND status = 'approved' AND is_admin = 0",
            (group_id, user_id),
        )

    # Rule 1: founder units -> admin.
    founder_groups = conn.execute(
        """SELECT id, husband_node_id, wife_node_id, husband_parent_group_id, marriage_status
           FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?""",
        (node_id, node_id),
    ).fetchall()
    for g in founder_groups:
        conn.execute(
            """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at)
               VALUES (?, ?, 'approved', 1, NULL, ?)
               ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved', is_admin = 1""",
            (g["id"], user_id, _now()),
        )
    is_married = bool(founder_groups)

    # Rules 2 & 3: birth unit, then its own two parent (grandparent) units.
    birth_unit_id = _find_parents_group_for_node(conn, node_id)
    (_ensure_left if is_married else _ensure_member)(birth_unit_id)
    if birth_unit_id:
        birth_unit = conn.execute(
            "SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (birth_unit_id,)
        ).fetchone()
        for grandparent_group_id in (birth_unit["husband_parent_group_id"], birth_unit["wife_parent_group_id"]):
            (_ensure_left if is_married else _ensure_member)(grandparent_group_id)

    # Rule 4: patrilocal in-laws -- wife founder of an active unit joins her husband's parents' unit.
    for g in founder_groups:
        if g["wife_node_id"] == node_id and g["marriage_status"] == "active":
            _ensure_member(g["husband_parent_group_id"])


def linked_with_parents(conn, user_id: int) -> bool:
    """True when a relative already placed this member in a tree WITH parents (their claimed node
    has parent links) -- they need no activation wizard; see activate_timeline()."""
    return bool(conn.execute(
        """SELECT 1 FROM family_nodes fn JOIN family_parent_links pl ON pl.child_node_id = fn.id
           WHERE fn.claimed_user_id = ? LIMIT 1""", (user_id,)).fetchone())


def activate_timeline(conn, user_id: int, payload: dict) -> dict:
    """The one-time Activation gate. Raises ValueError for bad input (already activated, missing
    required fields) and LookupError if the user doesn't exist. Commits internally, same shape as
    api_auth_register.

    payload["relationship"] (optional, 2026-10-20): one of _RELATIONSHIP_TO_PROFILE_STATUS's keys --
    the wizard's Step 2 answer. Synced to users.relationship_status here, in THIS transaction,
    because activate_timeline() is the one call every wizard run always makes (a 'single' answer
    never reaches marry_timeline() at all, so syncing there would silently drop it). Omitted
    entirely (None) by any caller that predates this field -- no sync attempted, not an error.

    payload["father_father"]/["father_mother"]/["mother_father"]/["mother_mother"] (optional,
    2026-10-20): grandparents, each shaped like father/mother. Links the newly found/created
    parents' unit to its own two parent units (the paternal and maternal grandparents' units) --
    the same husband_parent_group_id/wife_parent_group_id mechanism marry_timeline() already uses
    one generation up, just run here one generation further."""
    ensure_tables(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise LookupError("User not found")
    if user["timeline_activated_at"]:
        raise ValueError("Family Timeline is already activated")

    # Linked into a tree WITH parents by a relative (e.g. a parent linked their child by Public ID):
    # their place, parents and memberships already exist, and the wizard could never add a second
    # set of parents -- so they are simply activated now and shown their tree (2026-10-26; this used
    # to be a 400 that locked them out for good). A linked node WITHOUT parents (e.g. a spouse
    # linked into their partner's unit) still goes through the wizard below, which reuses the node
    # and adds their own parents.
    if linked_with_parents(conn, user_id):
        conn.execute("UPDATE users SET timeline_activated_at = ? WHERE id = ?", (_now(), user_id))
        _sync_family_membership(conn, user_id)
        conn.commit()
        return {"already_activated": True, "groups": my_family_groups(conn, user_id),
                "joined_requests": [], "notified": [], "created_node_ids": []}

    relationship = payload.get("relationship")
    if relationship is not None and relationship not in _RELATIONSHIP_TO_PROFILE_STATUS:
        raise ValueError("Unknown relationship status")

    results = {"joined_requests": [], "notified": [], "created_node_ids": []}
    # The member may ALREADY own a node before activating: someone else's tree can contain them
    # (e.g. a spouse added them and then linked that node to their account, or approved their
    # join). family_nodes.claimed_user_id is UNIQUE, so creating a second node crashed with an
    # IntegrityError (a 500) -- reuse the existing one instead (2026-10-26, found by the app).
    existing_self = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if existing_self:
        self_node_id = existing_self["id"]  # has no parents yet (linked_with_parents() handled that above)
    else:
        self_node_id = create_node(conn, user_id, user["name"], gender=user["gender"], claimed_user_id=user_id)
    results["self_node_id"] = self_node_id

    father = payload.get("father")
    if not father or not (father.get("name") or "").strip():
        raise ValueError("Father's name is required")
    father_node_id = _resolve_slot(conn, user_id, father, [], results, "father", default_gender="male")
    link_parent(conn, father_node_id, self_node_id, user_id)

    mother = payload.get("mother")
    if not mother or not (mother.get("name") or "").strip():
        raise ValueError("Mother's name is required")
    mother_node_id = _resolve_slot(conn, user_id, mother, [], results, "mother", default_gender="female")
    link_parent(conn, mother_node_id, self_node_id, user_id)

    parents_group_id, _ = _find_or_create_couple_group(
        conn, user_id, husband_node_id=father_node_id, wife_node_id=mother_node_id,
        member_node_ids=[self_node_id],
    )
    results["parents_group_id"] = parents_group_id
    results["parents_group_name"] = conn.execute("SELECT name FROM family_groups WHERE id = ?", (parents_group_id,)).fetchone()["name"]
    if existing_self:
        # A reused node may already be a founder of a couple unit someone else created (e.g. the
        # spouse's); hang that unit under these newly known parents so the tree stays connected.
        # Only fills an EMPTY link -- never overwrites a parent unit someone already set.
        conn.execute("UPDATE family_groups SET husband_parent_group_id = ? WHERE husband_node_id = ? AND husband_parent_group_id IS NULL",
                     (parents_group_id, self_node_id))
        conn.execute("UPDATE family_groups SET wife_parent_group_id = ? WHERE wife_node_id = ? AND wife_parent_group_id IS NULL",
                     (parents_group_id, self_node_id))

    _link_known_parents_group(conn, user_id, father_node_id, parents_group_id, "husband_parent_group_id",
                               payload.get("father_father"), payload.get("father_mother"), results,
                               "father_father", "father_mother")
    _link_known_parents_group(conn, user_id, mother_node_id, parents_group_id, "wife_parent_group_id",
                               payload.get("mother_father"), payload.get("mother_mother"), results,
                               "mother_father", "mother_mother")

    if relationship is not None:
        conn.execute("UPDATE users SET relationship_status = ? WHERE id = ?",
                     (_RELATIONSHIP_TO_PROFILE_STATUS[relationship], user_id))

    conn.execute("UPDATE users SET timeline_activated_at = ? WHERE id = ?", (_now(), user_id))
    _sync_family_membership(conn, user_id)
    conn.commit()
    return results


# ---- Marriage: self + spouse -> find-or-create THEIR OWN couple-unit, with children added as its
# (unmarried) child-members, and husband_parent_group_id/wife_parent_group_id set from whichever
# side already has a known birth unit. Callable any time after activation. ----

def _attach_children_to_group(conn, user_id: int, group_id: int, husband_node_id, wife_node_id,
                               children_payload, results: dict) -> list[int]:
    """Resolves each {"name", "gender"?, ...} entry in children_payload into a family_nodes
    placeholder, links it as a child of both husband_node_id/wife_node_id, and grants
    family_group_nodes (tree visibility) in group_id. Used by marry_timeline()'s two instant
    marriage-join branches (2026-10-26), which previously couldn't attach children at all -- there
    was nothing yet to attach them to before the join became instant. The main (non-join)
    marry_timeline() path still resolves children inline before group_id exists, since it needs
    their node ids UP FRONT to pass as _find_or_create_couple_group()'s member_node_ids."""
    child_node_ids = []
    for i, child in enumerate(children_payload or []):
        if not child or not (child.get("name") or "").strip():
            continue
        label = f"child_{i + 1}"
        child_node_id = _resolve_slot(conn, user_id, child, [], results, label)
        child_node_ids.append(child_node_id)
        if husband_node_id:
            link_parent(conn, husband_node_id, child_node_id, user_id)
        if wife_node_id:
            link_parent(conn, wife_node_id, child_node_id, user_id)
        conn.execute(
            "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
            (group_id, child_node_id, user_id, _now()),
        )
    return child_node_ids


def marry_timeline(conn, user_id: int, payload: dict) -> dict:
    ensure_tables(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise LookupError("User not found")
    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if not self_node:
        raise ValueError("Activate your Family Timeline before adding a spouse")
    self_node_id = self_node["id"]
    # 'divorced_widowed' is also allowed (not just 'married'): the Activation wizard's Step 2 can
    # map a Separated/Divorced/Widowed answer to this same profile bucket (see
    # activate_timeline()'s _RELATIONSHIP_TO_PROFILE_STATUS) and still needs to record that ex- or
    # late spouse, plus any children, in the tree -- this call isn't exclusively for an ongoing
    # marriage any more.
    if user["relationship_status"] not in ("married", "divorced_widowed"):
        raise ValueError("Set your relationship status to married first")

    if conn.execute(
        "SELECT 1 FROM family_groups WHERE (husband_node_id = ? OR wife_node_id = ?) AND marriage_status = 'active'",
        (self_node_id, self_node_id),
    ).fetchone():
        raise ValueError("You already have an active marriage recorded")

    spouse = payload.get("spouse")
    if not spouse or not (spouse.get("name") or "").strip():
        raise ValueError("Spouse's name is required")

    marriage_status = payload.get("marriage_status", "active")
    if marriage_status not in VALID_MARRIAGE_STATUSES:
        raise ValueError("Unknown marriage status")

    results = {"joined_requests": [], "notified": [], "created_node_ids": []}

    if spouse.get("action") == "join":
        # 2026-10-26 ruling: a marriage is a declared MUTUAL fact, not a claim on someone else's
        # unit that needs a third party's sign-off -- unlike every other join in this module (see
        # this module's docstring). Claims the empty founder slot immediately via
        # _claim_founder_slot() instead of queuing a people_requests row for the group's creator to
        # approve; the other founder is notified afterward, never blocked.
        group_id = spouse.get("group_id")
        group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()
        if not group:
            raise ValueError("That Family Group doesn't exist")
        # Never "whichever founder slot is empty" (2026-10-26: matching a man inside his PARENTS'
        # unit, where he is a child, made his wife claim his father's slot). The matched node must
        # be one of this unit's founders, and there are two legitimate cases: (a) it is the SPOUSE
        # -> claim the partner place next to them; (b) it is an unclaimed placeholder that already
        # stands for THIS member (their spouse entered them first) -> claim that placeholder.
        matched = spouse.get("matched_node_id")
        if matched not in (group["husband_node_id"], group["wife_node_id"]) or not matched:
            raise ValueError("You can only join as the spouse of one of that family unit's two founders")
        partner_node_id = group["wife_node_id"] if matched == group["husband_node_id"] else group["husband_node_id"]
        if partner_node_id and not _claimed_user_for_node(conn, partner_node_id):
            target_node_id = partner_node_id
        elif not _claimed_user_for_node(conn, matched):
            target_node_id = matched
        else:
            raise ValueError("That person's partner place in their family unit is already taken")
        other_founder_node_id = group["husband_node_id"] if target_node_id == group["wife_node_id"] else group["wife_node_id"]
        other_founder_user_id = _claimed_user_for_node(conn, other_founder_node_id)
        _claim_founder_slot(conn, target_node_id, user_id)
        group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()  # re-read: the slot just moved
        _sync_family_membership(conn, user_id)
        if other_founder_user_id:
            _notify_marriage(conn, user_id, other_founder_user_id)
        results["auto_joined"] = {"label": "spouse", "name": spouse["name"].strip(), "group_id": group_id}
        _attach_children_to_group(conn, user_id, group_id, group["husband_node_id"], group["wife_node_id"],
                                   payload.get("children"), results)
        conn.commit()
        return results

    spouse_node_id = _resolve_slot(conn, user_id, spouse, [], results, "spouse")

    # 2026-10-26: the spouse may be an EXISTING person (e.g. found by Public ID) who already founds
    # an active marriage. Creating or reusing a unit here either duplicated that marriage or
    # silently "succeeded" without adding this member. Instead: if their partner place is still an
    # unclaimed placeholder, claim it immediately (same automatic, unapproved marriage-join as the
    # "join" action above -- on claim this member becomes that unit's founder-admin); if it is
    # claimed, refuse.
    their_marriage = conn.execute(
        "SELECT * FROM family_groups WHERE (husband_node_id = ? OR wife_node_id = ?) AND marriage_status = 'active'",
        (spouse_node_id, spouse_node_id),
    ).fetchone()
    if their_marriage:
        partner_node_id = their_marriage["wife_node_id"] if their_marriage["husband_node_id"] == spouse_node_id else their_marriage["husband_node_id"]
        if partner_node_id and _claimed_user_for_node(conn, partner_node_id):
            raise ValueError(f"{spouse['name'].strip()} already has a recorded marriage in another family unit")
        if not partner_node_id:
            raise ValueError("That person's family unit has no partner place to claim")
        other_founder_user_id = _claimed_user_for_node(conn, spouse_node_id)
        _claim_founder_slot(conn, partner_node_id, user_id)
        group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (their_marriage["id"],)).fetchone()
        _sync_family_membership(conn, user_id)
        if other_founder_user_id:
            _notify_marriage(conn, user_id, other_founder_user_id)
        results["auto_joined"] = {"label": "spouse", "name": spouse["name"].strip(), "group_id": their_marriage["id"]}
        _attach_children_to_group(conn, user_id, their_marriage["id"], group["husband_node_id"], group["wife_node_id"],
                                   payload.get("children"), results)
        conn.commit()
        return results

    child_node_ids = []
    for i, child in enumerate(payload.get("children") or []):
        if not child or not (child.get("name") or "").strip():
            continue
        label = f"child_{i + 1}"
        child_node_id = _resolve_slot(conn, user_id, child, [], results, label)
        child_node_ids.append(child_node_id)
        link_parent(conn, self_node_id, child_node_id, user_id)
        link_parent(conn, spouse_node_id, child_node_id, user_id)

    if user["gender"] == "female":
        husband_node_id, wife_node_id = spouse_node_id, self_node_id
    else:
        # 'male', or anything else -- a known, named limitation of the husband/wife-shaped schema
        # this architecture itself specifies, not a judgement this code makes; see HANDOVER.md.
        husband_node_id, wife_node_id = self_node_id, spouse_node_id

    husband_parent_group_id = _find_parents_group_for_node(conn, husband_node_id)
    wife_parent_group_id = _find_parents_group_for_node(conn, wife_node_id)

    group_id, created = _find_or_create_couple_group(
        conn, user_id, husband_node_id, wife_node_id, member_node_ids=child_node_ids,
        husband_parent_group_id=husband_parent_group_id, wife_parent_group_id=wife_parent_group_id,
        marriage_status=marriage_status,
    )
    results["marital_group_id"] = group_id
    results["marital_group_name"] = conn.execute("SELECT name FROM family_groups WHERE id = ?", (group_id,)).fetchone()["name"]

    spouse_parent_side = "wife_parent_group_id" if spouse_node_id == wife_node_id else "husband_parent_group_id"
    _link_known_parents_group(conn, user_id, spouse_node_id, group_id, spouse_parent_side,
                               payload.get("spouse_father"), payload.get("spouse_mother"), results,
                               "spouse_father", "spouse_mother")

    _sync_family_membership(conn, user_id)
    conn.commit()
    return results


# ---- Reading: listing a user's units, one unit's own immediate neighborhood (not a multi-
# ancestor fan chart -- see this module's docstring for why), and the legacy whole-group view the
# (unchanged this pass) D3 frontend still calls. ----

def my_family_groups(conn, user_id: int) -> list[dict]:
    """The chat group list -- deliberately narrower than "every unit this node appears in"
    (that's what the D3 neighborhood view is for). Two rules, both 2026-10-20:
      - Dormant units (both founders deceased -- see _group_is_dormant()) are excluded entirely.
        They still render in the D3 tree, faded, as root ancestors -- just not as a chat to open.
      - is_founder tags each row so the frontend can tell "My Family" (the viewer's own founded
        unit) apart from "Joined Family" (approved into someone else's, e.g. their parents' unit)
        -- distinct from is_admin, since the creator of a freshly-founded unit is also always
        granted admin even when they're not a founder (see create_group()).
      - `role` (2026-10-27, additive): 'founder'|'admin'|'member', the same three-way label
        group_members_for() returns -- the honest version of is_admin alone, which rendered a
        plain child as "Admin" in their own parents' unit just because they happened to be the
        one who created it."""
    rows = conn.execute(
        """SELECT fg.id, fg.name, fg.kind, m.is_admin,
                  (fg.husband_node_id = sn.id OR fg.wife_node_id = sn.id) AS is_founder,
                  (SELECT COUNT(*) FROM family_group_members m2 WHERE m2.group_id = fg.id AND m2.status = 'approved') AS members
           FROM family_group_members m
           JOIN family_groups fg ON fg.id = m.group_id
           LEFT JOIN family_nodes sn ON sn.claimed_user_id = m.user_id
           WHERE m.user_id = ? AND m.status = 'approved' ORDER BY fg.id""",
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        if _group_is_dormant(conn, r["id"]):
            continue
        is_founder = bool(r["is_founder"])
        role = "founder" if is_founder else ("admin" if r["is_admin"] else "member")
        out.append({**dict(r), "is_founder": is_founder, "role": role})
    return out


def _person_summary(conn, node_id, viewer_user_id):
    """Gender, like name and DOB elsewhere in this module (_node_display_name()/_node_dob()),
    resolves live from `users.gender` once a node is claimed -- never trusting the stale snapshot
    typed in at placeholder-creation time. Matters in practice: a node created with a guessed or
    unknown gender (or none at all) must show the real person's own registered gender -- including
    'both' (third gender) -- the instant they're claimed, not whatever `family_nodes.gender` still
    says."""
    if not node_id:
        return None
    row = conn.execute(
        """SELECT fn.id, fn.claimed_user_id, fn.gender AS node_gender, fn.status, fn.is_deceased,
                  COALESCE(u.name, fn.display_name) AS name, u.gender AS user_gender,
                  u.profile_picture IS NOT NULL AS has_picture
           FROM family_nodes fn LEFT JOIN users u ON u.id = fn.claimed_user_id WHERE fn.id = ?""",
        (node_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"], "name": row["name"],
        "gender": row["user_gender"] if row["claimed_user_id"] else row["node_gender"],
        "status": row["status"], "claimed": bool(row["claimed_user_id"]), "is_deceased": bool(row["is_deceased"]),
        "is_viewer": row["claimed_user_id"] == viewer_user_id,
        "profile_picture_url": _profile_picture_url(row["claimed_user_id"]) if row["claimed_user_id"] and row["has_picture"] else None,
    }


def _member_count(conn, group_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM family_group_members WHERE group_id = ? AND status = 'approved'", (group_id,)
    ).fetchone()[0]


def _group_brief(conn, group_id, viewer_user_id):
    if not group_id:
        return None
    g = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not g:
        return None
    return {
        "group_id": g["id"], "name": g["name"],
        "husband": _person_summary(conn, g["husband_node_id"], viewer_user_id),
        "wife": _person_summary(conn, g["wife_node_id"], viewer_user_id),
        "is_dormant": _group_is_dormant(conn, group_id),
        "members": _member_count(conn, group_id),
    }


def neighborhood_for_group(conn, viewer_user_id: int, group_id: int):
    """One unit's own immediate neighborhood: the unit itself, its up-to-two parent units, its
    unmarried child-members, and its own child units (its children's marriages, if any). None if
    the group doesn't exist or the viewer isn't an approved member -- same 404-not-403 convention
    as tree_for_group()."""
    group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        return None
    member_row = conn.execute(
        "SELECT is_admin FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'",
        (group_id, viewer_user_id),
    ).fetchone()
    if not member_row:
        return None

    founder_ids = {group["husband_node_id"], group["wife_node_id"]}
    child_group_rows = conn.execute(
        "SELECT id, husband_node_id, wife_node_id FROM family_groups WHERE husband_parent_group_id = ? OR wife_parent_group_id = ?",
        (group_id, group_id),
    ).fetchall()
    # A married child is structurally BOTH a plain child-member here AND a founder of their own
    # unit below -- excluding them from unmarried_children too (not just founder_ids above) avoids
    # showing the same person as two separate cards in the neighborhood view.
    married_child_ids = {r["husband_node_id"] for r in child_group_rows} | {r["wife_node_id"] for r in child_group_rows}
    unmarried_children = [
        _person_summary(conn, r["node_id"], viewer_user_id)
        for r in conn.execute("SELECT node_id FROM family_group_nodes WHERE group_id = ?", (group_id,))
        if r["node_id"] not in founder_ids and r["node_id"] not in married_child_ids
    ]
    child_groups = [_group_brief(conn, r["id"], viewer_user_id) for r in child_group_rows]

    # "side" tags which founder's own birth unit this is -- a plain list position would silently
    # shift if only one side is known (e.g. husband's is missing but wife's exists would land at
    # index 0), which the frontend can't tell apart from "this IS the husband's side" without it.
    parent_groups = []
    for side, parent_group_id in (("husband", group["husband_parent_group_id"]), ("wife", group["wife_parent_group_id"])):
        pg = _group_brief(conn, parent_group_id, viewer_user_id)
        if pg:
            pg["side"] = side
            parent_groups.append(pg)

    return {
        "group_id": group_id,
        "name": group["name"],
        "husband": _person_summary(conn, group["husband_node_id"], viewer_user_id),
        "wife": _person_summary(conn, group["wife_node_id"], viewer_user_id),
        "is_dormant": _group_is_dormant(conn, group_id),
        "is_admin": _is_admin_of_group(conn, viewer_user_id, group_id),
        "members": _member_count(conn, group_id),
        "unmarried_children": unmarried_children,
        "parent_groups": parent_groups,
        "child_groups": child_groups,
    }


def tree_for_group(conn, viewer_user_id: int, group_id: int):
    """LEGACY whole-group view -- kept, unchanged in shape, because the D3 frontend (not touched
    this pass) still calls it. Synthesizes a spouse_links entry from the unit's own founder pair
    (family_spouse_links is deprecated and no longer written by new marriages) so the existing
    composite-couple rendering still sees a connector. None if the group doesn't exist or the
    viewer isn't an approved member -- 404-not-403, same convention as neighborhood_for_group()."""
    group = conn.execute("SELECT * FROM family_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        return None
    member_row = conn.execute(
        "SELECT is_admin FROM family_group_members WHERE group_id = ? AND user_id = ? AND status = 'approved'",
        (group_id, viewer_user_id),
    ).fetchone()
    if not member_row:
        return None

    node_rows = conn.execute(
        """SELECT fn.id, fn.claimed_user_id, fn.gender, fn.status, fn.is_deceased, COALESCE(u.name, fn.display_name) AS name
           FROM family_group_nodes fgn JOIN family_nodes fn ON fn.id = fgn.node_id
           LEFT JOIN users u ON u.id = fn.claimed_user_id
           WHERE fgn.group_id = ?""",
        (group_id,),
    ).fetchall()
    node_ids = [r["id"] for r in node_rows]
    nodes = [{
        "id": r["id"], "name": r["name"], "gender": r["gender"], "status": r["status"],
        "is_deceased": bool(r["is_deceased"]), "claimed": bool(r["claimed_user_id"]),
        "is_viewer": r["claimed_user_id"] == viewer_user_id,
    } for r in node_rows]

    parent_links, spouse_links = [], []
    if node_ids:
        placeholders = ",".join("?" * len(node_ids))
        parent_links = [dict(r) for r in conn.execute(
            f"""SELECT parent_node_id, child_node_id, status FROM family_parent_links
                WHERE parent_node_id IN ({placeholders}) AND child_node_id IN ({placeholders})""",
            node_ids + node_ids,
        )]
        spouse_links = [dict(r) for r in conn.execute(
            f"""SELECT node_lo_id, node_hi_id, status FROM family_spouse_links
                WHERE node_lo_id IN ({placeholders}) AND node_hi_id IN ({placeholders})""",
            node_ids + node_ids,
        )]
        if group["husband_node_id"] and group["wife_node_id"]:
            lo, hi = sorted((group["husband_node_id"], group["wife_node_id"]))
            if not any(s["node_lo_id"] == lo and s["node_hi_id"] == hi for s in spouse_links):
                spouse_links.append({"node_lo_id": lo, "node_hi_id": hi, "status": "active"})

    return {
        "group_id": group_id, "group_name": group["name"], "kind": group["kind"],
        "created_by_user_id": group["created_by_user_id"], "is_admin": bool(member_row["is_admin"]),
        "nodes": nodes, "parent_links": parent_links, "spouse_links": spouse_links,
    }
