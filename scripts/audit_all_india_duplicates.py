#!/usr/bin/env python3
"""India-wide location duplicate audit (READ-ONLY), 2026-11.

Walks the ENTIRE India hierarchy in the canonical Qumanity_Master.json (all 37 States/UTs, every
Zone/State/District/Tehsil/Village) and finds every genuine duplicate: two or more records of the
SAME CATEGORY, with the SAME NAME (trimmed + lowercased only -- no fuzzy matching, no suffix
stripping, no transliteration), under the SAME IMMEDIATE PARENT. Two villages with the same name
under different Tehsils are NOT a duplicate -- that is ordinary, legitimate Indian geography.

This is a RESEARCH script. It never writes to Qumanity_Master.json, static/data/subcontinent_
districts.json, static/data/india_districts_tehsils.json, or any SQLite table. It opens no
database connection at all -- the entire India hierarchy, including villages, lives inside
Qumanity_Master.json itself (confirmed this pass: each tehsil dict carries its own "villages" list
directly; india_villages is a separate, SQLite-only derived cache this script does not need and
does not touch). Its only write is its own new CSV report.

Source resolution reuses the repository's OWN established logic (scripts/import_india_villages.py's
resolve_master_json_path()/load_india_tree()) rather than inventing a new path convention.

Usage:
    python3 scripts/audit_all_india_duplicates.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import import_india_villages as iiv  # noqa: E402 -- reuses the established resolver, not reinvented

SUBCONTINENT_JSON = ROOT / "static" / "data" / "subcontinent_districts.json"
INDIA_DISTRICTS_JSON = ROOT / "static" / "data" / "india_districts_tehsils.json"
OUT_CSV = ROOT / "docs" / f"india_duplicate_audit_{date.today().isoformat()}.csv"

CSV_COLUMNS = [
    "dup_group_id", "category", "parent_id", "parent_name",
    "record_id", "record_name", "child_count", "sibling_ids", "overlap_note",
]


def normalize_name(name: str) -> str:
    """The ONLY normalization this audit applies anywhere: trim whitespace, lowercase. No fuzzy
    matching, no suffix stripping, no transliteration equivalence -- per this audit's own,
    deliberately narrow duplicate definition."""
    return (name or "").strip().lower()


def sha256_of(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def find_duplicates(records: list[dict], parent_id: str, parent_name: str, category: str,
                     child_key: str | None) -> list[dict]:
    """records: this parent's own immediate children (each a dict with 'id'/'name', and
    optionally a list under child_key for computing child_count/overlap). Groups by normalized
    name; returns one dict per DUPLICATE GROUP (len > 1), not yet flattened to CSV rows."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_name[normalize_name(r.get("name", ""))].append(r)
    groups = []
    for norm_name, members in by_name.items():
        if len(members) < 2:
            continue
        sibling_ids = [m["id"] for m in members]
        child_counts = []
        child_name_sets = []
        for m in members:
            children = (m.get(child_key) or []) if child_key else []
            child_counts.append(len(children))
            child_name_sets.append({normalize_name(c.get("name", "")) for c in children})
        overlap_note = _overlap_note(child_name_sets, child_key)
        groups.append({
            "category": category, "parent_id": parent_id, "parent_name": parent_name,
            "members": members, "sibling_ids": sibling_ids, "child_counts": child_counts,
            "combined_child_count": sum(child_counts), "overlap_note": overlap_note,
        })
    return groups


def _overlap_note(child_name_sets: list[set], child_key: str | None) -> str:
    if not child_key:
        return "leaf category -- no children to compare"
    if len(child_name_sets) != 2:
        return f"{len(child_name_sets)}-way duplicate -- pairwise overlap not computed (only 2-way groups are summarized)"
    a, b = child_name_sets
    overlap = len(a & b)
    total = len(a | b)
    if total == 0:
        return "both members have zero children -- nothing to compare"
    return f"{overlap}/{total} exact-normalized child names shared between the two members ({len(a)} vs {len(b)} children)"


def audit_india_tree(india: dict) -> dict:
    """Walks Zones -> States -> Districts -> Tehsils -> Villages. Returns totals and a flat list
    of duplicate groups across all four category levels."""
    totals = {"zones": 0, "states": 0, "districts": 0, "tehsils": 0, "villages": 0}
    all_groups = []

    for zone in india.get("Zones", []):
        totals["zones"] += 1
        states = zone.get("States", [])
        totals["states"] += len(states)
        all_groups += find_duplicates(states, zone["id"], zone["name"], "State", "Districts")

        for state in states:
            districts = state.get("Districts") or []
            totals["districts"] += len(districts)
            all_groups += find_duplicates(districts, state["id"], state["name"], "District", "tehsils")

            for district in districts:
                tehsils = district.get("tehsils") or []
                totals["tehsils"] += len(tehsils)
                all_groups += find_duplicates(tehsils, district["id"], district["name"], "Tehsil", "villages")

                for tehsil in tehsils:
                    villages = tehsil.get("villages") or []
                    totals["villages"] += len(villages)
                    all_groups += find_duplicates(villages, tehsil["id"], tehsil["name"], "Village", None)

    return {"totals": totals, "groups": all_groups}


def cross_reference_derived_files(india: dict) -> dict:
    """Compares the Master's own District/Tehsil ids+names (flattened across all states) against
    static/data/subcontinent_districts.json's corresponding records. Does NOT open either
    derived file in write mode -- read-only comparison only. india_districts_tehsils.json has the
    identical India-only shape, so it is compared the same way, separately.

    subcontinent_districts.json also covers the other 9 Sub-continent countries -- comparing
    Master's India-only districts/tehsils against that file's FULL multi-country content would
    make every non-India district look like a spurious "missing from Master" mismatch. Scoped to
    only the India state ids Master itself defines, to keep the comparison meaningful."""
    master_districts = {}  # id -> name
    master_tehsils = {}    # id -> name
    india_state_ids = set()
    for zone in india.get("Zones", []):
        for state in zone.get("States", []):
            india_state_ids.add(state["id"])
            for d in state.get("Districts") or []:
                master_districts[d["id"]] = d["name"]
                for t in d.get("tehsils") or []:
                    master_tehsils[t["id"]] = t["name"]

    def compare_against(path: Path, scope_to_india_states: bool) -> dict:
        if not path.is_file():
            return {"error": f"{path} not found"}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        derived_districts = {}
        derived_tehsils = {}
        for state_id, state in data.get("states", {}).items():
            if scope_to_india_states and state_id not in india_state_ids:
                continue
            for d in state.get("districts") or []:
                derived_districts[d["id"]] = d["name"]
                for t in d.get("tehsils") or []:
                    derived_tehsils[t["id"]] = t["name"]

        missing_districts_in_derived = sorted(set(master_districts) - set(derived_districts))
        missing_districts_in_master = sorted(set(derived_districts) - set(master_districts))
        district_name_mismatches = sorted(
            did for did in (set(master_districts) & set(derived_districts))
            if master_districts[did] != derived_districts[did]
        )
        missing_tehsils_in_derived = sorted(set(master_tehsils) - set(derived_tehsils))
        missing_tehsils_in_master = sorted(set(derived_tehsils) - set(master_tehsils))
        tehsil_name_mismatches = sorted(
            tid for tid in (set(master_tehsils) & set(derived_tehsils))
            if master_tehsils[tid] != derived_tehsils[tid]
        )
        return {
            "master_district_count": len(master_districts), "derived_district_count": len(derived_districts),
            "master_tehsil_count": len(master_tehsils), "derived_tehsil_count": len(derived_tehsils),
            "missing_districts_in_derived": missing_districts_in_derived,
            "missing_districts_in_master": missing_districts_in_master,
            "district_name_mismatches": district_name_mismatches,
            "missing_tehsils_in_derived": missing_tehsils_in_derived,
            "missing_tehsils_in_master": missing_tehsils_in_master,
            "tehsil_name_mismatches": tehsil_name_mismatches,
        }

    return {
        "subcontinent_districts.json": compare_against(SUBCONTINENT_JSON, scope_to_india_states=True),
        "india_districts_tehsils.json": compare_against(INDIA_DISTRICTS_JSON, scope_to_india_states=False),
    }


def write_csv(groups: list[dict], path: Path) -> int:
    rows_written = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for gid, group in enumerate(groups, start=1):
            for member, child_count in zip(group["members"], group["child_counts"]):
                writer.writerow({
                    "dup_group_id": gid,
                    "category": group["category"],
                    "parent_id": group["parent_id"],
                    "parent_name": group["parent_name"],
                    "record_id": member["id"],
                    "record_name": member["name"],
                    "child_count": child_count,
                    "sibling_ids": "|".join(group["sibling_ids"]),
                    "overlap_note": group["overlap_note"],
                })
                rows_written += 1
    return rows_written


def main() -> int:
    master_path = iiv.resolve_master_json_path()
    print(f"Canonical Master JSON: {master_path}")
    print(f"  size: {master_path.stat().st_size:,} bytes, SHA-256: {sha256_of(master_path)}")
    for p in (SUBCONTINENT_JSON, INDIA_DISTRICTS_JSON):
        if p.is_file():
            print(f"Derived file: {p} -- size {p.stat().st_size:,} bytes, SHA-256: {sha256_of(p)}")
        else:
            print(f"Derived file: {p} -- NOT FOUND")

    india = iiv.load_india_tree(master_path)
    result = audit_india_tree(india)
    totals = result["totals"]
    groups = result["groups"]

    print(f"\nTotal States/UTs examined: {totals['states']}")
    print(f"Total Zones examined: {totals['zones']}")
    print(f"Total Districts examined: {totals['districts']}")
    print(f"Total Tehsils examined: {totals['tehsils']}")
    print(f"Total Villages examined: {totals['villages']}")

    by_category = defaultdict(int)
    for g in groups:
        by_category[g["category"]] += 1
    print("\nDuplicate groups per category:")
    for cat in ("State", "District", "Tehsil", "Village"):
        print(f"  {cat}: {by_category.get(cat, 0)}")
    print(f"Total duplicate groups across all categories: {len(groups)}")

    cross_ref = cross_reference_derived_files(india)
    print("\nCanonical Master vs. derived-file agreement:")
    for fname, cmp in cross_ref.items():
        if "error" in cmp:
            print(f"  {fname}: {cmp['error']}")
            continue
        agree = (not cmp["missing_districts_in_derived"] and not cmp["missing_districts_in_master"]
                  and not cmp["district_name_mismatches"] and not cmp["missing_tehsils_in_derived"]
                  and not cmp["missing_tehsils_in_master"] and not cmp["tehsil_name_mismatches"])
        print(f"  {fname}: {'AGREE' if agree else 'DISAGREE'} "
              f"(districts master={cmp['master_district_count']} derived={cmp['derived_district_count']}, "
              f"missing-in-derived={len(cmp['missing_districts_in_derived'])}, "
              f"missing-in-master={len(cmp['missing_districts_in_master'])}, "
              f"name-mismatches={len(cmp['district_name_mismatches'])}; "
              f"tehsils master={cmp['master_tehsil_count']} derived={cmp['derived_tehsil_count']}, "
              f"missing-in-derived={len(cmp['missing_tehsils_in_derived'])}, "
              f"missing-in-master={len(cmp['missing_tehsils_in_master'])}, "
              f"name-mismatches={len(cmp['tehsil_name_mismatches'])})")
        if cmp["missing_tehsils_in_derived"]:
            sample = cmp["missing_tehsils_in_derived"][:5]
            print(f"    sample tehsil ids present in Master but missing from this derived file: {sample}")

    groups_sorted = sorted(groups, key=lambda g: g["combined_child_count"], reverse=True)
    top = groups_sorted[:10]
    print(f"\nTop {len(top)} largest duplicate groups (by combined child count):")
    for g in top:
        print(f"  [{g['category']}] parent {g['parent_id']} ({g['parent_name']}): "
              f"{g['sibling_ids']} -- combined {g['combined_child_count']} children -- {g['overlap_note']}")

    rows = write_csv(groups, OUT_CSV)
    print(f"\nWrote {rows} row(s) across {len(groups)} duplicate group(s) to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
