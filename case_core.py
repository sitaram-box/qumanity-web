"""Qumanity Economic Engine -- Case Management (Phase 2, 2026-11-25). See
docs/economic_engine_phase1_design_2026_11_25.md for the full Phase 1 design and the Founder's
final Phase 2 decisions (no Agent commission, Suppliers are registered members, Cases live on
the Home tab as a Council-filtered chat type, no telephony -- Case Chat only).

Phase 2 Step 1 (this file, for now): schema only -- `agents`, `suppliers`, `supplier_ratings`,
`qumanity_cases`, `case_logs`, `compass_tasks`. The state machine (create_case/assign_agent/
update_status/resolve_case/add_compass_task) and the unified can_manage_location() authority
checker land in Phase 2 Step 2, added to this same file.

`suppliers` IS the "extended user profile" the Founder's Decision 2 describes -- every Supplier,
from a fertilizer company to an individual delivery boy, is a registered Qumanity member who has
opted in to this directory, never a separate non-member entity. `agents` are salaried Qumanity
staff hired via the Admin Panel (Decision 1 -- no commission, so no collusion incentive); being
listed in one of these tables is what makes a user_id an Agent or a Supplier, there is no new role
column on `users` itself.
"""
from __future__ import annotations

import datetime as dt

import chat_core
import karma_core
import reports_core
import wallet_core

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    hired_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_agents_location ON agents(location_level, location_id, is_active);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    service_category TEXT NOT NULL,
    description TEXT,
    price_list TEXT,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_suppliers_directory
    ON suppliers(location_level, location_id, service_category, is_active);

CREATE TABLE IF NOT EXISTS qumanity_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_type TEXT NOT NULL,              -- 'commerce' | 'service_request'
    member_user_id INTEGER NOT NULL,
    agent_user_id INTEGER,
    supplier_user_id INTEGER,
    location_id TEXT NOT NULL,             -- the village the case was opened from
    location_level TEXT NOT NULL DEFAULT 'village',
    subject TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    escrow_amount INTEGER NOT NULL DEFAULT 0,
    chat_sub_id INTEGER,                   -- the board_core subgroup backing this case's Case Chat
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (member_user_id) REFERENCES users(id),
    FOREIGN KEY (agent_user_id) REFERENCES users(id),
    FOREIGN KEY (supplier_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_cases_member ON qumanity_cases(member_user_id);
CREATE INDEX IF NOT EXISTS idx_cases_agent ON qumanity_cases(agent_user_id, status);
CREATE INDEX IF NOT EXISTS idx_cases_status ON qumanity_cases(status);

CREATE TABLE IF NOT EXISTS case_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    author_user_id INTEGER,
    author_role TEXT NOT NULL,             -- 'member' | 'agent' | 'supplier' | 'system' | 'council'
    log_type TEXT NOT NULL,                -- see LOG_TYPES
    message TEXT,
    visibility TEXT NOT NULL DEFAULT 'member',  -- 'member' (Member can see) | 'internal' (Agent/Council only)
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES qumanity_cases(id)
);
CREATE INDEX IF NOT EXISTS idx_case_logs_case ON case_logs(case_id, created_at);

CREATE TABLE IF NOT EXISTS compass_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    agent_user_id INTEGER NOT NULL,
    note TEXT NOT NULL,
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',   -- 'open' | 'done'
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (case_id) REFERENCES qumanity_cases(id),
    FOREIGN KEY (agent_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_compass_agent ON compass_tasks(agent_user_id, status);

CREATE TABLE IF NOT EXISTS supplier_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    rater_user_id INTEGER NOT NULL,
    ratee_user_id INTEGER NOT NULL,
    ratee_role TEXT NOT NULL,              -- 'supplier' | 'agent' -- rated separately (Decision 4)
    stars INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (case_id) REFERENCES qumanity_cases(id),
    UNIQUE (case_id, rater_user_id, ratee_role)
);
"""

CASE_TYPES = ("commerce", "service_request")

# Union of both case_type sub-machines (docs/economic_engine_phase1_design_2026_11_25.md §2).
# service_request uses: created -> agent_assigned -> in_progress -> resolved (+ escalated).
# commerce additionally uses: supplier_contacted, pending_supplier, pending_payment, disputed,
# cancelled (only reachable before the escrow lock in pending_payment).
CASE_STATUSES = (
    "created", "agent_assigned", "supplier_contacted", "pending_supplier",
    "pending_payment", "in_progress", "resolved", "disputed", "escalated", "cancelled",
)
TERMINAL_STATUSES = {"resolved", "cancelled"}

LOG_TYPES = (
    "comment", "status_change", "supplier_selected", "escrow_locked",
    "escrow_released", "escrow_refunded", "compass_task", "rating",
)


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---- Phase 2 Step 2 (2026-11-25): the Case state machine, TID Comments, and the Compass -------
# Both sub-machines start at 'created' -- the Founder's own Step 2 brief said this twice and
# disagreed with itself (bullet 1 said a commerce Case starts at "PENDING_ESCROW", bullet 2's own
# worked example starts the SAME commerce chain at CREATED). Kept 'created' for both, since that
# matches bullet 2, the already-committed/approved CASE_STATUSES tuple above (there is no
# 'pending_escrow' status in it), and the Phase 1 design doc's own diagrams. Flagged, not guessed
# silently -- worth a quick confirmation if 2026-11-25's intent was actually to skip straight to
# an escrow-pending state.
ROLES = ("member", "agent", "supplier", "system", "council")

# service_request: created -> agent_assigned -> in_progress -> resolved (+ escalated branch).
_SERVICE_REQUEST_TRANSITIONS = {
    "created": {"agent_assigned", "cancelled"},
    "agent_assigned": {"in_progress", "escalated", "cancelled"},
    "in_progress": {"resolved", "escalated"},
    "escalated": {"agent_assigned", "in_progress", "resolved"},
}

# commerce: created -> agent_assigned -> supplier_contacted (<-> pending_supplier, the Compass
# loop) -> pending_payment (escrow locked on the way OUT of this state) -> in_progress ->
# resolved/disputed. 'cancelled' only reachable before the escrow lock; once it's locked, only
# a council-resolved 'disputed' case can still end in 'cancelled' (a refund), never a plain cancel.
_COMMERCE_TRANSITIONS = {
    "created": {"agent_assigned", "cancelled"},
    "agent_assigned": {"supplier_contacted", "escalated", "cancelled"},
    "supplier_contacted": {"pending_supplier", "pending_payment", "escalated", "cancelled"},
    "pending_supplier": {"supplier_contacted", "pending_payment", "cancelled"},
    "pending_payment": {"in_progress", "disputed"},
    "in_progress": {"resolved", "disputed", "escalated"},
    "disputed": {"resolved", "cancelled", "escalated"},
    "escalated": {"agent_assigned", "supplier_contacted", "in_progress", "resolved", "cancelled"},
}

TRANSITIONS = {"service_request": _SERVICE_REQUEST_TRANSITIONS, "commerce": _COMMERCE_TRANSITIONS}

# Decision 5 (2026-11-25, Founder): no fixed Qoin value is specified for a resolved
# service_request's karma award (there's no payment to size it off, unlike commerce's escrow) --
# a conservative, same-for-everyone default, tunable later, not meant to read as a considered
# figure the way COMMERCE_FEE_SPLIT in wallet_core.py is.
SERVICE_REQUEST_RESOLUTION_KARMA = 5


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _log(conn, case_id: int, author_user_id: int | None, author_role: str, log_type: str,
         message: str | None = None, visibility: str = "member") -> None:
    if author_role not in ROLES:
        raise ValueError(f"Unknown author_role: {author_role}")
    if log_type not in LOG_TYPES:
        raise ValueError(f"Unknown log_type: {log_type}")
    conn.execute(
        """INSERT INTO case_logs (case_id, author_user_id, author_role, log_type, message, visibility, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (case_id, author_user_id, author_role, log_type, message, visibility, _now()),
    )


def get_case(conn, case_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM qumanity_cases WHERE id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def _is_assigned_agent(conn, user_id: int, location_level: str, location_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM agents WHERE user_id = ? AND location_id = ? AND location_level = ? AND is_active = 1",
        (user_id, location_id, location_level),
    ).fetchone()
    return row is not None


def create_case(conn, member_user_id: int, case_type: str, location_id: str, subject: str,
                 location_level: str = "village") -> dict:
    """A Member opens a Case from their Village page (no authority check -- any Member may open
    one for themselves). Starts at 'created' for both case_type values -- see the module note
    above this section."""
    if case_type not in CASE_TYPES:
        raise ValueError(f"Unknown case_type: {case_type}")
    subject = (subject or "").strip()
    if not subject:
        raise ValueError("A subject is required")
    now = _now()
    cur = conn.execute(
        """INSERT INTO qumanity_cases
           (case_type, member_user_id, location_id, location_level, subject, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'created', ?, ?)""",
        (case_type, member_user_id, location_id, location_level, subject, now, now),
    )
    case_id = cur.lastrowid
    _log(conn, case_id, member_user_id, "member", "status_change", f"Case opened ({case_type}): {subject}")
    conn.commit()
    return get_case(conn, case_id)


def assign_agent(conn, case_id: int, agent_user_id: int, actor_user_id: int, is_admin: bool,
                  note: str | None = None) -> dict:
    """Either the location's authority (can_manage_location() -- Founder or seated council)
    assigning a named Agent, or an Agent picking up an unassigned/escalated Case themselves from
    their own queue (actor_user_id == agent_user_id). Either way the target must be a real,
    active Agent registered for this exact Case's location."""
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if case["status"] not in ("created", "escalated"):
        raise ValueError(f"Cannot assign an Agent while the case is '{case['status']}'")
    if not _is_assigned_agent(conn, agent_user_id, case["location_level"], case["location_id"]):
        raise ValueError("That user is not a registered, active Agent for this Case's location")
    self_pickup = actor_user_id == agent_user_id
    if not self_pickup and not chat_core.can_manage_location(
        conn, actor_user_id, case["location_level"], case["location_id"], is_admin
    ):
        raise PermissionError("Only this location's council/Founder, or the Agent themselves, may assign an Agent")
    conn.execute(
        "UPDATE qumanity_cases SET agent_user_id = ?, status = 'agent_assigned', updated_at = ? WHERE id = ?",
        (agent_user_id, _now(), case_id),
    )
    _log(conn, case_id, actor_user_id, "agent" if self_pickup else "council", "status_change",
         note or "Agent assigned to this Case")
    conn.commit()
    return get_case(conn, case_id)


def update_status(conn, case_id: int, new_status: str, actor_user_id: int, actor_role: str,
                   is_admin: bool, message: str | None = None, escrow_amount: int | None = None) -> dict:
    """Enforces TRANSITIONS[case_type]. 'resolved' is deliberately rejected here -- use
    resolve_case(), which also handles the escrow release / Karma award that status alone can't.
    Moving a commerce Case OUT of 'pending_payment' requires `escrow_amount` -- this is the exact
    moment wallet_core.lock_escrow() runs, so a Member with insufficient Qoins gets a ValueError
    here and the Case stays in 'pending_payment' (nothing is written beforehand). Moving INTO
    'cancelled' always calls wallet_core.refund_escrow() first (a safe no-op if nothing was ever
    locked), so a Member is never left with Qoins stuck in a dead Case.

    `is_admin` added in Phase 2 Step 3 (2026-11-25): Step 2 enforced the transition table but
    never checked WHO may trigger it -- fine while nothing called this over HTTP yet, not once
    `/api/agent/cases/<id>/status` is a real route. Same authority as resolve_case(): this Case's
    assigned Agent, or this location's council/Founder."""
    if new_status == "resolved":
        raise ValueError("Use resolve_case() to resolve a Case, not update_status()")
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if actor_user_id != case["agent_user_id"] and not chat_core.can_manage_location(
        conn, actor_user_id, case["location_level"], case["location_id"], is_admin
    ):
        raise PermissionError("Only this Case's assigned Agent, or this location's council/Founder, may change its status")
    legal = TRANSITIONS[case["case_type"]].get(case["status"], set())
    if new_status not in legal:
        raise ValueError(f"Cannot move a {case['case_type']} Case from '{case['status']}' to '{new_status}'")

    if case["case_type"] == "commerce" and case["status"] == "pending_payment" and new_status == "in_progress":
        if not escrow_amount or escrow_amount <= 0:
            raise ValueError("escrow_amount is required to leave pending_payment")
        wallet_core.lock_escrow(conn, case_id, case["member_user_id"], escrow_amount)
        conn.execute("UPDATE qumanity_cases SET escrow_amount = ? WHERE id = ?", (escrow_amount, case_id))
        _log(conn, case_id, case["member_user_id"], "member", "escrow_locked",
             f"{escrow_amount} Qoins locked in escrow")

    if new_status == "cancelled":
        refunded = wallet_core.refund_escrow(conn, case_id, case["member_user_id"])
        if refunded:
            _log(conn, case_id, actor_user_id, actor_role, "escrow_refunded", f"{refunded} Qoins refunded")

    conn.execute(
        "UPDATE qumanity_cases SET status = ?, updated_at = ? WHERE id = ?", (new_status, _now(), case_id)
    )
    _log(conn, case_id, actor_user_id, actor_role, "status_change",
         message or f"Status changed to {new_status}")
    conn.commit()
    return get_case(conn, case_id)


def add_compass_task(conn, case_id: int, agent_user_id: int, note: str, due_at: str | None = None) -> dict:
    """An Agent's own follow-up reminder (e.g. "Supplier out of stock, re-check Thursday") --
    'internal' visibility, never shown to the Member. Polled on page load (list_compass_tasks(),
    Step 3) -- no scheduler exists anywhere in this codebase, matching how presence/dormancy are
    already computed live rather than pushed."""
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if case["agent_user_id"] != agent_user_id:
        raise PermissionError("Only this Case's assigned Agent may add a Compass task")
    note = (note or "").strip()
    if not note:
        raise ValueError("A note is required")
    cur = conn.execute(
        "INSERT INTO compass_tasks (case_id, agent_user_id, note, due_at, created_at) VALUES (?, ?, ?, ?, ?)",
        (case_id, agent_user_id, note, due_at, _now()),
    )
    _log(conn, case_id, agent_user_id, "agent", "compass_task", note, visibility="internal")
    conn.commit()
    task = conn.execute("SELECT * FROM compass_tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(task)


def list_compass_tasks(conn, agent_user_id: int, open_only: bool = True) -> list[dict]:
    q = "SELECT * FROM compass_tasks WHERE agent_user_id = ?"
    params: list = [agent_user_id]
    if open_only:
        q += " AND status = 'open'"
    q += " ORDER BY due_at IS NULL, due_at, created_at"
    return [dict(r) for r in conn.execute(q, params)]


def _fee_location_ids(conn, case: dict) -> dict[str, str]:
    """village/state/country ids to credit COMMERCE_FEE_SPLIT into, resolved via
    reports_core.get_ancestor_at_level() (the Member's own present_location_json ancestry --
    same pattern reports_core itself uses, reused rather than reimplemented) -- wallet_core stays
    location-agnostic and never walks this tree itself (see wallet_core.release_escrow())."""
    ids: dict[str, str] = {}
    if case["location_level"] == "village":
        ids["village"] = case["location_id"]
    state_id = reports_core.get_ancestor_at_level(conn, case["member_user_id"], "state")
    if state_id:
        ids["state"] = state_id
    country_id = reports_core.get_ancestor_at_level(conn, case["member_user_id"], "country")
    if country_id:
        ids["country"] = country_id
    return ids


def resolve_case(conn, case_id: int, actor_user_id: int, actor_role: str, is_admin: bool,
                  outcome_note: str | None = None) -> dict:
    """The final step: releases escrow (commerce, full COMMERCE_FEE_SPLIT applied) or awards
    SERVICE_REQUEST_RESOLUTION_KARMA (service_request, to the Agent and the Supplier if one was
    attached -- e.g. a bhandara delivery helper). Only legal from 'in_progress' or 'disputed'
    (council-decided disputes resolve here too; a disputed Case the council instead REFUNDS goes
    through update_status(..., 'cancelled') instead, not this function). Caller must be this
    Case's assigned Agent, or this location's council/Founder (chat_core.can_manage_location) --
    the latter covers a council deciding a disputed Case."""
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if case["status"] not in ("in_progress", "disputed"):
        raise ValueError(f"Cannot resolve a Case from status '{case['status']}'")
    is_assigned_agent = actor_user_id == case["agent_user_id"]
    if not is_assigned_agent and not chat_core.can_manage_location(
        conn, actor_user_id, case["location_level"], case["location_id"], is_admin
    ):
        raise PermissionError("Only this Case's assigned Agent, or this location's council/Founder, may resolve it")

    if case["case_type"] == "commerce":
        if not case["supplier_user_id"]:
            raise ValueError("A commerce Case needs a Supplier attached before it can be resolved")
        fee_ids = _fee_location_ids(conn, case)
        result = wallet_core.release_escrow(conn, case_id, case["supplier_user_id"], fee_ids)
        _log(conn, case_id, actor_user_id, actor_role, "escrow_released",
             f"Released {result['supplier_amount']} Qoins to Supplier; fees: {result['fees']}")
    else:
        karma_core.add_individual_karma(
            conn, case["agent_user_id"], "noncommercial", SERVICE_REQUEST_RESOLUTION_KARMA,
            f"Case #{case_id} resolved: {case['subject']}", case["member_user_id"],
        )
        if case["supplier_user_id"]:
            karma_core.add_individual_karma(
                conn, case["supplier_user_id"], "noncommercial", SERVICE_REQUEST_RESOLUTION_KARMA,
                f"Case #{case_id} resolved: {case['subject']}", case["member_user_id"],
            )
        _log(conn, case_id, actor_user_id, actor_role, "status_change", "Karma awarded for resolving this Case")

    now = _now()
    conn.execute(
        "UPDATE qumanity_cases SET status = 'resolved', resolved_at = ?, updated_at = ? WHERE id = ?",
        (now, now, case_id),
    )
    _log(conn, case_id, actor_user_id, actor_role, "status_change", outcome_note or "Case resolved")
    conn.commit()
    return get_case(conn, case_id)


# ---- Phase 2 Step 3 (2026-11-25): list/view/comment helpers for the Member/Agent/Supplier APIs -

def list_for_member(conn, member_user_id: int, active_only: bool = True) -> list[dict]:
    q = "SELECT * FROM qumanity_cases WHERE member_user_id = ?"
    if active_only:
        q += " AND status NOT IN ('resolved', 'cancelled')"
    q += " ORDER BY created_at DESC"
    return [dict(r) for r in conn.execute(q, (member_user_id,))]


def get_agent(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM agents WHERE user_id = ? AND is_active = 1", (user_id,)).fetchone()
    return dict(row) if row else None


def list_for_agent(conn, agent_user_id: int) -> list[dict]:
    """This Agent's own queue: every Case already assigned to them (any status), plus every
    still-'created' (unassigned) Case at their own registered location -- an Agent sees fresh
    Cases opened at their location even before anyone has claimed one."""
    agent = get_agent(conn, agent_user_id)
    if not agent:
        raise PermissionError("Not a registered, active Agent")
    rows = conn.execute(
        """SELECT * FROM qumanity_cases
           WHERE agent_user_id = ?
              OR (status = 'created' AND location_id = ? AND location_level = ?)
           ORDER BY created_at DESC""",
        (agent_user_id, agent["location_id"], agent["location_level"]),
    ).fetchall()
    return [dict(r) for r in rows]


def can_view_case(conn, user_id: int, case: dict, is_admin: bool) -> bool:
    """The Member, the assigned Agent, the attached Supplier, or this location's council/Founder
    (the audit path reports_core.mask_identity() uses the same shape of check for)."""
    if user_id in (case["member_user_id"], case["agent_user_id"], case["supplier_user_id"]):
        return True
    return chat_core.can_manage_location(conn, user_id, case["location_level"], case["location_id"], is_admin)


def logs_for(conn, case_id: int, viewer_user_id: int, is_admin: bool) -> list[dict]:
    """The TID Comments for a Case. 'internal' entries (an Agent's own Compass notes, e.g.) are
    stripped out for the Member and the Supplier -- only this Case's assigned Agent, or this
    location's council/Founder, see them. That council/Founder visibility is deliberate, not a
    gap: it's what lets a Manager audit screen catch Agent-Supplier collusion (Phase 1 design
    doc §2) -- hiding internal notes from the people auditing for collusion would defeat the point."""
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if not can_view_case(conn, viewer_user_id, case, is_admin):
        raise PermissionError("You can't view this Case")
    can_see_internal = viewer_user_id == case["agent_user_id"] or chat_core.can_manage_location(
        conn, viewer_user_id, case["location_level"], case["location_id"], is_admin
    )
    q = "SELECT * FROM case_logs WHERE case_id = ?"
    if not can_see_internal:
        q += " AND visibility = 'member'"
    q += " ORDER BY id"
    return [dict(r) for r in conn.execute(q, (case_id,))]


def add_comment(conn, case_id: int, author_user_id: int, message: str, is_admin: bool = False) -> dict:
    """Posts to the Case Chat -- Decision 3/4 (2026-11-25): the TID Comments log IS the chat, and
    it's the only channel (no telephony). The author's role is derived from the Case itself
    (never trusted from the caller), so there's no way to post AS a role you don't actually hold
    on this Case; an admin override posts as 'system'. Only the Member, the assigned Agent, the
    attached Supplier, or an admin may post -- everyone else gets PermissionError."""
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if author_user_id == case["member_user_id"]:
        role = "member"
    elif author_user_id == case["agent_user_id"]:
        role = "agent"
    elif author_user_id == case["supplier_user_id"]:
        role = "supplier"
    elif is_admin:
        role = "system"
    else:
        raise PermissionError("Only this Case's Member, Agent, or Supplier may post to its chat")
    message = (message or "").strip()
    if not message:
        raise ValueError("A message is required")
    _log(conn, case_id, author_user_id, role, "comment", message, visibility="member")
    conn.commit()
    row = conn.execute("SELECT * FROM case_logs WHERE case_id = ? ORDER BY id DESC LIMIT 1", (case_id,)).fetchone()
    return dict(row)


def attach_supplier(conn, case_id: int, supplier_user_id: int, actor_user_id: int) -> dict:
    """Adds the chosen Supplier to a commerce Case (Decision 4 -- they then negotiate directly in
    the Case Chat, no 3-way call). Only this Case's own assigned Agent may do this, and the
    target must already be a registered Supplier (register_supplier())."""
    case = get_case(conn, case_id)
    if not case:
        raise LookupError("Case not found")
    if actor_user_id != case["agent_user_id"]:
        raise PermissionError("Only this Case's assigned Agent may add a Supplier")
    if not get_supplier(conn, supplier_user_id):
        raise ValueError("That user is not a registered Supplier")
    conn.execute(
        "UPDATE qumanity_cases SET supplier_user_id = ?, updated_at = ? WHERE id = ?",
        (supplier_user_id, _now(), case_id),
    )
    _log(conn, case_id, actor_user_id, "agent", "supplier_selected", f"Supplier #{supplier_user_id} added to this Case")
    conn.commit()
    return get_case(conn, case_id)


def register_supplier(conn, user_id: int, service_category: str, location_id: str, location_level: str,
                       description: str | None = None, price_list: str | None = None) -> dict:
    """Get-or-create a member's own Supplier directory listing (Decision 2 -- every Supplier is
    a registered Qumanity member; this IS their "extended user profile", not a new role column)."""
    service_category = (service_category or "").strip()
    if not service_category:
        raise ValueError("A service_category is required")
    now = _now()
    existing = conn.execute("SELECT id FROM suppliers WHERE user_id = ?", (user_id,)).fetchone()
    if existing:
        conn.execute(
            """UPDATE suppliers SET service_category = ?, description = ?, price_list = ?,
               location_id = ?, location_level = ?, is_active = 1, updated_at = ? WHERE user_id = ?""",
            (service_category, description, price_list, location_id, location_level, now, user_id),
        )
    else:
        conn.execute(
            """INSERT INTO suppliers (user_id, service_category, description, price_list,
               location_id, location_level, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, service_category, description, price_list, location_id, location_level, now, now),
        )
    conn.commit()
    return get_supplier(conn, user_id)


def get_supplier(conn, user_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM suppliers WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_suppliers(conn, location_level: str, location_id: str, service_category: str | None = None) -> list[dict]:
    """The Agent's own directory search (Decision 2): every active Supplier registered at this
    exact location, optionally narrowed to one service_category, each with their Karma score
    attached so the Agent can present price list + Karma together, per the brief."""
    q = "SELECT * FROM suppliers WHERE location_level = ? AND location_id = ? AND is_active = 1"
    params: list = [location_level, location_id]
    if service_category:
        q += " AND service_category = ?"
        params.append(service_category)
    q += " ORDER BY service_category, created_at"
    rows = [dict(r) for r in conn.execute(q, params)]
    for r in rows:
        r["karma"] = karma_core.individual_karma_score(conn, r["user_id"])
    return rows
