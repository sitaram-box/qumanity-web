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

# DOB-ID country digit (2026-11-25, the Founder's own decision): 1-9 for nine of the ten
# Indian Sub-continent countries (account_core.SUBCONTINENT_COUNTRY_IDS), 0 for everyone else on
# Earth -- Maldives included, despite being one of the ten Public-Account-Activation countries,
# since only nine digits were available alongside "0 = Rest of World".
_COUNTRY_DIGIT = {
    "O_AS_IND": "1",  # India
    "O_AS_NPL": "2",  # Nepal
    "O_AS_BTN": "3",  # Bhutan
    "O_AS_BGD": "4",  # Bangladesh
    "O_AS_MMR": "5",  # Myanmar
    "O_AS_LKA": "6",  # Sri Lanka
    "O_AS_PAK": "7",  # Pakistan
    "O_AS_BLC": "8",  # Balochistan
    "O_AS_AFG": "9",  # Afghanistan
    # O_AS_MDV (Maldives) and every other country id -> "0" (Rest of World), via the .get() default.
}

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
    """The 9-digit Private ID used to sign in: random, unique across all users, kept secret by its owner.

    Superseded by generate_dob_id() for new registrations (2026-11-25) -- kept here because
    identity_core.regenerate_private_code() (an admin-approved ID-correction path, unrelated to
    registration) still calls this, and migrating that path to DOB-IDs wasn't asked for and isn't
    done here."""
    import secrets
    for _ in range(max_attempts):
        code = f"{secrets.randbelow(10**9):09d}"
        if not conn.execute("SELECT 1 FROM users WHERE private_id_9digit = ?", (code,)).fetchone():
            return code
    raise RuntimeError("Could not generate a unique 9-digit Private ID")


def country_digit_for(country_id: str) -> str:
    """The single digit (0-9) generate_dob_id() prepends for a given birth_location country id.
    1-9 for nine of the ten Indian Sub-continent countries (account_core.SUBCONTINENT_COUNTRY_IDS);
    0 for every other country on Earth -- Maldives included, and birth_location has never been
    restricted to the Sub-continent list, see account_core.py's own docstring."""
    return _COUNTRY_DIGIT.get(country_id, "0")


def generate_dob_id(conn, dob: dt.date, country_digit: str, max_attempts: int = 10_000) -> str:
    """The new 9-digit Private ID (2026-11-25): country_digit + reversed(DDMMYYYY), decreasing by
    how many users already share this (dob, country_digit) pair until a free one is found.

    Deliberately string-based end to end until the final int() subtraction: DDMMYYYY is built with
    explicit zero-padding (not str(int)) and reversed as a string, so a year ending in 0 (one in
    ten of them) keeps its leading zero when the country digit is prepended -- casting the
    reversed date to int first, before prepending, would silently eat it (e.g. DOB 2000-01-01
    reverses to "00021010", not "21010").

    Counts against users.dob_id_country_digit (set alongside private_id_9digit by every caller),
    not a live re-derivation from birth_location_json, so the count query stays a plain indexed
    WHERE clause -- see migrations/047_dob_id_country_digit.py."""
    if country_digit not in "0123456789" or len(country_digit) != 1:
        raise ValueError("country_digit must be a single digit 0-9")

    ddmmyyyy = f"{dob.day:02d}{dob.month:02d}{dob.year:04d}"
    base_id_str = country_digit + ddmmyyyy[::-1]
    base_id = int(base_id_str)

    count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE dob = ? AND dob_id_country_digit = ?",
        (dob.isoformat(), country_digit),
    ).fetchone()[0]

    for offset in range(count, count + max_attempts):
        candidate_str = f"{base_id - offset:09d}"
        if candidate_str[0] != country_digit:
            # Underflowed past this country's 9-digit range. Cannot happen at realistic per-day
            # volumes (base_id is always 100,000,000+), but must not silently mint a wrong-country
            # or short ID rather than fail loudly.
            raise RuntimeError(f"DOB-ID space exhausted for dob={dob} country_digit={country_digit}")
        if not conn.execute(
            "SELECT 1 FROM users WHERE private_id_9digit = ?", (candidate_str,)
        ).fetchone():
            return candidate_str

    raise RuntimeError(f"Could not find a unique DOB-ID for dob={dob} country_digit={country_digit}")
