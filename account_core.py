"""Single source of truth for Qumanity's Public/Global account classification
(2026-11-08 Q-Punch security hardening), and for validating a present_location
change against that classification (2026-11-08 C1 fix).

Lives in its own tiny module -- not app.py -- specifically so other modules
that need to apply or check a present_location change can import it directly
without importing app.py, which would be circular (app.py already imports
election_core and social_core). Every module that needs account classification
or present-location validation imports it from here; do not duplicate
SUBCONTINENT_COUNTRY_IDS, account_access_type(), or
validate_present_location_change() anywhere else.

validate_present_location_change() is the ONE shared gate for every path that
can ever write users.present_location_json after registration:
  - app.py's self-service profile-change-request flow (submission at
    api_dashboard_edit_request, approval at api_admin_profile_decide), and
  - social_core.py's account-ID-request flow (submission at
    request_new_account(), approval at decide_account_request()) -- the
    "Path A" flow an independent adversarial review (2026-11-08) found was
    calling neither this function nor any of its sub-checks at all, letting a
    Global Account acquire a fabricated Public/India village present_location
    and cross the Global<->Public boundary. Both paths now call this same
    function, at both their submission and approval steps, so neither can
    drift out of sync with the other again.
"""

import json
from pathlib import Path

import provisional_location_core

BASE_DIR = Path(__file__).resolve().parent
WORLD_DATA_FILE = BASE_DIR / "static" / "data" / "global_countries.json"
SUBCONTINENT_STATES_FILE = BASE_DIR / "static" / "data" / "subcontinent_states.json"
SUBCONTINENT_DISTRICTS_FILE = BASE_DIR / "static" / "data" / "subcontinent_districts.json"


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# The 10 countries of the Indian Sub-continent (Balochistan is its own country in the location
# master, not a Pakistan province) -- Qumanity's Public Account Activation group. A user whose
# PRESENT location's country is one of these registers through the existing local
# (Zone/State/District/Tehsil/Village) Public Account path; everyone else registers as a Global
# Account instead, with a present location that stops at Country -- see app.py's
# api_auth_register(). Mauritius and every other country (e.g. Japan, Kenya) are Global. Birth
# location has never been restricted to this set; it can be anywhere on Earth.
SUBCONTINENT_COUNTRY_IDS = (
    "O_AS_IND", "O_AS_NPL", "O_AS_BTN", "O_AS_BGD", "O_AS_MMR",
    "O_AS_LKA", "O_AS_PAK", "O_AS_BLC", "O_AS_AFG", "O_AS_MDV",
)


def account_access_type(present_location: dict) -> str:
    """'public' if present_location's country is one of the 10 Public Account Activation
    countries (SUBCONTINENT_COUNTRY_IDS), else 'global'. Always derived live from
    present_location_json -- deliberately NOT a separate persisted column, so it can never drift
    out of sync if present_location is later corrected (e.g. via a council/Admin-approved change
    -- see this module's own docstring above for validate_present_location_change(), the shared
    gate BOTH paths that can ever change a user's present_location after registration call).

    This is THE single call site every permission check in this codebase should use rather than
    re-deriving or duplicating the SUBCONTINENT_COUNTRY_IDS comparison -- including
    election_core.py's Q-Punch eligibility gate (_present_village_id()), which calls this
    directly so that a village id sitting in a Global Account's present_location_json can never,
    by itself, grant Q-Punch eligibility: eligibility requires BOTH a village id AND this
    function independently agreeing the account is 'public'."""
    country_id = (present_location.get("country") or {}).get("id")
    return "public" if country_id in SUBCONTINENT_COUNTRY_IDS else "global"


LOCATION_LEVELS = ("continent", "country", "zone", "state", "district", "tehsil", "village")


def location_subfields_well_formed(location: dict) -> bool:
    """True iff every present location-level key (continent/country/zone/state/district/tehsil/
    village) in `location` is itself a dict, or absent/falsy -- every validator and registration
    branch that reads a level does so with `(location.get(lvl) or {}).get("id")`, which crashes
    with an unhandled AttributeError on a malformed payload like `"district": "CS.DL.3"` (a plain
    string instead of {"id": "CS.DL.3"}) rather than failing safely. Checked once, up front, by
    every entry point that accepts a present_location dict from a client, so a malformed field is
    always a clean 400/ValueError, never a 500 (2026-11-08, Task 1A)."""
    return all(not location.get(lvl) or isinstance(location.get(lvl), dict) for lvl in LOCATION_LEVELS)


def public_state_ids(country_id):
    """Valid state-level ids of one Public-timeline country."""
    data = _load_json(SUBCONTINENT_STATES_FILE)
    for country in data["countries"]:
        if country["id"] == country_id:
            return {st["id"] for zone in country["zones"] for st in zone["states"]}
    return set()


def is_valid_global_country(continent_id: str, country_id: str) -> bool:
    """True if `country_id` is a real country in the canonical world database
    (WORLD_DATA_FILE, the same 7-continent/229-country data /api/world-data serves) AND
    `continent_id` is genuinely that country's own parent continent -- never trusted from
    the client as two independent facts. Used only for a Global Account's Present Location
    (present_country_id not in SUBCONTINENT_COUNTRY_IDS); the 10 Public Account countries
    are validated against subcontinent_states.json instead, via public_state_ids()."""
    data = _load_json(WORLD_DATA_FILE)
    for continent in data["continents"]:
        if continent["id"] != continent_id:
            continue
        return any(c["id"] == country_id for c in continent["countries"])
    return False


def validate_zone_district_tehsil_ancestry(country_id: str, state_id: str, present_location: dict) -> tuple[bool, str]:
    """Validates Zone-belongs-to-Country+State, District-belongs-to-State, and (for a REAL,
    non-provisional) Tehsil-belongs-to-District, against the same static subcontinent_states.json
    / subcontinent_districts.json data the registration dropdowns themselves cascade from. No new
    hierarchy level, no migration -- this is the existing ground truth, always present in every
    environment. Shared by every entry point that writes users.present_location_json (2026-11-08
    hardening, Task 1A) so all of them enforce the identical rule.

    District is mandatory whenever a REAL Tehsil is submitted -- omitting District entirely used
    to skip this check, a confirmed, exploitable gap an independent review found (a Tehsil+Village
    pair genuinely belonging to a different State could be accepted by simply never submitting
    District). A PROVISIONAL (PROV-...) Tehsil is skipped here entirely -- its own, separate
    parent_verified_state_id check (in provisional_location_core, run by the caller) already
    covers it, and a provisional Tehsil's parent is deliberately not required to resolve against
    this static dataset (it may not exist there yet -- that is the entire point of the
    provisional-location system).

    Returns (True, "") or (False, "<reason>")."""
    zone_id = (present_location.get("zone") or {}).get("id")
    district_id = (present_location.get("district") or {}).get("id")
    tehsil_id = (present_location.get("tehsil") or {}).get("id")

    if zone_id:
        country_entry = next((c for c in _load_json(SUBCONTINENT_STATES_FILE)["countries"] if c["id"] == country_id), None)
        zone_entry = next((z for z in (country_entry or {}).get("zones", []) if z["id"] == zone_id), None)
        if not zone_entry:
            return False, "That zone does not belong to the selected Country"
        if not any(st["id"] == state_id for st in zone_entry.get("states", [])):
            return False, "That State does not belong to the selected Zone"

    tehsil_is_real = bool(tehsil_id) and provisional_location_core.from_present_location_id(tehsil_id) is None
    if tehsil_is_real and not district_id:
        return False, "A Tehsil requires its District to also be submitted"
    if district_id or tehsil_is_real:
        state_entry = (_load_json(SUBCONTINENT_DISTRICTS_FILE).get("states") or {}).get(state_id) or {}
        district_entry = next((d for d in state_entry.get("districts", []) if d["id"] == district_id), None)
        if not district_entry:
            return False, "That district does not belong to the selected State"
        if tehsil_is_real:
            tehsil_entry = next((t for t in district_entry.get("tehsils", []) if t["id"] == tehsil_id), None)
            if not tehsil_entry:
                return False, "That tehsil does not belong to the selected District"
    return True, ""


def validate_present_location_change(conn, user_id: int, new_present_location: dict) -> tuple[bool, str]:
    """The shared gate for every path that can ever write users.present_location_json after
    registration -- see this module's own docstring for the full list (app.py's profile-change-
    request flow, and social_core.py's account-ID-request flow). Before the 2026-11-08 hardening
    pass, the profile-change-request path applied whatever present_location JSON a council/Admin
    approved with ZERO shape or consistency checking -- not even the state-belongs-to-country check
    registration has always had. That is the realistic route (not a direct SQL edit, which no
    self-service flow can reach) by which an internally inconsistent present_location -- e.g. a
    Global country paired with a Subcontinent village id -- could have ended up on a real row.
    Returns (True, "") or (False, "<reason>").

    Also enforces: a change must stay within the user's EXISTING account classification -- Global
    stays Global, Public stays Public. There is no approved Global<->Public transition workflow
    built anywhere in this product today, and inventing one is out of scope for this function; see
    docs/HANDOVER.md for the documented limitation. A genuine cross-boundary relocation needs a
    dedicated, separately authorized feature, not a side effect of a generic edit/request ticket.

    Always re-reads the user's CURRENT present_location_json from `conn` to compute old_type, so
    calling this again at an approval step (after submission-time validation already passed)
    correctly re-validates against whatever the user's state is NOW -- not stale submission-time
    data (2026-11-08, C1 fix: this is what makes approval-time revalidation safe for a request that
    sat pending while the user's own account state changed).

    Also validates the FULL Zone/District/Tehsil/Village ancestry for a Public-country change, not
    just state-belongs-to-country."""
    if not isinstance(new_present_location, dict):
        return False, "Present location is required"
    if not location_subfields_well_formed(new_present_location):
        return False, "Present location fields must each be an object with an id"
    country_id = (new_present_location.get("country") or {}).get("id")
    continent_id = (new_present_location.get("continent") or {}).get("id")
    new_type = account_access_type(new_present_location)

    old_row = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
    old_type = account_access_type(json.loads(old_row["present_location_json"])) if old_row else new_type
    if new_type != old_type:
        return False, ("Moving your Present Location across the Public/Global Account boundary "
                        "isn't supported through this request -- contact Admin.")

    if new_type == "global":
        if not continent_id:
            return False, "Present location needs a continent"
        if any((new_present_location.get(lvl) or {}).get("id") for lvl in
               ("state", "zone", "district", "tehsil", "village")):
            return False, "A Global Account's present location can only be Continent and Country"
        if not is_valid_global_country(continent_id, country_id):
            return False, "Unknown continent/country"
        return True, ""

    state_id = (new_present_location.get("state") or {}).get("id")
    if state_id not in public_state_ids(country_id):
        return False, "Present location needs a valid state/province for its country"

    ok, reason = validate_zone_district_tehsil_ancestry(country_id, state_id, new_present_location)
    if not ok:
        return False, reason

    district_id = (new_present_location.get("district") or {}).get("id")
    tehsil_id = (new_present_location.get("tehsil") or {}).get("id")
    village_id = (new_present_location.get("village") or {}).get("id")

    provisional_location_core.ensure_tables(conn)
    for label, loc_id in (("tehsil", tehsil_id), ("village", village_id)):
        prov_id = provisional_location_core.from_present_location_id(loc_id) if loc_id else None
        if prov_id is None:
            continue
        prov = provisional_location_core.get_provisional(conn, prov_id)
        if not prov or prov["status"] in ("rejected", "merged"):
            return False, f"That provisional {label} is no longer available -- please search again"
        if prov["parent_verified_state_id"] != state_id:
            return False, f"That provisional {label} does not belong to the selected State"

    # Real (non-provisional) village ancestry, checked against india_villages.tehsil_id -- the
    # same table GET /api/india-villages/<tehsil_id> already serves from (a district with
    # direct_villages has its villages' tehsil_id column set to the district id itself, hence
    # `tehsil_id or district_id`). A village id that genuinely isn't in the authoritative records
    # is rejected outright, same as a confirmed mismatch -- "unverifiable" is never treated as
    # "confirmed valid". A village is also required to carry an immediate parent (Tehsil, or
    # District for a direct_villages district) -- a bare village id with no stated parent at all is
    # rejected rather than relying on an accidental `None`-never-matches-a-real-id side effect.
    village_is_real = bool(village_id) and provisional_location_core.from_present_location_id(village_id) is None
    if village_is_real:
        if not (tehsil_id or district_id):
            return False, "A Village requires its Tehsil or District to also be submitted"
        real = conn.execute("SELECT tehsil_id FROM india_villages WHERE id = ?", (village_id,)).fetchone()
        if real is None:
            return False, "That village could not be found in the location records"
        if real["tehsil_id"] != (tehsil_id or district_id):
            return False, "That village does not belong to the selected Tehsil/District"

    return True, ""
