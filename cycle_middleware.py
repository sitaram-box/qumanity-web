"""Phase 2 of the lunar-cycle archival system: stamps every write to an "ongoing activity" table
with the cycle_id (see lunar_calendar.py) that was active at write time, and tracks which cycle is
currently active in `cycle_state`.

This module never touches the pipeline (transfers between location levels, the N-2 safety rule)
or 0_Earth -- that's Phase 3/4. All it does is answer "what's the active cycle_id right now" and
record it on new rows; nothing here moves or archives data.

See docs/lunar_cycle_system.md and docs/phase_2_report.md for the full design and the table-by-
table include/exclude rationale behind STAMPED_TABLES below.
"""
from __future__ import annotations

import datetime as dt

import lunar_calendar

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycle_state (
    cycle_id TEXT PRIMARY KEY,
    start_date TEXT NOT NULL,
    mid_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    activated_at TEXT NOT NULL,
    closed_at TEXT,
    activated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_cycle_state_status ON cycle_state(status);
CREATE INDEX IF NOT EXISTS idx_cycle_state_activated_at ON cycle_state(activated_at);
"""

# Every table Phase 2 stamps with cycle_id -> the column holding a usable write timestamp for the
# migrations/003_backfill_cycle_ids.py pass, or None when the table has no timestamp column at all
# (board_votes), in which case a pre-existing row falls back to whatever cycle is active when the
# backfill runs. New writes (every call site below) always stamp with get_active_cycle_id() directly,
# regardless of this map -- it is read only by the backfill migration.
STAMPED_TABLES = {
    "wallet_transactions": "created_at",
    "election_candidates": "created_at",
    "election_votes": "voted_at",
    "karma_entries": "created_at",
    "collective_karma_log": "created_at",
    "business_ratings": "created_at",
    "board_posts": "created_at",
    "board_votes": None,
    "board_comments": "created_at",
    "board_messages": "created_at",
    "personal_messages": "created_at",
    "private_messages": "created_at",
    "account_ids": "created_at",
    "people_requests": "created_at",
    "account_id_requests": "created_at",
    "payment_orders": "created_at",
    "country_sentiment": "created_at",
    "zone_sentiment": "created_at",
    "app_reviews": "created_at",
    "profile_change_requests": "created_at",
    "volunteers": "created_at",
    "message_reactions": "created_at",
    "referrer_applications": "created_at",
    "subgroups": "created_at",
    "personal_groups": "created_at",
    "private_chats": "created_at",
    "subgroup_members": "requested_at",
    "personal_group_members": "created_at",
}


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _activate(conn, cycle_id: str, activated_by: str | None = None) -> dict:
    start, mid, end = lunar_calendar.get_cycle_dates(cycle_id)
    now = _now()
    conn.execute(
        """INSERT INTO cycle_state (cycle_id, start_date, mid_date, end_date, status, activated_at, activated_by)
           VALUES (?, ?, ?, ?, 'active', ?, ?)
           ON CONFLICT(cycle_id) DO UPDATE SET
               status = 'active', closed_at = NULL, activated_at = excluded.activated_at, activated_by = excluded.activated_by""",
        (cycle_id, start.isoformat(), mid.isoformat(), end.isoformat(), now, activated_by),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM cycle_state WHERE cycle_id = ?", (cycle_id,)).fetchone())


def get_active_cycle_row(conn) -> dict:
    """The single active cycle_state row, self-seeding it from lunar_calendar's own live
    computation the first time anything asks -- so Phase 2 works immediately after migration 001
    runs, with no separate manual "activate" step needed for the very first cycle."""
    ensure_tables(conn)
    row = conn.execute("SELECT * FROM cycle_state WHERE status = 'active' LIMIT 1").fetchone()
    if row:
        return dict(row)
    return _activate(conn, lunar_calendar.get_current_cycle_id(), activated_by="system:auto-seed")


def get_active_cycle_id(conn) -> str:
    return get_active_cycle_row(conn)["cycle_id"]


def transition_to(conn, cycle_id: str | None = None, activated_by: str | None = None) -> dict:
    """Closes the current active cycle and activates `cycle_id` (or, if omitted, whatever
    lunar_calendar says is the real current cycle right now). Manual only in Phase 2 -- nothing
    calls this automatically; Phase 5's cron is what eventually will. Does not touch the
    pipeline/safety rule (Phase 3) or any 0_Earth file (Phase 4): it only changes which cycle_id
    new writes get stamped with from this point on."""
    ensure_tables(conn)
    cycle_id = cycle_id or lunar_calendar.get_current_cycle_id()
    current = conn.execute("SELECT cycle_id FROM cycle_state WHERE status = 'active'").fetchone()
    if current and current["cycle_id"] == cycle_id:
        return get_active_cycle_row(conn)
    if current:
        conn.execute("UPDATE cycle_state SET status = 'closed', closed_at = ? WHERE cycle_id = ?", (_now(), current["cycle_id"]))
        conn.commit()
    return _activate(conn, cycle_id, activated_by)


def history(conn, limit: int = 50) -> list[dict]:
    """Every cycle_state row, newest-activated first -- for the status admin endpoint."""
    ensure_tables(conn)
    return [dict(r) for r in conn.execute("SELECT * FROM cycle_state ORDER BY activated_at DESC LIMIT ?", (limit,))]
