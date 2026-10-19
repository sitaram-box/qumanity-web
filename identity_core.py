"""Identity-correction tickets and the birth-time-unknown flag (2026-10-19).

Extends profile_change_requests (app.py) rather than building a parallel table -- reusing
FOUNDATIONAL_FIELDS / _recompute_profile() / api_admin_profile_decide() instead of duplicating
them. Adds three ticket types a user cannot resolve themselves, each routed to their BIRTH
village's council instead of straight to a Qmail reply:

  - id_change_a: birth location was wrong at registration. Corrects birth_location (which already
    cascades into zodiac/Kundali/elemental recompute via app.py's _recompute_profile) and, since
    the old 9-digit Private ID was issued under the wrong identity/location pairing, also re-rolls
    private_id_9digit.
  - id_change_b: the 9-digit Private ID is compromised or shared. Location is untouched; only
    private_id_9digit is re-rolled.
  - birth_time_correction: the user registered with "I don't remember my exact birth time"
    (users.birth_time_known = 0, tob defaulted to noon) and now has a real time to provide.

Two facts, confirmed by reading the code rather than assumed, govern how this module touches
(or doesn't touch) everything else:

  1. private_id_9digit is pure-random (id_generator.generate_private_code -> secrets.randbelow)
     and carries no relationship to birth_location, present_location, or account_id. account_id
     is present_location-derived (id_generator.generate_account_id), and Qmail's full address
     embeds account_id, not private_id_9digit (qmail_core.build_full_address). So regenerating
     private_id_9digit alone -- id_change_b, or the ID half of id_change_a -- never needs a
     Qmail resync. Only an approved present_location change does, and that already goes through
     social_core.regenerate_account_id(), untouched by this module.
  2. Every table keyed to a member's identity in this codebase -- board_posts.author_id,
     board_comments.user_id, wallets.owner_id, karma_entries.user_id, personal_group_members/
     private_chats/people_requests.user_id, qmail_messages.from_user_id/to_user_id,
     qoins (via wallets.id), recognition_stars.author_id -- uses users.id, the internal primary
     key, never private_id/private_id_9digit/account_id. Confirmed by grepping every CREATE
     TABLE in the codebase for such a foreign key and finding none. Regenerating either ID is a
     label change only; nothing listed above is touched, moved, or re-keyed by this module.
"""
from __future__ import annotations

import datetime as dt
import json

import id_generator
import qmail_core

REQUEST_TYPES = ("id_change_a", "id_change_b", "birth_time_correction")
MAX_ATTACHMENT_BYTES = qmail_core.MAX_ATTACHMENT_BYTES


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def ensure_tables(conn) -> None:
    """Additive-only. Assumes profile_change_requests already exists (app.py's
    _ensure_profile_change_table runs CREATE TABLE IF NOT EXISTS on it first, every time, before
    calling here) -- this only adds the columns/table this module introduces."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(profile_change_requests)")}
    if "request_type" not in cols:
        conn.execute("ALTER TABLE profile_change_requests ADD COLUMN request_type TEXT NOT NULL DEFAULT 'edit'")
    if "location_level" not in cols:
        conn.execute("ALTER TABLE profile_change_requests ADD COLUMN location_level TEXT")
    if "location_id" not in cols:
        conn.execute("ALTER TABLE profile_change_requests ADD COLUMN location_id TEXT")

    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "birth_time_known" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN birth_time_known INTEGER NOT NULL DEFAULT 1")

    conn.execute("""CREATE TABLE IF NOT EXISTS profile_change_attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        uploader_user_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        content_type TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        data BLOB NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (request_id) REFERENCES profile_change_requests(id)
    )""")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_profile_change_attachments_request "
        "ON profile_change_attachments(request_id)"
    )
    conn.commit()


def _birth_village_location(conn, user_id: int):
    """The user's CURRENT birth village, snapshotted onto the ticket at submission time -- so a
    queued ticket keeps pointing at the village whose council should decide it, even if some
    other approved change moves the user's birth_location before this one is decided. Returns
    (None, None) if their birth location has no mapped village (e.g. born outside the Indian
    Sub-continent) -- such a ticket is global-Admin-only, by omission: _is_admin_panel_user()'s
    location scope can never match a NULL location_level/location_id."""
    row = conn.execute("SELECT birth_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return None, None
    village = (json.loads(row["birth_location_json"]) or {}).get("village")
    if village and village.get("id"):
        return "village", village["id"]
    return None, None


def submit_request(conn, user_id: int, request_type: str, fields: dict, reason: str, cycle_id=None) -> int:
    """Queues a ticket for the user's birth village council (or the Founder/Admin, if the birth
    location has no mapped village). Raises ValueError for an unknown request_type. Returns the
    new request's id."""
    if request_type not in REQUEST_TYPES:
        raise ValueError(f"Unknown request_type: {request_type}")
    location_level, location_id = _birth_village_location(conn, user_id)
    cur = conn.execute(
        """INSERT INTO profile_change_requests
           (user_id, fields_json, reason, request_type, location_level, location_id, cycle_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, json.dumps(fields), reason or "", request_type, location_level, location_id, cycle_id),
    )
    conn.commit()
    return cur.lastrowid


def regenerate_private_code(conn, user_id: int) -> str:
    """Re-rolls the 9-digit login credential. Does not touch account_id, Qmail, or any other
    column -- see this module's docstring for why that's safe. Returns the new code; the caller
    is responsible for getting it to the user out of band (it is never logged here)."""
    new_code = id_generator.generate_private_code(conn)
    conn.execute("UPDATE users SET private_id_9digit = ? WHERE id = ?", (new_code, user_id))
    conn.commit()
    return new_code


def save_attachment(conn, request_id: int, uploader_user_id: int, filename: str,
                     content_type: str, data: bytes) -> int:
    """Same 2MB cap and extension/content-type allowlist as Qmail's attachments (qmail_core.py) --
    reused directly, not duplicated, so the two can never silently drift apart. Raises ValueError
    if `data` exceeds MAX_ATTACHMENT_BYTES, or qmail_core.AttachmentTypeError if the file type
    isn't allowed."""
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"Attachment exceeds the {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB limit")
    content_type = qmail_core.allowed_attachment_type(filename, content_type)
    cur = conn.execute(
        """INSERT INTO profile_change_attachments
           (request_id, uploader_user_id, filename, content_type, byte_size, data, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (request_id, uploader_user_id, filename, content_type, len(data), data, _now()),
    )
    conn.commit()
    return cur.lastrowid


def attachments_for(conn, request_id: int) -> list[dict]:
    """Metadata only (no `data`) -- same split as qmail_core.attachments_for()."""
    rows = conn.execute(
        "SELECT id, filename, content_type, byte_size, created_at FROM profile_change_attachments "
        "WHERE request_id = ?", (request_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_attachment(conn, attachment_id: int):
    """The full row, including `data` -- only the serve route should call this, after it has
    independently confirmed the requester may see the ticket this attachment belongs to."""
    return conn.execute(
        "SELECT * FROM profile_change_attachments WHERE id = ?", (attachment_id,)
    ).fetchone()
