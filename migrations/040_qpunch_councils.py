"""Q-Punch cascade, Phase 2 (2026-11-16): schema only, for the Tehsil-to-Earth governance layer
above the existing village-only pilot (election_core.py's own village_council/election_cycles).
No nomination, voting, or quarterly element-rotation logic is built here -- see the approved
governance brief this schema was designed against; Phase 3 is what will actually read and write
most of what this migration creates.

election_cycles.level (new column, NOT NULL DEFAULT 'village' so every pre-existing row keeps
being exactly what it already was): which governance level a cycle belongs to. 'village' keeps
running through the existing 12-sign-per-year cycle, completely unchanged; 'tehsil' through
'earth' are for Phase 3's not-yet-built 8-seat cycle.

qpunch_councils / qpunch_council_members (new tables, Tehsil and up only -- village_council is
untouched, per the brief's own "Village vs Upper Levels" distinction: the village's 24 members
still train for 11 months and go active for their one zodiac month, exactly as today).
qpunch_councils is one row per (location, level, term) -- 3/5/7/9/11/13-year terms per
election_core.TERM_YEARS_BY_LEVEL, for tehsil/district/state/zone/country/continent respectively,
15 years for earth. active_element/head_user_id/head_gender are deliberately left NULL by this
migration -- they exist so Phase 3's quarterly rotation (the term split into 4 equal quarters, one
element leading each) has somewhere to write its current state, not because anything computes them
yet. qpunch_council_members holds the 8 seats under each council, one row per (gender, element)
pair.

Both new tables, and the election_cycles.level column, are added via election_core.py's own
self-healing functions (ensure_council_columns()/ensure_qpunch_tables()) -- the same pattern
migration 027 already used for family_groups' own added columns -- so a database that skips this
file entirely still self-heals the first time any election_core.py route runs."""
from __future__ import annotations

import election_core


def run(conn) -> None:
    election_core.ensure_council_columns(conn)
    election_core.ensure_qpunch_tables(conn)
    print("    election_cycles.level, qpunch_councils, and qpunch_council_members ready.")
