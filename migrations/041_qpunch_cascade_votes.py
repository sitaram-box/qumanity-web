"""Q-Punch cascade, Phase 3 (2026-11-16): adds the two vote-shaped tables Phase 2's schema didn't
yet have -- see election_core.py's QPUNCH_SCHEMA docstring for the full reasoning on why each is
its own table rather than a widened version of an existing one:

qpunch_cascade_votes: the Lower House's own seat votes at Tehsil-and-up (parallel to village's
election_votes, not a reuse of it -- a Lower House voter can cast up to 8 votes per cycle, 1 male
+ 1 female per element with no "your own element" restriction, which election_votes' own
UNIQUE(election_cycle_id, voter_user_id, gender) constraint was never built to allow, and SQLite
can't widen a UNIQUE constraint on a live table in place).

qpunch_head_approvals / qpunch_head_approval_votes: the Upper House's 51%-approval referendum on
one quarter's Male candidate -- a yes/no vote on one person, not a pick-one-of-N election, so it
doesn't fit either votes table's shape either.

Added via election_core.ensure_qpunch_tables() -- the same self-healing function migration 040
already calls, now with 3 more CREATE TABLE statements in its own QPUNCH_SCHEMA string -- so a
database that skips this file entirely still self-heals the first time any election_core.py route
runs, same as every migration in this project that defers to its owning module."""
from __future__ import annotations

import election_core


def run(conn) -> None:
    election_core.ensure_qpunch_tables(conn)
    print("    qpunch_cascade_votes, qpunch_head_approvals, and qpunch_head_approval_votes ready.")
