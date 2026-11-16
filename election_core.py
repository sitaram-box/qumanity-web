"""Village Council elections — piloted on ONE village (see
`Qbox-Notes.txt`, "Please write cursor prompt to build a voting system in
Public Account - Village id..."). Each zodiac sign runs its own ~1-month
cycle: an 8-day nomination window, then a 14-day voting window, electing one
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
import logging
import sqlite3

import account_core
import cycle_middleware
import elemental_core
import geography_core
import id_generator
import karma_core
import wallet_core
from zodiac_core import ZODIAC_RANGES

logger = logging.getLogger(__name__)

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
MIN_CANDIDATE_KARMA = 200  # 2026-11-11: the public candidate table always claimed this; nomination_eligible() now actually enforces it

# Q-Punch cascade, Phase 2 (2026-11-16, schema only -- see migrations/040_qpunch_councils.py):
# Tehsil-and-up council term lengths in years, per the approved governance brief. 'village' is
# deliberately absent -- it keeps its own existing 1-year-per-sign cycle (TERM_DAYS above),
# unchanged, via the separate village_council table. Not consumed by any function yet; Phase 3
# (nomination/voting/the quarterly element-rotation logic) is what will read this.
TERM_YEARS_BY_LEVEL = {
    "tehsil": 3, "district": 5, "state": 7, "zone": 9, "country": 11, "continent": 13, "earth": 15,
}

_SIGN_ORDER = [z["sign"] for z in ZODIAC_RANGES]
_SIGN_BY_NAME = {z["sign"]: z for z in ZODIAC_RANGES}

# Q-Punch cascade, Phase 3 (2026-11-16): the quarterly element-rotation order (reused, not
# redefined -- elemental_core.ELEMENTS is the one canonical list/order every element-aware part of
# this codebase already reads, e.g. the Statistics Dashboard's own element donut). Values stored
# in active_element/qpunch_council_members.element are this exact casing ("Fire", not "fire"),
# matching user_zodiac.sun_element's own stored casing -- Phase 2's own schema comments said
# lowercase, which was wrong before anything actually wrote to these columns; corrected here.
ELEMENT_ORDER = elemental_core.ELEMENTS  # ["Fire", "Earth", "Air", "Water"]
HEAD_APPROVAL_DAYS = 7  # not specified in the approved brief -- same order of magnitude as a
# village voting window (VOTING_DAYS above); each quarter is at minimum ~274 days (a 3-year Tehsil
# term's shortest quarter), so 7 days is a small fraction of any quarter, not a judgment call that
# meaningfully shortens anyone's actual leadership time.

# Q-Punch cascade, Phase 2-3: Tehsil-and-up council schema (village_council, above, is untouched
# and keeps its own 12-sign-seat shape -- see the approved brief's "Village vs Upper Levels"
# section). One qpunch_councils row per (location, level, term): 8 qpunch_council_members rows
# under it, one per gender x element. active_element/head_user_id/head_gender start NULL and are
# set by ensure_head_approval_current() below, once a term's first quarter actually begins.
#
# qpunch_cascade_votes (Phase 3, new): the Lower House's own seat votes -- NOT the same table as
# village's election_votes, even though the shape looks similar, because the uniqueness rule
# genuinely differs. A village voter casts at most 2 votes per cycle (1 male + 1 female, for their
# own sign's single seat) -- election_votes' own UNIQUE(election_cycle_id, voter_user_id, gender)
# encodes exactly that. A Lower House voter at Tehsil+ casts up to 8 (1 male + 1 female, per EACH
# of the 4 elements, with no "your own element" restriction -- the whole Lower House decides every
# seat), so the uniqueness key needs `element` too. Widening election_votes' own constraint would
# mean rebuilding that live table (SQLite can't ALTER a UNIQUE constraint in place) for a
# capability village voting never needed -- a parallel table is the lower-risk choice.
#
# qpunch_head_approvals / qpunch_head_approval_votes (Phase 3, new): the Upper House's 51%-approval
# ballot on one quarter's Male candidate -- structurally a yes/no referendum on ONE person, not a
# "pick one of N candidates for a seat" election, so it doesn't fit either votes table's own shape.
# One qpunch_head_approvals row per (council, element) -- at most 4 per council, one per quarter --
# `result` stays NULL while voting is open and is set once (approved|rejected) when the window
# closes; qpunch_head_approval_votes holds the individual ballots behind it.
#
# No SQL CHECK constraints on level/gender/element, same convention as every other status-ish
# column in this codebase (e.g. q_card_core.py's _STATUSES) -- Python enforces valid values.
QPUNCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS qpunch_councils (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    level TEXT NOT NULL,              -- tehsil | district | state | zone | country | continent | earth (never 'village')
    term_start TEXT NOT NULL,         -- ISO date
    term_end TEXT NOT NULL,           -- ISO date
    election_cycle_id INTEGER,        -- the election_cycles row (its own new level column set to match) that elected this council
    active_element TEXT,              -- Fire | Earth | Air | Water -- the quarter currently leading; NULL until its term starts
    head_user_id INTEGER,             -- the Male or Female of active_element currently holding Head for this quarter
    head_gender TEXT,                 -- male | female -- which of the active element's pair actually holds Head
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (location_id, level, term_start),
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id),
    FOREIGN KEY (head_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_qpunch_councils_location ON qpunch_councils(location_id, level);

CREATE TABLE IF NOT EXISTS qpunch_council_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    gender TEXT NOT NULL,             -- male | female
    element TEXT NOT NULL,            -- Fire | Earth | Air | Water
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (council_id, gender, element),  -- exactly one seat per gender x element on a council
    UNIQUE (council_id, user_id),          -- the same person can't hold two seats on one council
    FOREIGN KEY (council_id) REFERENCES qpunch_councils(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_qpunch_council_members_user ON qpunch_council_members(user_id);

CREATE TABLE IF NOT EXISTS qpunch_cascade_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_cycle_id INTEGER NOT NULL,
    voter_user_id INTEGER NOT NULL,
    candidate_user_id INTEGER NOT NULL,
    gender TEXT NOT NULL,             -- male | female
    element TEXT NOT NULL,            -- Fire | Earth | Air | Water -- which of the 4 seats this vote is for
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (election_cycle_id, voter_user_id, gender, element),
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id),
    FOREIGN KEY (voter_user_id) REFERENCES users(id),
    FOREIGN KEY (candidate_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_qpunch_cascade_votes_cycle ON qpunch_cascade_votes(election_cycle_id);

CREATE TABLE IF NOT EXISTS qpunch_head_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    council_id INTEGER NOT NULL,
    element TEXT NOT NULL,
    male_candidate_user_id INTEGER NOT NULL,
    female_candidate_user_id INTEGER NOT NULL,
    approval_start TEXT NOT NULL,
    approval_end TEXT NOT NULL,
    result TEXT,                      -- NULL while open; 'approved' | 'rejected' once the window closes
    UNIQUE (council_id, element),
    FOREIGN KEY (council_id) REFERENCES qpunch_councils(id)
);

CREATE TABLE IF NOT EXISTS qpunch_head_approval_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    approval_id INTEGER NOT NULL,
    voter_user_id INTEGER NOT NULL,
    approve INTEGER NOT NULL,         -- 1 = approve the Male as Head, 0 = reject (defaults to the Female)
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (approval_id, voter_user_id),
    FOREIGN KEY (approval_id) REFERENCES qpunch_head_approvals(id)
);

-- Upper House Sovereignty, Phase 5 (2026-11-16): a direct-democracy referendum the general public
-- (not just the Lower/Upper House machinery above) can call on ANY question at ANY level, whose
-- "passed" result overrides the Q-Punch council's own decisions -- see initiate_people_vote()'s
-- own docstring for how this relates to cast_head_approval_vote() above (the Head Approval is one
-- standing, pre-wired instance of this same general power, not a separate mechanism).
CREATE TABLE IF NOT EXISTS qpunch_people_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    level TEXT NOT NULL,              -- village | tehsil | district | state | zone | country | continent | earth
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- open | passed | failed
    votes_for INTEGER,                -- NULL while open (hidden during live voting, same convention
    votes_against INTEGER,            -- election_summary()'s own show_votes already uses) -- set once tally_people_vote() resolves it
    initiated_by_user_id INTEGER NOT NULL,
    start_time TEXT NOT NULL,         -- ISO date, same granularity as every other window in this module
    end_time TEXT NOT NULL,
    FOREIGN KEY (initiated_by_user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_qpunch_people_votes_location ON qpunch_people_votes(location_id, level, status);

CREATE TABLE IF NOT EXISTS qpunch_people_vote_ballots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vote_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    in_favour INTEGER NOT NULL,       -- 1 = for, 0 = against
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (vote_id, user_id),
    FOREIGN KEY (vote_id) REFERENCES qpunch_people_votes(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


def ensure_qpunch_tables(conn) -> None:
    """Creates every Q-Punch cascade table (Phase 2's councils/members, Phase 3's cascade votes
    and head approvals -- see QPUNCH_SCHEMA's own docstring) if they don't already exist --
    idempotent, same self-healing convention every *_core.py module in this codebase uses for its
    own tables."""
    conn.executescript(QPUNCH_SCHEMA)
    conn.commit()


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
    # Q-Punch cascade, Phase 2 (2026-11-16): every pre-existing election_cycles row is a village
    # cycle (the only level that existed before this), so the default keeps them exactly what they
    # already were -- Phase 3's Tehsil-and-up cycles are the only rows that will ever set this to
    # anything else.
    cycle_cols = {r["name"] for r in conn.execute("PRAGMA table_info(election_cycles)")}
    if "level" not in cycle_cols:
        conn.execute("ALTER TABLE election_cycles ADD COLUMN level TEXT NOT NULL DEFAULT 'village'")
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
    """Computes the winner tally for a closed cycle from the CURRENT election_votes data, and
    writes it into village_council + election_cycles.

    2026-11-08 FIX (Task 1B): this used to tally ONCE EVER per (village_id, zodiac_sign, year) --
    skipping entirely, forever, if a village_council row already existed, regardless of whether
    the votes underlying that row had changed since the row was first written. That meant a cycle
    whose status was first observed as "closed" before all of its votes existed permanently froze
    a null/incomplete tally, even after real votes were later cast for that exact cycle.
    Confirmed as the actual root cause, not assumed: tools/website-check/check_app_api.py's "week
    4: winners have the most votes" check failed with real votes on record (male=15, female=11)
    but winners/vote-counts reported as None/0 -- and the real qumanity_prototype.db's own
    village_council row for Libra 2026 / Rohini Sector 24 shows exactly this: tallied
    2026-10-17 with ZERO election_votes rows for that cycle on record at the time. Candidate
    creation, vote casting/persistence, and cycle-status derivation were all independently
    verified correct (a direct repro reproduced the right winners when _ensure_tallied was not
    short-circuited by a stale existing row) -- the bug is isolated entirely to this one
    skip-if-exists guard, so this is the smallest responsible fix: tallying is a cheap,
    deterministic read of election_votes with no side effect that must only ever run once -- no
    reward or Qoin payout is tied to becoming a winner anywhere in this codebase (confirmed by
    grep; the only Q-Punch-adjacent reward, wallet_core.unlock_user_share, fires on a VOTER's
    first-ever vote, never on tallying) -- so recomputing it every time a cycle is seen as closed,
    and overwriting the existing village_council/election_cycles winner columns with the fresh
    result, is safe and correct, not a new election mechanism or a policy change."""
    ensure_council_columns(conn)

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

    existing = conn.execute(
        "SELECT 1 FROM village_council WHERE village_id = ? AND zodiac_sign = ? AND year = ?",
        (cycle["village_id"], cycle["zodiac_sign"], cycle["year"]),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE village_council SET male_head_user_id = ?, female_head_user_id = ?,
               election_cycle_id = ?, leadership_start = ?, leadership_end = ?,
               updated_at = CURRENT_TIMESTAMP
               WHERE village_id = ? AND zodiac_sign = ? AND year = ?""",
            (winners["male"], winners["female"], cycle["id"], leadership_start, leadership_end,
             cycle["village_id"], cycle["zodiac_sign"], cycle["year"]),
        )
    else:
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
    """The user's present village id -- but ONLY when account_core.account_access_type()
    independently agrees their account is 'public' (2026-11-08 Q-Punch hardening). Every Q-Punch
    eligibility check (nomination_eligible, voting_eligible, member_guide) goes through this one
    function, so this is the single place that needed to change: a Global Account is never
    Q-Punch eligible merely because a village id happens to sit in its present_location_json --
    e.g. from a stale or malformed profile-change-request record, or a future bug elsewhere --
    since account_access_type() recomputes the classification independently from the SAME
    present_location_json, using the country id, not the presence of a village key. A row whose
    country is outside SUBCONTINENT_COUNTRY_IDS always gets None here, full stop."""
    loc = json.loads(user_row["present_location_json"])
    if account_core.account_access_type(loc) != "public":
        return None
    village = loc.get("village")
    return village["id"] if village else None


def _age_years(dob_iso: str, today: dt.date) -> int:
    dob = dt.date.fromisoformat(dob_iso)
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def nomination_eligible(conn, user_row, cycle: dict) -> tuple[bool, str]:
    level = cycle.get("level") or "village"
    if level != "village":
        # Q-Punch cascade, Phase 3: nomination above village is "are you a currently-serving
        # member of the level below, at a child of this location" -- never residency or age/karma
        # (those are the village-specific gates above; the brief names no equivalent for Tehsil+,
        # and inventing one isn't asked for).
        if user_row["id"] not in get_lower_house(conn, level, cycle["village_id"]):
            child_level = geography_core.LEVELS[geography_core.LEVELS.index(level) + 1]
            return False, f"Nomination for {level} is only open to currently-serving {child_level}-level council members here."
        zodiac = conn.execute("SELECT sun_element FROM user_zodiac WHERE user_id = ?", (user_row["id"],)).fetchone()
        if not zodiac or zodiac["sun_element"] not in ELEMENT_ORDER:
            return False, "Could not determine your element."
        if (user_row["gender"] or "").lower() not in ("male", "female"):
            return False, "Nomination is open to Male and Female candidates only."
        return True, ""
    if _present_village_id(user_row) != cycle["village_id"]:
        return False, "Nomination is only open to residents of this pilot village."
    age = _age_years(user_row["dob"], dt.date.today())
    if age < 25 or age > 60:
        return False, "Candidates must be Yuvak or Vridh, aged 25 to 60."
    # 2026-11-11 (Product Truth Audit, finding C29): karma was always shown next to a candidate's
    # name (candidates_for_cycle()/current_cycle_for_village() below) but never actually gated
    # candidacy -- the public candidate-requirement table claimed a 200 threshold that nothing
    # enforced. Peer-nomination-count and dispute-record checks, also claimed on that table, are
    # deliberately NOT added here: neither a peer-endorsement feature nor a per-user dispute record
    # exists anywhere in this codebase, and gating on a count nothing can ever produce would make
    # candidacy permanently impossible, silently disabling the only live election pilot.
    karma = karma_core.individual_karma_score(conn, user_row["id"])["total"]
    if karma < MIN_CANDIDATE_KARMA:
        return False, f"Candidates need at least {MIN_CANDIDATE_KARMA} karma on the public ledger (you have {karma})."
    zodiac = conn.execute("SELECT sun_sign FROM user_zodiac WHERE user_id = ?", (user_row["id"],)).fetchone()
    if not zodiac or zodiac["sun_sign"] != cycle["zodiac_sign"]:
        return False, f"Only members born under {cycle['zodiac_sign']} can stand in this cycle."
    if (user_row["gender"] or "").lower() not in ("male", "female"):
        return False, "Nomination is open to Male and Female candidates only."
    return True, ""


def voting_eligible(conn, user_row, cycle: dict, today: dt.date | None = None) -> tuple[bool, str]:
    """Village cycles: residents born under THIS cycle's sign vote (docs/voting_logic.md) -- men for the
    male seat, women for the female seat; third-gender members by their present gender."""
    level = cycle.get("level") or "village"
    if level != "village":
        # Q-Punch cascade, Phase 3: only the Lower House votes -- not the general public (that's
        # the SEPARATE Upper House 51%-approval vote, see cast_head_approval_vote()). Every Lower
        # House member may vote on every one of the 8 seats, not just their own element's.
        if user_row["id"] not in get_lower_house(conn, level, cycle["village_id"]):
            child_level = geography_core.LEVELS[geography_core.LEVELS.index(level) + 1]
            return False, f"Voting for {level} is only open to currently-serving {child_level}-level council members here."
        return True, ""
    if _present_village_id(user_row) != cycle["village_id"]:
        return False, "Voting is only open to residents of this pilot village."
    today = today or dt.date.today()
    if _age_years(user_row["dob"], today) < 5:
        return False, "Voting is open to members aged 5 and up."
    zodiac = conn.execute("SELECT sun_sign FROM user_zodiac WHERE user_id = ?", (user_row["id"],)).fetchone()
    if not zodiac or zodiac["sun_sign"] != cycle["zodiac_sign"]:
        return False, f"Only members born under {cycle['zodiac_sign']} vote in this cycle."
    return True, ""


def nominate(conn, user_row, reason: str, why_vote: str, changes: str, past_work: str = "",
             level: str = "village", location_id: str | None = None) -> dict:
    """The 4-question candidacy form: why they're running, why members should vote for them, what
    they'd change, and (optionally) past work. `manifest` (the old single free-text field) is kept
    populated from `reason` so any legacy reader still sees something sensible.

    level/location_id (2026-11-16, Q-Punch cascade Phase 3): level='village' (the default) keeps
    nominating for PILOT_VILLAGE_ID exactly as before -- every existing caller that never passes
    these two keywords is unaffected. level='tehsil'..'earth' nominates for that location's
    current multi-year-term cycle instead (current_cycle_for_location()), and skips the
    village-only CANDIDATES_PER_GENDER cap -- the approved brief names no equivalent cap for
    Tehsil+, where "the top Male/Female per element wins" already bounds the field naturally."""
    ensure_council_columns(conn)
    if level == "village":
        cycle = current_cycle_for_village(conn, PILOT_VILLAGE_ID)
    else:
        if not location_id:
            raise ValueError("location_id is required for a non-village nomination")
        cycle = current_cycle_for_location(conn, level, location_id)
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
    if level == "village" and _gender_full(conn, cycle["id"], user_row["gender"]):
        raise ValueError(f"This month's {CANDIDATES_PER_GENDER} {user_row['gender'].lower()} candidates have already been chosen.")
    conn.execute(
        """INSERT INTO election_candidates
           (election_cycle_id, user_id, gender, manifest, form_reason, form_why_vote, form_changes, form_past_work, cycle_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cycle["id"], user_row["id"], user_row["gender"].lower(), reason,
         reason, why_vote, changes, (past_work or "").strip(), cycle_middleware.get_active_cycle_id(conn)),
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


def cast_vote(conn, user_row, candidate_user_id: int, gender: str, today: dt.date | None = None,
              level: str = "village", location_id: str | None = None, element: str | None = None) -> None:
    """level/location_id/element (2026-11-16, Q-Punch cascade Phase 3): level='village' (the
    default) is exactly the original village vote, unchanged -- every existing caller that never
    passes these three keywords is unaffected. level='tehsil'..'earth' casts a Lower House seat
    vote instead, into qpunch_cascade_votes rather than election_votes (see that table's own
    schema comment for why it's a separate table, not a widened version of this one) -- `element`
    is required, since a Tehsil+ voter may cast up to 8 votes in one cycle (1 male + 1 female per
    element, no "your own element" restriction), where election_votes' own UNIQUE constraint only
    ever needed to allow 2. The wallet-share-unlock reward below is deliberately NOT extended to
    cascade voting -- it's specifically "a resident's first-ever vote in the village pilot"
    (wallet_core.unlock_user_share()'s own contract), and the brief doesn't ask for a second,
    separate reward trigger here."""
    if level != "village":
        if not location_id or not element:
            raise ValueError("location_id and element are required for a non-village vote")
        element = element.strip().title()
        cycle = current_cycle_for_location(conn, level, location_id, today)
        if cycle["status"] != "voting":
            raise ValueError("Voting is not open for the current cycle.")
        ok, reason = voting_eligible(conn, user_row, cycle, today)
        if not ok:
            raise ValueError(reason)
        if element not in ELEMENT_ORDER:
            raise ValueError("Unknown element.")
        candidate = conn.execute(
            """SELECT ec.status, ec.gender, uz.sun_element FROM election_candidates ec
               JOIN user_zodiac uz ON uz.user_id = ec.user_id
               WHERE ec.election_cycle_id = ? AND ec.user_id = ?""",
            (cycle["id"], candidate_user_id),
        ).fetchone()
        if not candidate or candidate["status"] != "approved":
            raise ValueError("That candidate isn't approved for this cycle.")
        if candidate["gender"] != gender:
            raise ValueError("Candidate/gender mismatch.")
        if candidate["sun_element"] != element:
            raise ValueError("That candidate isn't running for this element's seat.")
        already = conn.execute(
            "SELECT 1 FROM qpunch_cascade_votes WHERE election_cycle_id = ? AND voter_user_id = ? AND gender = ? AND element = ?",
            (cycle["id"], user_row["id"], gender, element),
        ).fetchone()
        if already:
            raise ValueError(f"You've already voted for {gender} {element} in this cycle.")
        conn.execute(
            "INSERT INTO qpunch_cascade_votes (election_cycle_id, voter_user_id, candidate_user_id, gender, element) VALUES (?, ?, ?, ?, ?)",
            (cycle["id"], user_row["id"], candidate_user_id, gender, element),
        )
        conn.commit()
        return

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
        """INSERT INTO election_votes (election_cycle_id, voter_user_id, candidate_user_id, gender, cycle_id)
           VALUES (?, ?, ?, ?, ?)""",
        (cycle["id"], user_row["id"], candidate_user_id, gender, cycle_middleware.get_active_cycle_id(conn)),
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


# ---- Q-Punch cascade, Phase 3 (2026-11-16): Tehsil-to-Earth nomination, voting, and the
# quarterly rotating Head. village_council/election_candidates/election_votes and every function
# above this point keep their exact existing village behavior -- level='village' (the default
# everywhere below) always takes the original code path, unchanged. ----

def get_lower_house(conn, level: str, location_id: str) -> list[int]:
    """Every user_id currently serving on an active council one level below (level, location_id)
    -- e.g. get_lower_house(conn, "tehsil", "CS.DL.3.4") returns every village_council member
    (both genders, all 12 signs, each currently within their own leadership term) across every
    village under that tehsil. THIS is a location's voting pool for its own cascade election --
    never stored, always computed live from geography_core.get_children() plus whichever table
    the child level's council data actually lives in: village_council for a village child,
    qpunch_council_members for anything else. Returns [] for 'village' itself (nothing sits below
    it to form a Lower House from) or for a location with no children yet."""
    idx = geography_core.LEVELS.index(level)
    if idx >= len(geography_core.LEVELS) - 1:
        return []
    child_level = geography_core.LEVELS[idx + 1]
    child_ids = geography_core.get_children(conn, level, location_id)
    if not child_ids:
        return []
    today = dt.date.today().isoformat()
    placeholders = ",".join("?" for _ in child_ids)
    if child_level == "village":
        rows = conn.execute(
            f"""SELECT male_head_user_id, female_head_user_id FROM village_council
               WHERE village_id IN ({placeholders}) AND leadership_start <= ? AND leadership_end >= ?""",
            (*child_ids, today, today),
        ).fetchall()
        members = set()
        for r in rows:
            if r["male_head_user_id"]:
                members.add(r["male_head_user_id"])
            if r["female_head_user_id"]:
                members.add(r["female_head_user_id"])
        return sorted(members)
    rows = conn.execute(
        f"""SELECT DISTINCT qcm.user_id FROM qpunch_council_members qcm
           JOIN qpunch_councils qc ON qc.id = qcm.council_id
           WHERE qc.location_id IN ({placeholders}) AND qc.level = ?
             AND qc.term_start <= ? AND qc.term_end >= ?""",
        (*child_ids, child_level, today, today),
    ).fetchall()
    return sorted(r["user_id"] for r in rows)


def current_cycle_for_location(conn, level: str, location_id: str, today: dt.date | None = None) -> dict:
    """Tehsil-and-up equivalent of current_cycle_for_village(): get-or-create the active
    election_cycles row for ONE multi-year term's single election -- nomination, then voting, then
    results, electing all 8 seats (1 Male + 1 Female per element) at once, unlike village's 12
    staggered per-sign cycles. Term length comes from TERM_YEARS_BY_LEVEL. Nomination/voting
    window lengths reuse NOMINATION_DAYS/VOTING_DAYS -- the approved brief didn't specify
    different figures for these levels, so this keeps the one pair of numbers village elections
    already use rather than inventing a second pair with no stated basis.

    election_cycles.zodiac_sign/element have no meaning above village (there is no one "sign" or
    "element" for an 8-seat election) but are NOT NULL columns on a table this module doesn't own
    the schema of (see ensure_council_columns()'s own note on election_cycles predating this
    codebase) -- '' is stored in both, a documented placeholder, never read for a non-village
    cycle. village_id holds `location_id` here -- the column name is generic in practice even
    though it predates this reuse; renaming it would touch every existing village query for no
    behavioral gain.

    Deliberately NOT village's own "recompute the window fresh every call, resync if it drifted"
    pattern: that is safe for village only because _sign_window() is a pure function of the
    calendar (the same sign+today always gives back the same window, no matter when it's called).
    Here, a first-ever cycle's nomination_start has no such calendar anchor -- it is simply
    "whenever this function first ran" -- so recomputing it from `today` on every later call would
    silently push a live nomination/voting window forward every time this is read with a later
    date, before any council has ever formed. Once a cycle row exists and is still live (today has
    not yet passed its own stored voting_end), THIS function always reads its stored dates
    as-is; a new row is only ever created when there is no live one to find."""
    ensure_qpunch_tables(conn)
    today = today or dt.date.today()
    if level not in TERM_YEARS_BY_LEVEL:
        raise ValueError(f"Unknown cascade level: {level}")
    term_years = TERM_YEARS_BY_LEVEL[level]

    row = conn.execute(
        "SELECT * FROM election_cycles WHERE village_id = ? AND level = ? ORDER BY id DESC LIMIT 1",
        (location_id, level),
    ).fetchone()
    # A cycle whose own voting has closed is NOT automatically "stale" -- the council it (will)
    # produce serves for years afterward, and this row stays its historical record throughout
    # that whole term. The NEXT cycle is only needed once that council's own term has ended (or
    # immediately, if this cycle somehow never produced one at all -- see the loop below). Right
    # after voting closes but before the first tally, no council exists yet for this row; that is
    # not "needs a new cycle", it is "needs tallying", which the closed-status branch below
    # already does every time it's called.
    needs_new = row is None
    if not needs_new and today > dt.date.fromisoformat(row["voting_end"]):
        council = conn.execute(
            "SELECT term_end FROM qpunch_councils WHERE location_id = ? AND level = ? AND election_cycle_id = ?",
            (location_id, level, row["id"]),
        ).fetchone()
        needs_new = council is not None and today > dt.date.fromisoformat(council["term_end"])
    if needs_new:
        prev = conn.execute(
            "SELECT term_end FROM qpunch_councils WHERE location_id = ? AND level = ? ORDER BY term_end DESC LIMIT 1",
            (location_id, level),
        ).fetchone()
        nomination_start = (dt.date.fromisoformat(prev["term_end"]) + dt.timedelta(days=1)) if prev else today
        nomination_end = nomination_start + dt.timedelta(days=NOMINATION_DAYS - 1)
        voting_start = nomination_end + dt.timedelta(days=1)
        voting_end = voting_start + dt.timedelta(days=VOTING_DAYS - 1)
        # OR IGNORE (2026-11-16): election_cycles' own UNIQUE is (village_id, zodiac_sign, year) --
        # for a cascade level, zodiac_sign is always '', so two concurrent first-ever requests for
        # the same location+year (both having read `row is None` above, before either committed)
        # would otherwise race a plain INSERT into an IntegrityError -> 500. Whichever request's
        # insert wins, the loser's is silently skipped and the re-SELECT below reads the winner's
        # row either way, so both requests end up agreeing on the one real cycle. The try/except is
        # defense in depth for an IntegrityError OR IGNORE does NOT suppress (e.g. a FOREIGN KEY or
        # CHECK failure) -- logged, then the re-SELECT is given a chance to find a row some other
        # request already committed before re-raising if there's truly nothing to fall back to.
        try:
            conn.execute(
                """INSERT OR IGNORE INTO election_cycles
                   (village_id, zodiac_sign, element, level, year, nomination_start, nomination_end,
                    voting_start, voting_end, status)
                   VALUES (?, '', '', ?, ?, ?, ?, ?, ?, 'nomination')""",
                (location_id, level, nomination_start.year, nomination_start.isoformat(), nomination_end.isoformat(),
                 voting_start.isoformat(), voting_end.isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            logger.exception(
                "current_cycle_for_location: INSERT OR IGNORE still raised IntegrityError "
                "(location_id=%s, level=%s, year=%s); falling back to existing row if any",
                location_id, level, nomination_start.year,
            )
            conn.rollback()
        row = conn.execute(
            "SELECT * FROM election_cycles WHERE village_id = ? AND level = ? ORDER BY id DESC LIMIT 1",
            (location_id, level),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"current_cycle_for_location: no election_cycles row for "
                f"location_id={location_id!r} level={level!r} after insert+fallback"
            )

    nomination_end = dt.date.fromisoformat(row["nomination_end"])
    voting_end = dt.date.fromisoformat(row["voting_end"])
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
    cycle["term_years"] = term_years
    if status == "closed":
        council_id = _ensure_tallied_location(conn, cycle, term_years)
        cycle["council_id"] = council_id
    return cycle


def _ensure_tallied_location(conn, cycle: dict, term_years: int) -> int:
    """Tallies a closed Tehsil-and-up cycle: for each of the 4 elements, the Male and Female
    candidate with the most qpunch_cascade_votes wins that element's seat -- same plurality rule
    village uses (_ensure_tallied() above), just 8 seats instead of 2. Writes qpunch_councils (the
    term row) and qpunch_council_members (the 8 seats). Re-tallies every time this is called on a
    closed cycle -- idempotent, same reasoning as _ensure_tallied()'s own 2026-11-08 fix: a cheap,
    deterministic read with no side effect that must only ever run once. Returns the council's id."""
    term_start = dt.date.fromisoformat(cycle["voting_end"]) + dt.timedelta(days=1)
    term_end = dt.date(term_start.year + term_years, term_start.month, term_start.day) - dt.timedelta(days=1)

    winners = {}
    for element in ELEMENT_ORDER:
        winners[element] = {}
        for gender in ("male", "female"):
            row = conn.execute(
                """SELECT candidate_user_id, COUNT(*) AS votes FROM qpunch_cascade_votes
                   WHERE election_cycle_id = ? AND gender = ? AND element = ?
                   GROUP BY candidate_user_id ORDER BY votes DESC, MIN(id) ASC LIMIT 1""",
                (cycle["id"], gender, element),
            ).fetchone()
            winners[element][gender] = row["candidate_user_id"] if row else None

    existing = conn.execute(
        "SELECT id FROM qpunch_councils WHERE location_id = ? AND level = ? AND term_start = ?",
        (cycle["village_id"], cycle["level"], term_start.isoformat()),
    ).fetchone()
    if existing:
        council_id = existing["id"]
        conn.execute(
            "UPDATE qpunch_councils SET term_end = ?, election_cycle_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (term_end.isoformat(), cycle["id"], council_id),
        )
    else:
        cur = conn.execute(
            """INSERT INTO qpunch_councils (location_id, level, term_start, term_end, election_cycle_id)
               VALUES (?, ?, ?, ?, ?)""",
            (cycle["village_id"], cycle["level"], term_start.isoformat(), term_end.isoformat(), cycle["id"]),
        )
        council_id = cur.lastrowid

    for element in ELEMENT_ORDER:
        for gender in ("male", "female"):
            user_id = winners[element][gender]
            if user_id is None:
                continue
            conn.execute(
                """INSERT INTO qpunch_council_members (council_id, user_id, gender, element)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(council_id, gender, element) DO UPDATE SET user_id = excluded.user_id""",
                (council_id, user_id, gender, element),
            )
    conn.commit()
    return council_id


def _quarter_bounds(council: dict) -> list[tuple[dt.date, dt.date, str]]:
    """The term's 4 equal(-ish) quarters as (start, end, element) triples, in ELEMENT_ORDER -- a
    term's day count rarely divides evenly by 4, so any leftover days are folded into the 4th
    (Water) quarter rather than overshooting the term's own end date."""
    start = dt.date.fromisoformat(council["term_start"])
    end = dt.date.fromisoformat(council["term_end"])
    quarter_days = ((end - start).days + 1) // 4
    bounds = []
    cursor = start
    for i, element in enumerate(ELEMENT_ORDER):
        q_end = end if i == 3 else cursor + dt.timedelta(days=quarter_days - 1)
        bounds.append((cursor, q_end, element))
        cursor = q_end + dt.timedelta(days=1)
    return bounds


def _current_quarter(council: dict, today: dt.date | None = None) -> tuple[dt.date, dt.date, str] | None:
    today = today or dt.date.today()
    for q_start, q_end, element in _quarter_bounds(council):
        if q_start <= today <= q_end:
            return q_start, q_end, element
    return None  # term hasn't started yet, or has fully ended


def ensure_head_approval_current(conn, council: dict, today: dt.date | None = None) -> dict:
    """Keeps qpunch_councils.active_element/head_user_id/head_gender current for `council`, and
    get-or-creates the qpunch_head_approvals row for whichever element's quarter is active right
    now -- same "recompute from today's date, write if changed" pattern current_cycle_for_village()
    already uses for a cycle's own status. Call this any time a council's current Head or active
    element is needed for display, or before an incoming head-approval vote.

    The 51% rule (approved brief): the active element's Male candidate becomes Head if his share
    of the approval vote (approve / (approve + reject)) is >= 0.51 once the approval window
    closes; otherwise the Female is Head for that quarter, by default. While the window is still
    open, head_user_id/head_gender stay NULL -- the brief's rule only resolves once voting
    actually closes, so this never guesses early. Returns the (possibly updated) council dict."""
    today = today or dt.date.today()
    quarter = _current_quarter(council, today)
    if not quarter:
        return council  # term not yet started, or fully over -- nothing to rotate
    q_start, q_end, element = quarter

    members = {r["gender"]: r["user_id"] for r in conn.execute(
        "SELECT gender, user_id FROM qpunch_council_members WHERE council_id = ? AND element = ?",
        (council["id"], element),
    )}
    male_id, female_id = members.get("male"), members.get("female")

    approval = conn.execute(
        "SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = ?",
        (council["id"], element),
    ).fetchone()
    if not approval and male_id and female_id:
        approval_start = q_start
        approval_end = min(q_start + dt.timedelta(days=HEAD_APPROVAL_DAYS - 1), q_end)
        conn.execute(
            """INSERT INTO qpunch_head_approvals
               (council_id, element, male_candidate_user_id, female_candidate_user_id, approval_start, approval_end)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (council["id"], element, male_id, female_id, approval_start.isoformat(), approval_end.isoformat()),
        )
        conn.commit()
        approval = conn.execute(
            "SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = ?",
            (council["id"], element),
        ).fetchone()

    head_user_id, head_gender = None, None
    if approval:
        result = approval["result"]
        if result is None and today > dt.date.fromisoformat(approval["approval_end"]):
            tally = conn.execute(
                "SELECT COALESCE(SUM(approve), 0) AS yes, COUNT(*) AS n FROM qpunch_head_approval_votes WHERE approval_id = ?",
                (approval["id"],),
            ).fetchone()
            result = "approved" if (tally["n"] > 0 and (tally["yes"] / tally["n"]) >= 0.51) else "rejected"
            conn.execute("UPDATE qpunch_head_approvals SET result = ? WHERE id = ?", (result, approval["id"]))
            conn.commit()
        if result == "approved":
            head_user_id, head_gender = approval["male_candidate_user_id"], "male"
        elif result == "rejected":
            head_user_id, head_gender = approval["female_candidate_user_id"], "female"

    if council.get("active_element") != element or council.get("head_user_id") != head_user_id or council.get("head_gender") != head_gender:
        conn.execute(
            "UPDATE qpunch_councils SET active_element = ?, head_user_id = ?, head_gender = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (element, head_user_id, head_gender, council["id"]),
        )
        conn.commit()
        council = dict(council)
        council.update(active_element=element, head_user_id=head_user_id, head_gender=head_gender)
    return council


def _present_location_matches(user_row, level: str, location_id: str) -> bool:
    """True if user_row's PRESENT location, at `level`, is exactly `location_id` -- the Upper
    House residency check (the approved brief's "general public at that location"), generalized
    from _present_village_id()'s own identical village-only check above (left untouched; this is
    a separate helper, not a rewrite of it, since every existing village call site already depends
    on its exact current behavior)."""
    loc = json.loads(user_row["present_location_json"])
    if account_core.account_access_type(loc) != "public":
        return False
    return (loc.get(level) or {}).get("id") == location_id


def cast_head_approval_vote(conn, user_row, council_id: int, approve: bool, today: dt.date | None = None) -> None:
    """Upper House vote: approve or reject the active quarter's Male candidate as Head. No karma
    or age gate -- the approved brief describes the Upper House as simply "the general public at
    that location," the same bar village voting uses for residency (not candidacy).

    Constitutionally (2026-11-16), this is ONE standing, pre-wired instance of the Upper House's
    own general sovereignty power -- see this module's "Upper House Sovereignty" section further
    down (initiate_people_vote()/cast_people_vote()/tally_people_vote()): the same population, the
    same residency bar, and the same 51%-of-ballots-cast threshold, just asked automatically every
    quarter on this one specific question rather than called by the people themselves on whatever
    they choose to ask. This function's own mechanics are unchanged by that section's addition."""
    council = conn.execute("SELECT * FROM qpunch_councils WHERE id = ?", (council_id,)).fetchone()
    if not council:
        raise LookupError("Council not found")
    council = ensure_head_approval_current(conn, dict(council), today)
    if not _present_location_matches(user_row, council["level"], council["location_id"]):
        raise ValueError(f"Head approval voting is only open to residents of this {council['level']}.")
    approval = conn.execute(
        "SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = ?",
        (council_id, council["active_element"]),
    ).fetchone()
    if not approval or approval["result"] is not None:
        raise ValueError("Head approval voting is not currently open for this council.")
    already = conn.execute(
        "SELECT 1 FROM qpunch_head_approval_votes WHERE approval_id = ? AND voter_user_id = ?",
        (approval["id"], user_row["id"]),
    ).fetchone()
    if already:
        raise ValueError("You've already voted on this quarter's Head approval.")
    conn.execute(
        "INSERT INTO qpunch_head_approval_votes (approval_id, voter_user_id, approve) VALUES (?, ?, ?)",
        (approval["id"], user_row["id"], 1 if approve else 0),
    )
    conn.commit()


def candidates_for_cycle_by_element(conn, cycle_id: int) -> dict:
    """Tehsil-and-up equivalent of candidates_for_cycle(): approved candidates grouped
    {element: {"male": [...], "female": [...]}}. Element is read live from the candidate's own
    user_zodiac.sun_element, never stored redundantly on election_candidates -- a user's element
    can't change once set, so there is nothing to drift out of sync, and this avoids a second
    column recording a fact user_zodiac already owns."""
    ensure_council_columns(conn)
    rows = conn.execute(
        """SELECT ec.id, ec.user_id, ec.gender, ec.manifest, ec.status, ec.form_reason, ec.form_why_vote,
                  ec.form_changes, ec.form_past_work, u.name, uz.sun_element AS element
           FROM election_candidates ec JOIN users u ON u.id = ec.user_id
           JOIN user_zodiac uz ON uz.user_id = ec.user_id
           WHERE ec.election_cycle_id = ? AND ec.status = 'approved'
           ORDER BY u.name""",
        (cycle_id,),
    ).fetchall()
    result = {element: {"male": [], "female": []} for element in ELEMENT_ORDER}
    for r in rows:
        candidate = dict(r)
        candidate["karma"] = karma_core.individual_karma_score(conn, r["user_id"])
        if r["element"] in result and r["gender"] in ("male", "female"):
            result[r["element"]][r["gender"]].append(candidate)
    return result


def council_members_display(conn, council_id: int) -> dict:
    """{element: {"male": {...}, "female": {...}}} for one qpunch_councils row -- names/karma
    filled in, same display convention council_roster() already uses for village seats."""
    rows = conn.execute(
        """SELECT qcm.gender, qcm.element, qcm.user_id, u.name
           FROM qpunch_council_members qcm JOIN users u ON u.id = qcm.user_id
           WHERE qcm.council_id = ?""",
        (council_id,),
    ).fetchall()
    result = {element: {"male": None, "female": None} for element in ELEMENT_ORDER}
    for r in rows:
        if r["element"] in result and r["gender"] in ("male", "female"):
            result[r["element"]][r["gender"]] = {
                "user_id": r["user_id"], "name": r["name"],
                "karma": karma_core.individual_karma_score(conn, r["user_id"]),
            }
    return result


def cascade_status(conn, level: str, location_id: str, user_row, today: dt.date | None = None) -> dict:
    """The Tehsil-and-up equivalent of the village election page's own bundle (cycle + eligibility
    + council) -- backs GET /api/election/status for level != 'village'. Unlike the village
    route's several separate inline queries, this is one function so app.py's route stays a thin
    auth-and-call wrapper, same as election_summary() already is for village."""
    today = today or dt.date.today()
    cycle = current_cycle_for_location(conn, level, location_id, today)
    nomination_ok, nomination_reason = nomination_eligible(conn, user_row, cycle)
    voting_ok, voting_reason = voting_eligible(conn, user_row, cycle, today)
    already_nominated = bool(conn.execute(
        "SELECT 1 FROM election_candidates WHERE election_cycle_id = ? AND user_id = ?",
        (cycle["id"], user_row["id"]),
    ).fetchone())
    voted = [dict(r) for r in conn.execute(
        "SELECT gender, element FROM qpunch_cascade_votes WHERE election_cycle_id = ? AND voter_user_id = ?",
        (cycle["id"], user_row["id"]),
    )]

    council = None
    council_row = conn.execute(
        "SELECT * FROM qpunch_councils WHERE location_id = ? AND level = ? ORDER BY term_end DESC LIMIT 1",
        (location_id, level),
    ).fetchone()
    if council_row and dt.date.fromisoformat(council_row["term_end"]) >= today:
        council_row = ensure_head_approval_current(conn, dict(council_row), today)
        # Phase 4 (2026-11-16): the frontend's own approval-ballot visibility needs to know (a)
        # whether an approval vote is open to cast at all right now, (b) whether THIS viewer is
        # Upper House here, and (c) whether they already voted -- all three so the UI can show the
        # ballot only to someone who can actually use it, rather than showing it to everyone and
        # relying on a POST failing afterward.
        approval = None
        if council_row["active_element"] and not council_row["head_user_id"]:
            approval_row = conn.execute(
                "SELECT * FROM qpunch_head_approvals WHERE council_id = ? AND element = ?",
                (council_row["id"], council_row["active_element"]),
            ).fetchone()
            if approval_row and approval_row["result"] is None:
                already_voted = bool(conn.execute(
                    "SELECT 1 FROM qpunch_head_approval_votes WHERE approval_id = ? AND voter_user_id = ?",
                    (approval_row["id"], user_row["id"]),
                ).fetchone())
                approval = {
                    "male_candidate_user_id": approval_row["male_candidate_user_id"],
                    "approval_end": approval_row["approval_end"], "already_voted": already_voted,
                }
        council = {
            "id": council_row["id"], "term_start": council_row["term_start"], "term_end": council_row["term_end"],
            "active_element": council_row["active_element"], "head_user_id": council_row["head_user_id"],
            "head_gender": council_row["head_gender"],
            "members": council_members_display(conn, council_row["id"]),
            "is_upper_house": _present_location_matches(user_row, level, location_id),
            "approval": approval,
        }

    return {
        "level": level, "location_id": location_id,
        "cycle": {
            "status": cycle["status"], "year": cycle["year"], "term_years": cycle.get("term_years"),
            "nomination_start": cycle["nomination_start"], "nomination_end": cycle["nomination_end"],
            "voting_start": cycle["voting_start"], "voting_end": cycle["voting_end"],
        },
        "eligibility": {
            "can_nominate": nomination_ok and cycle["status"] == "nomination" and not already_nominated,
            "nominate_reason": "" if nomination_ok else nomination_reason,
            "already_nominated": already_nominated,
            "can_vote": voting_ok and cycle["status"] == "voting",
            "vote_reason": "" if voting_ok else voting_reason,
            "voted": voted,
        },
        "lower_house_size": len(get_lower_house(conn, level, location_id)),
        "council": council,
    }


# ---- Upper House Sovereignty, Phase 5 (2026-11-16) ----
# The Upper House at any (level, location_id) is always that location's own general population --
# literally every registered member there (_present_location_matches() below, the same check
# cast_head_approval_vote() already uses), never just the Lower House or the Q-Punch council
# itself. Its power is not limited to the one standing 51% Head Approval question: the Upper House
# may call a direct referendum -- a People's Vote -- on ANY question, at ANY time, and a PASSED
# People's Vote is binding on the Q-Punch council for that location. Head Approval is simply the
# one question this project pre-wires and asks automatically every quarter; a People's Vote is the
# same underlying power, asked on whatever the people themselves choose to ask.
#
# This pass builds the record only -- initiate/cast/tally and the three routes below. Actually
# ENFORCING a passed vote's result against the Q-Punch council's own decisions (e.g. overriding
# who currently holds Head, or vetoing a specific council action) is explicitly a separate, later
# task, per the brief that authorized this: "For now, we just need the record." Nothing here
# changes cast_head_approval_vote()'s or ensure_head_approval_current()'s own behavior.

PEOPLE_VOTE_DAYS = VOTING_DAYS  # 14 -- no duration was specified for a People's Vote; reuses the
# same window length every other Q-Punch ballot in this module already uses rather than inventing
# a third number with no stated basis.


def initiate_people_vote(conn, level: str, location_id: str, title: str, description: str,
                          initiated_by_user_id: int, today: dt.date | None = None) -> dict:
    """Opens a new People's Vote -- the Upper House's own power to call a direct referendum on any
    question, not just the standing Head Approval one (see this section's own header comment).

    initiated_by_user_id (2026-11-16): not part of the brief's own 3-argument sketch of this
    function, but added here -- without recording who called the vote there would be nothing to
    check Upper House eligibility against, and no attribution at all for a power this
    consequential. Must itself be a member of (level, location_id)'s own population.

    At most one OPEN vote per (location_id, level) at a time -- a second question waits for the
    first to resolve rather than running two overlapping referenda on the same population at once."""
    ensure_qpunch_tables(conn)
    today = today or dt.date.today()
    initiator = conn.execute("SELECT * FROM users WHERE id = ?", (initiated_by_user_id,)).fetchone()
    if not initiator or not _present_location_matches(initiator, level, location_id):
        raise PermissionError(f"Only a member of this {level}'s own population can call a People's Vote here.")
    title = (title or "").strip()
    if not title:
        raise ValueError("A title is required.")
    if conn.execute(
        "SELECT 1 FROM qpunch_people_votes WHERE location_id = ? AND level = ? AND status = 'open'",
        (location_id, level),
    ).fetchone():
        raise ValueError("A People's Vote is already open for this location.")
    start = today
    end = start + dt.timedelta(days=PEOPLE_VOTE_DAYS - 1)
    cur = conn.execute(
        """INSERT INTO qpunch_people_votes
           (location_id, level, title, description, initiated_by_user_id, start_time, end_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (location_id, level, title, (description or "").strip() or None, initiated_by_user_id,
         start.isoformat(), end.isoformat()),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM qpunch_people_votes WHERE id = ?", (cur.lastrowid,)).fetchone())


def cast_people_vote(conn, vote_id: int, user_id: int, in_favour: bool, today: dt.date | None = None) -> None:
    """One ballot per Upper House member per People's Vote. `in_favour` is never shown back to
    anyone while the vote is open -- votes_for/votes_against stay NULL until tally_people_vote()
    resolves the vote, the same "no running tallies mid-vote" convention election_summary()'s own
    show_votes flag already enforces for village elections."""
    today = today or dt.date.today()
    vote = conn.execute("SELECT * FROM qpunch_people_votes WHERE id = ?", (vote_id,)).fetchone()
    if not vote:
        raise LookupError("People's Vote not found")
    if vote["status"] != "open" or today > dt.date.fromisoformat(vote["end_time"]):
        raise ValueError("This People's Vote is not open for voting.")
    user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user_row or not _present_location_matches(user_row, vote["level"], vote["location_id"]):
        raise PermissionError(f"Only a member of this {vote['level']}'s own population can vote here.")
    if conn.execute(
        "SELECT 1 FROM qpunch_people_vote_ballots WHERE vote_id = ? AND user_id = ?", (vote_id, user_id)
    ).fetchone():
        raise ValueError("You've already voted on this People's Vote.")
    conn.execute(
        "INSERT INTO qpunch_people_vote_ballots (vote_id, user_id, in_favour) VALUES (?, ?, ?)",
        (vote_id, user_id, 1 if in_favour else 0),
    )
    conn.commit()


def tally_people_vote(conn, vote_id: int, today: dt.date | None = None) -> dict:
    """Resolves a People's Vote once its window has closed: 'passed' if votes_for is >= 51% of
    all ballots cast (for + against) -- the identical 51% share Head Approval already uses, not a
    different threshold, since the brief is explicit that Head Approval is one instance of this
    same power. A vote with zero ballots cast never passes (0/0 is never >= 0.51). Safe to call on
    an already-open, not-yet-due vote (a no-op, returns it unchanged) or an already-resolved one
    (returns the cached result, never re-tallies a decided vote)."""
    today = today or dt.date.today()
    vote = conn.execute("SELECT * FROM qpunch_people_votes WHERE id = ?", (vote_id,)).fetchone()
    if not vote:
        raise LookupError("People's Vote not found")
    if vote["status"] != "open":
        return dict(vote)
    if today <= dt.date.fromisoformat(vote["end_time"]):
        return dict(vote)
    tally = conn.execute(
        "SELECT COALESCE(SUM(in_favour), 0) AS votes_for, COALESCE(SUM(1 - in_favour), 0) AS votes_against "
        "FROM qpunch_people_vote_ballots WHERE vote_id = ?",
        (vote_id,),
    ).fetchone()
    votes_for, votes_against = tally["votes_for"], tally["votes_against"]
    total = votes_for + votes_against
    status = "passed" if (total > 0 and (votes_for / total) >= 0.51) else "failed"
    conn.execute(
        "UPDATE qpunch_people_votes SET status = ?, votes_for = ?, votes_against = ? WHERE id = ?",
        (status, votes_for, votes_against, vote_id),
    )
    conn.commit()
    result = dict(vote)
    result.update(status=status, votes_for=votes_for, votes_against=votes_against)
    return result


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
    "IND": [("BJP", "BJP / NDA Alliance"), ("INC", "INC / INDIA Alliance"), ("OTH", "Other")],
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
NOT_VOTED = ("NOTVOTED", "Not Voted / NOTA")


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
    """Past elections (every Lok Sabha year except the latest/upcoming one, and Vidhan Sabha
    "last") lock forever once saved -- a second attempt to change one is rejected outright,
    the whole save fails, and nothing is written. Only the upcoming slots (Lok Sabha's newest
    year, Vidhan Sabha's "next") can be changed and re-saved at any time."""
    ensure_history_table(conn)
    valid = {code for code, _ in parties_for_country(country_code)}
    years = loksabha_years(conn, country_code)
    locked_slots = {("loksabha", str(y)) for y in years[:-1]} | {("vidhansabha", "last")}
    existing = {
        (r["kind"], r["slot"]): r["choice"]
        for r in conn.execute("SELECT kind, slot, choice FROM election_history_entries WHERE user_id = ?", (user_id,))
    }

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
        if (kind, slot) in locked_slots and existing.get((kind, slot)) not in (None, choice):
            label = f"{slot} Lok Sabha" if kind == "loksabha" else "Vidhan Sabha's last election"
            raise ValueError(f"Your {label} answer is already saved and can't be changed.")

    for kind, slot, choice in entries:
        conn.execute(
            """INSERT INTO election_history_entries (user_id, kind, slot, choice, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, kind, slot) DO UPDATE SET choice=excluded.choice, updated_at=CURRENT_TIMESTAMP""",
            (user_id, kind, slot, choice),
        )
    # A slot cleared back to "no answer" in this save is deleted rather than stored as empty --
    # but never a locked slot that already has a saved answer (that's a change, not a clear).
    for kind, slot_field, slots in (("loksabha", "loksabha", [str(y) for y in years]), ("vidhansabha", "vidhansabha", ["last", "next"])):
        sent = data.get(slot_field) or {}
        for slot in slots:
            if slot in sent and not sent[slot]:
                if (kind, slot) in locked_slots and existing.get((kind, slot)) is not None:
                    label = f"{slot} Lok Sabha" if kind == "loksabha" else "Vidhan Sabha's last election"
                    raise ValueError(f"Your {label} answer is already saved and can't be cleared.")
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
    """Aggregate sentiment for the NEXT (upcoming) Lok Sabha election -- the one slot every user
    can keep changing, so this is the live-sentiment figure, not a record of past votes."""
    ensure_history_table(conn)
    next_year = str(loksabha_years(conn, country_code)[-1])
    rows = conn.execute(
        """SELECT eh.choice FROM election_history_entries eh JOIN users u ON u.id = eh.user_id
           WHERE eh.kind = 'loksabha' AND eh.slot = ?
             AND json_extract(u.present_location_json, '$.country.id') = ?""",
        (next_year, country_id),
    ).fetchall()
    return _breakdown(rows, country_code)


def vidhansabha_aggregate(conn, state_id: str, country_code: str):
    """Aggregate sentiment for the NEXT (upcoming) Vidhan Sabha election."""
    ensure_history_table(conn)
    rows = conn.execute(
        """SELECT eh.choice FROM election_history_entries eh JOIN users u ON u.id = eh.user_id
           WHERE eh.kind = 'vidhansabha' AND eh.slot = 'next'
             AND json_extract(u.present_location_json, '$.state.id') = ?""",
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
                   form_reason, form_why_vote, form_changes, form_past_work, cycle_id) VALUES (?, ?, ?, ?, 'approved', ?, ?, ?, ?, ?)""",
                (cycle["id"], u["id"], gender, "", rng.choice(_FORM_REASONS), rng.choice(_FORM_WHY), rng.choice(_FORM_CHANGES), "",
                 cycle_middleware.get_active_cycle_id(conn)),
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
