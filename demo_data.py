"""demo_data.py — the single source of every value the public, read-only Hacker-News
demo (GET /demo/rohini-sector-24, registered in app.py) can ever render.

LIVE-MODULE EXCEPTION (the only one in this file, approved 2026-11-15): this module
imports zodiac_core and kundali_analyser and calls generate_kundali()/analyse() once,
below, with an explicitly fabricated birth input (DEMO_KUNDALI_DOB/TOB/LAT/LNG) -- never
a real member's data, never a database read. Both functions are pure: confirmed by
reading their full bodies, neither touches the database or looks up a user. Every other
value in this file is a hardcoded Python literal.

No other import from board_core, family_core, election_core, app, db, or any other
database-touching module anywhere in this file. get_demo_context() is the only function
other code may call -- nothing else in this module should be read by name from outside it.

This file deliberately contains no reference, anywhere, to the real Q-Punch pilot village's
internal location id or the name of the constant that holds it in election_core.py, and no
real Rohini Sector 24 member's name -- the village shown is real geography, but the demo must
not depend on (or echo) its live location id. DEMO_VILLAGE_LABEL below is the only label used
anywhere in this module or the template it feeds.
"""
from __future__ import annotations

import datetime as dt

import kundali_analyser
import zodiac_core

DEMO_VILLAGE_LABEL = "Rohini Sector 24 — demonstration village"

DEMO_BANNER_TEXT = "Public read-only demo — synthetic data. No real member information is shown."
DEMO_GROUPING_NOTE = "Grouped for this demo tour — not identical to the live dashboard's tabs."

# ---------------------------------------------------------------------------
# The one calculated value in this module: a Kundali chart from a fabricated
# birth input. See the module docstring above for why this is safe.
# ---------------------------------------------------------------------------
DEMO_KUNDALI_DOB = dt.date(1990, 1, 1)
DEMO_KUNDALI_TOB = dt.time(12, 0, 0)
DEMO_KUNDALI_LAT = 28.7196   # Rohini, Delhi -- approximate public coordinates, not tied to any member
DEMO_KUNDALI_LNG = 77.1058

_demo_kundali_raw = zodiac_core.generate_kundali(DEMO_KUNDALI_DOB, DEMO_KUNDALI_TOB, DEMO_KUNDALI_LAT, DEMO_KUNDALI_LNG)
_demo_kundali_view = kundali_analyser.analyse(DEMO_KUNDALI_DOB.isoformat(), _demo_kundali_raw)

DEMO_KUNDALI = {
    "note": "Example chart, generated from a demonstration birth date.",
    "dob_label": "1 January 1990 (demonstration date)",
    "tob_label": "12:00 PM (demonstration time)",
    "location_label": "Rohini Sector 24 (approximate coordinates)",
    "chart_svg": _demo_kundali_view["chart_svg"],
    "table": _demo_kundali_view["table"],
    "elemental_balance": _demo_kundali_view["elemental_balance"],
    "house_strength": _demo_kundali_view["house_strength"],
    "aspects": _demo_kundali_view["aspects"],
    "dasha": _demo_kundali_view["dasha"],
    "ascendant_note": _demo_kundali_view["ascendant_note"],
}

# ---------------------------------------------------------------------------
# Personal timeline: Demo User + Demo Family Tree + Karma + Qoins
# ---------------------------------------------------------------------------
DEMO_USER = {
    "name": "Asha Demo",
    "account_id_label": "DEMO-ACCOUNT-ID (fictional — not a real Account ID)",
    "gender": "Female",
    "age_years": 36,
    "age_category": "Yuvak (Youth)",
    "mother_tongue": "Hindi",
    "sun_sign": "Capricorn",
    "sun_element": "Earth",
}

DEMO_KARMA = {
    "total": 128,
    "commercial": 40,
    "noncommercial": 88,
    "explainer": "Karma is a social-credit score for service to others — never money, and never convertible to Qoins.",
}

DEMO_QOINS = {
    "balance": 540,
    "inr_equivalent": 540,
    "weekly_history": [
        {"week": "Demo Week 1", "change": "+120", "reason": "Registration bonus (demo)"},
        {"week": "Demo Week 2", "change": "+80", "reason": "Village post reached its vote threshold (demo)"},
        {"week": "Demo Week 3", "change": "-20", "reason": "Shared with a referred member (demo)"},
        {"week": "Demo Week 4", "change": "+360", "reason": "Community service recognised by the village (demo)"},
    ],
    "explainer": "1 Qoin = ₹1. Qoins are Qumanity's ethical, service-backed economy — a separate system from Karma.",
}

DEMO_FAMILY_MEMBERS = [
    {"id": "gf1", "name": "Mohan Demo", "gender": "Male", "relationship_to_viewer": "Grandfather", "age_years": 78},
    {"id": "gm1", "name": "Savitri Demo", "gender": "Female", "relationship_to_viewer": "Grandmother", "age_years": 74},
    {"id": "f1", "name": "Rohan Demo", "gender": "Male", "relationship_to_viewer": "Father", "age_years": 56},
    {"id": "m1", "name": "Priya Demo", "gender": "Female", "relationship_to_viewer": "Mother", "age_years": 52},
    {"id": "self", "name": "Asha Demo", "gender": "Female", "relationship_to_viewer": "You (demo user)", "age_years": 36},
    {"id": "c1", "name": "Vihaan Demo", "gender": "Male", "relationship_to_viewer": "Son", "age_years": 6},
    {"id": "c2", "name": "Myra Demo", "gender": "Female", "relationship_to_viewer": "Daughter", "age_years": 3},
]
# (parent_id, child_id) -- enough to draw a small three-generation tree.
DEMO_FAMILY_EDGES = [
    ("gf1", "f1"), ("gm1", "f1"),
    ("f1", "self"), ("m1", "self"),
    ("self", "c1"), ("self", "c2"),
]

# ---------------------------------------------------------------------------
# Public timeline: Collective Board + Q-Punch
# ---------------------------------------------------------------------------
DEMO_BOARD_POSTS = [
    {
        "id": "demo-post-1",
        "author_name": "Karan Demo",
        "title": "Proposal: weekly park clean-up rota",
        "content": "Suggest a rotating weekly clean-up for the community park, starting Saturdays. (Demonstration post.)",
        "score": 14,
        "comment_count": 3,
        "created_at_label": "3 demo-days ago",
        "status_label": "Active",
    },
    {
        "id": "demo-post-2",
        "author_name": "Leela Demo",
        "title": "Tuition support for Class 10 students",
        "content": "Offering two free evening study sessions a week for students preparing for board exams. (Demonstration post.)",
        "score": 22,
        "comment_count": 7,
        "created_at_label": "6 demo-days ago",
        "status_label": "Elevated to Tehsil",
    },
    {
        "id": "demo-post-3",
        "author_name": "Devika Demo",
        "title": "Water-logging near the main market",
        "content": "Recurring water-logging after rain near the market entrance. Flagging for council attention. (Demonstration post.)",
        "score": 9,
        "comment_count": 2,
        "created_at_label": "1 demo-day ago",
        "status_label": "Active",
    },
    {
        "id": "demo-post-4",
        "author_name": "Arjun Demo",
        "title": "Thank you to the morning walk group",
        "content": "A note of appreciation for the volunteers who keep the morning walking path clean. (Demonstration post.)",
        "score": 31,
        "comment_count": 5,
        "created_at_label": "9 demo-days ago",
        "status_label": "Active",
    },
]

DEMO_BOARD_STATS = {
    "total_members": 180,
    "total_posts": 24,
    "total_votes": 412,
}

DEMO_QPUNCH = {
    "cycle_label": "Demonstration Election Cycle — Zodiac Sign: Capricorn",
    "status_label": "Nominations open (demonstration)",
    "candidates_male": [
        {"name": "Suresh Demo", "reason": "12 demo-years resident, wants to improve the park and street lighting."},
        {"name": "Anil Demo", "reason": "Runs the demo-village's water-supply coordination group."},
    ],
    "candidates_female": [
        {"name": "Kavita Demo", "reason": "Organizes the demo-village's weekend tuition programme."},
        {"name": "Meena Demo", "reason": "Leads the demo-village's community health outreach."},
    ],
    "turnout_label": "Turnout figures are sealed until voting closes (demonstration).",
    "explainer": "Q-Punch rotates village council leadership by the zodiac calendar — one male and one female head elected every sign-period, six months.",
}

# ---------------------------------------------------------------------------
# Global timeline: geographic hierarchy
# ---------------------------------------------------------------------------
DEMO_GEOGRAPHIC_HIERARCHY = ["Village", "Tehsil", "District", "State", "Zone", "Country", "Continent", "Earth"]

DEMO_GLOBAL_STATS = [
    {"label": "India", "members": "120,000+ (demo figure)"},
    {"label": "Nepal", "members": "8,000+ (demo figure)"},
    {"label": "Bangladesh", "members": "15,000+ (demo figure)"},
    {"label": "Rest of the Qumanity world", "members": "40,000+ (demo figure)"},
]

DEMO_GLOBAL_EXPLAINER = (
    "Every member's local Public account (village level) rolls up through Tehsil, "
    "District, State and Zone into their Country, then into their Continent, and "
    "finally into one shared Global Timeline for Earth — the same nested ledger at every scale."
)


def get_demo_context() -> dict:
    """The one dict the demo route passes to the demo template. Nothing else in this
    module should be read by name from outside it."""
    return {
        "banner_text": DEMO_BANNER_TEXT,
        "grouping_note": DEMO_GROUPING_NOTE,
        "village_label": DEMO_VILLAGE_LABEL,
        "user": DEMO_USER,
        "karma": DEMO_KARMA,
        "qoins": DEMO_QOINS,
        "family_members": DEMO_FAMILY_MEMBERS,
        "family_edges": DEMO_FAMILY_EDGES,
        "kundali": DEMO_KUNDALI,
        "board_posts": DEMO_BOARD_POSTS,
        "board_stats": DEMO_BOARD_STATS,
        "qpunch": DEMO_QPUNCH,
        "geographic_hierarchy": DEMO_GEOGRAPHIC_HIERARCHY,
        "global_stats": DEMO_GLOBAL_STATS,
        "global_explainer": DEMO_GLOBAL_EXPLAINER,
    }
