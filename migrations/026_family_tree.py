"""Family Tree and Family Groups, Phase 1 (2026-10-20): schema for family_core.py -- see that
module's docstring for the full architecture and why this is deliberately NOT built on top of
personal_groups (category='family' there already carries privacy-sensitive meaning for
social_core.is_family_member()/hide_identity).

Adds: family_nodes, family_parent_links, family_spouse_links (the genealogical tree), and
family_groups, family_group_members, family_group_messages, family_group_nodes (the shared,
joinable chat/network layer on top of it), plus users.timeline_activated_at.

Schema-only, like every other migration in this project. family_core.ensure_tables() is the
single source of truth for all of this -- also called lazily from every family/* route, so a DB
that skips this file entirely still self-heals on first use."""
from __future__ import annotations

import family_core


def run(conn) -> None:
    family_core.ensure_tables(conn)
    print("    family_nodes, family_parent_links, family_spouse_links, family_groups, "
          "family_group_members, family_group_messages, family_group_nodes, and "
          "users.timeline_activated_at ready.")
