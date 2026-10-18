#!/usr/bin/env python3
"""
WARNING: THIS SCRIPT IS RETIRED. DO NOT RUN.
It sources from SITAXML.xml, which uses a different ID scheme
from Qumanity_Master.json (the authoritative source). Running
it silently breaks the village dropdown and registration.
See docs/india_location_fix.md.

Historical docstring (for reference only -- do not follow these instructions):

Import all 621,057 real villages from SITAXML.xml into the
india_villages SQLite table, indexed by tehsil_id -- too large (~15-20MB)
to ship as one static JSON like india_districts_tehsils.json, so the
Village step of the location wizard fetches them per-tehsil on demand
via GET /api/india-villages/<tehsil_id> instead.

Run once (or whenever SITAXML.xml changes):
    python3 scripts/import_india_villages.py
"""
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# SITAXML_SOURCE_PATH overrides this (2026-10-11, removing a hardcoded single-Mac path) --
# moot in practice, since this script refuses to run at all without --i-know-this-is-retired.
SRC = os.environ.get(
    "SITAXML_SOURCE_PATH",
    str(Path.home() / "Qumanity_Data" / "SITAXML.xml"),
)
DB_PATH = Path(__file__).resolve().parent.parent.parent / "qumanity_prototype.db"
BATCH_SIZE = 5000


def main():
    if "--i-know-this-is-retired" not in sys.argv:
        print(__doc__)
        print(
            "Refusing to run: this script is retired. Use scripts/import_india_villages.py "
            "(the Qumanity_Master.json version) instead. Pass --i-know-this-is-retired if you "
            "truly intend to run this SITAXML-sourced import anyway.",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM india_villages")
    conn.commit()

    current_tehsil_id = None
    batch = []
    total = 0

    for event, el in ET.iterparse(SRC, events=("start", "end")):
        tag = el.tag
        if event == "start" and tag == "Public_Tehsil":
            current_tehsil_id = el.get("id")
        elif event == "end" and tag == "Public_Tehsil":
            current_tehsil_id = None
            el.clear()
        elif event == "end" and tag == "Public_Village":
            if current_tehsil_id is not None:
                vid = el.get("id")
                name = (el.get("Name") or "").strip()
                batch.append((vid, current_tehsil_id, name))
                total += 1
                if len(batch) >= BATCH_SIZE:
                    conn.executemany(
                        "INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)", batch
                    )
                    conn.commit()
                    batch = []
            el.clear()
        elif event == "end" and tag == "Public_District":
            el.clear()

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)", batch
        )
        conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM india_villages").fetchone()[0]
    print(f"Imported {total} villages, {count} rows in table")
    conn.close()


if __name__ == "__main__":
    main()
