"""Admin Panel: general queries/complaints (2026-10-18). See migrations/020_admin_panel.py's
docstring for why this is a separate table from reports_core.py's reports, not a generalization
of it -- a karma complaint has no location and no council escalation ladder, which is the entire
point of that module.

create()'s route is deliberately not wired up in this pass (2026-10-18) -- this file builds the
complete model (matching reports_core.py's/recovery_core.py's own create/list/act shape), but no
citizen-facing "submit a query" entry point exists yet; that is a separate, later decision.
"""
from __future__ import annotations

import datetime as dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_queries_user ON admin_queries(user_id);
CREATE INDEX IF NOT EXISTS idx_admin_queries_status ON admin_queries(status, created_at);

CREATE TABLE IF NOT EXISTS admin_query_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    author_user_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (query_id) REFERENCES admin_queries(id)
);
CREATE INDEX IF NOT EXISTS idx_admin_query_replies_query ON admin_query_replies(query_id, created_at);
"""

CATEGORIES = ("account", "karma", "wallet", "other")
STATUSES = ("open", "answered", "closed")


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create(conn, user_id: int, category: str, subject: str, body: str) -> int:
    ensure_tables(conn)
    category = category if category in CATEGORIES else "other"
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not subject or not body:
        raise ValueError("Subject and message are required")
    cur = conn.execute(
        "INSERT INTO admin_queries (user_id, category, subject, body, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
        (user_id, category, subject, body, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get(conn, query_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM admin_queries WHERE id = ?", (query_id,)).fetchone()
    return dict(r) if r else None


def list_mine(conn, user_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM admin_queries WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def list_open(conn) -> list[dict]:
    """Every query that isn't closed, newest first -- the Admin Panel feed's source for this
    ticket type. Includes the asking user's name and their latest reply timestamp (if any) so the
    combined feed can render a preview without an N+1 query per ticket."""
    ensure_tables(conn)
    rows = conn.execute(
        """SELECT q.*, u.name AS author_name,
                  (SELECT MAX(created_at) FROM admin_query_replies r WHERE r.query_id = q.id) AS last_reply_at
           FROM admin_queries q JOIN users u ON u.id = q.user_id
           WHERE q.status != 'closed' ORDER BY q.created_at DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def replies_for(conn, query_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT r.*, u.name AS author_name FROM admin_query_replies r
           JOIN users u ON u.id = r.author_user_id WHERE r.query_id = ? ORDER BY r.created_at ASC""",
        (query_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def reply(conn, admin_user_id: int, query_id: int, message: str) -> None:
    query = get(conn, query_id)
    if not query:
        raise LookupError("Query not found")
    message = (message or "").strip()
    if not message:
        raise ValueError("Reply message is required")
    conn.execute(
        "INSERT INTO admin_query_replies (query_id, author_user_id, message, created_at) VALUES (?, ?, ?, ?)",
        (query_id, admin_user_id, message, _now()),
    )
    conn.execute("UPDATE admin_queries SET status = 'answered' WHERE id = ?", (query_id,))
    conn.commit()


def close(conn, query_id: int) -> None:
    query = get(conn, query_id)
    if not query:
        raise LookupError("Query not found")
    conn.execute("UPDATE admin_queries SET status = 'closed' WHERE id = ?", (query_id,))
    conn.commit()
