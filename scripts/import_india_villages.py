#!/usr/bin/env python3
"""Import all real villages from Qumanity_Master.json into the india_villages SQLite
table, indexed by tehsil_id -- too large (~630K rows) to ship as one static JSON like
india_districts_tehsils.json, so the Village step of the location wizard fetches them
per-tehsil on demand via GET /api/india-villages/<tehsil_id> instead.

IMPORTANT (2026-10-11 correction): this script previously imported from a SITAXML.xml
source whose district/tehsil ids were independently numbered from Qumanity_Master.json's
own tree -- the same ID format (e.g. "CS.DL.3.4") pointed at a DIFFERENT real place in
each source (SITAXML's CS.DL.3.4 is "Patel Nagar"; Master.json's CS.DL.3.4 is "Bawana").
`static/data/india_districts_tehsils.json` and `static/data/subcontinent_districts.json`
(what the registration dropdowns actually serve for Zone/State/District/Tehsil) are
generated from Master.json, so a SITAXML-sourced `india_villages` table silently returned
either the WRONG tehsil's villages or none at all for any tehsil whose number didn't
happen to collide -- see docs/india_location_fix.md (the original 2026-09-28 fix, and
its "Incident: 2026-10-11" section covering this regression and its fix). Master.json is
now the single source for every India level from Zone down to Village -- do not
reintroduce a SITAXML-sourced import here again. The retired SITAXML version lives at
scripts/_retired/import_india_villages_SITAXML.py, guarded behind a flag it refuses to
run without.

Run once (or whenever Qumanity_Master.json's India tree changes):
    python3 scripts/import_india_villages.py
"""
import json
import sqlite3
from pathlib import Path

MASTER_JSON = Path("/Users/macmudgal/Desktop/0_Earth/Qumanity_Master.json")
DB_PATH = Path(__file__).resolve().parent.parent / "qumanity_prototype.db"
BATCH_SIZE = 5000


def main():
    with open(MASTER_JSON, encoding="utf-8") as f:
        master = json.load(f)

    asia = next(c for c in master["Continents"] if c["name"] == "Asia")
    india = next(c for c in asia["Countries"] if c.get("name") == "India")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM india_villages")
    conn.commit()

    batch = []
    total = 0
    for zone in india["Zones"]:
        for state in zone["States"]:
            for district in state["Districts"]:
                for tehsil in district["tehsils"]:
                    tehsil_id = tehsil["id"]
                    for village in tehsil.get("villages", []):
                        vid = village.get("id")
                        name = (village.get("name") or "").strip()
                        if not vid or not name:
                            continue
                        batch.append((vid, tehsil_id, name))
                        total += 1
                        if len(batch) >= BATCH_SIZE:
                            conn.executemany(
                                "INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)", batch
                            )
                            conn.commit()
                            batch = []

    if batch:
        conn.executemany(
            "INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)", batch
        )
        conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM india_villages").fetchone()[0]
    print(f"Imported {total} villages from Master.json, {count} rows in table")
    conn.close()


if __name__ == "__main__":
    main()
