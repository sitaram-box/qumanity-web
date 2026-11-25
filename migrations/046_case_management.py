"""Qumanity Economic Engine, Phase 2 Step 1 (2026-11-25): adds the Case Management schema
(agents, suppliers, supplier_ratings, qumanity_cases, case_logs, compass_tasks) via the new
case_core.py module. See docs/economic_engine_phase1_design_2026_11_25.md for the full design
and the Founder's Phase 2 decisions this schema encodes.

Delegates to case_core.ensure_tables() -- the same self-healing-module pattern every migration in
this project follows (see migration 045), so a database that skips this file entirely still
self-heals the first time case_core's own route runs."""
from __future__ import annotations

import case_core


def run(conn) -> None:
    case_core.ensure_tables(conn)
    print("    qumanity_cases, case_logs, compass_tasks, agents, suppliers, supplier_ratings ready.")
