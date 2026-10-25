#!/usr/bin/env python3
"""Fixes Haryana's incomplete district list in Qumanity_Master.json (2026-10-20 audit, amended
2026-10-25 after a second pass found a third kind of error -- see below).

THE BUG, PART 1: Master.json's India tree lists only 10 of Haryana's 22 real districts. 10 of
the other 12 already exist in the source, just one level too deep, nested as a TEHSIL under an
older/combined parent district (e.g. "Rewari" is a tehsil of "Gurgaon", not its own district --
so a user registering from Rewari can never find it in the District dropdown, only Gurgaon).

THE BUG, PART 2 (found 2026-10-25, corrects the original plan): the remaining 2 districts --
Bhiwani, Mahendragarh -- and the 1 genuinely missing one, Charkhi Dadri, were NOT absent from the
source at all, as the original version of this script assumed. They're all three merged into a
single Master.json entry named "Bhiwani-Mahendragarh" (id NS.HR.7), which carries real village
data for all of them under their own correctly-named tehsils (Bhiwani/Tosham/Loharu/Siwani;
Mahendragarh/Narnaul/Ateli/Nangal Chaudhry; Dadri/Badhra). The original plan would have shipped
Charkhi Dadri as a fabricated, empty placeholder district while real village data for it sat one
entry away -- SPLIT_BHIWANI_MAHENDRAGARH below fixes that by splitting the merged entry into its
three real districts, reusing their real tehsils/villages, inventing nothing.

THE FIX: promote each of the 10 demoted tehsils (PROMOTIONS) to be its own top-level district
(reusing its existing villages unchanged -- only the tehsil's own id, and its new parent
district's id, are new), and split "Bhiwani-Mahendragarh" (SPLIT_BHIWANI_MAHENDRAGARH) into its
three real constituent districts, each keeping its own real tehsils and villages. 10 + 3 new
districts, on top of the 9 original districts that keep their name (Bhiwani-Mahendragarh itself
is removed, not kept, since nothing remains under that merged name) = 22, Haryana's real count.

SAFETY: this script does NOT touch the database, the website's generated JSON files, or any
user's location data by itself -- it only edits (a backed-up copy of) Qumanity_Master.json.
Two further, separate scripts handle the rest of the safety net:
  - scripts/migrate_haryana_location_ids.py -- must run AFTER this, to re-point any existing
    user whose present/birth location was filed under one of the OLD (soon-to-be-stale) ids.
  - scripts/regenerate_location_data.py -- must run after THAT, to rebuild the website's
    district/tehsil JSON files and the india_villages table from the corrected Master.json.
Running this script alone, without the other two, would make existing Rewari-area residents'
accounts resolve to a district/tehsil id that no longer exists in the tree.

Defaults to a DRY RUN (computes and prints the full before/after picture, writes nothing) --
pass --apply to actually back up and overwrite Master.json and write the remap manifest that
migrate_haryana_location_ids.py needs.

Usage:
    python3 scripts/fix_haryana_districts.py              # dry run -- prints the plan only
    python3 scripts/fix_haryana_districts.py --apply       # backs up + writes Master.json,
                                                            # writes scripts/haryana_id_remap.json
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "scripts" / "haryana_id_remap.json"

# (old_district_id, old_district_name, [tehsil names to promote], new_district_id, new_district_name)
# New ids continue Haryana's existing single-character suffix scheme (1-9, A) with B-K.
# A tehsil name list with more than one entry (Panipat) means multiple existing tehsils merge
# under ONE new district -- matching reality (Panipat district has "Panipat City" and "Panipat
# Rural" tehsils; the source already has both, just filed under the wrong parent, Karnal).
PROMOTIONS = [
    ("NS.HR.6", "Sirsa", ["Fatehabad"], "NS.HR.B", "Fatehabad"),
    ("NS.HR.8", "Rohtak", ["Jhajjar"], "NS.HR.C", "Jhajjar"),
    ("NS.HR.4", "Sonipat", ["Jind"], "NS.HR.D", "Jind"),
    ("NS.HR.2", "Kurukshetra", ["Kaithal"], "NS.HR.E", "Kaithal"),
    ("NS.HR.9", "Gurgaon", ["Nuh"], "NS.HR.F", "Nuh"),
    ("NS.HR.A", "Faridabad", ["Palwal"], "NS.HR.G", "Palwal"),
    ("NS.HR.1", "Ambala", ["Panchkula"], "NS.HR.H", "Panchkula"),
    ("NS.HR.3", "Karnal", ["Panipat City", "Panipat Rural"], "NS.HR.I", "Panipat"),
    ("NS.HR.9", "Gurgaon", ["Rewari"], "NS.HR.J", "Rewari"),
    ("NS.HR.1", "Ambala", ["Yamunanagar"], "NS.HR.K", "Yamunanagar"),
]

# NS.HR.7 "Bhiwani-Mahendragarh" isn't one tehsil demoted -- the whole district entry is a MERGER
# of three real Haryana districts. All of its tehsils redistribute into these three; nothing is
# left over under the old merged name (apply_split() checks this and raises if any tehsil isn't
# accounted for). New ids continue straight on from PROMOTIONS' own B-K scheme: L, M, N.
SPLIT_BHIWANI_MAHENDRAGARH = {
    "old_district_id": "NS.HR.7", "old_district_name": "Bhiwani-Mahendragarh",
    "splits": [
        ("NS.HR.L", "Bhiwani", ["Bhiwani", "Tosham", "Loharu", "Siwani"]),
        ("NS.HR.M", "Mahendragarh", ["Mahendragarh", "Narnaul", "Ateli", "Nangal Chaudhry"]),
        ("NS.HR.N", "Charkhi Dadri", ["Dadri", "Badhra"]),
    ],
}


def resolve_master_json_path() -> Path:
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


def find_haryana(master: dict) -> dict:
    asia = next(c for c in master["Continents"] if c["name"] == "Asia")
    india = next(c for c in asia["Countries"] if c.get("name") == "India")
    for zone in india["Zones"]:
        for state in zone["States"]:
            if (state.get("name") or "").strip().lower() == "haryana":
                return state
    raise LookupError("Haryana not found in Qumanity_Master.json")


def apply_promotions(haryana: dict) -> list[dict]:
    """Mutates haryana["Districts"] in place: removes each named tehsil from its old district and
    appends a new top-level district containing it (re-ided under the new district). Returns the
    remap manifest migrate_haryana_location_ids.py needs: one entry per OLD tehsil id."""
    manifest = []

    for old_district_id, old_district_name, tehsil_names, new_district_id, new_district_name in PROMOTIONS:
        old_district = next((d for d in haryana["Districts"] if d["id"] == old_district_id), None)
        if old_district is None:
            raise LookupError(f"Expected old district {old_district_id} ({old_district_name}) not found -- "
                               f"Master.json may have changed since this script was written; re-verify before applying.")
        if old_district["name"] != old_district_name:
            raise ValueError(f"District {old_district_id} is named {old_district['name']!r}, expected "
                              f"{old_district_name!r} -- re-verify before applying.")

        moved_tehsils = []
        for tehsil_name in tehsil_names:
            match = next((t for t in old_district["tehsils"] if t["name"] == tehsil_name), None)
            if match is None:
                raise LookupError(f"Expected tehsil {tehsil_name!r} not found under {old_district_name} -- "
                                   f"re-verify before applying.")
            old_district["tehsils"].remove(match)
            moved_tehsils.append(match)

        new_tehsils = []
        for i, t in enumerate(moved_tehsils, start=1):
            old_tehsil_id = t["id"]
            new_tehsil_id = f"{new_district_id}.{i}"
            t["id"] = new_tehsil_id
            new_tehsils.append(t)
            manifest.append({
                "old_district_id": old_district_id, "old_district_name": old_district_name,
                "old_tehsil_id": old_tehsil_id, "old_tehsil_name": t["name"],
                "new_district_id": new_district_id, "new_district_name": new_district_name,
                "new_tehsil_id": new_tehsil_id, "new_tehsil_name": t["name"],
            })

        haryana["Districts"].append({"id": new_district_id, "name": new_district_name, "tehsils": new_tehsils})

    return manifest


def apply_split(haryana: dict, split: dict) -> list[dict]:
    """Removes the old MERGED district entirely and redistributes every one of its tehsils into
    the new, real districts named in split['splits'] -- unlike apply_promotions() (where the old
    district survives, just missing the tehsil(s) that moved out), nothing remains under the old
    merged name once this returns: Bhiwani-Mahendragarh never meant one place, so there's nothing
    left to keep a row for. Raises if any tehsil under the old district isn't claimed by exactly
    one entry in split['splits'] -- silently dropping a tehsil nobody's list mentions would lose
    its villages, so this refuses to apply rather than guess. Returns the same remap-manifest
    shape apply_promotions() does, so migrate_haryana_location_ids.py needs no changes to consume
    both in one run."""
    old_district = next((d for d in haryana["Districts"] if d["id"] == split["old_district_id"]), None)
    if old_district is None:
        raise LookupError(f"Expected old district {split['old_district_id']} ({split['old_district_name']}) not found -- "
                           f"Master.json may have changed since this script was written; re-verify before applying.")
    if old_district["name"] != split["old_district_name"]:
        raise ValueError(f"District {split['old_district_id']} is named {old_district['name']!r}, expected "
                          f"{split['old_district_name']!r} -- re-verify before applying.")

    unclaimed_tehsil_names = {t["name"] for t in old_district["tehsils"]}
    manifest = []
    new_districts = []
    for new_district_id, new_district_name, tehsil_names in split["splits"]:
        moved_tehsils = []
        for tehsil_name in tehsil_names:
            match = next((t for t in old_district["tehsils"] if t["name"] == tehsil_name), None)
            if match is None:
                raise LookupError(f"Expected tehsil {tehsil_name!r} not found under {split['old_district_name']} -- "
                                   f"re-verify before applying.")
            moved_tehsils.append(match)
            unclaimed_tehsil_names.discard(tehsil_name)

        new_tehsils = []
        for i, t in enumerate(moved_tehsils, start=1):
            old_tehsil_id = t["id"]
            new_tehsil_id = f"{new_district_id}.{i}"
            t["id"] = new_tehsil_id
            new_tehsils.append(t)
            manifest.append({
                "old_district_id": split["old_district_id"], "old_district_name": split["old_district_name"],
                "old_tehsil_id": old_tehsil_id, "old_tehsil_name": t["name"],
                "new_district_id": new_district_id, "new_district_name": new_district_name,
                "new_tehsil_id": new_tehsil_id, "new_tehsil_name": t["name"],
            })
        new_districts.append({"id": new_district_id, "name": new_district_name, "tehsils": new_tehsils})

    if unclaimed_tehsil_names:
        raise ValueError(f"split['splits'] doesn't account for every tehsil under {split['old_district_name']}: "
                          f"{sorted(unclaimed_tehsil_names)} left over -- fix the splits list before applying, "
                          f"rather than silently losing their villages.")

    haryana["Districts"].remove(old_district)
    haryana["Districts"].extend(new_districts)
    return manifest


def _village_count(district: dict) -> int:
    return sum(len(t.get("villages", [])) for t in district["tehsils"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Back up and overwrite Master.json, and write the remap manifest. Without this flag, prints the plan only.")
    args = parser.parse_args()

    master_path = resolve_master_json_path()
    print(f"Reading {master_path} ...")
    with open(master_path, encoding="utf-8") as f:
        master = json.load(f)

    haryana = find_haryana(master)
    before_count = len(haryana["Districts"])
    before_villages = sum(_village_count(d) for d in haryana["Districts"])

    working = copy.deepcopy(master)
    haryana_working = find_haryana(working)
    manifest = apply_promotions(haryana_working)
    manifest += apply_split(haryana_working, SPLIT_BHIWANI_MAHENDRAGARH)

    after_count = len(haryana_working["Districts"])
    after_villages = sum(_village_count(d) for d in haryana_working["Districts"])

    print(f"\nHaryana districts: {before_count} -> {after_count} (+{after_count - before_count})")
    print(f"Haryana villages:  {before_villages:,} -> {after_villages:,} "
          f"({'unchanged' if before_villages == after_villages else 'CHANGED -- investigate'})")
    print(f"\n{len(manifest)} tehsil(s) re-ided across {len(set((m['old_district_id'] for m in manifest)))} old district(s):")
    for m in manifest:
        print(f"  {m['old_tehsil_id']} ({m['old_tehsil_name']}, under {m['old_district_name']}) "
              f"-> district {m['new_district_id']} ({m['new_district_name']}), tehsil {m['new_tehsil_id']}")

    if not args.apply:
        print("\nDry run only -- nothing written. Re-run with --apply to write Master.json and the remap manifest.")
        return

    if before_villages != after_villages:
        print("\nABORTING: village count changed during promotion -- this should never happen. Not writing anything.", file=sys.stderr)
        sys.exit(1)

    backup_path = master_path.with_name(f"{master_path.stem}.before_haryana_fix_{dt.datetime.now():%Y%m%d_%H%M%S}{master_path.suffix}")
    print(f"\nBacking up original to {backup_path} ...")
    backup_path.write_text(json.dumps(master, ensure_ascii=False), encoding="utf-8")

    print(f"Writing corrected Master.json to {master_path} ...")
    master_path.write_text(json.dumps(working, ensure_ascii=False), encoding="utf-8")

    print(f"Writing remap manifest to {MANIFEST_PATH} ...")
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nDone. Next: python3 scripts/migrate_haryana_location_ids.py --apply")


if __name__ == "__main__":
    main()
