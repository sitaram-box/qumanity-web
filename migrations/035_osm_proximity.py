"""Adds the OSM Coordinate Linking tables for the Q-Map foundation (2026-11): osm_proximity_jobs
(durable job queue), osm_feature_cache (shared OSM feature cache), user_osm_proximity (the
user-to-OSM-feature association table). See osm_proximity_core.py's own module docstring for the
full architecture and consent model.
"""
from __future__ import annotations

import osm_proximity_core


def run(conn) -> None:
    osm_proximity_core.ensure_tables(conn)
    print("    osm_proximity_jobs / osm_feature_cache / user_osm_proximity ready.")
