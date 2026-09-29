#!/usr/bin/env python3
"""Import all 621,057 real villages from SITAXML.xml into the
india_villages SQLite table, indexed by tehsil_id — too large (~15-20MB)
to ship as one static JSON like india_districts_tehsils.json, so the
Village step of the location wizard fetches them per-tehsil on demand
via GET /api/india-villages/<tehsil_id> instead.

Run once (or whenever SITAXML.xml changes):
    python3 scripts/import_india_villages.py
"""
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

SRC = "/Users/macmudgal/Desktop/Windows Data/sita foundation/SITA Project Data/SITAXML.xml"
DB_PATH = Path(__file__).resolve().parent.parent / "qumanity_prototype.db"
BATCH_SIZE = 5000


def main():
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
