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
