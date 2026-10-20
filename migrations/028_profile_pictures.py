"""Adds users.profile_picture and users.profile_picture_updated_at (2026-10-20), needed for the
Private Account profile-picture upload and for showing a real avatar on family-tree cards and
search results instead of only a colored initial. The picture is stored as a BLOB directly on
the row -- same precedent as qmail_attachments (migration 023) and profile_change_attachments
(identity_core.py) -- so it survives a Railway redeploy without a separately-configured disk
mount. Both columns default to NULL -- every existing user, on every database this runs against,
has no picture until they upload one.
"""
from __future__ import annotations

def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "profile_picture" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN profile_picture BLOB")
    if "profile_picture_updated_at" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN profile_picture_updated_at TEXT")
    conn.commit()
    print("    users.profile_picture / users.profile_picture_updated_at ready (both default NULL).")
