"""Private ID / Account ID generation.

Format: [RandomPrefix]-[Initials]-[GenderCode][AgeCode]-[ElementCode]-[LocationPath]
e.g.    X7K-RM-GM-A2-ZFL-CS.DL.1.1.10

Private ID is generated from birth_location (fixed, never changes once set).
Account ID is generated from present_location (can be regenerated if a user
moves — not built yet, since there's no login/session system to trigger it
from; see README's "Next phases").

Two deliberate deviations from the original brief's sample code:
- The brief's ElementCode table implies a per-sign code ("ZFL = Fire Leo"),
  but its own get_element_code() returns the SAME code for all three signs
  of an element (Aries/Leo/Sagittarius all -> "ZFL"). We follow the code,
  not the prose: ElementCode is element-only (4 possible values), reusing
  the tropical Sun-element already computed for the Fire/Earth/Air/Water
  governance system (elemental_core.py), not a second zodiac lookup.
- The brief's uniqueness check is an in-memory `set()`, which resets every
  process restart and isn't safe for a real persisted app. Uniqueness here
  is instead checked against the users table itself (private_id/account_id
  columns), so it holds across restarts and multiple workers.
"""

from __future__ import annotations

import datetime as dt
import random
import string

ELEMENT_CODE = {"Fire": "ZFL", "Earth": "ZEA", "Air": "ZAI", "Water": "ZWA"}

_GENDER_CODE = {"male": "GM", "female": "GF"}  # "both" (and anything else) -> GB


def gender_code(gender: str) -> str:
    return _GENDER_CODE.get((gender or "").lower(), "GB")


def age_code(dob: dt.date, as_of: dt.date | None = None) -> str:
    """Age is frozen at registration time — an ID's age code never changes
    later, matching the brief's "Private ID is fixed" rule."""
    as_of = as_of or dt.date.today()
    age = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
    if age < 25:
        return "A1"
    if age < 50:
        return "A2"
    if age < 76:
        return "A3"
    return "A4"


def element_code(element: str) -> str:
    return ELEMENT_CODE.get(element, "ZFL")


def location_path_for(location: dict | None) -> str:
    """Python port of location_select.js's locationPath(): each level's id
    is already the full hierarchical path (e.g. a village id like
    "CS.DL.1.1.10" already encodes zone/state/district/tehsil), so the path
    is just the deepest selected level's id — never a concatenation of
    several levels' ids (see location_select.js's own comment on this)."""
    location = location or {}
    for key in ("village", "tehsil", "district", "state", "zone", "country", "continent"):
        node = location.get(key)
        if node and node.get("id"):
            return node["id"]
    return ""


def _random_prefix(length: int = 3) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "XX"
    first = parts[0][0].upper()
    last = parts[-1][0].upper() if len(parts) > 1 else parts[0][-1].upper()
    return first + last


def _build_id(name, gender, dob, tob, element, location) -> str:
    return "-".join([
        _random_prefix(),
        _initials(name),
        gender_code(gender) + age_code(dob),
        element_code(element),
        location_path_for(location),
    ])


def _generate_unique(conn, column: str, name, gender, dob, tob, element, location, max_attempts=20) -> str:
    for _ in range(max_attempts):
        candidate = _build_id(name, gender, dob, tob, element, location)
        exists = conn.execute(
            f"SELECT 1 FROM users WHERE {column} = ?", (candidate,)
        ).fetchone()
        if not exists:
            return candidate
    raise RuntimeError(f"Could not generate a unique {column} after {max_attempts} attempts")


def generate_private_id(conn, name, gender, dob, tob, element, birth_location) -> str:
    return _generate_unique(conn, "private_id", name, gender, dob, tob, element, birth_location)


def generate_account_id(conn, name, gender, dob, tob, element, present_location) -> str:
    return _generate_unique(conn, "account_id", name, gender, dob, tob, element, present_location)


def generate_private_code(conn, max_attempts=200) -> str:
    """The 9-digit Private ID used to sign in: random, unique across all users, kept secret by its owner."""
    import secrets
    for _ in range(max_attempts):
        code = f"{secrets.randbelow(10**9):09d}"
        if not conn.execute("SELECT 1 FROM users WHERE private_id_9digit = ?", (code,)).fetchone():
            return code
    raise RuntimeError("Could not generate a unique 9-digit Private ID")
