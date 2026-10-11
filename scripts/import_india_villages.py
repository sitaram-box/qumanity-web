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

IMPORTANT (2026-10-11, part 2 -- Railway data-seeding fix): this script previously
hardcoded a Mac-only path to Qumanity_Master.json, so it silently couldn't run at all
inside the Railway container (production shipped with an empty india_villages table --
see docs/india_location_fix.md's "Incident: 2026-10-11 Production DB Never Seeded"
section). Master.json and the DB path are now resolved from MASTER_JSON_PATH/QM_DB_PATH
env vars with environment-appropriate fallbacks (see resolve_master_json_path() /
resolve_db_path() below) -- the same script now runs unmodified on Mac dev or inside the
Railway container.

Usage:
    python3 scripts/import_india_villages.py              # import
    python3 scripts/import_india_villages.py --dry-run     # count only, no DB writes
    python3 scripts/import_india_villages.py --verify      # import, then sanity-check
    python3 scripts/import_india_villages.py --dry-run --verify   # dry-run ignores --verify
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BATCH_SIZE = 5000
PROGRESS_EVERY = 100_000


def resolve_master_json_path() -> Path:
    """MASTER_JSON_PATH env var first; otherwise, in order: the Railway volume, the repo
    root (in case it's ever bundled there), then the Mac dev default. Exits with a clear
    error listing every path tried if none exist."""
    candidates = []
    env = os.environ.get("MASTER_JSON_PATH")
    if env:
        candidates.append(Path(env).expanduser())
    candidates += [
        Path("/data/Qumanity_Master.json"),
        REPO_ROOT / "Qumanity_Master.json",
        Path("~/Desktop/0_Earth/Qumanity_Master.json").expanduser(),
    ]
    for c in candidates:
        if c.exists():
            return c
    print("ERROR: Qumanity_Master.json not found. Tried:", file=sys.stderr)
    for c in candidates:
        print(f"  {c}", file=sys.stderr)
    sys.exit(1)


def resolve_db_path() -> Path:
    """QM_DB_PATH env var first (same variable db.py itself honors, so this script always
    writes to the exact DB the running app reads) -- otherwise the Railway volume if it's
    mounted, else the local repo-root default."""
    env = os.environ.get("QM_DB_PATH")
    if env:
        return Path(env).expanduser()
    if Path("/data").is_dir():
        return Path("/data/qumanity_prototype.db")
    return REPO_ROOT / "qumanity_prototype.db"


def load_india_tree(master_path: Path) -> dict:
    with open(master_path, encoding="utf-8") as f:
        master = json.load(f)
    asia = next(c for c in master["Continents"] if c["name"] == "Asia")
    india = next(c for c in asia["Countries"] if c.get("name") == "India")
    return india


def iter_villages(india: dict):
    """Yields (village_id, tehsil_id, name) for every village in the India tree."""
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
                        yield vid, tehsil_id, name


def do_dry_run(master_path: Path) -> int:
    india = load_india_tree(master_path)
    total = 0
    tehsil_ids = set()
    for vid, tehsil_id, name in iter_villages(india):
        total += 1
        tehsil_ids.add(tehsil_id)
        if total % PROGRESS_EVERY == 0:
            print(f"[dry-run] {total:,} villages counted so far...")
    print(f"[dry-run] Would import {total:,} villages across {len(tehsil_ids):,} tehsils. No DB writes made.")
    return total


def do_import(master_path: Path, db_path: Path) -> int:
    india = load_india_tree(master_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM india_villages")
    conn.commit()

    batch = []
    total = 0
    for vid, tehsil_id, name in iter_villages(india):
        batch.append((vid, tehsil_id, name))
        total += 1
        if len(batch) >= BATCH_SIZE:
            conn.executemany("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)", batch)
            conn.commit()
            batch = []
        if total % PROGRESS_EVERY == 0:
            print(f"[import] {total:,} villages imported so far...")

    if batch:
        conn.executemany("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)", batch)
        conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM india_villages").fetchone()[0]
    conn.close()
    print(f"Imported {total:,} villages from {master_path}, {count:,} rows in table at {db_path}")
    return count


def do_verify(db_path: Path) -> bool:
    """Sanity check after import: village count, distinct tehsil_id count, and how many of
    those tehsil_ids are NOT present in subcontinent_districts.json (the file the
    registration dropdowns actually serve) -- should be 0. Mirrors the same check
    app.py's _validate_india_villages_loaded() runs at boot (see docs/india_location_fix.md)."""
    conn = sqlite3.connect(db_path)
    village_count = conn.execute("SELECT COUNT(*) FROM india_villages").fetchone()[0]
    db_tehsil_ids = {r[0] for r in conn.execute("SELECT DISTINCT tehsil_id FROM india_villages")}
    conn.close()

    districts_path = REPO_ROOT / "static" / "data" / "subcontinent_districts.json"
    web_tehsil_ids = set()
    if districts_path.exists():
        with open(districts_path, encoding="utf-8") as f:
            web = json.load(f)
        web_tehsil_ids = {t["id"] for state in web["states"].values() for d in state["districts"] for t in d["tehsils"]}

    orphaned = db_tehsil_ids - web_tehsil_ids
    print(f"[verify] village_count: {village_count:,}")
    print(f"[verify] distinct tehsil_id count: {len(db_tehsil_ids):,}")
    print(f"[verify] tehsil_id values NOT in subcontinent_districts.json: {len(orphaned):,}")

    ok = village_count > 0 and len(orphaned) == 0
    print("[verify] PASS" if ok else "[verify] FAIL")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Count what would be imported, without writing to the DB.")
    parser.add_argument("--verify", action="store_true", help="After importing, run the tehsil_id sanity check and print PASS/FAIL.")
    args = parser.parse_args()

    master_path = resolve_master_json_path()

    if args.dry_run:
        do_dry_run(master_path)
        return

    db_path = resolve_db_path()
    do_import(master_path, db_path)

    if args.verify:
        ok = do_verify(db_path)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
