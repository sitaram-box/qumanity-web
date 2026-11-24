"""Geography hierarchy: "what are the direct child locations of X" -- built for the Q-Punch
cascade's Lower House (Phase 2, 2026-11-16, schema-and-helpers-only pass, see
migrations/040_qpunch_councils.py): a Tehsil's Lower House is every currently-serving council
member across every village directly under that tehsil, so answering "which locations sit one
level below this one" is shared plumbing every cascade level's election logic will need in Phase
3. This module only answers that question -- it does not touch elections, councils, or any
Q-Punch table itself.

Reuses the SAME static geography data the registration dropdowns and account_core.py's own
ancestry validators (validate_zone_district_tehsil_ancestry()) already read -- never a second,
independently-maintained copy of the hierarchy.

Two different mechanisms, because the underlying ID schemes genuinely differ (confirmed by reading
account_core.py and the actual JSON files, not assumed):
  - continent->country, country->zone, zone->state, state->district, district->tehsil: looked up
    from the existing static JSON files (global_countries.json for continent->country;
    subcontinent_states.json for country->zone and zone->state; subcontinent_districts.json for
    state->district and district->tehsil). These ids do NOT share a parseable prefix across the
    continent/country/zone boundary (e.g. "O_AS" -> "O_AS_IND" -> "IND/CS" -> "CS.DL") -- there is
    no dot-suffix shortcut there, the real hierarchy has to come from the real data.
  - tehsil->village: a direct SQL lookup against india_villages.tehsil_id, the dedicated,
    already-indexed foreign key built for exactly this -- not a string match against the id.

Within India's own State->District->Tehsil chain, a child id IS always its parent id plus one more
dot-separated segment (confirmed against subcontinent_districts.json: state "CS.AN" -> district
"CS.AN.1" -> tehsil "CS.AN.1.1") -- the one place this module actually uses that dot-suffix
convention is to find which STATE a district id belongs to (subcontinent_districts.json nests
districts under their owning state, so a lone district id can't be looked up without knowing
that), by stripping the district id's own last segment. This is a documented, deliberate reliance
on today's id-generation convention, not a general-purpose id parser.

get_children() never mutates and never writes to the DB; `conn` is read-only here, needed only
for the tehsil->village branch.

get_parent()/get_siblings() (Chat-as-Dashboard Phase 2 Step 1, 2026-11-24): the reverse and
sideways questions get_children() was never asked. Built for the new Public/Global rail's
"adjacent locations" list (siblings) and the 3-strike request escalation (parent, repeatedly, to
find who decides the next strike) -- both need these, so they live here rather than being
duplicated in chat_core.py. Reuse the EXACT SAME static JSON files and the same dot-suffix
convention documented above; never a second, independently-maintained copy of the hierarchy.
get_parent() additionally accepts level == "earth" (get_children() never did, and still doesn't --
Earth has no children to list, but it IS the parent of every continent, so get_parent() needs to
know about it where get_children() never had to).
"""
from __future__ import annotations

import json
from pathlib import Path

import account_core

BASE_DIR = Path(__file__).resolve().parent
GLOBAL_COUNTRIES_FILE = BASE_DIR / "static" / "data" / "global_countries.json"

LEVELS = account_core.LOCATION_LEVELS  # ("continent", "country", "zone", "state", "district", "tehsil", "village")
LEVELS_WITH_EARTH = LEVELS + ("earth",)  # get_parent()'s own valid-level set -- see module docstring


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _children_continent_country(continent_id: str) -> list[str]:
    for continent in _load_json(GLOBAL_COUNTRIES_FILE)["continents"]:
        if continent["id"] == continent_id:
            return [c["id"] for c in continent["countries"]]
    return []


def _children_country_zone(country_id: str) -> list[str]:
    for country in _load_json(account_core.SUBCONTINENT_STATES_FILE)["countries"]:
        if country["id"] == country_id:
            return [z["id"] for z in country.get("zones", [])]
    return []  # a Global (non-subcontinent) country has no zones at all -- an empty list, not an error


def _children_zone_state(zone_id: str) -> list[str]:
    for country in _load_json(account_core.SUBCONTINENT_STATES_FILE)["countries"]:
        for zone in country.get("zones", []):
            if zone["id"] == zone_id:
                return [st["id"] for st in zone.get("states", [])]
    return []


def _children_state_district(state_id: str) -> list[str]:
    state_entry = (_load_json(account_core.SUBCONTINENT_DISTRICTS_FILE).get("states") or {}).get(state_id) or {}
    return [d["id"] for d in state_entry.get("districts", [])]


def _children_district_tehsil(district_id: str) -> list[str]:
    # subcontinent_districts.json nests districts under their owning state, with no flat
    # district->tehsils index of its own -- so the owning state has to be found first. Rather than
    # require the caller to pass it separately (get_children()'s whole point is "just give me a
    # location_id"), this strips the district id's own last dot segment to recover its parent
    # state id (see this module's own docstring: "CS.AN.1" -> "CS.AN") -- the one place this
    # module relies on the id's own shape rather than reading it from data.
    state_id = district_id.rsplit(".", 1)[0]
    state_entry = (_load_json(account_core.SUBCONTINENT_DISTRICTS_FILE).get("states") or {}).get(state_id) or {}
    district_entry = next((d for d in state_entry.get("districts", []) if d["id"] == district_id), None)
    return [t["id"] for t in (district_entry or {}).get("tehsils", [])]


def _children_tehsil_village(conn, tehsil_id: str) -> list[str]:
    return [r["id"] for r in conn.execute("SELECT id FROM india_villages WHERE tehsil_id = ?", (tehsil_id,))]


def get_children(conn, level: str, location_id: str) -> list[str]:
    """Every direct child location id of (level, location_id) -- e.g. get_children(conn, "tehsil",
    "CS.DL.3.4") returns every village id under that tehsil. `conn` is required on every call for a
    uniform signature, even though only the tehsil branch actually reads from it (villages are the
    one level with no static JSON source -- see this module's own docstring).

    Returns [] for an id not found in the relevant data, or for level == "village" (nothing sits
    below it) -- never raises for "nothing found", since a cascade level with zero children today
    (e.g. a freshly-registered tehsil with no villages yet) is a real, valid state for Phase 3's
    election logic to handle, not a caller error. Raises ValueError only for a `level` string that
    isn't one of account_core.LOCATION_LEVELS at all -- a genuine caller mistake."""
    if level not in LEVELS:
        raise ValueError(f"Unknown level: {level}")
    return {
        "continent": _children_continent_country,
        "country": _children_country_zone,
        "zone": _children_zone_state,
        "state": _children_state_district,
        "district": _children_district_tehsil,
        "tehsil": lambda loc_id: _children_tehsil_village(conn, loc_id),
        "village": lambda loc_id: [],
    }[level](location_id)


def _parent_village_tehsil(conn, village_id: str) -> dict | None:
    row = conn.execute("SELECT tehsil_id FROM india_villages WHERE id = ?", (village_id,)).fetchone()
    return {"level": "tehsil", "id": row["tehsil_id"]} if row and row["tehsil_id"] else None


def _parent_by_dot_suffix(location_id: str, parent_level: str) -> dict | None:
    # The one place get_parent() relies on the dot-suffix id convention this module's own
    # docstring documents (state->district->tehsil only) -- a malformed id with no dot segment at
    # all is treated as "no parent found" (None), not a crash, mirroring get_children()'s own
    # "nothing found is a valid state, not a caller error" stance.
    if "." not in location_id:
        return None
    return {"level": parent_level, "id": location_id.rsplit(".", 1)[0]}


def _parent_state_zone(state_id: str) -> dict | None:
    for country in _load_json(account_core.SUBCONTINENT_STATES_FILE)["countries"]:
        for zone in country.get("zones", []):
            if any(st["id"] == state_id for st in zone.get("states", [])):
                return {"level": "zone", "id": zone["id"]}
    return None


def _parent_zone_country(zone_id: str) -> dict | None:
    for country in _load_json(account_core.SUBCONTINENT_STATES_FILE)["countries"]:
        if any(z["id"] == zone_id for z in country.get("zones", [])):
            return {"level": "country", "id": country["id"]}
    return None


def _parent_country_continent(country_id: str) -> dict | None:
    for continent in _load_json(GLOBAL_COUNTRIES_FILE)["continents"]:
        if any(c["id"] == country_id for c in continent["countries"]):
            return {"level": "continent", "id": continent["id"]}
    return None


def get_parent(conn, level: str, location_id: str) -> dict | None:
    """{"level":..., "id":...} for the direct parent of (level, location_id), or None when
    `level` is "earth" (nothing sits above it) or location_id isn't found in the owning data for
    its level -- never raises for "nothing found", same convention as get_children(). Raises
    ValueError only for a `level` string outside LEVELS_WITH_EARTH.

    zone/country/continent parents are found by searching the nesting JSON (no shared-id-prefix
    shortcut exists across that boundary -- see module docstring); state/district/tehsil parents
    use the documented dot-suffix convention instead, exactly like get_children()'s own
    _children_district_tehsil() already does in the other direction."""
    if level not in LEVELS_WITH_EARTH:
        raise ValueError(f"Unknown level: {level}")
    if level == "earth":
        return None
    if level == "continent":
        return {"level": "earth", "id": "EARTH"}
    return {
        "country": _parent_country_continent,
        "zone": _parent_zone_country,
        "state": _parent_state_zone,
        "district": lambda loc_id: _parent_by_dot_suffix(loc_id, "state"),
        "tehsil": lambda loc_id: _parent_by_dot_suffix(loc_id, "district"),
        "village": lambda loc_id: _parent_village_tehsil(conn, loc_id),
    }[level](location_id)


def get_siblings(conn, level: str, location_id: str) -> list[str]:
    """Every OTHER location id at this same level sharing (level, location_id)'s own parent --
    i.e. get_children() of the parent, minus location_id itself. [] for level == "earth" (nothing
    else is Earth) or when no parent is found (an orphaned/unknown id) -- deliberately built on
    get_parent() + get_children() rather than a third, independent lookup per level, so there is
    exactly one place each level's actual hierarchy data is read from."""
    if level == "earth":
        return []
    parent = get_parent(conn, level, location_id)
    if not parent:
        return []
    return [cid for cid in get_children(conn, parent["level"], parent["id"]) if cid != location_id]
