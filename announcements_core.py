"""Item 8: Announcements. One-way messages a location's council member (or the Founder/Admin,
always) publishes to everyone in that location -- shown in the location's sidebar, pinned atop
its [Level] Lok panel, and surfaced via a dedicated unread-count/dropdown in the dashboard header.

Council membership only exists at village level today (village_council -- one male/female head
per village per zodiac-month term, see election_core.py). Every other level has no elected-council
data model yet, so publishing there always falls back to Founder/Admin only (app.py logs a note
each time that fallback is the *only* reason a publish succeeded, so usage is visible once higher
levels get real councils)."""
from __future__ import annotations

import datetime as dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,   -- earth|continent|country|zone|state|district|tehsil|village
    author_user_id TEXT NOT NULL,
    title TEXT,
    body TEXT NOT NULL,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_ann_location ON announcements(location_id, created_at DESC);

CREATE TABLE IF NOT EXISTS announcement_reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    announcement_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(announcement_id, user_id),
    FOREIGN KEY (announcement_id) REFERENCES announcements(id)
);
"""

LEVELS = ("earth", "continent", "country", "zone", "state", "district", "tehsil", "village")


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_council_member(conn, user_id, location_id, location_level: str) -> bool:
    """Village only -- see module docstring. Every other level has no elected-council data
    model yet and always returns False (the route falls back to admin-only there)."""
    if location_level != "village":
        return False
    today = dt.date.today().isoformat()
    row = conn.execute(
        """SELECT 1 FROM village_council
           WHERE village_id = ? AND leadership_start <= ? AND leadership_end >= ?
             AND (male_head_user_id = ? OR female_head_user_id = ?)""",
        (location_id, today, today, str(user_id), str(user_id)),
    ).fetchone()
    return row is not None


def can_publish_announcement(conn, user_id, location_id, location_level, is_admin: bool) -> bool:
    """Admin/Founder always can (passed in -- _is_admin() reads the Flask session and belongs in
    app.py, not here, same pattern as board_core.send_message's own is_admin parameter). Otherwise
    only an active village council member, and only at village level -- see is_council_member()."""
    if is_admin:
        return True
    return is_council_member(conn, user_id, location_id, location_level)


def create(conn, author_user_id, location_id, location_level, title, body, image_url=None) -> int:
    cur = conn.execute(
        """INSERT INTO announcements (location_id, location_level, author_user_id, title, body, image_url)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (location_id, location_level, str(author_user_id), title or None, body, image_url or None),
    )
    conn.commit()
    return cur.lastrowid


def list_for_location(conn, user_id, location_level, location_id, limit=20) -> list[dict]:
    rows = conn.execute(
        """SELECT a.id, a.title, a.body, a.image_url, a.created_at, u.name AS author_name,
                  (ar.id IS NOT NULL) AS is_read
           FROM announcements a
           JOIN users u ON u.id = a.author_user_id
           LEFT JOIN announcement_reads ar ON ar.announcement_id = a.id AND ar.user_id = ?
           WHERE a.location_id = ? AND a.location_level = ? AND a.is_active = 1
           ORDER BY a.created_at DESC LIMIT ?""",
        (str(user_id), location_id, location_level, limit),
    ).fetchall()
    return [
        {
            "id": r["id"], "title": r["title"], "body": r["body"], "image_url": r["image_url"],
            "created_at": r["created_at"], "author_name": r["author_name"], "is_read": bool(r["is_read"]),
        }
        for r in rows
    ]


def mark_read(conn, user_id, announcement_id) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO announcement_reads (announcement_id, user_id) VALUES (?, ?)",
        (announcement_id, str(user_id)),
    )
    conn.commit()


def unread_count(conn, user_id, location_chain: list[tuple[str, str]]) -> int:
    """location_chain: the user's own lineage, e.g. [('earth', 'EARTH'), ('continent', 'AS'),
    ('country', 'O_AS_IND'), ('zone', 'IND/CS'), ('state', 'CS.DL'), ...] -- only the levels the
    user actually has (a user outside the Indian sub-continent has no zone..village entries)."""
    if not location_chain:
        return 0
    where = " OR ".join(["(a.location_level = ? AND a.location_id = ?)"] * len(location_chain))
    params = [v for pair in location_chain for v in pair]
    row = conn.execute(
        f"""SELECT COUNT(*) FROM announcements a
            WHERE a.is_active = 1 AND ({where})
              AND NOT EXISTS (SELECT 1 FROM announcement_reads ar WHERE ar.announcement_id = a.id AND ar.user_id = ?)""",
        params + [str(user_id)],
    ).fetchone()
    return row[0]


def unread_recent(conn, user_id, location_chain: list[tuple[str, str]], limit=5) -> list[dict]:
    if not location_chain:
        return []
    where = " OR ".join(["(a.location_level = ? AND a.location_id = ?)"] * len(location_chain))
    params = [v for pair in location_chain for v in pair]
    rows = conn.execute(
        f"""SELECT a.id, a.title, a.body, a.location_level, a.location_id, a.created_at, u.name AS author_name
            FROM announcements a
            JOIN users u ON u.id = a.author_user_id
            WHERE a.is_active = 1 AND ({where})
              AND NOT EXISTS (SELECT 1 FROM announcement_reads ar WHERE ar.announcement_id = a.id AND ar.user_id = ?)
            ORDER BY a.created_at DESC LIMIT ?""",
        params + [str(user_id), limit],
    ).fetchall()
    return [
        {
            "id": r["id"], "title": r["title"], "body": r["body"], "location_level": r["location_level"],
            "location_id": r["location_id"], "created_at": r["created_at"], "author_name": r["author_name"],
        }
        for r in rows
    ]
