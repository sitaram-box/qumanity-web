"""Nuclear Family Node architecture (2026-10-20): a family_groups row becomes a MARRIAGE UNIT, not
a generic container -- see family_core.py's module docstring for the full lifecycle (creation,
sub-nodes, dormancy, chat hierarchy).

Adds to family_groups: husband_node_id, wife_node_id (the unit's two founders),
husband_parent_group_id, wife_parent_group_id (each founder's own birth unit, if known), and
marriage_status (replaces family_spouse_links, deprecated as of this pass, as the "already
married" check -- see family_core.py's docstring for why). Also adds people_requests.target_node_id
(a spousal join request now means "let me claim this specific empty founder slot," which needs to
be recorded on the request itself).

Schema-only, like every other migration in this project. family_core.ensure_tables() is the single
source of truth for all of this -- also called lazily from every family/* route, so a DB that
skips this file entirely still self-heals on first use."""
from __future__ import annotations

import family_core


def run(conn) -> None:
    family_core.ensure_tables(conn)
    print("    family_groups.husband_node_id/wife_node_id/husband_parent_group_id/"
          "wife_parent_group_id/marriage_status, and people_requests.target_node_id ready.")
