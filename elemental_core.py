"""Personal elemental balance (from a full kundali) and location-level
elemental aggregation (for the governance/village Five-Elements division).

Location aggregation deliberately uses the TROPICAL sun element (see
zodiac_core.py's docstring) — that's the element that actually classifies
a user into Fire/Earth/Air/Water for governance purposes per the brief's
Part 1 table, and it's the one piece of elemental data every user has
regardless of whether a full kundali could be computed.
"""

from __future__ import annotations

import datetime as dt
import json

import qmail_core
from id_generator import age_code
from zodiac_core import ZODIAC_RANGES

ELEMENTS = ["Fire", "Earth", "Air", "Water"]

SIGN_ELEMENT = {z["sign"]: z["element"] for z in ZODIAC_RANGES}

AGE_BAND_LABELS = {"A1": "0–24", "A2": "25–49", "A3": "50–75", "A4": "76+"}


def compute_elemental_balance(sun_element: str, kundali: dict) -> dict:
    """Count how many chart points (tropical Sun + sidereal Moon/Ascendant
    + 5 visible planets = 8 points; Rahu/Ketu are shadow points, excluded
    from element-balance by convention) fall in each element.

    Space (Akasha) has no zodiac sign in this system — per the brief, it
    represents the database/collective field, not a personal trait — so
    space_balance is always 0 here.
    """
    counts = {e: 0 for e in ELEMENTS}
    counts[sun_element] += 1

    for point in ("moon", "ascendant"):
        sign = kundali.get(point, {}).get("sign")
        if sign in SIGN_ELEMENT:
            counts[SIGN_ELEMENT[sign]] += 1

    for planet in ("Mars", "Mercury", "Jupiter", "Venus", "Saturn"):
        sign = kundali.get("planets", {}).get(planet, {}).get("sign")
        if sign in SIGN_ELEMENT:
            counts[SIGN_ELEMENT[sign]] += 1

    dominant = max(counts, key=counts.get)
    return {
        "fire_balance": counts["Fire"],
        "earth_balance": counts["Earth"],
        "air_balance": counts["Air"],
        "water_balance": counts["Water"],
        "space_balance": 0,
        "dominant_element": dominant,
    }


def location_levels_for(birth_location: dict) -> list[tuple[str, str]]:
    """(location_id, location_type) pairs to increment, from most specific
    to least, for a birth_location dict shaped like the registration
    wizard's pendingSelection: {continent, country, state?, zone?,
    district?, tehsil?, village?}."""
    levels = [("EARTH", "earth")]
    continent = birth_location.get("continent") or {}
    country = birth_location.get("country") or {}
    state = birth_location.get("state")

    if continent.get("id"):
        levels.append((continent["id"], "continent"))
    if country.get("id"):
        levels.append((country["id"], "country"))
    if state and state.get("id"):
        zone = birth_location.get("zone") or {}
        if zone.get("id"):
            levels.append((zone["id"], "zone"))
        levels.append((state["id"], "state"))
        district = birth_location.get("district")
        if district and district.get("id"):
            levels.append((district["id"], "district"))
            tehsil = birth_location.get("tehsil")
            if tehsil and tehsil.get("id"):
                levels.append((tehsil["id"], "tehsil"))
                village = birth_location.get("village")
                if village and village.get("id"):
                    levels.append((village["id"], "village"))
    return levels


def update_location_stats(conn, birth_location: dict, sun_element: str) -> None:
    """Upsert location_elements counts at every level from Earth down to
    state (or country, for non-India users) for one newly registered user."""
    col = {"Fire": "fire_count", "Earth": "earth_count", "Air": "air_count", "Water": "water_count"}[sun_element]
    for location_id, location_type in location_levels_for(birth_location):
        conn.execute(
            f"""
            INSERT INTO location_elements (location_id, location_type, {col}, total_users, updated_at)
            VALUES (?, ?, 1, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(location_id, location_type) DO UPDATE SET
                {col} = {col} + 1,
                total_users = total_users + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (location_id, location_type),
        )
    conn.commit()


def recompute_location_elements(conn, dry_run: bool = False) -> dict:
    """Full, correct rebuild of location_elements (2026-10-17, corrected 2026-10-17 later the same
    day): total_users counts PRESENT-location members only -- a user born in village A and living
    in village B is a member of B, not A; A gets no total_users credit for them at all. birth_users
    is separate, metadata-only -- "how many real users (is_demo=0, is_removed=0) were born here" --
    never counted toward total_users, never driving membership/voting/participation (voting and
    updates have always been present-location-only; this just makes the stored aggregate agree with
    that, instead of silently tracking a different population). The elemental breakdown
    (fire/earth/air/water_count) reflects present-location members too, for the same reason: those
    are the location's actual members. A FIRST version of this function (committed nowhere, only
    ever a local uncommitted diff) used birth_location for everything, which was the underlying bug
    this corrects -- not update_location_stats() itself (still birth-location-keyed, unchanged,
    since that increments at registration time for a different, still-valid purpose: "where did
    this location's people come from," tracked independently of where they live now).

    DELETEs every row and reinserts only locations with a nonzero total_users OR birth_users (a
    location can have one without the other -- a birth-only location, like someone's home village
    they no longer live in, still deserves a row with total_users=0, birth_users>0, not no row at
    all). india_scoreboard()/location_elements_row_to_dict() already default a missing row's
    total_users to 0, so dropping a location with neither population is still handled correctly by
    every existing caller.

    dry_run=True computes and returns everything exactly as a real run would, but rolls back
    instead of committing -- the DB is left completely untouched. The returned "new_rows" dict IS
    the would-be post-recompute state either way, so a caller never needs to re-query the table
    after a dry run to see what WOULD have changed (it can't -- nothing changed)."""
    import datetime as dt

    present_rows = conn.execute(
        """SELECT u.present_location_json, z.sun_element FROM users u
           JOIN user_zodiac z ON z.user_id = u.id
           WHERE u.is_demo = 0 AND u.is_removed = 0"""
    ).fetchall()
    birth_rows = conn.execute(
        "SELECT birth_location_json FROM users WHERE is_demo = 0 AND is_removed = 0"
    ).fetchall()

    tallies: dict[tuple[str, str], dict[str, int]] = {}

    def _bucket(key):
        return tallies.setdefault(key, {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0, "total": 0, "birth": 0})

    for row in present_rows:
        present_location = json.loads(row["present_location_json"])
        sun_element = row["sun_element"]
        for key in location_levels_for(present_location):
            t = _bucket(key)
            if sun_element in t:
                t[sun_element] += 1
            t["total"] += 1

    for row in birth_rows:
        birth_location = json.loads(row["birth_location_json"])
        for key in location_levels_for(birth_location):
            _bucket(key)["birth"] += 1

    before_count = conn.execute("SELECT COUNT(*) FROM location_elements").fetchone()[0]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    conn.execute("DELETE FROM location_elements")
    for (location_id, location_type), t in tallies.items():
        conn.execute(
            """INSERT INTO location_elements (location_id, location_type, fire_count, earth_count,
                                               air_count, water_count, space_count, total_users,
                                               birth_users, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)""",
            (location_id, location_type, t["Fire"], t["Earth"], t["Air"], t["Water"], t["total"], t["birth"], now),
        )

    # Q-Punch council addresses (2026-10-18): a location's address, once created, is permanent
    # (qmail_core.sync_qpunch_addresses never retires one), so this only ever adds rows. Run in
    # the same transaction as the location_elements rebuild above so a dry run rolls both back
    # together -- a dry run must create zero addresses, the same as it writes zero stats.
    qpunch_created = qmail_core.sync_qpunch_addresses(
        conn, {key: t["total"] for key, t in tallies.items()}
    )

    if dry_run:
        conn.rollback()
    else:
        conn.commit()

    return {
        "real_users_counted": len(present_rows),
        "rows_before": before_count,
        "rows_after": len(tallies),
        "qpunch_addresses_created": qpunch_created,
        "new_rows": {
            key: {"total_users": t["total"], "birth_users": t["birth"], "fire_count": t["Fire"],
                  "earth_count": t["Earth"], "air_count": t["Air"], "water_count": t["Water"]}
            for key, t in tallies.items()
        },
    }


def registered_user_stats_from_rows(rows) -> dict:
    """Registered-user demographics for one location (country, continent,
    or the whole Earth — the caller decides via its SQL WHERE clause, this
    just tallies whatever rows it's given): Total Humans, gender
    breakdown (male/female/both — the three categories this app collects),
    age-band breakdown (reusing id_generator.age_code's A1-A4 bands
    directly), and zodiac element/sign breakdown. NOT population/capital/
    area/currency — this app has never ingested that data, and the real
    ask (per the user) is about registered users, not the country itself.

    `rows` are (gender, dob, sun_sign, sun_element) tuples/Rows, e.g. from
    `SELECT u.gender, u.dob, z.sun_sign, z.sun_element FROM users u JOIN
    user_zodiac z ...`.
    """
    gender = {"male": 0, "female": 0, "both": 0}
    age_bands = {code: 0 for code in AGE_BAND_LABELS}
    elements = {e: 0 for e in ELEMENTS}
    signs = {z["sign"]: 0 for z in ZODIAC_RANGES}  # canonical Aries..Pisces order

    today = dt.date.today()
    total = 0
    for row in rows:
        total += 1
        gender[row["gender"] if row["gender"] in gender else "both"] += 1
        age_bands[age_code(dt.date.fromisoformat(row["dob"]), today)] += 1
        if row["sun_element"] in elements:
            elements[row["sun_element"]] += 1
        if row["sun_sign"] in signs:
            signs[row["sun_sign"]] += 1

    return {
        "total_humans": total,
        "gender": gender,
        "age_bands": [{"code": c, "label": AGE_BAND_LABELS[c], "count": age_bands[c]} for c in ("A1", "A2", "A3", "A4")],
        "elements": elements,
        "signs": signs,
    }


def _suppress_small_count(value):
    """Same rule as app.py's _suppress_small_count (1-4 -> "<5", 0 stays 0) -- duplicated here,
    not imported, to avoid a circular import (app.py imports elemental_core, not the reverse).
    Used for every person-count this module returns: total_users, birth_users, each element
    count in location_elements_row_to_dict, and the zone/state/total_members counts in
    india_scoreboard. The rule is identical regardless of which population is being counted."""
    return "<5" if isinstance(value, int) and 0 < value < 5 else value


def location_elements_row_to_dict(row) -> dict:
    total = row["total_users"] or 0
    pct = lambda n: round(100 * n / total, 1) if total else 0.0

    def suppressed_count_and_pct(raw_count):
        """A count's percentage is nulled whenever the count itself is suppressed -- a
        percentage computed from a small population re-identifies exactly as the count did
        (e.g. "66.7%" in a 3-member village implies the total is 3 and the count is 2), so
        suppressing the count but leaving its percentage would undo the suppression."""
        count = raw_count or 0
        percentage = pct(count)
        if 0 < count < 5:
            return "<5", None
        return count, percentage

    fire_count, fire_percentage = suppressed_count_and_pct(row["fire_count"])
    earth_count, earth_percentage = suppressed_count_and_pct(row["earth_count"])
    air_count, air_percentage = suppressed_count_and_pct(row["air_count"])
    water_count, water_percentage = suppressed_count_and_pct(row["water_count"])
    space_count, space_percentage = suppressed_count_and_pct(row["space_count"])

    return {
        "location_id": row["location_id"],
        "location_type": row["location_type"],
        "total_users": _suppress_small_count(total),
        "birth_users": _suppress_small_count(row["birth_users"] or 0),
        "fire_count": fire_count, "fire_percentage": fire_percentage,
        "earth_count": earth_count, "earth_percentage": earth_percentage,
        "air_count": air_count, "air_percentage": air_percentage,
        "water_count": water_count, "water_percentage": water_percentage,
        "space_count": space_count, "space_percentage": space_percentage,
        "updated_at": row["updated_at"],
    }


def india_scoreboard(conn, india_states_data: dict, top_n: int = 10) -> dict:
    """The homepage's live India scoreboard: total registered members, Zones ranked by
    `total_users`, and the top `top_n` States ranked the same way -- all from
    `location_elements` (already kept current by `update_location_stats` on every
    registration), joined against `india_states.json`'s zone/state names for display. A
    zone/state with no members yet is still listed, at 0.

    Sorting, ranking and the total_members sum all use the raw counts -- small-count
    suppression (_suppress_small_count) is applied only at the end, to the values actually
    returned, so a suppressed "<5" string never has to be sorted or summed."""
    totals = {
        (r["location_type"], r["location_id"]): r["total_users"]
        for r in conn.execute("SELECT location_type, location_id, total_users FROM location_elements WHERE location_type IN ('zone', 'state')")
    }
    zones = []
    states = []
    for zone in india_states_data.get("zones", []):
        zones.append({"id": zone["id"], "name": zone["name"], "total_users": totals.get(("zone", zone["id"]), 0)})
        for state in zone.get("states", []):
            states.append({"id": state["id"], "name": state["name"], "zone_id": zone["id"], "total_users": totals.get(("state", state["id"]), 0)})
    zones.sort(key=lambda z: z["total_users"], reverse=True)
    states.sort(key=lambda s: s["total_users"], reverse=True)
    for rank, z in enumerate(zones, 1):
        z["rank"] = rank
    for rank, s in enumerate(states, 1):
        s["rank"] = rank
    total_members = sum(z["total_users"] for z in zones)

    top_states = states[:top_n]
    for z in zones:
        z["total_users"] = _suppress_small_count(z["total_users"])
    for s in top_states:
        s["total_users"] = _suppress_small_count(s["total_users"])

    return {
        "total_members": _suppress_small_count(total_members),
        "zones": zones,
        "states": top_states,
        "states_total_count": len(states),
    }
