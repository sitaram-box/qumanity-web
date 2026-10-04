"""Display gating for Election History and Perception Calculator aggregates (Founder, 2026-10-04).

Both features keep working exactly as before for a user's OWN saved input -- saving a party
choice (`election_core.save_party_history`) or casting a Pro/Anti vote (`perception_core.
cast_country_vote`/`cast_zone_vote`) is untouched. What this module gates is the CALCULATED,
aggregated result (the % breakdown everyone would otherwise see) -- kept hidden system-wide until
one of the conditions below is met, per the Founder's explicit instruction: "Keep it hidden for
now... it will be displayed only when Admin member like myself/mentor ask you to display it with a
proper logic."

Election History aggregate -- auto-opens on either of:
  1. The Sun-enters-Aries civil-calendar date (this app's zodiac system uses fixed MM-DD boundaries
     everywhere, never real ephemeris -- see zodiac_core.ZODIAC_RANGES's Aries start "03-21"; there
     is no "Sun enters Aries" astronomical helper anywhere in this codebase to reuse, so this reuses
     that same fixed-date convention rather than introducing a new one) of year 2028, staying open
     for exactly 1 year, then closing again.
  2. Earlier, for 1 year from whenever the count of India-resident users with a saved election
     history entry first reaches 50,00,000 (5,000,000) -- "to give survey reports only 1 year before
     [the] next national election of Lok Sabha in 2029." Once crossed, the trigger date is frozen in
     `system_settings` so the 1-year window doesn't keep sliding as the count keeps growing.
A manual Admin override (`set_override`) can force it open or force it shut regardless of the above.

Perception Calculator aggregate -- no automatic trigger was specified; it opens ONLY via a manual
Admin override, which may optionally carry its own display-until date ("a logic of time as well").

Where it's shown: Election History aggregate surfaces only on a Country or State page
(`election_core.loksabha_aggregate`/`vidhansabha_aggregate`, via `/api/election-sentiment/...`) --
never on Zone/Village/Tehsil/District/Continent/Earth. (The eventual intent, once this opens, is for
State/Vidhan-Sabha data to be shown nested inside its Zone's own page rather than a separate State
page, so a user can check their own state within zone context -- that's a `board.js` navigation
change to make when the gate actually opens, not something to build blind while it's hidden.)
Perception Calculator aggregate surfaces on the dashboard's Country/Zone Perception cards
(`/api/perception/country/<id>`, `/api/perception/zone/<id>`).
"""
from __future__ import annotations

import datetime as dt
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by INTEGER,
    updated_at TEXT NOT NULL
);
"""

ARIES_2028_START = dt.date(2028, 3, 21)
INDIA_SAVED_COUNT_THRESHOLD = 5_000_000
WINDOW_DAYS = 365

INDIA_COUNTRY_ID = "O_AS_IND"


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _get(conn, key: str) -> dict | None:
    row = conn.execute("SELECT value FROM system_settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def _set(conn, key: str, value: dict, admin_user_id: int | None) -> None:
    conn.execute(
        """INSERT INTO system_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by,
               updated_at = excluded.updated_at""",
        (key, json.dumps(value), admin_user_id, _now()),
    )
    conn.commit()


def _window_active(start: dt.date, today: dt.date) -> bool:
    return start <= today < start + dt.timedelta(days=WINDOW_DAYS)


def india_election_history_saved_count(conn) -> int:
    """Distinct India-resident (present location) users with at least one saved election-history
    entry -- the headcount the 50,00,000 early-unlock threshold is measured against."""
    row = conn.execute(
        """SELECT COUNT(DISTINCT u.id) AS n FROM users u
           JOIN election_history_entries eh ON eh.user_id = u.id
           WHERE json_extract(u.present_location_json, '$.country.id') = ?""",
        (INDIA_COUNTRY_ID,),
    ).fetchone()
    return row["n"] if row else 0


def election_history_visibility(conn, today: dt.date | None = None) -> dict:
    ensure_tables(conn)
    today = today or dt.date.today()

    override = _get(conn, "election_history_override")
    if override is not None:
        until = dt.date.fromisoformat(override["display_until"]) if override.get("display_until") else None
        if override.get("enabled") and (until is None or today <= until):
            return {"visible": True, "reason": "Opened by Admin override."}
        if override.get("enabled") is False:
            return {"visible": False, "reason": "Hidden by Admin override."}

    if _window_active(ARIES_2028_START, today):
        return {"visible": True, "reason": "Open for 1 year from the Sun entering Aries, 2028."}

    crossed = _get(conn, "election_history_threshold_crossed_at")
    if crossed:
        crossed_date = dt.date.fromisoformat(crossed["date"])
        if _window_active(crossed_date, today):
            return {"visible": True, "reason": "Open for 1 year: 50,00,000+ India users have saved their choice."}
    else:
        count = india_election_history_saved_count(conn)
        if count >= INDIA_SAVED_COUNT_THRESHOLD:
            _set(conn, "election_history_threshold_crossed_at", {"date": today.isoformat(), "count": count}, None)
            return {"visible": True, "reason": "Open for 1 year: 50,00,000+ India users have saved their choice."}

    return {"visible": False, "reason": "Election History results open in 2028, or earlier at 50,00,000 saved responses from India."}


def perception_visibility(conn, today: dt.date | None = None) -> dict:
    ensure_tables(conn)
    today = today or dt.date.today()

    override = _get(conn, "perception_override")
    if override is not None:
        until = dt.date.fromisoformat(override["display_until"]) if override.get("display_until") else None
        if override.get("enabled") and (until is None or today <= until):
            return {"visible": True, "reason": "Opened by Admin override."}

    return {"visible": False, "reason": "Perception Calculator results are shown only when the Founder opens them."}


def set_override(conn, key: str, enabled: bool | None, display_until: str | None, admin_user_id: int | None) -> dict:
    if key not in ("election_history", "perception"):
        raise ValueError("Unknown visibility key.")
    if display_until:
        dt.date.fromisoformat(display_until)  # validates format, raises ValueError if malformed
    value = {"enabled": enabled, "display_until": display_until}
    _set(conn, f"{key}_override", value, admin_user_id)
    return value


def admin_snapshot(conn) -> dict:
    """Everything an Admin needs to decide whether to flip either gate."""
    return {
        "election_history": dict(
            election_history_visibility(conn),
            override=_get(conn, "election_history_override"),
            india_saved_count=india_election_history_saved_count(conn),
            threshold=INDIA_SAVED_COUNT_THRESHOLD,
            threshold_crossed_at=_get(conn, "election_history_threshold_crossed_at"),
            scheduled_window_start=ARIES_2028_START.isoformat(),
        ),
        "perception": dict(
            perception_visibility(conn),
            override=_get(conn, "perception_override"),
        ),
    }
