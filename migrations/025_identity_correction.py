"""Identity-correction tickets and the birth-time-unknown flag (2026-10-19): schema for
extending profile_change_requests (app.py) rather than building a parallel id_change_requests
table -- see identity_core.py's module docstring for the three new ticket types and the full
reasoning (why regenerating the 9-digit Private ID never needs a Qmail resync, and why every
other table in this codebase stays correctly attached automatically).

Schema-only, like every other migration in this project. identity_core.ensure_tables() is the
single source of truth for these columns/tables -- it's also called lazily from app.py's
_ensure_profile_change_table() on every request that touches a profile-change ticket, so a DB
that skips this file entirely still self-heals on first use. This file exists for the explicit,
ordered migration run anyway, matching every other schema change in this project."""
from __future__ import annotations

import identity_core


def run(conn) -> None:
    identity_core.ensure_tables(conn)
    print("    profile_change_requests.request_type/location_level/location_id, "
          "profile_change_attachments, and users.birth_time_known ready.")
