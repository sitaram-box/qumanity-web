"""Unified Chat Architecture, Phase 2 Step 1 (2026-11-24): generalizes board_core's Village-only
`subgroups` into location-level-generic Governance Channels (needed for things like a Tehsil
"Water Supply" channel, which the old village-only schema could never represent), adds the new
chat_core.py module's temporary cross-location access table (the dual Account ID feature), and
adds users.last_seen_at/presence_override for the new presence system. See the Phase 1 research
response (2026-11-20, this engagement) for the full reasoning behind each piece.

Delegates to board_core.ensure_sub_tables() (already self-healing, now also handles the subgroups
generalization) and chat_core.ensure_tables() (the new module) -- the same self-healing-module
pattern every migration in this project already follows, so a database that skips this file
entirely still self-heals the first time either module's own route runs."""
from __future__ import annotations

import board_core
import chat_core


def run(conn) -> None:
    board_core.ensure_sub_tables(conn)
    chat_core.ensure_tables(conn)
    print("    subgroups generalized to (location_id, location_level); temporary_location_access, "
          "users.last_seen_at/presence_override ready.")
