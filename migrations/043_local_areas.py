"""Local Areas (2026-11-18): sub-divisions within a village -- a membership/identity layer only,
no Collective Board of their own (Decision 2 of this feature's approved architecture; posting,
voting and Qoins stay on the Village board). See local_area_core.py's own module docstring for the
full rule set (one Local Area per user at a time, hard-locked moves after the first free join,
Nayak/Nayika-or-Founder-only creation and move approval).

local_areas: one row per named sub-division of a village. local_area_members: one row per
user-per-Local-Area they've ever joined (status active|left -- never deleted, since the lock is
"you've been in one before," not just "are you in one now"). local_area_move_requests: one row per
pending/approved/denied move, including the first-ever request after a leave.

Added via local_area_core.ensure_tables() -- the same self-healing function this migration calls,
so a database that skips this file entirely still self-heals the first time any local_area_core.py
route runs, same as every migration in this project that defers to its owning module."""
from __future__ import annotations

import local_area_core


def run(conn) -> None:
    local_area_core.ensure_tables(conn)
    print("    local_areas, local_area_members and local_area_move_requests ready.")
