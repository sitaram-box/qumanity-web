"""Village Council elections — piloted on ONE village (see
`Qbox-Notes.txt`, "Please write cursor prompt to build a voting system in
Public Account - Village id..."). Each zodiac sign runs its own ~1-month
cycle: a 7-day nomination window, then a 14-day voting window, electing one
Male "Nayak" and one Female "Nayika" for that sign's council seat (24 seats
across a full year, repeating annually).

Scoped to PILOT_VILLAGE_ID rather than every village, per the product
decision to pilot first — the old prototype did the same thing (hardcoded
to a single demo village). Everything here takes a village_id parameter
rather than assuming the constant, so lifting that restriction later is a
matter of passing a different id in, not restructuring this module.
"""

from __future__ import annotations

import datetime as dt
import json

import id_generator
import karma_core
import wallet_core
from zodiac_core import ZODIAC_RANGES

# Same village the old Qumanity prototype used as its election pilot
# ("Rohini Sector-24", Delhi) — also where this project's own test users
# already live.
PILOT_VILLAGE_ID = "CS.DL.3.4.1A"  # Rohini Sector 24, Bawana, North West Delhi -- corrected 2026-09-28 (was CS.DL.5.4.1E, a village-id collision from the old SITAXML-derived India data; see docs/india_location_fix.md)

# The monthly 4-week rhythm of a sign's cycle (founder, 2026-09-29):
#   week 1  (8 days from the sign's start)  candidates come forward   e.g. Libra 23-30 Sep
#   weeks 2-3 (14 days)                     voting                    e.g. Libra 1-14 Oct
#   week 4  (to the end of the sign)        results; winners serve 1 year   e.g. Libra 15-22 Oct
NOMINATION_DAYS = 8
VOTING_DAYS = 14
TERM_DAYS = 365
CANDIDATES_PER_GENDER = 3

_SIGN_ORDER = [z["sign"] for z in ZODIAC_RANGES]
_SIGN_BY_NAME = {z["sign"]: z for z in ZODIAC_RANGES}


def ensure_council_columns(conn) -> None:
    """In-place migrations for columns added after election_candidates/village_council were first
    created (those two tables plus election_cycles/election_votes predate this codebase -- there is
    no CREATE TABLE for them anywhere, they already exist live in the DB -- so new fields are always
    added this way, matching app.py's own _ensure_user_columns() pattern)."""
    cand_cols = {r["name"] for r in conn.execute("PRAGMA table_info(election_candidates)")}
    for col, ddl in (
        ("form_reason", "TEXT"), ("form_why_vote", "TEXT"), ("form_changes", "TEXT"), ("form_past_work", "TEXT"),
    ):
        if col not in cand_cols:
            conn.execute(f"ALTER TABLE election_candidates ADD COLUMN {col} {ddl}")
    council_cols = {r["name"] for r in conn.execute("PRAGMA table_info(village_council)")}
    for col, ddl in (
        ("training_start", "TEXT"), ("training_end", "TEXT"),
        ("leadership_start", "TEXT"), ("leadership_end", "TEXT"),
    ):
        if col not in council_cols:
            conn.execute(f"ALTER TABLE village_council ADD COLUMN {col} {ddl}")
    conn.commit()


def council_term_status(council_row: dict, today: dt.date | None = None) -> str:
    """'leadership' | 'completed', derived from a village_council row's own 1-year term
    (leadership_start/leadership_end, see _winner_term()/TERM_DAYS -- there is no separate
    training phase any more)."""
    today = today or dt.date.today()
    ls, le = council_row.get("leadership_start"), council_row.get("leadership_end")
    if ls and le and dt.date.fromisoformat(ls) <= today <= dt.date.fromisoformat(le):
        return "leadership"
    if ls and today < dt.date.fromisoformat(ls):
        return "leadership"
    return "completed"


def _sign_window(sign: str, today: dt.date) -> tuple[dt.date, dt.date]:
    """The (start, end) dates of THIS occurrence of `sign`'s tropical date
    range — the one containing (or nearest upcoming to) `today`. Handles
    Capricorn's year-wrap (Dec 22 -> Jan 19)."""
    z = _SIGN_BY_NAME[sign]
    sm, sd = (int(p) for p in z["start"].split("-"))
    em, ed = (int(p) for p in z["end"].split("-"))
    if (sm, sd) <= (em, ed):
        start = dt.date(today.year, sm, sd)
        end = dt.date(today.year, em, ed)
        if end < start:  # shouldn't happen for non-wrapping signs, but stay safe
            end = dt.date(today.year + 1, em, ed)
    else:  # Capricorn: wraps the New Year
        if today.month == 1:
            start = dt.date(today.year - 1, sm, sd)
            end = dt.date(today.year, em, ed)
        else:
            start = dt.date(today.year, sm, sd)
            end = dt.date(today.year + 1, em, ed)
    return start, end


def current_cycle_for_village(conn, village_id: str, today: dt.date | None = None) -> dict:
    """Get-or-create today's active election_cycles row for this village,
    recomputing its status (nomination/voting/closed) from today's date.
    Tallies and writes village_council results the first time a cycle is
    seen as closed."""
    today = today or dt.date.today()
    tropical = None
    for z in ZODIAC_RANGES:
        sm, sd = (int(p) for p in z["start"].split("-"))
        em, ed = (int(p) for p in z["end"].split("-"))
        date_str = f"{today.month:02d}-{today.day:02d}"
        if sm <= em:
            if z["start"] <= date_str <= z["end"]:
                tropical = z
                break
        else:
            if date_str >= z["start"] or date_str <= z["end"]:
                tropical = z
                break
    sign, element = tropical["sign"], tropical["element"]
    start, _end = _sign_window(sign, today)
    nomination_start = start
    nomination_end = start + dt.timedelta(days=NOMINATION_DAYS - 1)
    voting_start = nomination_end + dt.timedelta(days=1)
    voting_end = voting_start + dt.timedelta(days=VOTING_DAYS - 1)
    year = start.year

    row = conn.execute(
        """SELECT * FROM election_cycles WHERE village_id = ? AND zodiac_sign = ? AND year = ?""",
        (village_id, sign, year),
    ).fetchone()
    if not row:
        conn.execute(
            """INSERT INTO election_cycles
               (village_id, zodiac_sign, element, year, nomination_start, nomination_end,
                voting_start, voting_end, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'nomination')""",
            (village_id, sign, element, year, nomination_start.isoformat(), nomination_end.isoformat(),
             voting_start.isoformat(), voting_end.isoformat()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM election_cycles WHERE village_id = ? AND zodiac_sign = ? AND year = ?",
            (village_id, sign, year),
        ).fetchone()

    if (row["nomination_end"], row["voting_start"], row["voting_end"]) != (
        nomination_end.isoformat(), voting_start.isoformat(), voting_end.isoformat()
    ) and not conn.execute("SELECT 1 FROM election_votes WHERE election_cycle_id = ? LIMIT 1", (row["id"],)).fetchone():
        conn.execute(
            "UPDATE election_cycles SET nomination_start = ?, nomination_end = ?, voting_start = ?, voting_end = ? WHERE id = ?",
            (nomination_start.isoformat(), nomination_end.isoformat(), voting_start.isoformat(), voting_end.isoformat(), row["id"]),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM election_cycles WHERE id = ?", (row["id"],)).fetchone()

    if today <= nomination_end:
        status = "nomination"
    elif today <= voting_end:
        status = "voting"
    else:
        status = "closed"

    if status != row["status"]:
        conn.execute("UPDATE election_cycles SET status = ? WHERE id = ?", (status, row["id"]))
        conn.commit()

    cycle = dict(row)
    cycle["status"] = status
    if status == "closed":
        _ensure_tallied(conn, cycle)
        winner_row = conn.execute(
            "SELECT male_winner_user_id, female_winner_user_id FROM election_cycles WHERE id = ?", (cycle["id"],)
        ).fetchone()
        cycle["male_winner_user_id"] = winner_row["male_winner_user_id"]
        cycle["female_winner_user_id"] = winner_row["female_winner_user_id"]
    return cycle


def _ensure_tallied(conn, cycle: dict) -> None:
    ensure_council_columns(conn)
    existing = conn.execute(
        "SELECT 1 FROM village_council WHERE village_id = ? AND zodiac_sign = ? AND year = ?",
        (cycle["village_id"], cycle["zodiac_sign"], cycle["year"]),
    ).fetchone()
    if existing:
        return

    winners = {}
    for gender in ("male", "female"):
        row = conn.execute(
            """SELECT candidate_user_id, COUNT(*) AS votes FROM election_votes
               WHERE election_cycle_id = ? AND gender = ?
               GROUP BY candidate_user_id ORDER BY votes DESC, MIN(id) ASC LIMIT 1""",
            (cycle["id"], gender),
        ).fetchone()
        winners[gender] = row["candidate_user_id"] if row else None

    # Winners lead immediately, no separate training phase: a "Work-time validity of 1 year"
    # starting the day after voting closes (founder, 2026-09-29 -- see _winner_term()/TERM_DAYS,
    # which election_summary() already uses for the same figure). There is no training window any
    # more, so training_start/training_end are left NULL; council_term_status() treats a row with
    # no training dates and a leadership window as either "leadership" or "completed".
    leadership_start, leadership_end = _winner_term(cycle)

    conn.execute(
        """INSERT INTO village_council
           (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, election_cycle_id,
            leadership_start, leadership_end)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cycle["village_id"], cycle["zodiac_sign"], cycle["year"], winners["male"], winners["female"], cycle["id"],
         leadership_start, leadership_end),
    )
    conn.execute(
        "UPDATE election_cycles SET male_winner_user_id = ?, female_winner_user_id = ? WHERE id = ?",
        (winners["male"], winners["female"], cycle["id"]),
    )
    conn.commit()


def _present_village_id(user_row) -> str | None:
    loc = json.loads(user_row["present_location_json"])
    village = loc.get("village")
    return village["id"] if village else None


def _age_years(dob_iso: str, today: dt.date) -> int:
    dob = dt.date.fromisoformat(dob_iso)
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def nomination_eligible(conn, user_row, cycle: dict) -> tuple[bool, str]:
    if _present_village_id(user_row) != cycle["village_id"]:
        return False, "Nomination is only open to residents of this pilot village."
    age = _age_years(user_row["dob"], dt.date.today())
    if age < 25 or age > 60:
        return False, "Candidates must be Yuvak or Vridh, aged 25 to 60."
    zodiac = conn.execute("SELECT sun_sign FROM user_zodiac WHERE user_id = ?", (user_row["id"],)).fetchone()
    if not zodiac or zodiac["sun_sign"] != cycle["zodiac_sign"]:
        return False, f"Only members born under {cycle['zodiac_sign']} can stand in this cycle."
    if (user_row["gender"] or "").lower() not in ("male", "female"):
        return False, "Nomination is open to Male and Female candidates only."
    return True, ""


def voting_eligible(conn, user_row, cycle: dict, today: dt.date | None = None) -> tuple[bool, str]:
    """Village cycles: residents born under THIS cycle's sign vote (docs/voting_logic.md) -- men for the
    male seat, women for the female seat; third-gender members by their present gender."""
    if _present_village_id(user_row) != cycle["village_id"]:
        return False, "Voting is only open to residents of this pilot village."
    today = today or dt.date.today()
    if _age_years(user_row["dob"], today) < 5:
        return False, "Voting is open to members aged 5 and up."
    zodiac = conn.execute("SELECT sun_sign FROM user_zodiac WHERE user_id = ?", (user_row["id"],)).fetchone()
    if not zodiac or zodiac["sun_sign"] != cycle["zodiac_sign"]:
        return False, f"Only members born under {cycle['zodiac_sign']} vote in this cycle."
    return True, ""


def nominate(conn, user_row, reason: str, why_vote: str, changes: str, past_work: str = "") -> dict:
    """The 4-question candidacy form: why they're running, why members should vote for them, what
    they'd change, and (optionally) past work. `manifest` (the old single free-text field) is kept
    populated from `reason` so any legacy reader still sees something sensible."""
    ensure_council_columns(conn)
    cycle = current_cycle_for_village(conn, PILOT_VILLAGE_ID)
    if cycle["status"] != "nomination":
        raise ValueError("Nomination is closed for the current cycle.")
    ok, elig_reason = nomination_eligible(conn, user_row, cycle)
    if not ok:
        raise ValueError(elig_reason)
    reason, why_vote, changes = reason.strip(), why_vote.strip(), changes.strip()
    if not reason or not why_vote or not changes:
        raise ValueError("Please answer why you're running, why members should vote for you, and what you'd change.")
    existing = conn.execute(
        "SELECT 1 FROM election_candidates WHERE election_cycle_id = ? AND user_id = ?",
        (cycle["id"], user_row["id"]),
    ).fetchone()
    if existing:
        raise ValueError("You've already submitted a nomination for this cycle.")
    if _gender_full(conn, cycle["id"], user_row["gender"]):
        raise ValueError(f"This month's {CANDIDATES_PER_GENDER} {user_row['gender'].lower()} candidates have already been chosen.")
    conn.execute(
        """INSERT INTO election_candidates
           (election_cycle_id, user_id, gender, manifest, form_reason, form_why_vote, form_changes, form_past_work)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cycle["id"], user_row["id"], user_row["gender"].lower(), reason,
         reason, why_vote, changes, (past_work or "").strip()),
    )
    conn.commit()
    return cycle


def candidates_for_cycle(conn, cycle_id: int) -> dict:
    ensure_council_columns(conn)
    rows = conn.execute(
        """SELECT ec.id, ec.user_id, ec.gender, ec.manifest, ec.status, ec.form_reason, ec.form_why_vote,
                  ec.form_changes, ec.form_past_work, u.name
           FROM election_candidates ec JOIN users u ON u.id = ec.user_id
           WHERE ec.election_cycle_id = ? AND ec.status = 'approved'
           ORDER BY u.name""",
        (cycle_id,),
    ).fetchall()
    result = {"male": [], "female": []}
    for r in rows:
        candidate = dict(r)
        candidate["karma"] = karma_core.individual_karma_score(conn, r["user_id"])
        result.setdefault(r["gender"], []).append(candidate)
    return result


def cast_vote(conn, user_row, candidate_user_id: int, gender: str, today: dt.date | None = None) -> None:
    cycle = current_cycle_for_village(conn, PILOT_VILLAGE_ID, today)
    if cycle["status"] != "voting":
        raise ValueError("Voting is not open for the current cycle.")
    ok, reason = voting_eligible(conn, user_row, cycle, today)
    if not ok:
        raise ValueError(reason)
    candidate = conn.execute(
        "SELECT status, gender FROM election_candidates WHERE election_cycle_id = ? AND user_id = ?",
        (cycle["id"], candidate_user_id),
    ).fetchone()
    if not candidate or candidate["status"] != "approved":
        raise ValueError("That candidate isn't approved for this cycle.")
    if candidate["gender"] != gender:
        raise ValueError("Candidate/gender mismatch.")
    voter_gender = (user_row["gender"] or "").lower()
    if voter_gender in ("male", "female") and voter_gender != gender:
        raise ValueError("Men vote for male candidates and women for female candidates.")
    already = conn.execute(
        "SELECT 1 FROM election_votes WHERE election_cycle_id = ? AND voter_user_id = ? AND gender = ?",
        (cycle["id"], user_row["id"], gender),
    ).fetchone()
    if already:
        raise ValueError(f"You've already voted for {gender} in this cycle.")

    is_first_vote_ever = not conn.execute(
        "SELECT 1 FROM election_votes WHERE voter_user_id = ? LIMIT 1", (user_row["id"],)
    ).fetchone()

    conn.execute(
        """INSERT INTO election_votes (election_cycle_id, voter_user_id, candidate_user_id, gender)
           VALUES (?, ?, ?, ?)""",
        (cycle["id"], user_row["id"], candidate_user_id, gender),
    )
    conn.commit()

    if is_first_vote_ever:
        wallet_core.unlock_user_share(conn, user_row["id"])


def council_roster(conn, village_id: str) -> list[dict]:
    ensure_council_columns(conn)
    rows = conn.execute(
        """SELECT vc.zodiac_sign, vc.year, vc.male_head_user_id, vc.female_head_user_id,
                  mu.name AS male_head_name, fu.name AS female_head_name,
                  vc.training_start, vc.training_end, vc.leadership_start, vc.leadership_end
           FROM village_council vc
           LEFT JOIN users mu ON mu.id = vc.male_head_user_id
           LEFT JOIN users fu ON fu.id = vc.female_head_user_id
           WHERE vc.village_id = ?
           ORDER BY vc.year DESC,
                    CASE vc.zodiac_sign
                        WHEN 'Aries' THEN 1 WHEN 'Taurus' THEN 2 WHEN 'Gemini' THEN 3 WHEN 'Cancer' THEN 4
                        WHEN 'Leo' THEN 5 WHEN 'Virgo' THEN 6 WHEN 'Libra' THEN 7 WHEN 'Scorpio' THEN 8
                        WHEN 'Sagittarius' THEN 9 WHEN 'Capricorn' THEN 10 WHEN 'Aquarius' THEN 11 WHEN 'Pisces' THEN 12
                    END""",
        (village_id,),
    ).fetchall()
    out = []
    for r in rows:
        seat = dict(r)
        seat["term_status"] = council_term_status(seat)
        if seat["male_head_user_id"]:
            seat["male_head_karma"] = karma_core.individual_karma_score(conn, seat["male_head_user_id"])
        if seat["female_head_user_id"]:
            seat["female_head_karma"] = karma_core.individual_karma_score(conn, seat["female_head_user_id"])
        out.append(seat)
    return out


# ---- Private, optional election-history record (Lok Sabha / Vidhan Sabha) ----
# Q-Punch history needs no free-text field -- it is read straight from the ballots the user
# really cast (election_votes) plus the tallied result (village_council), so nothing here can
# be typed inconsistently with what actually happened.

# Three real-party options per country -- the ruling-side alliance, the main opposition alliance,
# and "everyone else" (independents, regional parties, NOTA/boycott). Researched per-country for
# the 10 Indian Sub-continent countries (2026-09-28); India's own 3 are the founder's exact
# wording. "Not Voted" is appended automatically for every country by parties_for_country() below,
# as a 4th, explicit option -- distinct from simply leaving a year unanswered.
PARTIES_BY_COUNTRY = {
    # Checked against each country's latest national election (2026-09-29):
    # Nepal Mar 2026 (RSP majority; NC, CPN-UML next), Bangladesh Feb 2026 (BNP; Jamaat-e-Islami
    # opposition; Awami League banned), Sri Lanka Nov 2024 (NPP; SJB), Pakistan Feb 2024 (PML-N-led
    # government; PTI opposition; PPP), Balochistan assembly 2024 (PPP, PML-N, JUI-F), Bhutan Jan 2024
    # (PDP; BTP), Maldives Apr 2024 (PNC; MDP), Myanmar 2025-26 junta-run vote (USDP; NLD dissolved).
    "IND": [("BJP", "BJP / NDA Alliance"), ("INC", "INC / INDIA Alliance"), ("OTH", "OTH / Independent / Regional / NOTA")],
    "NPL": [("RSP", "Rastriya Swatantra Party"), ("NC", "Nepali Congress"), ("OTH", "CPN-UML / NCP / Other")],
    "BGD": [("BNP", "BNP"), ("JI", "Jamaat-e-Islami"), ("OTH", "NCP / Jatiya Party / Other")],
    "LKA": [("NPP", "NPP (National People's Power)"), ("SJB", "SJB"), ("OTH", "SLPP / UNP / Other")],
    "PAK": [("PMLN", "PML-N"), ("PTI", "PTI"), ("OTH", "PPP / Other")],
    "BLC": [("PPP", "PPP"), ("PMLN", "PML-N"), ("OTH", "JUI-F / BNP / PTI / Other")],
    "BTN": [("PDP", "PDP"), ("BTP", "Bhutan Tendrel Party"), ("OTH", "DPT / DNT / Other")],
    "MDV": [("PNC", "PNC"), ("MDP", "MDP"), ("OTH", "The Democrats / JP / Other")],
    "AFG": [("OTH", "OTH / no elections currently held")],
    "MMR": [("USDP", "USDP"), ("NLD", "NLD / NUG"), ("OTH", "Other")],
}
DEFAULT_PARTIES = PARTIES_BY_COUNTRY["IND"]
NOT_VOTED = ("NOTVOTED", "Not Voted")


def parties_for_country(country_code: str):
    base = PARTIES_BY_COUNTRY.get((country_code or "").upper(), DEFAULT_PARTIES)
    return [*base, NOT_VOTED]


# ---- Election cycle config: which years Lok Sabha shows (past 2 + next 1), council-editable ----
# Seeded per country with a 5-year term by default (India's real cycle); a country whose real
# interval differs, or whose most recent election year needs correcting, is fixed by editing this
# row via /api/admin/election-cycle -- never by editing this file.
CYCLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS election_cycle_config (
    country_code TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- 'loksabha' (only Lok Sabha uses fixed, nationwide years)
    last_election_year INTEGER NOT NULL,
    interval_years INTEGER NOT NULL,
    updated_by INTEGER,
    updated_at TEXT,
    PRIMARY KEY (country_code, kind)
);
"""
DEFAULT_LAST_ELECTION_YEAR = 2024
DEFAULT_INTERVAL_YEARS = 5


def ensure_cycle_table(conn):
    conn.executescript(CYCLE_SCHEMA)
    conn.commit()


def get_cycle_config(conn, country_code: str, kind: str = "loksabha") -> dict:
    ensure_cycle_table(conn)
    country_code = (country_code or "IND").upper()
    row = conn.execute(
        "SELECT * FROM election_cycle_config WHERE country_code = ? AND kind = ?", (country_code, kind)
    ).fetchone()
    if row:
        return {"country_code": country_code, "kind": kind, "last_election_year": row["last_election_year"], "interval_years": row["interval_years"]}
    return {"country_code": country_code, "kind": kind, "last_election_year": DEFAULT_LAST_ELECTION_YEAR, "interval_years": DEFAULT_INTERVAL_YEARS}


def set_cycle_config(conn, country_code: str, kind: str, last_election_year, interval_years, updated_by: int) -> None:
    ensure_cycle_table(conn)
    try:
        last_election_year = int(last_election_year)
        interval_years = int(interval_years)
    except (TypeError, ValueError):
        raise ValueError("last_election_year and interval_years must both be whole numbers")
    if interval_years < 1:
        raise ValueError("The interval between elections must be at least 1 year")
    if last_election_year < 1900 or last_election_year > 2200:
        raise ValueError("last_election_year looks wrong")
    conn.execute(
        """INSERT INTO election_cycle_config (country_code, kind, last_election_year, interval_years, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(country_code, kind) DO UPDATE SET last_election_year=excluded.last_election_year,
             interval_years=excluded.interval_years, updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP""",
        ((country_code or "IND").upper(), kind, int(last_election_year), int(interval_years), updated_by),
    )
    conn.commit()


def loksabha_years(conn, country_code: str, today: dt.date | None = None) -> list[int]:
    """[previous, most-recent, next] election years -- always exactly 2 past + 1 upcoming, rolling
    forward automatically once the "next" year shown has itself passed. E.g. today inside
    2026-2029 -> [2019, 2024, 2029]; today in 2030+ -> [2024, 2029, 2034]."""
    today = today or dt.date.today()
    cfg = get_cycle_config(conn, country_code, "loksabha")
    last, interval = cfg["last_election_year"], cfg["interval_years"]
    nxt = last + interval
    while today.year > nxt:
        last, nxt = nxt, nxt + interval
    return [last - interval, last, nxt]


def all_cycle_configs(conn) -> list[dict]:
    """Every country's Lok Sabha cycle config (seeded defaults included), for the admin/council screen."""
    ensure_cycle_table(conn)
    rows = {r["country_code"]: dict(r) for r in conn.execute("SELECT * FROM election_cycle_config WHERE kind = 'loksabha'")}
    out = []
    for code in PARTIES_BY_COUNTRY:
        if code in rows:
            out.append({"country_code": code, "last_election_year": rows[code]["last_election_year"], "interval_years": rows[code]["interval_years"]})
        else:
            out.append({"country_code": code, "last_election_year": DEFAULT_LAST_ELECTION_YEAR, "interval_years": DEFAULT_INTERVAL_YEARS})
    return out


# ---- The user's own recorded answers, one row per (user, kind, slot) so the Lok Sabha years can
# roll forward (see loksabha_years above) without ever needing a schema change. `slot` is a year
# ("2024") for Lok Sabha, or "last"/"next" for Vidhan Sabha (which has no fixed, nationwide years).
ENTRIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS election_history_entries (
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    slot TEXT NOT NULL,
    choice TEXT NOT NULL,
    updated_at TEXT,
    PRIMARY KEY (user_id, kind, slot)
);
"""


def ensure_history_table(conn):
    conn.executescript(ENTRIES_SCHEMA)
    conn.commit()


def get_party_history(conn, user_id: int, country_code: str = "IND") -> dict:
    ensure_history_table(conn)
    years = loksabha_years(conn, country_code)
    rows = {r["slot"]: r["choice"] for r in conn.execute(
        "SELECT slot, choice FROM election_history_entries WHERE user_id = ? AND kind = ?", (user_id, "loksabha")
    )}
    vs_rows = {r["slot"]: r["choice"] for r in conn.execute(
        "SELECT slot, choice FROM election_history_entries WHERE user_id = ? AND kind = ?", (user_id, "vidhansabha")
    )}
    return {
        "loksabha_years": years,
        "loksabha": {str(y): rows.get(str(y)) for y in years},
        "vidhansabha": {"last": vs_rows.get("last"), "next": vs_rows.get("next")},
    }


def save_party_history(conn, user_id: int, data: dict, country_code: str = "IND") -> None:
    ensure_history_table(conn)
    valid = {code for code, _ in parties_for_country(country_code)}
    years = loksabha_years(conn, country_code)
    entries = []  # (kind, slot, choice)
    for y in years:
        v = (data.get("loksabha") or {}).get(str(y))
        if v:
            if v not in valid:
                raise ValueError(f"{v} is not a recognised choice for this country")
            entries.append(("loksabha", str(y), v))
    vs = data.get("vidhansabha") or {}
    for slot in ("last", "next"):
        v = vs.get(slot)
        if v:
            if v not in valid:
                raise ValueError(f"{v} is not a recognised choice for this country")
            entries.append(("vidhansabha", slot, v))
    for kind, slot, choice in entries:
        conn.execute(
            """INSERT INTO election_history_entries (user_id, kind, slot, choice, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, kind, slot) DO UPDATE SET choice=excluded.choice, updated_at=CURRENT_TIMESTAMP""",
            (user_id, kind, slot, choice),
        )
    # A slot cleared back to "no answer" in this save is deleted rather than stored as empty.
    for kind, slot_field, slots in (("loksabha", "loksabha", [str(y) for y in years]), ("vidhansabha", "vidhansabha", ["last", "next"])):
        sent = data.get(slot_field) or {}
        for slot in slots:
            if slot in sent and not sent[slot]:
                conn.execute("DELETE FROM election_history_entries WHERE user_id = ? AND kind = ? AND slot = ?", (user_id, kind, slot))
    conn.commit()


def qpunch_history(conn, user_id: int) -> list[dict]:
    """Every Q-Punch ballot this user has really cast, newest first, with whether that candidate won."""
    rows = conn.execute(
        """SELECT ec.zodiac_sign, ec.year, ev.voted_at, cand.name AS candidate_name, ev.candidate_user_id, ev.gender,
                  vc.male_head_user_id, vc.female_head_user_id
           FROM election_votes ev
           JOIN election_cycles ec ON ec.id = ev.election_cycle_id
           JOIN users cand ON cand.id = ev.candidate_user_id
           LEFT JOIN village_council vc ON vc.election_cycle_id = ec.id
           WHERE ev.voter_user_id = ? ORDER BY ev.voted_at DESC""",
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        won = r["candidate_user_id"] in (r["male_head_user_id"], r["female_head_user_id"])
        out.append({"year": r["year"], "sign": r["zodiac_sign"], "candidate": r["candidate_name"], "gender": r["gender"], "at": r["voted_at"], "won": bool(won)})
    return out


# ---- Aggregate sentiment: Lok-Sabha-equivalent on a Country page, Vidhan-Sabha-equivalent on a
# State page. Never shown at Village/Tehsil/District/Zone/Continent/Earth, and never per-person --
# only the % breakdown, from whoever in that place chose to record a 2029/next-election answer. ----

def loksabha_aggregate(conn, country_id: str, country_code: str):
    rows = conn.execute(
        """SELECT eh.loksabha_2029 AS choice FROM election_history eh JOIN users u ON u.id = eh.user_id
           WHERE json_extract(u.present_location_json, '$.country.id') = ? AND eh.loksabha_2029 IS NOT NULL""",
        (country_id,),
    ).fetchall()
    return _breakdown(rows, country_code)


def vidhansabha_aggregate(conn, state_id: str, country_code: str):
    rows = conn.execute(
        """SELECT eh.vidhansabha_next AS choice FROM election_history eh JOIN users u ON u.id = eh.user_id
           WHERE json_extract(u.present_location_json, '$.state.id') = ? AND eh.vidhansabha_next IS NOT NULL""",
        (state_id,),
    ).fetchall()
    return _breakdown(rows, country_code)


def _breakdown(rows, country_code):
    parties = parties_for_country(country_code)
    total = len(rows)
    counts = {code: 0 for code, _ in parties}
    for r in rows:
        if r["choice"] in counts:
            counts[r["choice"]] += 1
    return {"total_responses": total,
            "parties": [{"code": code, "label": label, "count": counts[code],
                        "pct": round(100 * counts[code] / total) if total else 0} for code, label in parties]}


# ---- The monthly 4-week election rhythm: timeline, per-member guide, Q-Punch summary ----------------

def election_weeks(cycle: dict) -> list[dict]:
    """The 4 steps of a sign's cycle with their real dates."""
    nom_s, nom_e = dt.date.fromisoformat(cycle["nomination_start"]), dt.date.fromisoformat(cycle["nomination_end"])
    vot_s, vot_e = dt.date.fromisoformat(cycle["voting_start"]), dt.date.fromisoformat(cycle["voting_end"])
    _s, sign_end = _sign_window(cycle["zodiac_sign"], nom_s)
    res_s = vot_e + dt.timedelta(days=1)
    sign = cycle["zodiac_sign"]
    return [
        {"week": 1, "key": "nomination", "title": "Candidates come forward", "start": nom_s.isoformat(), "end": nom_e.isoformat(),
         "text": f"{sign} men and women aged 25-60 living here stand as candidates and share their record, promises and plans."},
        {"week": 2, "key": "voting", "title": "Voting opens", "start": vot_s.isoformat(), "end": (vot_s + dt.timedelta(days=6)).isoformat(),
         "text": f"Every {sign} member aged 5+ living here votes once: men for a male candidate, women for a female candidate."},
        {"week": 3, "key": "voting", "title": "Voting continues", "start": (vot_s + dt.timedelta(days=7)).isoformat(), "end": vot_e.isoformat(),
         "text": "Read each candidate's record before you choose. Voting closes at the end of this week."},
        {"week": 4, "key": "results", "title": "Results & new leaders", "start": res_s.isoformat(), "end": max(sign_end, res_s).isoformat(),
         "text": f"The man and woman with the most votes become the {sign} leaders of the village for one year."},
    ]


def current_week(cycle: dict, today: dt.date | None = None) -> int:
    today = (today or dt.date.today()).isoformat()
    for w in election_weeks(cycle):
        if w["start"] <= today <= w["end"]:
            return w["week"]
    return 4 if today > election_weeks(cycle)[-1]["end"] else 1


def _winner_term(cycle: dict) -> tuple[str, str]:
    start = dt.date.fromisoformat(cycle["voting_end"]) + dt.timedelta(days=1)
    return start.isoformat(), (start + dt.timedelta(days=TERM_DAYS - 1)).isoformat()


def _next_cycle_start(sign: str, today: dt.date) -> str:
    """Start date of `sign`'s current cycle if it is running, else of its next one."""
    start, end = _sign_window(sign, today)
    if end < today:  # this occurrence is over: the next one (mid-year anchors avoid Feb 29 and Capricorn's wrap)
        start, _ = _sign_window(sign, dt.date(today.year, 6, 1))
        if start <= today:
            start, _ = _sign_window(sign, dt.date(today.year + 1, 6, 1))
    return start.isoformat()


def _gender_full(conn, cycle_id: int, gender: str) -> bool:
    """Each month has at most CANDIDATES_PER_GENDER approved candidates per gender."""
    return conn.execute("SELECT COUNT(*) FROM election_candidates WHERE election_cycle_id = ? AND gender = ? AND status = 'approved'",
                        (cycle_id, (gender or "").lower())).fetchone()[0] >= CANDIDATES_PER_GENDER


def member_guide(conn, user_row, cycle: dict, today: dt.date | None = None) -> dict:
    """What THIS member should know and do in this month's cycle -- the education shown in Q-Punch
    and counted in the notification bell when there is something to do."""
    today = today or dt.date.today()
    week = current_week(cycle, today)
    z = conn.execute("SELECT sun_sign FROM user_zodiac WHERE user_id = ?", (user_row["id"],)).fetchone()
    my_sign = z["sun_sign"] if z else None
    in_village = _present_village_id(user_row) == cycle["village_id"]
    sign = cycle["zodiac_sign"]
    nominated = bool(conn.execute("SELECT 1 FROM election_candidates WHERE election_cycle_id = ? AND user_id = ?",
                                  (cycle["id"], user_row["id"])).fetchone())
    voted = [r["gender"] for r in conn.execute("SELECT gender FROM election_votes WHERE election_cycle_id = ? AND voter_user_id = ?",
                                               (cycle["id"], user_row["id"]))]
    can_stand, stand_reason = nomination_eligible(conn, user_row, cycle)
    if can_stand and _gender_full(conn, cycle["id"], user_row["gender"]):
        can_stand, stand_reason = False, f"This month's {CANDIDATES_PER_GENDER} {(user_row['gender'] or '').lower()} candidates have been chosen."
    can_vote, vote_reason = voting_eligible(conn, user_row, cycle, today)
    action = None
    if not in_village:
        role, text = "outside", "This village's election is for the people living here."
    elif my_sign != sign:
        role = "watch"
        text = (f"This month is {sign}'s election. Yours ({my_sign}) begins on {_next_cycle_start(my_sign, today)}: "
                "you'll be invited to stand as a candidate in week 1 and to vote in weeks 2-3.") if my_sign else f"This month is {sign}'s election."
    elif cycle["status"] == "nomination":
        if nominated:
            role, text = "candidate", "You are a candidate this month. Voting runs in weeks 2-3."
        elif can_stand:
            role, text, action = "can_stand", "It's your sign's month! You can stand as a candidate this week.", "stand"
        else:
            role, text = "voter_soon", f"It's your sign's month. {stand_reason} You can vote in weeks 2-3."
    elif cycle["status"] == "voting":
        if nominated:
            role, text = "candidate", "You are a candidate. Members of your sign are voting now."
        elif can_vote and not voted:
            role, text, action = "can_vote", "It's your sign's month! Vote now for one candidate.", "vote"
        elif voted:
            role, text = "voted", "Thank you — your vote is counted. Results come in week 4."
        else:
            role, text = "watch", vote_reason
    else:
        role, text = "results", "Voting is over. See your village's new leaders below."
    return {"my_sign": my_sign, "my_gender": (user_row["gender"] or "").lower(), "role": role, "text": text, "action": action, "week": week,
            "nominated": nominated, "voted_genders": voted, "can_stand": can_stand and cycle["status"] == "nomination" and not nominated,
            "can_vote": can_vote and cycle["status"] == "voting"}


def election_summary(conn, village_id: str, today: dt.date | None = None) -> dict:
    """The village election card for Q-Punch: cycle, 4-week timeline, candidates, turnout, winners."""
    today = today or dt.date.today()
    cycle = current_cycle_for_village(conn, village_id, today)
    cands = candidates_for_cycle(conn, cycle["id"])
    votes = {r["candidate_user_id"]: r["n"] for r in conn.execute(
        "SELECT candidate_user_id, COUNT(*) AS n FROM election_votes WHERE election_cycle_id = ? GROUP BY candidate_user_id", (cycle["id"],))}
    show_votes = cycle["status"] == "closed"
    out_cands = {g: [{"user_id": c["user_id"], "name": c["name"], "reason": c.get("form_reason") or c.get("manifest") or "",
                      "why_vote": c.get("form_why_vote") or "", "changes": c.get("form_changes") or "",
                      "votes": votes.get(c["user_id"], 0) if show_votes else None} for c in lst]
                 for g, lst in cands.items() if g in ("male", "female")}
    turnout = conn.execute("SELECT COUNT(DISTINCT voter_user_id) FROM election_votes WHERE election_cycle_id = ?", (cycle["id"],)).fetchone()[0]
    eligible_voters = 0
    for u in conn.execute("SELECT u.id, u.dob, u.present_location_json, z.sun_sign FROM users u JOIN user_zodiac z ON z.user_id = u.id "
                          "WHERE json_extract(u.present_location_json, '$.village.id') = ? AND z.sun_sign = ?", (village_id, cycle["zodiac_sign"])):
        if _age_years(u["dob"], today) >= 5:
            eligible_voters += 1
    winners = None
    if cycle["status"] == "closed":
        term_start, term_end = _winner_term(cycle)
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM users WHERE id IN (?, ?)",
                                                        (cycle.get("male_winner_user_id") or 0, cycle.get("female_winner_user_id") or 0))}
        winners = {"male": names.get(cycle.get("male_winner_user_id")), "female": names.get(cycle.get("female_winner_user_id")),
                   "male_votes": votes.get(cycle.get("male_winner_user_id"), 0), "female_votes": votes.get(cycle.get("female_winner_user_id"), 0),
                   "term_start": term_start, "term_end": term_end}
    return {"village_id": village_id, "sign": cycle["zodiac_sign"], "element": cycle["element"], "year": cycle["year"],
            "status": cycle["status"], "week": current_week(cycle, today), "weeks": election_weeks(cycle),
            "candidates": out_cands, "turnout": turnout, "eligible_voters": eligible_voters, "winners": winners,
            "cycle_id": cycle["id"]}


# ---- Automation (pilot village): pick candidates in week 1, cast votes in weeks 2-3 --------------------

_FORM_REASONS = ["I want our lanes clean and lit at night.", "Our children need a safe park and a library.",
                 "I will make the village water supply reliable.", "I want every elder to get help on time.",
                 "I will bring local jobs and skills training.", "I want the council to listen to every family."]
_FORM_WHY = ["I have served my neighbours for years.", "I keep my word and work hard.", "I know every street of this village.",
             "I will report every rupee we spend.", "I listen first and act fast."]
_FORM_CHANGES = ["Monthly open meetings in the park.", "A helpline for elders.", "Weekly cleanliness drives.",
                 "Better street lights and CCTV.", "Skill classes for youth."]


def auto_nominate(conn, village_id: str, per_gender: int = CANDIDATES_PER_GENDER, rng=None, today: dt.date | None = None) -> dict:
    """Week 1: randomly choose `per_gender` eligible men and women of this month's sign as candidates
    (approved at once). Idempotent: tops up to `per_gender` per gender, never adds more."""
    import random
    rng = rng or random.Random()
    ensure_council_columns(conn)
    today = today or dt.date.today()
    cycle = current_cycle_for_village(conn, village_id, today)
    if cycle["status"] != "nomination":
        raise ValueError("Candidates are chosen in week 1 (nomination) only.")
    picked = {"male": [], "female": []}
    rows = conn.execute("SELECT u.* FROM users u JOIN user_zodiac z ON z.user_id = u.id "
                        "WHERE json_extract(u.present_location_json, '$.village.id') = ? AND z.sun_sign = ?",
                        (village_id, cycle["zodiac_sign"])).fetchall()
    for gender in ("male", "female"):
        have = conn.execute("SELECT COUNT(*) FROM election_candidates WHERE election_cycle_id = ? AND gender = ?",
                            (cycle["id"], gender)).fetchone()[0]
        already = {r["user_id"] for r in conn.execute("SELECT user_id FROM election_candidates WHERE election_cycle_id = ?", (cycle["id"],))}
        pool = [u for u in rows if (u["gender"] or "").lower() == gender and u["id"] not in already and nomination_eligible(conn, u, cycle)[0]]
        rng.shuffle(pool)
        for u in pool[: max(0, per_gender - have)]:
            conn.execute(
                """INSERT INTO election_candidates (election_cycle_id, user_id, gender, manifest, status,
                   form_reason, form_why_vote, form_changes, form_past_work) VALUES (?, ?, ?, ?, 'approved', ?, ?, ?, ?)""",
                (cycle["id"], u["id"], gender, "", rng.choice(_FORM_REASONS), rng.choice(_FORM_WHY), rng.choice(_FORM_CHANGES), ""),
            )
            picked[gender].append(u["name"])
    conn.execute("UPDATE election_candidates SET manifest = form_reason WHERE election_cycle_id = ? AND (manifest IS NULL OR manifest = '')", (cycle["id"],))
    conn.commit()
    return picked


def auto_vote(conn, village_id: str, rng=None, today: dt.date | None = None, turnout: float = 1.0) -> dict:
    """Weeks 2-3: every eligible member of this month's sign who hasn't voted picks one candidate of
    their gender at random (`turnout` = share of eligible members who vote). Goes through cast_vote,
    so every rule is enforced exactly as for a real voter."""
    import random
    rng = rng or random.Random()
    today = today or dt.date.today()
    cycle = current_cycle_for_village(conn, village_id, today)
    if cycle["status"] != "voting":
        raise ValueError("Automated voting runs in weeks 2-3 (voting) only.")
    cands = candidates_for_cycle(conn, cycle["id"])
    cast = {"male": 0, "female": 0, "skipped": 0}
    rows = conn.execute("SELECT u.* FROM users u JOIN user_zodiac z ON z.user_id = u.id "
                        "WHERE json_extract(u.present_location_json, '$.village.id') = ? AND z.sun_sign = ?",
                        (village_id, cycle["zodiac_sign"])).fetchall()
    for u in rows:
        gender = (u["gender"] or "").lower()
        if gender not in ("male", "female") or not cands.get(gender) or rng.random() > turnout:
            cast["skipped"] += 1
            continue
        choice = rng.choice(cands[gender])
        try:
            cast_vote(conn, u, choice["user_id"], gender, today)
            cast[gender] += 1
        except ValueError:
            cast["skipped"] += 1
    return cast
