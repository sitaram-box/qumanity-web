"""Admin Panel: general queries/complaints (2026-10-18). See migrations/020_admin_panel.py's
docstring for why this is a separate table from reports_core.py's reports, not a generalization
of it -- a karma complaint has no location and no council escalation ladder, which is the entire
point of that module.

create()'s route went unwired deliberately in the first pass (2026-10-18) -- this file built the
complete model (matching reports_core.py's/recovery_core.py's own create/list/act shape) before
any citizen-facing "submit a query" entry point existed. That entry point now exists, twice:
POST /api/queries (logged-in, unchanged, user_id always set) and the new POST /api/support/ticket
(2026-10-28, the public AI Support ticket route -- no login required, user_id is NULL,
guest_name/guest_contact carry who to reply to). See migrations/031_admin_queries_guest.py for
why user_id had to become nullable via a table rebuild rather than a plain ADD COLUMN.

2026-11-14: a THIRD anonymous entry point, POST /api/recovery/admin-ticket (app.py), for a member
with no usable Family Tree and no working OTP channel -- the 'account_recovery' category, using
the same user_id=NULL/guest_name/guest_contact shape the AI Support ticket already established,
plus five new nullable columns (migrations/038_account_recovery_fallback.py) this category alone
populates: date_of_birth/present_location_json/contact_method (the claim itself, structured) and
verification_status/verification_notes (the Admin's own identity-verification workflow state --
deliberately a different axis from `status`, which only ever means "has an Admin responded to/
closed this ticket," never "is this person who they say they are").
"""
from __future__ import annotations

import datetime as dt
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    guest_name TEXT,
    guest_contact TEXT,
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

# account/karma/wallet/other: a logged-in member's own query about their account (the original
# 2026-10-18 scope). query/complaint/proposal (2026-10-28): the public AI Support widget's own
# categories -- a different, broader classification for an anonymous visitor's ticket, not a
# replacement for the first four. account_recovery (2026-11-14): the new no-Family-Tree recovery
# fallback's own category -- see api_recovery_admin_ticket() in app.py, the only place that ever
# assigns it (never read from client input). Every one of these coexists in the same column; the
# Admin Panel's own filter buttons key off `source` (report/id_recovery/query/council/
# account_recovery), never off `category` directly, so adding these doesn't touch any existing
# filter.
CATEGORIES = ("account", "karma", "wallet", "query", "complaint", "proposal", "account_recovery", "other")
STATUSES = ("open", "answered", "closed")
VERIFICATION_STATUSES = ("pending", "verified", "rejected")
CONTACT_METHODS = ("phone", "email", "member_private_id")


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(admin_queries)")}
    for col in ("date_of_birth", "present_location_json", "contact_method", "verification_status", "verification_notes"):
        if col not in cols:
            conn.execute(f"ALTER TABLE admin_queries ADD COLUMN {col} TEXT")
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create(conn, user_id: int | None, category: str, subject: str, body: str,
           guest_name: str | None = None, guest_contact: str | None = None,
           date_of_birth: str | None = None, present_location: dict | None = None,
           contact_method: str | None = None) -> int:
    """user_id is None for an anonymous AI Support ticket (POST /api/support/ticket) or an
    account_recovery ticket (POST /api/recovery/admin-ticket) -- guest_name is then required
    (something to show the Admin instead of a real account's name) and guest_contact is optional
    for a plain query (an email reply_core can send the Admin's reply to, or a Private ID the
    visitor already has) but REQUIRED for account_recovery, where it holds the exact value named
    by contact_method. Either way guest_contact is never validated as a real account here, only
    stored and shown as-is -- see api_support_ticket()/api_recovery_admin_ticket() in app.py for
    the callers that distinguish what shape it actually is.

    date_of_birth/present_location/contact_method are account_recovery-only (None for every other
    category's call site, unchanged) -- present_location is stored as JSON, the same
    present_location_json convention users.present_location_json already uses, so every existing
    location-formatting helper in this codebase reads it back unchanged."""
    ensure_tables(conn)
    category = category if category in CATEGORIES else "other"
    subject = (subject or "").strip()
    body = (body or "").strip()
    guest_name = (guest_name or "").strip() or None
    guest_contact = (guest_contact or "").strip() or None
    if not subject or not body:
        raise ValueError("Subject and message are required")
    if user_id is None and not guest_name:
        raise ValueError("Your name is required")
    present_location_json = json.dumps(present_location) if present_location is not None else None
    verification_status = "pending" if category == "account_recovery" else None
    cur = conn.execute(
        """INSERT INTO admin_queries
           (user_id, guest_name, guest_contact, category, subject, body, status,
            date_of_birth, present_location_json, contact_method, verification_status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)""",
        (user_id, guest_name, guest_contact, category, subject, body,
         date_of_birth, present_location_json, contact_method, verification_status, _now()),
    )
    conn.commit()
    return cur.lastrowid


def set_verification(conn, query_id: int, status: str, notes: str | None, admin_user_id: int) -> None:
    """Records the Admin's identity-verification decision for an account_recovery ticket --
    DELIBERATELY separate from reply()/close() below, which only ever touch the ticket's own
    `status` (has an Admin responded/closed this), never this column (is this person who they
    claim to be). `notes` is Admin-internal only; api_account_recovery_detail() in app.py is the
    only reader, and only for a global-admin caller -- never returned to the requester's own,
    unauthenticated status/reference lookup, because there isn't one (account_recovery tickets
    have no public status-check route at all, unlike the Family-Tree recovery flow's tracking
    code -- see this feature's own API contract in docs/phone_app_api.md for why)."""
    query = get(conn, query_id)
    if not query or query["category"] != "account_recovery":
        raise LookupError("Account recovery ticket not found")
    if status not in VERIFICATION_STATUSES:
        raise ValueError("Unknown verification status")
    conn.execute(
        "UPDATE admin_queries SET verification_status = ?, verification_notes = ? WHERE id = ?",
        (status, (notes or "").strip() or None, query_id),
    )
    conn.commit()


def append_verification_note(conn, query_id: int, line: str) -> None:
    """Appends one timestamped, append-only line to verification_notes -- how a completed
    recovery action (a Private ID reveal, a temporary PIN generation) is recorded against this
    ticket, WITHOUT a dedicated column duplicating what id_recovery_reveals (for a reveal) or the
    PIN change itself already records elsewhere, and WITHOUT ever writing the revealed Private ID
    or the generated PIN into this text -- callers of this function must never pass either."""
    query = get(conn, query_id)
    if not query or query["category"] != "account_recovery":
        raise LookupError("Account recovery ticket not found")
    existing = query["verification_notes"] or ""
    stamped = f"{_now()}: {line.strip()}"
    combined = (existing + "\n" + stamped) if existing else stamped
    conn.execute("UPDATE admin_queries SET verification_notes = ? WHERE id = ?", (combined, query_id))
    conn.commit()


def get(conn, query_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM admin_queries WHERE id = ?", (query_id,)).fetchone()
    return dict(r) if r else None


def list_mine(conn, user_id: int) -> list[dict]:
    rows = conn.execute("SELECT * FROM admin_queries WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def get_for_member(conn, user_id: int, query_id: int) -> dict | None:
    """The asking member's own view of one query: the original and the text and time of each
    reply, nothing else -- not who on the admin side replied, and not the status history. None
    if the query doesn't exist OR belongs to someone else; the two are deliberately the same to
    the caller, the same posture as the council routes' 404."""
    ensure_tables(conn)
    q = conn.execute(
        "SELECT id, category, subject, body, created_at FROM admin_queries WHERE id = ? AND user_id = ?",
        (query_id, user_id),
    ).fetchone()
    if not q:
        return None
    result = dict(q)
    result["replies"] = [
        dict(r) for r in conn.execute(
            "SELECT message, created_at FROM admin_query_replies WHERE query_id = ? ORDER BY created_at, id",
            (query_id,),
        ).fetchall()
    ]
    return result


def list_open(conn) -> list[dict]:
    """Every query that isn't closed, newest first -- the Admin Panel feed's source for this
    ticket type. Includes the asking user's name and their latest reply timestamp (if any) so the
    combined feed can render a preview without an N+1 query per ticket.

    2026-10-28: LEFT JOIN, not the original INNER JOIN -- an anonymous AI Support ticket has
    user_id = NULL, and an INNER JOIN against users would silently drop that row from the feed
    entirely (no matching users row, no result row), not just show it without a name. author_name
    falls back to guest_name for those; author_has_picture/author_profile_picture_url are always
    None/False for a guest (there's no users row to have a picture)."""
    ensure_tables(conn)
    rows = conn.execute(
        """SELECT q.*, COALESCE(u.name, q.guest_name) AS author_name, u.gender AS author_gender,
                  COALESCE(u.profile_picture IS NOT NULL, 0) AS author_has_picture,
                  (SELECT MAX(created_at) FROM admin_query_replies r WHERE r.query_id = q.id) AS last_reply_at
           FROM admin_queries q LEFT JOIN users u ON u.id = q.user_id
           WHERE q.status != 'closed' ORDER BY q.created_at DESC"""
    ).fetchall()
    return [_with_author_picture(dict(r), "user_id") for r in rows]


def _with_author_picture(d: dict, author_id_key: str) -> dict:
    """Converts the `author_has_picture` boolean every query/reply row carries into the one URL
    form every QMAvatar.render() caller uses -- same pattern as family_core._profile_picture_url()."""
    d["author_profile_picture_url"] = f"/api/users/{d[author_id_key]}/profile-picture" if d.pop("author_has_picture") else None
    return d


def replies_for(conn, query_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT r.*, u.name AS author_name, u.gender AS author_gender,
                  u.profile_picture IS NOT NULL AS author_has_picture
           FROM admin_query_replies r
           JOIN users u ON u.id = r.author_user_id WHERE r.query_id = ? ORDER BY r.created_at ASC""",
        (query_id,),
    ).fetchall()
    return [_with_author_picture(dict(r), "author_user_id") for r in rows]


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
