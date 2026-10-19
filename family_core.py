"""Family Tree and Family Groups (2026-10-20): the "Family Homes" architecture, Phase 1 (data +
backend only -- no D3 UI yet, see docs discussion for the phased plan).

Two layers, deliberately separate:

  - family_nodes / family_parent_links / family_spouse_links: the genealogical tree itself. A node
    is a PERSON the tree knows about, whether claimed (linked to a real users.id) or still empty
    (just a typed name, waiting to be claimed, possibly already deceased -- see is_deceased).
    Parent/spouse edges connect nodes to each other, independent of any group.
  - family_groups / family_group_members / family_group_messages / family_group_nodes: a shared,
    joinable container -- a chat + a subset of nodes a specific set of real members can see drawn
    as one tree. A node can appear in more than one group (e.g. a shared grandparent, visible in
    both someone's lineage group and a larger extended group); a group's nodes are NOT its
    members -- an empty node has no user_id to be a chat member with.

Deliberately NOT built on personal_groups: that table's category='family' already means something
different and privacy-sensitive (a user's own private Paternal/Maternal sub-grouping of their 1:1
connections -- see social_core.is_family_member(), which hide_identity's exemption depends on).
Reusing it here would make "belongs to a big searchable extended Family Group" quietly satisfy
"is this person's close family," which is a real privacy leak, not just a naming clash.

LINEAGE vs MARITAL groups (2026-10-20 restructure): a person's birth family (their parents'
household, where they're a child) and their marital family (the one they co-found with a spouse,
where they're a co-head) are structurally different groups with different admin semantics --
family_groups.kind distinguishes them ('lineage' | 'marital' | 'general', the last being whatever
an admin later repurposes a group into, e.g. renaming "PSharma Family Group" into "Mudgal Family"
to encompass a larger extended family -- kind is only ever read at CREATION time to pick a naming
algorithm, never enforced afterward).

  - activate_timeline(): father + mother only, pure lineage. Creates the user's self-node,
    resolves each parent (create a new empty/deceased node / request to join an existing lineage
    group / notify a suspected-unactivated real user), and -- only if at least one parent was
    freshly created, i.e. no existing group already covers this family -- creates ONE new
    kind='lineage' group. Sets users.timeline_activated_at (one-time gate).
  - marry_timeline(): spouse + children, callable any time after activation (first call, or much
    later on marriage) -- never part of activate_timeline(), so marital-group creation lives in
    exactly one place. Same create/join/notify shape for the spouse slot. A join onto an existing
    spouse's group grants is_admin=1 automatically (see add_member()) -- no separate "creation
    gate" counter is needed; re-marriage after a prior marriage's family_spouse_links.status is
    set to 'separated'/'deceased' is allowed (checked, not hard-blocked, against any still-ACTIVE
    spouse link).

Admin succession when a group's sole admin's own node is later marked deceased is a known,
deliberately UNSOLVED edge case for this phase -- see docs/HANDOVER.md.
"""
from __future__ import annotations

import datetime as dt

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
    created_by_user_id INTEGER NOT NULL,   -- historical/audit only -- NOT the permission-check column, see family_group_members.is_admin
    kind TEXT NOT NULL DEFAULT 'lineage',  -- lineage | marital | general -- read only at creation, to pick a naming algorithm
    eldest_node_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_family_groups_creator ON family_groups(created_by_user_id);

CREATE TABLE IF NOT EXISTS family_group_members (
    group_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'approved',  -- approved | left
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
        conn.execute("ALTER TABLE family_groups ADD COLUMN kind TEXT NOT NULL DEFAULT 'lineage'")

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


def mark_deceased(conn, user_id: int, node_id: int, is_deceased: bool = True) -> None:
    """Toggles a node's deceased flag. Any ADMIN of a group this node belongs to may do this --
    purely a tree-display attribute, never touching the real users row or that account's login
    capability even for a claimed node (a real, separate, far more sensitive admin action)."""
    if not conn.execute("SELECT 1 FROM family_nodes WHERE id = ?", (node_id,)).fetchone():
        raise LookupError("Node not found")
    allowed = conn.execute(
        """SELECT 1 FROM family_group_nodes fgn JOIN family_group_members fgm ON fgm.group_id = fgn.group_id
           WHERE fgn.node_id = ? AND fgm.user_id = ? AND fgm.is_admin = 1 AND fgm.status = 'approved'""",
        (node_id, user_id),
    ).fetchone()
    if not allowed:
        raise PermissionError("Only an admin of a group this person belongs to can change this")
    conn.execute("UPDATE family_nodes SET is_deceased = ? WHERE id = ?", (1 if is_deceased else 0, node_id))
    conn.commit()


def link_parent(conn, parent_node_id: int, child_node_id: int, created_by_user_id: int) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO family_parent_links (parent_node_id, child_node_id, created_by_user_id, created_at)
           VALUES (?, ?, ?, ?)""",
        (parent_node_id, child_node_id, created_by_user_id, _now()),
    )


def link_spouse(conn, node_a_id: int, node_b_id: int, created_by_user_id: int) -> None:
    lo, hi = sorted((node_a_id, node_b_id))
    conn.execute(
        """INSERT OR IGNORE INTO family_spouse_links (node_lo_id, node_hi_id, created_by_user_id, created_at)
           VALUES (?, ?, ?, ?)""",
        (lo, hi, created_by_user_id, _now()),
    )


# ---- Naming: two different algorithms for two different group kinds (2026-10-20). Both produce
# "FirstInitial + Surname + Family Group" text; they differ in WHO they pick as the naming basis. ----

def _group_name_from(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "Family Group"
    first_initial = parts[0][0].upper()
    surname = parts[-1] if len(parts) > 1 else parts[0]
    return f"{first_initial}{surname} Family Group"


def _generation_rank(conn, self_node_id: int, node_id: int) -> int:
    """Lower = older generation. Phase 1 activation only ever creates one level up (parents) and
    one level down (children) relative to the activating user's own self-node, so a direct
    family_parent_links membership check is enough -- no need for a full graph walk yet. A
    node's DOB is nearly always unknown for a freshly-typed parent (the activation form doesn't
    even collect one), while the activating user's OWN dob is always known (mandatory at
    registration) -- comparing raw DOB alone would make the user themself "eldest" almost every
    time, which is backwards. Generation always wins outright; DOB only breaks a tie within the
    SAME generation (e.g. deciding between father and mother). Deliberately NOT affected by
    is_deceased -- a deceased parent still outranks the living activating user by generation (the
    lineage naming rule explicitly allows a dead elder's name)."""
    if node_id == self_node_id:
        return 0
    if conn.execute(
        "SELECT 1 FROM family_parent_links WHERE parent_node_id = ? AND child_node_id = ?", (node_id, self_node_id),
    ).fetchone():
        return -1  # a parent of the activating user
    if conn.execute(
        "SELECT 1 FROM family_parent_links WHERE parent_node_id = ? AND child_node_id = ?", (self_node_id, node_id),
    ).fetchone():
        return 1  # a child of the activating user
    return 0  # spouse, or anything else not generation-linked to self -- treated as the same tier


def _pick_eldest_lineage(conn, self_node_id: int, node_ids: list[int]):
    """Lineage naming: generation always wins (parent > self > child); DOB, then created_at,
    break ties within a generation. Alive/deceased plays no part -- a dead father can still lend
    his name (the point of the lineage rule, per the approved spec)."""
    scored = []
    for nid in node_ids:
        rank = _generation_rank(conn, self_node_id, nid)
        dob = _node_dob(conn, nid) or "9999-99-99"  # dob-absent sorts after any real ISO date
        row = conn.execute("SELECT created_at FROM family_nodes WHERE id = ?", (nid,)).fetchone()
        scored.append((rank, dob, row["created_at"] if row else "", nid))
    scored.sort()
    return scored[0][3] if scored else None


def _pick_eldest_marital(conn, spouse_node_ids: list[int], self_node_id: int):
    """Marital naming: only ALIVE candidates are eligible (an admin must be alive); among those,
    earliest DOB wins. If nobody in the pair is alive yet (shouldn't normally happen -- the
    activating user themself must be alive to be creating this), falls back to the lineage
    algorithm so this never returns None for a non-empty pool."""
    alive = []
    for nid in spouse_node_ids:
        if _node_is_deceased(conn, nid):
            continue
        dob = _node_dob(conn, nid) or "9999-99-99"
        alive.append((dob, nid))
    if alive:
        alive.sort()
        return alive[0][1]
    return _pick_eldest_lineage(conn, self_node_id, spouse_node_ids)


def _generate_group_name_lineage(conn, self_node_id: int, node_ids: list[int]):
    eldest_id = _pick_eldest_lineage(conn, self_node_id, node_ids)
    name = _node_display_name(conn, eldest_id) if eldest_id else None
    return (_group_name_from(name) if name else "Family Group"), eldest_id


def _generate_group_name_marital(conn, self_node_id: int, spouse_pool_node_ids: list[int]):
    eldest_id = _pick_eldest_marital(conn, spouse_pool_node_ids, self_node_id)
    name = _node_display_name(conn, eldest_id) if eldest_id else None
    return (_group_name_from(name) if name else "Family Group"), eldest_id


def create_group(conn, created_by_user_id: int, node_ids: list[int], kind: str, name: str, eldest_node_id) -> int:
    """The low-level mechanics only -- naming is computed by the caller (create_lineage_group() /
    create_marital_group()), since lineage and marital groups use different naming algorithms.
    The creator is always inserted as is_admin=1 -- they founded it."""
    cur = conn.execute(
        "INSERT INTO family_groups (name, created_by_user_id, kind, eldest_node_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (name, created_by_user_id, kind, eldest_node_id, _now()),
    )
    group_id = cur.lastrowid
    conn.execute(
        "INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at) VALUES (?, ?, 'approved', 1, NULL, ?)",
        (group_id, created_by_user_id, _now()),
    )
    for nid in node_ids:
        conn.execute(
            "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
            (group_id, nid, created_by_user_id, _now()),
        )
    return group_id


def create_lineage_group(conn, created_by_user_id: int, self_node_id: int, node_ids: list[int]) -> int:
    name, eldest_id = _generate_group_name_lineage(conn, self_node_id, node_ids)
    return create_group(conn, created_by_user_id, node_ids, "lineage", name, eldest_id)


def create_marital_group(conn, created_by_user_id: int, self_node_id: int, spouse_node_id, node_ids: list[int]) -> int:
    spouse_pool = [self_node_id] + ([spouse_node_id] if spouse_node_id else [])
    name, eldest_id = _generate_group_name_marital(conn, self_node_id, spouse_pool)
    return create_group(conn, created_by_user_id, node_ids, "marital", name, eldest_id)


def add_member(conn, group_id: int, user_id: int, invited_by=None) -> None:
    """Approves user_id into the group's chat membership AND adds their own self-node into the
    group's node-set, so the shared tree actually shows them -- linked via whatever parent/spouse
    edge already connects their self-node to a node already in this group, created immediately at
    activation/request time (see request_join_group()), independent of this approval.

    Admin derivation (2026-10-20): grants is_admin=1 if-and-only-if the joiner has an ACTIVE
    family_spouse_links edge to a node whose claimed user is ALREADY an approved admin of this
    SAME group -- not merely "a spouse edge to any node in the group" (safer: a coincidental edge
    to an unrelated member would not qualify). A child joining a parent's lineage group never
    qualifies, since a child has no spouse edge to anyone in that group. Derived fresh every time,
    never stored, so it can't drift out of sync with the underlying edges."""
    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    is_admin = 0
    if self_node:
        is_admin = 1 if conn.execute(
            """SELECT 1 FROM family_spouse_links fsl
               JOIN family_nodes fn ON fn.id = (CASE WHEN fsl.node_lo_id = ? THEN fsl.node_hi_id ELSE fsl.node_lo_id END)
               JOIN family_group_members fgm ON fgm.user_id = fn.claimed_user_id AND fgm.group_id = ?
               WHERE (fsl.node_lo_id = ? OR fsl.node_hi_id = ?) AND fsl.status = 'active'
                 AND fgm.is_admin = 1 AND fgm.status = 'approved'""",
            (self_node["id"], group_id, self_node["id"], self_node["id"]),
        ).fetchone() else 0

    conn.execute(
        """INSERT INTO family_group_members (group_id, user_id, status, is_admin, invited_by, created_at) VALUES (?, ?, 'approved', ?, ?, ?)
           ON CONFLICT(group_id, user_id) DO UPDATE SET status = 'approved', is_admin = excluded.is_admin""",
        (group_id, user_id, is_admin, invited_by, _now()),
    )
    if self_node:
        conn.execute(
            "INSERT OR IGNORE INTO family_group_nodes (group_id, node_id, added_by_user_id, added_at) VALUES (?, ?, ?, ?)",
            (group_id, self_node["id"], user_id, _now()),
        )


def request_join_group(conn, user_id: int, group_id: int) -> int:
    """Queues a join request for the group's FOUNDING creator to approve (not every current
    co-admin -- a known Phase 1 simplification) -- via the same people_requests table
    social_core.py already uses for group invites/rejoins (kind='family_group_join', group_id
    repurposed to hold family_groups.id, same overloading convention 'rejoin' already uses for
    private_chats.id). social_core.decide_request() has the matching accept-side branch.
    Returns the new request's id."""
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
    if conn.execute(
        "SELECT 1 FROM people_requests WHERE from_user_id=? AND to_user_id=? AND kind='family_group_join' AND group_id=? AND status='pending'",
        (user_id, group["created_by_user_id"], group_id),
    ).fetchone():
        raise ValueError("A join request is already waiting")
    cur = conn.execute(
        "INSERT INTO people_requests (from_user_id, to_user_id, kind, group_id, created_at, cycle_id) VALUES (?, ?, 'family_group_join', ?, ?, ?)",
        (user_id, group["created_by_user_id"], group_id, _now(), cycle_middleware.get_active_cycle_id(conn)),
    )
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
        results.append({
            "type": "group", "group_id": r["group_id"], "group_name": r["group_name"], "group_kind": r["group_kind"],
            "matched_node_id": r["node_id"], "matched_name": r["matched_name"], "member_count": member_count,
        })

    for r in conn.execute(
        "SELECT id, name FROM users WHERE name LIKE ? COLLATE NOCASE AND timeline_activated_at IS NULL AND id != ?",
        (pattern, viewer_user_id),
    ):
        results.append({"type": "unactivated_user", "user_id": r["id"], "name": r["name"]})

    if not results:
        results.append({"type": "none"})
    return results


# ---- Relation slot resolution: shared by activate_timeline() (father/mother) and
# marry_timeline() (spouse/children) ----

def _resolve_slot(conn, user_id: int, entry: dict, fresh_node_ids: list, results: dict, label: str):
    """One relation entry -- {"name", "action": "create"|"join"|"notify", "is_deceased"?, ...}.
    Returns the family_nodes.id this entry ends up representing (always non-None once a name was
    given -- 'notify' still creates a normal empty node; the ping is a side effect, not a
    different structural outcome, so parent/spouse/child linking works uniformly either way)."""
    if not entry or not (entry.get("name") or "").strip():
        return None
    action = entry.get("action", "create")
    name = entry["name"].strip()

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
        node_id = create_node(conn, user_id, name)
        fresh_node_ids.append(node_id)
        results["created_node_ids"].append({"label": label, "node_id": node_id, "name": name})
        return node_id

    node_id = create_node(conn, user_id, name, is_deceased=bool(entry.get("is_deceased")))
    fresh_node_ids.append(node_id)
    results["created_node_ids"].append({"label": label, "node_id": node_id, "name": name, "is_deceased": bool(entry.get("is_deceased"))})
    return node_id


# ---- Activation: pure lineage (father + mother). Spouse/children now go through
# marry_timeline() below, never here -- see this module's docstring for why. ----

def activate_timeline(conn, user_id: int, payload: dict) -> dict:
    """The one-time Activation gate. Raises ValueError for bad input (already activated, missing
    required fields) and LookupError if the user doesn't exist. Commits internally, same shape as
    api_auth_register."""
    ensure_tables(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise LookupError("User not found")
    if user["timeline_activated_at"]:
        raise ValueError("Family Timeline is already activated")

    results = {"joined_requests": [], "notified": [], "created_node_ids": []}
    self_node_id = create_node(conn, user_id, user["name"], gender=user["gender"], claimed_user_id=user_id)
    results["self_node_id"] = self_node_id

    lineage_node_ids = [self_node_id]

    father = payload.get("father")
    if not father or not (father.get("name") or "").strip():
        raise ValueError("Father's name is required")
    father_node_id = _resolve_slot(conn, user_id, father, lineage_node_ids, results, "father")
    link_parent(conn, father_node_id, self_node_id, user_id)

    mother = payload.get("mother")
    if not mother or not (mother.get("name") or "").strip():
        raise ValueError("Mother's name is required")
    mother_node_id = _resolve_slot(conn, user_id, mother, lineage_node_ids, results, "mother")
    link_parent(conn, mother_node_id, self_node_id, user_id)

    if len(lineage_node_ids) > 1:
        # At least one parent was freshly created -- no existing group already covers this
        # family, so found one. If BOTH father and mother matched into existing groups instead,
        # lineage_node_ids stays [self_node_id] alone and no new group is created at all; the
        # user simply ends up with pending join-requests into those existing group(s).
        group_id = create_lineage_group(conn, user_id, self_node_id, lineage_node_ids)
        results["lineage_group_id"] = group_id
        results["lineage_group_name"] = conn.execute("SELECT name FROM family_groups WHERE id = ?", (group_id,)).fetchone()["name"]

    conn.execute("UPDATE users SET timeline_activated_at = ? WHERE id = ?", (_now(), user_id))
    conn.commit()
    return results


# ---- Marriage: spouse + children -> a new (or joined) marital group. Callable any time after
# activation, and re-callable for a genuinely new marriage once a prior one's spouse link is no
# longer 'active' (separated/deceased) -- family_spouse_links keeps every marriage's own history
# rather than overwriting it. ----

def marry_timeline(conn, user_id: int, payload: dict) -> dict:
    ensure_tables(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise LookupError("User not found")
    self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    if not self_node:
        raise ValueError("Activate your Family Timeline before adding a spouse")
    self_node_id = self_node["id"]
    if user["relationship_status"] != "married":
        raise ValueError("Set your relationship status to married first")

    if conn.execute(
        "SELECT 1 FROM family_spouse_links WHERE (node_lo_id = ? OR node_hi_id = ?) AND status = 'active'",
        (self_node_id, self_node_id),
    ).fetchone():
        raise ValueError("You already have an active marriage recorded")

    spouse = payload.get("spouse")
    if not spouse or not (spouse.get("name") or "").strip():
        raise ValueError("Spouse's name is required")

    results = {"joined_requests": [], "notified": [], "created_node_ids": []}
    marital_node_ids = [self_node_id]

    if spouse.get("action") == "join":
        # Joining an EXISTING marital group is not the same as father/mother/child joins: the
        # node the search matched (whatever placeholder name the group's founder typed, e.g. an
        # empty "Diana Mehta") is NOT me -- claiming/merging an empty node into a real identity is
        # the deferred Phase 4 concern this module's docstring already flags, not built yet. For
        # Phase 1, a spousal join instead links directly to the group's CURRENT ADMIN's own
        # (real, claimed) self-node -- the actual person already running that household -- so the
        # spouse edge, and therefore add_member()'s admin derivation, lands on someone real.
        group_id = spouse.get("group_id")
        group = conn.execute("SELECT * FROM family_groups WHERE id = ? AND kind = 'marital'", (group_id,)).fetchone()
        if not group:
            raise ValueError("That isn't a marital Family Group")
        admin_row = conn.execute(
            "SELECT user_id FROM family_group_members WHERE group_id = ? AND is_admin = 1 AND status = 'approved' LIMIT 1",
            (group_id,),
        ).fetchone()
        if not admin_row:
            raise ValueError("That group has no admin to link to")
        admin_self_node = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (admin_row["user_id"],)).fetchone()
        request_join_group(conn, user_id, group_id)
        results["joined_requests"].append({"label": "spouse", "name": spouse["name"].strip(), "group_id": group_id})
        spouse_node_id = admin_self_node["id"]
    else:
        spouse_node_id = _resolve_slot(conn, user_id, spouse, marital_node_ids, results, "spouse")

    link_spouse(conn, self_node_id, spouse_node_id, user_id)

    for i, child in enumerate(payload.get("children") or []):
        if not child or not (child.get("name") or "").strip():
            continue
        label = f"child_{i + 1}"
        child_node_id = _resolve_slot(conn, user_id, child, marital_node_ids, results, label)
        link_parent(conn, self_node_id, child_node_id, user_id)
        link_parent(conn, spouse_node_id, child_node_id, user_id)

    if len(marital_node_ids) > 1:
        # Spouse (and/or at least one child) was freshly created -- found a new marital group.
        # If the spouse instead matched/joined an existing marital group, marital_node_ids stays
        # [self_node_id] alone (children with no spouse yet confirmed don't get a group of their
        # own here -- adding them to the spouse's EXISTING group happens once that join is
        # approved and the matching claim/add flow runs, a Phase 4 concern, not built yet).
        group_id = create_marital_group(conn, user_id, self_node_id, spouse_node_id, marital_node_ids)
        results["marital_group_id"] = group_id
        results["marital_group_name"] = conn.execute("SELECT name FROM family_groups WHERE id = ?", (group_id,)).fetchone()["name"]

    conn.commit()
    return results


# ---- Reading a group's tree / listing a user's groups ----

def my_family_groups(conn, user_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT fg.id, fg.name, fg.kind, m.is_admin,
                  (SELECT COUNT(*) FROM family_group_members m2 WHERE m2.group_id = fg.id AND m2.status = 'approved') AS members
           FROM family_group_members m JOIN family_groups fg ON fg.id = m.group_id
           WHERE m.user_id = ? AND m.status = 'approved' ORDER BY fg.id""",
        (user_id,),
    )]


def tree_for_group(conn, viewer_user_id: int, group_id: int):
    """None if the group doesn't exist or the viewer isn't an approved member -- the route turns
    that into a 404, never a 403, so a stranger can't confirm a specific family's existence by
    probing ids (same convention the Admin Panel's council scope already uses). The founding
    creator is always an approved, is_admin=1 member too (create_group() inserts them), so there's
    no separate "or is the creator" fallback needed here any more."""
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

    return {
        "group_id": group_id, "group_name": group["name"], "kind": group["kind"],
        "created_by_user_id": group["created_by_user_id"], "is_admin": bool(member_row["is_admin"]),
        "nodes": nodes, "parent_links": parent_links, "spouse_links": spouse_links,
    }
