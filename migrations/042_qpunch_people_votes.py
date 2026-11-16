"""Upper House Sovereignty, Phase 5 (2026-11-16): schema for the People's Vote -- a direct
referendum the Upper House (a location's own general population, never just its Lower House or
Q-Punch council) can call on any question, at any level. See election_core.py's own "Upper House
Sovereignty" section header for the full constitutional reasoning, and
cast_head_approval_vote()'s own docstring for how the existing 51% Head Approval relates to this
(one standing, pre-wired instance of the same power -- unchanged by this migration).

qpunch_people_votes: one row per referendum (location, level, title, description, status, the
cached votes_for/votes_against once resolved, and its voting window). qpunch_people_vote_ballots:
one row per individual ballot.

This pass builds the record only, per the brief that authorized it -- actually enforcing a passed
vote's result against the Q-Punch council's own decisions is a separate, later task.

Added via election_core.ensure_qpunch_tables() -- the same self-healing function migrations 040
and 041 already call, now with 2 more CREATE TABLE statements in its own QPUNCH_SCHEMA string --
so a database that skips this file entirely still self-heals the first time any election_core.py
route runs, same as every migration in this project that defers to its owning module."""
from __future__ import annotations

import election_core


def run(conn) -> None:
    election_core.ensure_qpunch_tables(conn)
    print("    qpunch_people_votes and qpunch_people_vote_ballots ready.")
