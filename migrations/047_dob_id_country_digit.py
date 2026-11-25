"""Adds users.dob_id_country_digit (2026-11-25): the single digit (0-9) recorded at ID-assignment
time for the new DOB-based Private ID scheme (id_generator.generate_dob_id). Stored rather than
re-derived from birth_location_json on every registration so the "how many users already share
this (dob, country_digit) pair" count in generate_dob_id() stays a plain indexed WHERE clause.
See docs/economic_engine_phase1_design_2026_11_25.md's sibling design note for the DOB-ID scheme
(country_digit_for() in id_generator.py) and migrate_to_dob_ids.py for the one-off backfill of
existing users.
"""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "dob_id_country_digit" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN dob_id_country_digit TEXT")
    conn.commit()
    print("    users.dob_id_country_digit ready (default NULL).")
