"""Family Tree birth order (2026-11-18, Phase 1 Item 3): an admin-settable manual override for
ordering siblings/children when neither a real nor an approximate date of birth is known -- see
family_core.py's own _sort_people_by_birth() for how this, dob/dob_approx, and created_at combine
into one sort key. Added via family_core.ensure_tables() -- the same self-healing function this
migration calls, same thin-delegate pattern as migrations/043_local_areas.py."""
from __future__ import annotations

import family_core


def run(conn) -> None:
    family_core.ensure_tables(conn)
    print("    family_nodes.birth_order ready.")
