"""Crowdsourced Location System, MVP Phases A/B/C/E (2026-11): schema for
provisional_location_core.py -- see that module's own docstring for the full three-layer
architecture (verified directory / provisional submissions / GPS observations).

Adds: provisional_locations, provisional_location_members, location_submission_events,
user_location_observations, location_centroid_observations.

Schema-only, like every other migration in this project (see migrations/026_family_tree.py for
the identical pattern). provisional_location_core.ensure_tables() is the single source of truth
for all of this -- also called lazily from every provisional-location/observation route, so a DB
that skips this file entirely still self-heals on first use.

Deliberately does NOT create any OSM table (osm_features / qmap_location_osm_features /
osm_query_jobs) -- those belong to the explicitly deferred OSM/Overpass/Q-Map phase, not this
migration."""
from __future__ import annotations

import provisional_location_core


def run(conn) -> None:
    provisional_location_core.ensure_tables(conn)
    print("    provisional_locations, provisional_location_members, location_submission_events, "
          "user_location_observations, location_centroid_observations ready.")
