"""App tour status and the one-time member rating & review.

Every member sees the app tour once (they may skip it). Whether they finish or skip, they get ONE
chance to rate Qumanity out of 5 stars and leave a short review (max 100 characters); saying
"No thanks" also uses that chance. A review is shown publicly (for marketing) only when the member
allowed it AND an admin approved it; the public list shows first name and village, never IDs.
"""
from __future__ import annotations

import datetime as dt
import json

MAX_REVIEW_CHARS = 100
TOUR_STATES = ("done", "skipped")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_onboarding (
    user_id INTEGER PRIMARY KEY,
    tour_status TEXT,
    tour_at TEXT,
    review_prompt_done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS app_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    text TEXT NOT NULL DEFAULT '',
    allow_public INTEGER NOT NULL DEFAULT 0,
    approved INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'app',
    created_at TEXT NOT NULL
);
"""


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def status(conn, user_id):
    row = conn.execute("SELECT tour_status, review_prompt_done FROM user_onboarding WHERE user_id = ?", (user_id,)).fetchone()
    return {"tour": row["tour_status"] if row else None, "review_done": bool(row and row["review_prompt_done"])}


def _upsert(conn, user_id):
    conn.execute("INSERT OR IGNORE INTO user_onboarding (user_id) VALUES (?)", (user_id,))


def set_tour(conn, user_id, state):
    if state not in TOUR_STATES:
        raise ValueError("Tour status must be 'done' or 'skipped'")
    _upsert(conn, user_id)
    conn.execute("UPDATE user_onboarding SET tour_status = ?, tour_at = ? WHERE user_id = ?", (state, _now(), user_id))
    conn.commit()


def submit_review(conn, user_id, rating, text, allow_public, source="app"):
    """The member's one review. Raises PermissionError if they already used their one chance."""
    if status(conn, user_id)["review_done"]:
        raise PermissionError("You have already shared your rating — thank you!")
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise ValueError("Choose 1 to 5 stars")
    if not 1 <= rating <= 5:
        raise ValueError("Choose 1 to 5 stars")
    text = " ".join((text or "").split())
    if len(text) > MAX_REVIEW_CHARS:
        raise ValueError(f"Keep your review within {MAX_REVIEW_CHARS} characters")
    conn.execute(
        "INSERT INTO app_reviews (user_id, rating, text, allow_public, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, rating, text, 1 if allow_public else 0, source, _now()),
    )
    _upsert(conn, user_id)
    conn.execute("UPDATE user_onboarding SET review_prompt_done = 1 WHERE user_id = ?", (user_id,))
    conn.commit()


def decline_review(conn, user_id):
    """'No thanks' — the one chance is used without a review."""
    _upsert(conn, user_id)
    conn.execute("UPDATE user_onboarding SET review_prompt_done = 1 WHERE user_id = ?", (user_id,))
    conn.commit()


def _public_name(name, present_location_json):
    first = (name or "").split()[0] if (name or "").split() else "Member"
    try:
        loc = json.loads(present_location_json or "{}")
    except ValueError:
        loc = {}
    place = (loc.get("village") or {}).get("name") or (loc.get("country") or {}).get("name") or ""
    return first, place


def public_reviews(conn, limit=20):
    """Average rating over ALL reviews, plus the approved public ones (newest first) for marketing."""
    agg = conn.execute("SELECT COUNT(*) AS n, AVG(rating) AS avg FROM app_reviews").fetchone()
    rows = conn.execute(
        """SELECT r.rating, r.text, r.created_at, u.name, u.present_location_json
           FROM app_reviews r JOIN users u ON u.id = r.user_id
           WHERE r.allow_public = 1 AND r.approved = 1 AND r.text != ''
           ORDER BY r.created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        first, place = _public_name(r["name"], r["present_location_json"])
        out.append({"rating": r["rating"], "text": r["text"], "name": first, "place": place, "at": r["created_at"]})
    return {"count": agg["n"], "average": round(agg["avg"], 1) if agg["avg"] else None, "reviews": out}


def all_reviews(conn):
    """Admin view: every review, with whether the member allowed public display."""
    rows = conn.execute(
        """SELECT r.id, r.rating, r.text, r.allow_public, r.approved, r.source, r.created_at, u.name, u.present_location_json
           FROM app_reviews r JOIN users u ON u.id = r.user_id ORDER BY r.created_at DESC"""
    ).fetchall()
    out = []
    for r in rows:
        first, place = _public_name(r["name"], r["present_location_json"])
        out.append({"id": r["id"], "rating": r["rating"], "text": r["text"], "allow_public": bool(r["allow_public"]),
                    "approved": bool(r["approved"]), "source": r["source"], "at": r["created_at"], "name": first, "place": place})
    return out


def set_approved(conn, review_id, approved):
    row = conn.execute("SELECT allow_public FROM app_reviews WHERE id = ?", (review_id,)).fetchone()
    if not row:
        raise LookupError("Review not found")
    if approved and not row["allow_public"]:
        raise PermissionError("This member did not allow public display")
    conn.execute("UPDATE app_reviews SET approved = ? WHERE id = ?", (1 if approved else 0, review_id))
    conn.commit()
