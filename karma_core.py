"""Karma: a Social Credit / accountability score — never money, and never automatically converted
to or from Qoins (the spendable currency). Two kinds, per the Founder's decision (2026-09-29):

- **Commercial** individual karma: earned only from a customer's rating of a real, local (present-
  village) business transaction (a `business`-category personal_groups). A very good rating
  (4-5 stars) earns karma for the provider; a poor one can cost them karma too — this module only
  tracks the karma side of that transaction, never the Qoins the business itself might charge.
- **Non-commercial** individual karma: a person's own good work with no paid transaction behind
  it — for now, wired to a village-level Collective Board post that freezes with a positive score
  (the same moment that already earns the author Qoins, in board_core.py).

**Collective karma** is not owned by a person: it's a running score per LOCATION (village up to
Earth), bumped by the collective's own recognised actions — a Tehsil-and-above Collective Board
post freezing positively (the village's own post already counts as *individual* karma above, so a
post that has risen past the village is being credited to the wider group it now represents).
Shown on every Public/Global location page, not on a private profile.

"Karma Score + Qoins together" as a reward is documented in the Founder's own words as a future
*possibility*, not a formula — nothing here computes or credits Qoins.
"""
from __future__ import annotations

import datetime as dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS karma_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,             -- 'commercial' | 'noncommercial'
    points INTEGER NOT NULL,
    reason TEXT NOT NULL,
    from_user_id INTEGER,           -- the rater, for a 'commercial' entry; NULL otherwise
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_karma_entries_user ON karma_entries(user_id);

CREATE TABLE IF NOT EXISTS collective_karma (
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,   -- village | tehsil | district | state | zone | country | continent | earth
    points INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (location_id, location_level)
);
CREATE TABLE IF NOT EXISTS collective_karma_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    location_level TEXT NOT NULL,
    points INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- One business (a 'business'-category personal_groups row) rated by one customer; ratings can be
-- updated (a person's opinion of a business can change), and each update re-scores the karma delta.
CREATE TABLE IF NOT EXISTS business_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    rater_user_id INTEGER NOT NULL,
    provider_user_id INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(group_id, rater_user_id)
);
"""

# A very good rating (4-5 stars) is the only case the Founder described as earning karma; a poor
# one (1-2 stars) is treated symmetrically as an accountability cost, and an average one (3) is
# neutral -- reasonable given "Social Credit / accountability score" is the module's whole point.
STAR_KARMA = {5: 15, 4: 8, 3: 0, 2: -5, 1: -15}


def ensure_tables(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ---- Individual karma ----

def add_individual_karma(conn, user_id: int, kind: str, points: int, reason: str, from_user_id: int | None = None) -> None:
    if kind not in ("commercial", "noncommercial"):
        raise ValueError("Unknown karma kind")
    ensure_tables(conn)
    conn.execute(
        "INSERT INTO karma_entries (user_id, kind, points, reason, from_user_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, kind, points, reason, from_user_id, _now()),
    )
    conn.commit()


def individual_karma_score(conn, user_id: int) -> dict:
    ensure_tables(conn)
    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN kind = 'commercial' THEN points END), 0) AS commercial,
             COALESCE(SUM(CASE WHEN kind = 'noncommercial' THEN points END), 0) AS noncommercial,
             COALESCE(SUM(points), 0) AS total
           FROM karma_entries WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    return {"commercial": row["commercial"], "noncommercial": row["noncommercial"], "total": row["total"]}


def individual_karma_history(conn, user_id: int, limit: int = 50) -> list[dict]:
    ensure_tables(conn)
    rows = conn.execute(
        """SELECT k.kind, k.points, k.reason, k.created_at, u.name AS from_name
           FROM karma_entries k LEFT JOIN users u ON u.id = k.from_user_id
           WHERE k.user_id = ? ORDER BY k.id DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Collective karma (per location, not per person) ----

def bump_collective_karma(conn, location_id: str, location_level: str, points: int, reason: str) -> None:
    ensure_tables(conn)
    conn.execute(
        """INSERT INTO collective_karma (location_id, location_level, points, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(location_id, location_level) DO UPDATE SET points = points + excluded.points, updated_at = excluded.updated_at""",
        (location_id, location_level, points, _now()),
    )
    conn.execute(
        "INSERT INTO collective_karma_log (location_id, location_level, points, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (location_id, location_level, points, reason, _now()),
    )
    conn.commit()


def collective_karma_score(conn, location_id: str, location_level: str) -> int:
    ensure_tables(conn)
    row = conn.execute(
        "SELECT points FROM collective_karma WHERE location_id = ? AND location_level = ?",
        (location_id, location_level),
    ).fetchone()
    return row["points"] if row else 0


# ---- Commercial karma: rating a village-level business ----

def rate_business(conn, rater_user_id: int, group_id: int, stars: int, comment: str | None) -> dict:
    ensure_tables(conn)
    if not 1 <= int(stars) <= 5:
        raise ValueError("Rate a business 1 to 5 stars")
    import json

    group = conn.execute("SELECT * FROM personal_groups WHERE id = ?", (group_id,)).fetchone()
    if not group:
        raise LookupError("Business not found")
    if group["category"] != "business":
        raise ValueError("Only business groups can be rated")
    provider_id = group["owner_user_id"]
    if provider_id == rater_user_id:
        raise ValueError("You can't rate your own business")

    rater = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (rater_user_id,)).fetchone()
    provider = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (provider_id,)).fetchone()
    if not rater or not provider:
        raise LookupError("User not found")
    rater_village = (json.loads(rater["present_location_json"]).get("village") or {}).get("id")
    provider_village = (json.loads(provider["present_location_json"]).get("village") or {}).get("id")
    if not rater_village or rater_village != provider_village:
        raise PermissionError("Commercial karma is only for a business in your own present village")

    stars = int(stars)
    points = STAR_KARMA[stars]
    existing = conn.execute(
        "SELECT stars FROM business_ratings WHERE group_id = ? AND rater_user_id = ?", (group_id, rater_user_id)
    ).fetchone()
    if existing:
        # replace the old karma delta with the new one, so re-rating doesn't double-count
        old_points = STAR_KARMA[existing["stars"]]
        conn.execute(
            "UPDATE business_ratings SET stars = ?, comment = ?, updated_at = ? WHERE group_id = ? AND rater_user_id = ?",
            (stars, (comment or "").strip()[:500], _now(), group_id, rater_user_id),
        )
        delta = points - old_points
        if delta:
            add_individual_karma(conn, provider_id, "commercial", delta, f"Rating updated to {stars}★ ({group['name']})", rater_user_id)
    else:
        conn.execute(
            "INSERT INTO business_ratings (group_id, rater_user_id, provider_user_id, stars, comment, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (group_id, rater_user_id, provider_id, stars, (comment or "").strip()[:500], _now(), _now()),
        )
        if points:
            add_individual_karma(conn, provider_id, "commercial", points, f"Rated {stars}★ ({group['name']})", rater_user_id)
    conn.commit()
    return {"status": "ok", "stars": stars, "points_awarded": points}


def business_ratings(conn, group_id: int) -> list[dict]:
    ensure_tables(conn)
    rows = conn.execute(
        """SELECT br.stars, br.comment, br.created_at, u.name AS rater_name
           FROM business_ratings br JOIN users u ON u.id = br.rater_user_id
           WHERE br.group_id = ? ORDER BY br.id DESC""",
        (group_id,),
    ).fetchall()
    return [dict(r) for r in rows]
