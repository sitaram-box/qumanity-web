#!/usr/bin/env python3
"""Standalone CLI entry point for the OSM proximity worker -- runs one bounded batch of queued
Overpass proximity lookups and exits. Useful for a manual run or a cron-style invocation outside
the in-process BackgroundScheduler that osm_proximity_core.init_scheduler() already registers
(that scheduler runs this same logic automatically every 15 minutes inside the running app; this
script exists for ad hoc/manual runs, same relationship fetch_north_west_delhi_osm.py has to
nothing automatic). See osm_proximity_core.py's own module docstring for the full architecture,
consent model, and the Overpass fair-use caveat.

Usage:
    python3 osm_proximity_worker.py [--worker-id NAME]
"""
from __future__ import annotations

import argparse
import sys

import db as dbmod
import osm_proximity_core


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worker-id", default="manual-run", help="Identifies this worker instance in the job-claim log")
    args = ap.parse_args()

    conn = dbmod.get_db()
    try:
        osm_proximity_core.ensure_tables(conn)
        result = osm_proximity_core.run_worker_once(conn, worker_id=args.worker_id)
    finally:
        conn.close()

    print(f"Jobs processed: {result['jobs_processed']}")
    for r in result["results"]:
        print(f"  {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
