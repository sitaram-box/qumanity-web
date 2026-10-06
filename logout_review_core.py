"""Item 10: the Logout rating/review gate. One optional 1-5 star rating +
free-text review per user PER LUNAR CYCLE (lunar_calendar.get_current_cycle_id()).
Submitting hides the gate for the rest of the cycle; Skip does not save a row,
so the rating screen reappears on the next logout this cycle until the user
actually submits -- see has_reviewed() / save_review().

Not the same system as review_core.py / app_reviews: that one is a single,
ONE-TIME rating tied to finishing/skipping the onboarding tour (user_id is
UNIQUE there -- one row ever). This one is per-cycle by design (user_id,
cycle_id) can repeat across cycles -- so the two tables and the two
*_core modules are intentionally separate, not a duplicate."""
from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    rating INTEGER,
    review TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, cycle_id)
);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def has_reviewed(conn, user_id, cycle_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM user_reviews WHERE user_id = ? AND cycle_id = ?", (str(user_id), cycle_id)
    ).fetchone()
    return row is not None


def save_review(conn, user_id, cycle_id: str, rating: int | None, review: str | None) -> None:
    """Idempotent: a second call for the same (user_id, cycle_id) -- e.g. a double-click or a
    retried request -- quietly overwrites rather than erroring on the UNIQUE constraint."""
    conn.execute(
        """INSERT INTO user_reviews (user_id, cycle_id, rating, review)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, cycle_id) DO UPDATE SET rating = excluded.rating, review = excluded.review""",
        (str(user_id), cycle_id, rating, review),
    )
    conn.commit()


def admin_summary(conn, cycle_id: str) -> dict:
    rows = conn.execute(
        """SELECT ur.id, ur.user_id, u.name, ur.rating, ur.review, ur.created_at
           FROM user_reviews ur LEFT JOIN users u ON u.id = ur.user_id
           WHERE ur.cycle_id = ? ORDER BY ur.created_at DESC""",
        (cycle_id,),
    ).fetchall()
    rated = [r["rating"] for r in rows if r["rating"] is not None]
    rating_avg = round(sum(rated) / len(rated), 2) if rated else None
    return {
        "cycle_id": cycle_id,
        "count": len(rows),
        "rating_avg": rating_avg,
        "reviews": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "name": r["name"],
                "rating": r["rating"],
                "review": r["review"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }
