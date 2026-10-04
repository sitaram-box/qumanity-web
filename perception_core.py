"""Perception Calculator: annual Pro/Anti sentiment voting, kept deliberately separate from the
existing private Election History feature (`election_core.py`'s `election_history_entries`) --
that one is filled out privately and only ever shown back to the same user; this one is cast
straight onto a Public page and its aggregate is what everyone sees there (Founder, 2026-09-29).

Two kinds, matching the Founder's own UI scoping (2026-09-29 answer): "It is only available on
India country and zone pages. For other 9 countries have only country perception option." -- so:

- **Country Perception** ("Global Sentiment" in the original spec): any of the 10 Sub-continent
  countries (`app.SUBCONTINENT_COUNTRY_IDS`), open to any user except on their OWN birth country.
- **Zone Perception**: India's own zones only, open to any user except on their OWN birth zone.

The original spec also described a State-level table; the Founder's own scoping answer mentions
only "country and Zone" pages, so State Perception is dropped from this build (not because it's
wrong, just not asked for at this pass).

Eligibility is always based on **birth** location (`users.birth_location_json`), never present
location -- "Even if a user temporarily lives abroad, their voting rights remain tied to their
birth location" (spec, verbatim).

## The annual cycle

- **Voting window**: Oct 1 - Dec 31 of a "voting_year" Y. Votes are hidden (no aggregate is shown)
  while this window is open.
- **Freeze**: the moment Jan 1 (Y+1) is reached, Y's votes are tallied once into `..._stats` and
  never recomputed from raw votes again (this is compute-on-read, like `election_core._ensure_tallied`
  -- no cron job needed).
- **Display**: the most recently frozen year's results are what's shown, for the ENTIRE following
  calendar year -- i.e. on any given date, `displayed_year = today.year - 1`. That is continuously
  true through Jan-Sep (the spec's literal "displayed Jan 1-Sep 30") AND through Oct-Dec of the same
  year, even though a brand new voting window (for voting_year = today.year) is open right then --
  "a new cycle opens Oct 1 while old results keep displaying until next Jan 1", exactly as specified.
- **One vote per person per voting_year**: once a user has cast a vote for a given
  country/zone + voting_year, they cannot cast a second one that year (the spec's "one vote change
  per year" is read here as one write per year, not unlimited toggling).
"""
from __future__ import annotations

import datetime as dt
import json

import cycle_middleware

SUBCONTINENT_COUNTRY_IDS = (
    "O_AS_IND", "O_AS_NPL", "O_AS_BTN", "O_AS_BGD", "O_AS_MMR",
    "O_AS_LKA", "O_AS_PAK", "O_AS_BLC", "O_AS_AFG", "O_AS_MDV",
)
INDIA_COUNTRY_ID = "O_AS_IND"

SCHEMA = """
CREATE TABLE IF NOT EXISTS country_sentiment (
    user_id INTEGER NOT NULL,
    country_id TEXT NOT NULL,
    voting_year INTEGER NOT NULL,
    vote TEXT NOT NULL,             -- 'pro' | 'anti'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, country_id, voting_year)
);
CREATE TABLE IF NOT EXISTS country_sentiment_stats (
    country_id TEXT NOT NULL,
    voting_year INTEGER NOT NULL,
    pro_count INTEGER NOT NULL DEFAULT 0,
    anti_count INTEGER NOT NULL DEFAULT 0,
    frozen_at TEXT NOT NULL,
    PRIMARY KEY (country_id, voting_year)
);

CREATE TABLE IF NOT EXISTS zone_sentiment (
    user_id INTEGER NOT NULL,
    zone_id TEXT NOT NULL,
    voting_year INTEGER NOT NULL,
    vote TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, zone_id, voting_year)
);
CREATE TABLE IF NOT EXISTS zone_sentiment_stats (
    zone_id TEXT NOT NULL,
    voting_year INTEGER NOT NULL,
    pro_count INTEGER NOT NULL DEFAULT 0,
    anti_count INTEGER NOT NULL DEFAULT 0,
    frozen_at TEXT NOT NULL,
    PRIMARY KEY (zone_id, voting_year)
);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def current_window(today: dt.date | None = None) -> dict:
    """The Oct 1 - Dec 31 window always belongs to `today.year` (past if we're in Jan-Sep, live if
    we're in Oct-Dec, upcoming is never a distinct case since it can't be in the future within the
    same year). Results always shown are the PRIOR window's frozen stats."""
    today = today or dt.date.today()
    voting_year = today.year
    is_voting = 10 <= today.month <= 12
    return {
        "status": "voting" if is_voting else "closed",
        "voting_year": voting_year,
        "displayed_year": today.year - 1,
        "window_start": f"{voting_year}-10-01",
        "window_end": f"{voting_year}-12-31",
    }


def _birth_country_id(conn, user_id: int) -> str | None:
    row = conn.execute("SELECT birth_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or not row["birth_location_json"]:
        return None
    loc = json.loads(row["birth_location_json"])
    return (loc.get("country") or {}).get("id")


def _birth_zone_id(conn, user_id: int) -> str | None:
    row = conn.execute("SELECT birth_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row or not row["birth_location_json"]:
        return None
    loc = json.loads(row["birth_location_json"])
    return (loc.get("zone") or {}).get("id")


# ---- Country Perception ----

def cast_country_vote(conn, user_id: int, country_id: str, vote: str) -> dict:
    ensure_tables(conn)
    if country_id not in SUBCONTINENT_COUNTRY_IDS:
        raise ValueError("Perception voting is only open for the Sub-continent's 10 countries.")
    if vote not in ("pro", "anti"):
        raise ValueError("Vote must be 'pro' or 'anti'.")
    window = current_window()
    if window["status"] != "voting":
        raise ValueError("Perception voting is only open October 1 - December 31.")
    if _birth_country_id(conn, user_id) == country_id:
        raise ValueError("You can't vote Perception on your own birth country.")
    existing = conn.execute(
        "SELECT 1 FROM country_sentiment WHERE user_id = ? AND country_id = ? AND voting_year = ?",
        (user_id, country_id, window["voting_year"]),
    ).fetchone()
    if existing:
        raise ValueError("You've already cast your Perception vote for this country this year.")
    now = _now()
    conn.execute(
        """INSERT INTO country_sentiment (user_id, country_id, voting_year, vote, created_at, updated_at, cycle_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, country_id, window["voting_year"], vote, now, now, cycle_middleware.get_active_cycle_id(conn)),
    )
    conn.commit()
    return {"status": "ok", "voting_year": window["voting_year"], "vote": vote}


def _ensure_country_frozen(conn, country_id: str, voting_year: int) -> None:
    existing = conn.execute(
        "SELECT 1 FROM country_sentiment_stats WHERE country_id = ? AND voting_year = ?",
        (country_id, voting_year),
    ).fetchone()
    if existing:
        return
    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN vote = 'pro' THEN 1 ELSE 0 END), 0) AS pro_count,
             COALESCE(SUM(CASE WHEN vote = 'anti' THEN 1 ELSE 0 END), 0) AS anti_count
           FROM country_sentiment WHERE country_id = ? AND voting_year = ?""",
        (country_id, voting_year),
    ).fetchone()
    conn.execute(
        "INSERT INTO country_sentiment_stats (country_id, voting_year, pro_count, anti_count, frozen_at) VALUES (?, ?, ?, ?, ?)",
        (country_id, voting_year, row["pro_count"], row["anti_count"], _now()),
    )
    conn.commit()


def country_results(conn, country_id: str, user_id: int | None = None) -> dict:
    ensure_tables(conn)
    window = current_window()
    displayed_year = window["displayed_year"]
    _ensure_country_frozen(conn, country_id, displayed_year)
    row = conn.execute(
        "SELECT pro_count, anti_count FROM country_sentiment_stats WHERE country_id = ? AND voting_year = ?",
        (country_id, displayed_year),
    ).fetchone()
    result = {
        "country_id": country_id,
        "voting_year": displayed_year,
        "pro_count": row["pro_count"] if row else 0,
        "anti_count": row["anti_count"] if row else 0,
        "window": window,
        "my_vote": None,
        "can_vote": False,
        "vote_reason": "",
    }
    if user_id is not None:
        my_vote_row = conn.execute(
            "SELECT vote FROM country_sentiment WHERE user_id = ? AND country_id = ? AND voting_year = ?",
            (user_id, country_id, window["voting_year"]),
        ).fetchone()
        result["my_vote"] = my_vote_row["vote"] if my_vote_row else None
        if window["status"] != "voting":
            result["vote_reason"] = "Perception voting opens October 1."
        elif _birth_country_id(conn, user_id) == country_id:
            result["vote_reason"] = "You can't vote Perception on your own birth country."
        elif my_vote_row:
            result["vote_reason"] = "You've already voted this year."
        else:
            result["can_vote"] = True
    return result


# ---- Zone Perception (India only) ----

def cast_zone_vote(conn, user_id: int, zone_id: str, vote: str) -> dict:
    ensure_tables(conn)
    if vote not in ("pro", "anti"):
        raise ValueError("Vote must be 'pro' or 'anti'.")
    window = current_window()
    if window["status"] != "voting":
        raise ValueError("Perception voting is only open October 1 - December 31.")
    if _birth_zone_id(conn, user_id) == zone_id:
        raise ValueError("You can't vote Perception on your own birth zone.")
    existing = conn.execute(
        "SELECT 1 FROM zone_sentiment WHERE user_id = ? AND zone_id = ? AND voting_year = ?",
        (user_id, zone_id, window["voting_year"]),
    ).fetchone()
    if existing:
        raise ValueError("You've already cast your Perception vote for this zone this year.")
    now = _now()
    conn.execute(
        """INSERT INTO zone_sentiment (user_id, zone_id, voting_year, vote, created_at, updated_at, cycle_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, zone_id, window["voting_year"], vote, now, now, cycle_middleware.get_active_cycle_id(conn)),
    )
    conn.commit()
    return {"status": "ok", "voting_year": window["voting_year"], "vote": vote}


def _ensure_zone_frozen(conn, zone_id: str, voting_year: int) -> None:
    existing = conn.execute(
        "SELECT 1 FROM zone_sentiment_stats WHERE zone_id = ? AND voting_year = ?",
        (zone_id, voting_year),
    ).fetchone()
    if existing:
        return
    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN vote = 'pro' THEN 1 ELSE 0 END), 0) AS pro_count,
             COALESCE(SUM(CASE WHEN vote = 'anti' THEN 1 ELSE 0 END), 0) AS anti_count
           FROM zone_sentiment WHERE zone_id = ? AND voting_year = ?""",
        (zone_id, voting_year),
    ).fetchone()
    conn.execute(
        "INSERT INTO zone_sentiment_stats (zone_id, voting_year, pro_count, anti_count, frozen_at) VALUES (?, ?, ?, ?, ?)",
        (zone_id, voting_year, row["pro_count"], row["anti_count"], _now()),
    )
    conn.commit()


def zone_results(conn, zone_id: str, user_id: int | None = None) -> dict:
    ensure_tables(conn)
    window = current_window()
    displayed_year = window["displayed_year"]
    _ensure_zone_frozen(conn, zone_id, displayed_year)
    row = conn.execute(
        "SELECT pro_count, anti_count FROM zone_sentiment_stats WHERE zone_id = ? AND voting_year = ?",
        (zone_id, displayed_year),
    ).fetchone()
    result = {
        "zone_id": zone_id,
        "voting_year": displayed_year,
        "pro_count": row["pro_count"] if row else 0,
        "anti_count": row["anti_count"] if row else 0,
        "window": window,
        "my_vote": None,
        "can_vote": False,
        "vote_reason": "",
    }
    if user_id is not None:
        my_vote_row = conn.execute(
            "SELECT vote FROM zone_sentiment WHERE user_id = ? AND zone_id = ? AND voting_year = ?",
            (user_id, zone_id, window["voting_year"]),
        ).fetchone()
        result["my_vote"] = my_vote_row["vote"] if my_vote_row else None
        if window["status"] != "voting":
            result["vote_reason"] = "Perception voting opens October 1."
        elif _birth_zone_id(conn, user_id) == zone_id:
            result["vote_reason"] = "You can't vote Perception on your own birth zone."
        elif my_vote_row:
            result["vote_reason"] = "You've already voted this year."
        else:
            result["can_vote"] = True
    return result
