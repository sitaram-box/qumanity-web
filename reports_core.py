"""Item 9: Citizen Report, Qumanity's FIR-equivalent. A private concern a citizen files from
their Village Lok page, visible only to the council currently holding it (never public, unlike
board posts). See docs/reports_design.md for the full design + the Founder's approved decisions.

Escalation ladder matches board_core.LEVELS' order (village is the only level a report can be
*created* at; it can only move upward from there, never back down). Council membership only
exists at village level today (village_council), same gap already approved for announcements_core
-- every level past village falls back to Founder/Admin until real elected councils exist there;
the caller (app.py) logs a note each time that fallback is the reason a holder got assigned."""
from __future__ import annotations

import datetime as dt
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,
    body TEXT NOT NULL,
    anonymous INTEGER DEFAULT 0,
    status TEXT DEFAULT 'open',
    current_holder_level TEXT,
    current_holder_id TEXT,
    escalation_path TEXT DEFAULT '[]',
    sla_deadline TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_reports_holder ON reports(current_holder_level, current_holder_id);
CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, sla_deadline);

CREATE TABLE IF NOT EXISTS report_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    author_user_id TEXT NOT NULL,
    author_role TEXT,
    update_type TEXT NOT NULL,
    message TEXT,
    new_deadline TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES reports(id)
);
CREATE INDEX IF NOT EXISTS idx_report_updates ON report_updates(report_id, created_at);
"""

LEVELS = ("village", "tehsil", "district", "state", "zone", "country", "continent", "earth")
SLA_DAYS = 10
UPDATE_TYPES = ("acknowledged", "needs_time", "resolved", "denied", "escalated", "comment")
TERMINAL_STATUSES = {"resolved": "resolved", "denied": "denied"}


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get_ancestor_at_level(conn, user_id, target_level: str) -> str | None:
    """The reporting citizen's own ancestor id at target_level, walked from their present
    location -- never a separately-looked-up "escalation target" (docs/reports_design.md §4/Decision 4)."""
    if target_level == "earth":
        return "EARTH"
    row = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return None
    loc = json.loads(row["present_location_json"] or "{}")
    entry = loc.get(target_level)
    return entry["id"] if entry else None


def is_holder_council(conn, user_id, holder_level, holder_id, is_admin: bool) -> bool:
    """Same gap as announcements_core.is_council_member: only village has real elected data."""
    if is_admin:
        return True
    if holder_level != "village":
        return False
    today = dt.date.today().isoformat()
    row = conn.execute(
        """SELECT 1 FROM village_council
           WHERE village_id = ? AND leadership_start <= ? AND leadership_end >= ?
             AND (male_head_user_id = ? OR female_head_user_id = ?)""",
        (holder_id, today, today, str(user_id), str(user_id)),
    ).fetchone()
    return row is not None


def create(conn, user_id, village_id, body, anonymous: bool) -> dict:
    sla = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=SLA_DAYS)).isoformat()
    cur = conn.execute(
        """INSERT INTO reports (user_id, location_id, location_level, body, anonymous,
                                 current_holder_level, current_holder_id, sla_deadline)
           VALUES (?, 'village', 'village', ?, ?, 'village', ?, ?)""",
        (str(user_id), body, 1 if anonymous else 0, village_id, sla),
    )
    conn.commit()
    return {"id": cur.lastrowid, "sla_deadline": sla}


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"], "user_id": r["user_id"], "location_id": r["location_id"],
        "location_level": r["location_level"], "body": r["body"], "anonymous": bool(r["anonymous"]),
        "status": r["status"], "current_holder_level": r["current_holder_level"],
        "current_holder_id": r["current_holder_id"], "escalation_path": json.loads(r["escalation_path"] or "[]"),
        "sla_deadline": r["sla_deadline"], "created_at": r["created_at"], "resolved_at": r["resolved_at"],
    }


def get(conn, report_id) -> dict | None:
    r = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return _row_to_dict(r) if r else None


def can_view(conn, user_id, report: dict, is_admin: bool) -> bool:
    if is_admin or str(report["user_id"]) == str(user_id):
        return True
    return is_holder_council(conn, user_id, report["current_holder_level"], report["current_holder_id"], is_admin)


def mask_identity(conn, report: dict, viewer_user_id, is_admin: bool) -> dict:
    """Anonymous hides identity from the council too -- not merely some other audience, since
    reports have no public view at all (Decision 2). Owner always sees their own identity; Admin
    always sees the real identity regardless of the flag."""
    out = dict(report)
    is_owner = str(report["user_id"]) == str(viewer_user_id)
    if report["anonymous"] and not is_owner and not is_admin:
        out["author_name"] = "Anonymous Citizen"
        out.pop("user_id", None)
    else:
        u = conn.execute("SELECT name FROM users WHERE id = ?", (report["user_id"],)).fetchone()
        out["author_name"] = u["name"] if u else "Unknown"
    return out


def list_mine(conn, user_id) -> list[dict]:
    rows = conn.execute(
        """SELECT r.*, (SELECT ru.created_at FROM report_updates ru WHERE ru.report_id = r.id
                         ORDER BY ru.created_at DESC LIMIT 1) AS last_update_at
           FROM reports r WHERE r.user_id = ? ORDER BY r.created_at DESC""",
        (str(user_id),),
    ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        d["last_update_at"] = r["last_update_at"]
        out.append(d)
    return out


def list_inbox(conn, location_level, location_id) -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM reports WHERE current_holder_level = ? AND current_holder_id = ?
           AND status NOT IN ('resolved', 'denied') ORDER BY sla_deadline ASC""",
        (location_level, location_id),
    ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        d["body_preview"] = d["body"][:140]
        if d["anonymous"]:
            d["author_name"] = "Anonymous Citizen"
            d.pop("user_id", None)
        out.append(d)
    return out


def list_all_open(conn) -> list[dict]:
    """Every non-terminal report, ANY location -- the Admin Panel's global feed (2026-10-18).
    Unlike list_inbox() (scoped to one holder), this has no location filter: is_admin already
    bypasses can_view()/is_holder_council() for every individual report (see those two
    functions), so the Founder seeing every open report in one aggregated list is the same
    access they already had one report at a time, not a new grant. Joins users directly for
    author_name rather than reusing list_inbox()'s contract (which leaves a non-anonymous
    report's name unresolved) -- a new function, so it doesn't change what list_inbox()'s own
    existing callers already depend on."""
    rows = conn.execute(
        """SELECT r.*, u.name AS real_author_name FROM reports r
           LEFT JOIN users u ON u.id = CAST(r.user_id AS INTEGER)
           WHERE r.status NOT IN ('resolved', 'denied') ORDER BY r.sla_deadline ASC"""
    ).fetchall()
    out = []
    for r in rows:
        d = _row_to_dict(r)
        d["body_preview"] = d["body"][:140]
        if d["anonymous"]:
            d["author_name"] = "Anonymous Citizen"
            d.pop("user_id", None)
        else:
            d["author_name"] = r["real_author_name"] or "Unknown"
        out.append(d)
    return out


def updates_for(conn, report_id) -> list[dict]:
    rows = conn.execute(
        """SELECT ru.*, u.name AS author_name FROM report_updates ru
           LEFT JOIN users u ON u.id = ru.author_user_id
           WHERE ru.report_id = ? ORDER BY ru.created_at DESC""",
        (report_id,),
    ).fetchall()
    return [
        {
            "id": r["id"], "author_name": r["author_name"], "author_role": r["author_role"],
            "update_type": r["update_type"], "message": r["message"], "new_deadline": r["new_deadline"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def _append_path(conn, report_id, level, holder_id, outcome):
    row = conn.execute("SELECT escalation_path FROM reports WHERE id = ?", (report_id,)).fetchone()
    path = json.loads(row["escalation_path"] or "[]")
    path.append({"level": level, "id": holder_id, "at": _now_iso(), "outcome": outcome})
    conn.execute("UPDATE reports SET escalation_path = ? WHERE id = ?", (json.dumps(path), report_id))


def add_update(conn, report_id, author_user_id, author_role, update_type, message=None, new_deadline=None):
    if update_type not in UPDATE_TYPES:
        raise ValueError(f"Unknown update_type: {update_type}")
    if update_type == "needs_time" and not new_deadline:
        raise ValueError("needs_time requires new_deadline")
    report = get(conn, report_id)
    if report is None:
        raise LookupError("Unknown report")

    conn.execute(
        """INSERT INTO report_updates (report_id, author_user_id, author_role, update_type, message, new_deadline)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (report_id, str(author_user_id), author_role, update_type, message, new_deadline),
    )

    if update_type == "needs_time":
        conn.execute("UPDATE reports SET sla_deadline = ?, status = 'in_progress' WHERE id = ?", (new_deadline, report_id))
    elif update_type == "acknowledged":
        conn.execute("UPDATE reports SET status = 'in_progress' WHERE id = ?", (report_id,))
    elif update_type in TERMINAL_STATUSES:
        _append_path(conn, report_id, report["current_holder_level"], report["current_holder_id"], update_type)
        conn.execute(
            "UPDATE reports SET status = ?, resolved_at = ? WHERE id = ?",
            (TERMINAL_STATUSES[update_type], _now_iso(), report_id),
        )
    conn.commit()


def escalate(conn, report_id, author_user_id, author_role):
    """Moves the report to the next level up (village -> tehsil -> ... -> earth), resets the SLA
    to a fresh 10 days (Decision 1), and logs a system update. Returns (new_level, new_holder_id,
    is_fallback) -- is_fallback is True when the new level has no elected council, so app.py can
    log the required fallback note."""
    report = get(conn, report_id)
    if report is None:
        raise LookupError("Unknown report")
    current = report["current_holder_level"]
    idx = LEVELS.index(current)
    if idx == len(LEVELS) - 1:
        raise ValueError("Already at Earth -- nothing to escalate to")
    new_level = LEVELS[idx + 1]
    new_holder_id = get_ancestor_at_level(conn, report["user_id"], new_level)
    if new_holder_id is None:
        raise ValueError(f"Could not resolve the reporting citizen's {new_level} for escalation")

    _append_path(conn, report_id, current, report["current_holder_id"], "escalated")
    new_sla = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=SLA_DAYS)).isoformat()
    conn.execute(
        "UPDATE reports SET current_holder_level = ?, current_holder_id = ?, sla_deadline = ?, status = 'escalated' WHERE id = ?",
        (new_level, new_holder_id, new_sla, report_id),
    )
    conn.execute(
        """INSERT INTO report_updates (report_id, author_user_id, author_role, update_type, message, new_deadline)
           VALUES (?, ?, ?, 'escalated', ?, ?)""",
        (report_id, str(author_user_id), author_role, f"Escalated to {new_level.capitalize()}", new_sla),
    )
    conn.commit()
    is_fallback = new_level != "village"
    return new_level, new_holder_id, is_fallback
