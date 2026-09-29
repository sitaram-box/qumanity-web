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


def location_elements_row_to_dict(row) -> dict:
    total = row["total_users"] or 0
    pct = lambda n: round(100 * n / total, 1) if total else 0.0
    return {
        "location_id": row["location_id"],
        "location_type": row["location_type"],
        "total_users": total,
        "fire_count": row["fire_count"], "fire_percentage": pct(row["fire_count"]),
        "earth_count": row["earth_count"], "earth_percentage": pct(row["earth_count"]),
        "air_count": row["air_count"], "air_percentage": pct(row["air_count"]),
        "water_count": row["water_count"], "water_percentage": pct(row["water_count"]),
        "space_count": row["space_count"], "space_percentage": pct(row["space_count"]),
        "updated_at": row["updated_at"],
    }
