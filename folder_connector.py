"""Writes each newly-registered user into the REAL geographic folder tree
at /Users/macmudgal/Desktop/0_Earth/Continents/ (separate from and outside
this project — see README's "Nested folder integration" section).

That tree already exists on disk (built from Qumanity_Master.json): fully
scaffolded for India down to village level (5 zones / 37 states / 547
districts / 7,289 tehsils / 635,622 villages, all empty placeholder folders
today), and a bare per-country skeleton for the rest of the world (no
Zones/States below country level anywhere outside India yet).

Folder-naming scheme (reverse-engineered from the real tree, not invented):
    Continents/<contFolder>/Countries/<countryFolder>/Zones/<countryFolder>:<zoneCode>/
    States/<countryFolder>:<stateId>/Districts/<countryFolder>:<districtId>/
    Tehsils/<countryFolder>:<tehsilId>/Villages/<countryFolder>:<villageId>
where <contFolder>/<countryFolder> are the continent/country's own JSON id
with its leading "O" swapped for "0" (e.g. "O_AS_IND" -> "0_AS_IND"), and
<zoneId>/<stateId>/<districtId>/<tehsilId>/<villageId> are used exactly as
they already appear throughout this app (location_select.js's sel.path,
elemental_core.location_levels_for) -- e.g. state id "CS.DL", village id
"CS.DL.1.1.10" -- except the zone, whose folder suffix is only the part
after "/" in its JSON id ("IND/CS" -> "CS").

This walks only as deep as the location data goes AND the real folder
already exists, then creates the user's folder at whatever level that is
(country-level only for a non-India registrant). It never fabricates
missing scaffold levels -- if a level's folder isn't there, we stop one
level up rather than inventing new geography on disk.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

EARTH_ROOT = Path(os.environ.get("QM_EARTH_ROOT", "/Users/macmudgal/Desktop/0_Earth"))
CONTINENTS_ROOT = EARTH_ROOT / "Continents"

_ZONE_LEVEL = ("zone", "Zones")
_LOCATION_LEVELS = [
    ("zone", "Zones"),
    ("state", "States"),
    ("district", "Districts"),
    ("tehsil", "Tehsils"),
    ("village", "Villages"),
]

_USER_CATEGORY_DIRS = ("BORN_HERE", "LIVING_HERE")

SUB_ACCOUNTS = ("private_account", "personal_account", "public_account", "global_account")


def _root_char_fix(qid: str) -> str:
    """Continent/country ids start with Earth's root id "O" in the JSON
    (e.g. "O_AS_IND") but the matching folder on disk starts with "0"
    (digit zero) instead -- e.g. "0_AS_IND"."""
    return "0" + qid[1:] if qid.startswith("O_") else qid


def resolve_location_dir(location: dict) -> Path | None:
    """Walk continent -> country -> zone -> state -> district -> tehsil ->
    village, stopping at the deepest level that's both present in
    `location` and already exists as a real folder on disk."""
    location = location or {}
    continent = location.get("continent") or {}
    if not continent.get("id"):
        return None
    path = CONTINENTS_ROOT / _root_char_fix(continent["id"])
    if not path.exists():
        return None

    country = location.get("country") or {}
    if not country.get("id"):
        return path
    country_folder = _root_char_fix(country["id"])
    candidate = path / "Countries" / country_folder
    if not candidate.exists():
        return path
    path = candidate

    # Level containers are named per country on disk (India: Tehsils/Villages,
    # Nepal: LocalLevels/Wards, Bhutan: Chiwogs, ...), and some countries have
    # villages hanging straight off a district -- so find the child folder by
    # its own "<country>:<id>" name inside whichever container holds it,
    # skipping any level (e.g. tehsil) the location doesn't carry.
    for key, _container in _LOCATION_LEVELS:
        node = location.get(key)
        if not node or not node.get("id"):
            continue
        suffix = node["id"].split("/")[-1] if key == "zone" else node["id"]
        found = _find_child(path, f"{country_folder}:{suffix}")
        if found is None:
            break
        path = found

    return path


def _find_child(path: Path, child_name: str) -> Path | None:
    for container in path.iterdir():
        if container.name in _USER_CATEGORY_DIRS or ":" in container.name or not container.is_dir():
            continue
        candidate = container / child_name
        if candidate.exists():
            return candidate
    return None


def create_user_folder(location_dir: Path, category: str, element: str, user_id: str) -> Path:
    """<location_dir>/<category>/<Element>/<user_id>/{private,personal,public,global}_account/
    where category is "BORN_HERE" (at the birth location, keyed by Private ID)
    or "LIVING_HERE" (at the present location, keyed by Account ID)."""
    user_dir = location_dir / category / element / user_id
    for sub in SUB_ACCOUNTS:
        (user_dir / sub).mkdir(parents=True, exist_ok=True)
    return user_dir


def save_account_ids(private_user_dir: Path, account_id: str) -> None:
    """private_account/account_ids.json under a BORN_HERE user folder -- every
    Account ID ever linked to this Private ID (a user gets a new Account ID
    each time they move and re-register their present location)."""
    ids_file = private_user_dir / "private_account" / "account_ids.json"
    ids = []
    if ids_file.exists():
        with open(ids_file, "r", encoding="utf-8") as f:
            ids = json.load(f)
    if account_id not in ids:
        ids.append(account_id)
    with open(ids_file, "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=2, ensure_ascii=False)


def save_user_profile(user_dir: Path, profile: dict) -> None:
    profile_file = user_dir / "private_account" / "profile.json"
    with open(profile_file, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)


def save_change_request(user_dir: Path, request_data: dict) -> Path:
    """Queues an Edit Profile request for a human committee to review --
    nothing here approves or applies it, since there's no governance/
    council system built yet to actually do that review."""
    requests_dir = user_dir / "private_account" / "change_requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    request_file = requests_dir / f"{timestamp}.json"
    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(request_data, f, indent=2, ensure_ascii=False)
    return request_file


def register_user_folder(
    birth_location: dict, present_location: dict, element: str, profile: dict
) -> dict:
    """Create the real on-disk folders for a newly registered user: a
    BORN_HERE tree at the birth location (keyed by Private ID, with an
    account_ids.json listing every Account ID ever linked to it) and a
    LIVING_HERE tree at the present location (keyed by Account ID). Either
    half is skipped (None in the result) if its location can't be resolved
    to a real folder on this machine -- callers should treat that as a soft
    failure, not a registration error."""
    created_at = dt.datetime.utcnow().isoformat() + "Z"
    result = {"born_here": None, "living_here": None}

    birth_dir = resolve_location_dir(birth_location)
    if birth_dir is not None:
        born_user_dir = create_user_folder(birth_dir, "BORN_HERE", element, profile["private_id"])
        save_user_profile(born_user_dir, {**profile, "created_at": created_at})
        save_account_ids(born_user_dir, profile["account_id"])
        result["born_here"] = born_user_dir

    present_dir = resolve_location_dir(present_location)
    if present_dir is not None:
        living_user_dir = create_user_folder(present_dir, "LIVING_HERE", element, profile["account_id"])
        save_user_profile(living_user_dir, {**profile, "created_at": created_at})
        result["living_here"] = living_user_dir

    return result
