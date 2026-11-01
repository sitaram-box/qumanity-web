#!/usr/bin/env python3
"""Classify whether each Indian state/UT's "District" level in the canonical Qumanity_Master.json
is more consistent with ELECTORAL geography (Lok Sabha constituencies) or REVENUE geography (real
administrative districts) -- the structural hypothesis raised during the 2026-11 platform-upgrade
reconciliation audit (Maharashtra's "empty tehsils" turned out to mostly be Assembly Constituency
names, not real revenue tehsils with a genuine village gap).

READ-ONLY. This script:
  - Never writes to Qumanity_Master.json or any file under ~/Desktop/0_Earth/.
  - Never adds villages, tehsils, or districts.
  - Never renames, reparents, or reclassifies any Master JSON record.
  - Only reads the Master JSON and the reference dataset, and writes NEW report files elsewhere
    (see --output-dir).

Usage:
    python3 scripts/classify_india_electoral_vs_revenue_geography.py --output-dir <dir>
    python3 scripts/classify_india_electoral_vs_revenue_geography.py \\
        --master-json-path /path/to/Qumanity_Master.json \\
        --constituency-csv static/data/reference/lok_sabha_constituencies_543.csv \\
        --output-dir <dir>

2026-11 REWRITE: the previous version used only a directional-suffix regex (West/East/Rural/
City/...) as its primary evidence. That is kept here as a SECONDARY diagnostic only (per the
owner's explicit instruction: "it may remain as a diagnostic feature if useful, but it must not
determine the principal classification"). The PRIMARY method is now direct name-by-name matching
of every Master JSON district-level record against a verified, checked-in reference dataset of
all 543 real Lok Sabha constituencies -- see static/data/reference/lok_sabha_constituencies_543.csv
and its own README.md for full provenance, cross-check methodology, and this dataset's one
disclosed limitation (sourced from a community-republished LGD mirror, not a live LGD/ECI fetch
this session).

IMPORTANT DISTINCTION (the owner's own explicit warning, kept literally true throughout this
script and its output): a Lok Sabha constituency is NOT the same geographical unit as a revenue
district. A constituency can span parts of several districts; a district can be split across
several constituencies. A name match is real, meaningful evidence that a Master JSON record may
be electoral rather than revenue geography -- it is never treated as proof by itself, and a state
is never auto-classified from a single matching record.

Matching rules (exact vs. normalized only -- NO fuzzy/substring matching is used as evidence,
per the owner's explicit instruction):
  - EXACT: the Master JSON record's name string is byte-identical to a reference constituency
    name in the same state.
  - NORMALIZED: not byte-identical, but equal after normalize_name() (case/whitespace/Unicode
    NFKC folding only -- never a spelling correction, never a substring check).
  - ALIAS: a documented, sourced alternate name -- see ALIAS_MAP below. Empty in this pass (no
    individually-verified per-constituency alias was available this session); the mechanism
    exists and is reported, but nothing is silently invented to fill it.
  - UNMATCHED: none of the above.

Classification thresholds (transparent, fixed, documented -- not tuned to produce a particular
result): a state's "match ratio" is (exact + normalized + alias matches) / (total district
records). Matches are only ever counted WITHIN the same state (never across states, per the
owner's explicit instruction).
  - match_ratio >= 0.5                                  -> LIKELY_ELECTORAL_GEOGRAPHY
  - match_ratio == 0 AND a revenue-reference count also matches -> LIKELY_REVENUE_GEOGRAPHY
  - match_ratio == 0 AND no revenue reference available  -> UNRESOLVED (insufficient evidence)
  - 0 < match_ratio < 0.5                                -> MIXED_GEOGRAPHY
  - single-district UT                                   -> SPECIAL_ADMINISTRATIVE_CASE
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DIRECTIONAL_SUFFIX_RE = re.compile(r"\b(West|East|North|South|Central|Rural|City|Outer|Cantonment)\b", re.IGNORECASE)

SPECIAL_CASE_STATES = {
    "Chandigarh", "Daman and Diu", "Dadra and Nagar Haveli", "Lakshadweep", "Ladakh",
    "Andaman and Nicobar Islands",
}  # the six genuine single-district UNION TERRITORIES (constitutionally distinct from a STATE
# that merely happens to have 1 district today, e.g. Mizoram/Sikkim, which stay classified
# normally) -- "electoral vs. revenue" isn't a meaningful question with n=1 either way.

# Deliberately empty -- see module docstring's "ALIAS" rule. Format, if/when populated:
#   ALIAS_MAP[("State Name", "alternate name as it appears in Master JSON")] = "official constituency name"
# Each entry would need its own source/reason documented in a comment immediately above it.
ALIAS_MAP: dict[tuple[str, str], str] = {}

# Deliberately sparse, hedged revenue-district reference -- see the previous pass's own
# documented limitation (secondary sources actively disagree on several states' real district
# counts). None means "not verified this session, do not guess."
REVENUE_DISTRICTS_APPROX = {
    "Haryana": (22, "high -- matches this project's own already-verified, already-corrected Master JSON list"),
    "Uttar Pradesh": (75, "medium -- consistent across most sources checked this session"),
    "Goa": (2, "medium"),
    "Rajasthan": ((41, 50), "low -- secondary sources actively disagree; needs LGD"),
    "Andhra Pradesh": ((13, 26), "low -- secondary sources actively disagree; needs LGD"),
    "Gujarat": ((33, 34), "low -- secondary sources disagree by one; needs LGD"),
    "Madhya Pradesh": (55, "low -- single-source figure, not cross-checked"),
}


def normalize_name(name: str) -> str:
    """Case/whitespace/Unicode-NFKC/"&"-vs-"and"-insensitive comparison key ONLY -- never a
    spelling correction, never a substring/fuzzy check. The "&"->"and" rule is the one punctuation
    normalization this script applies, found necessary and verified this session (the reference
    CSV's source spells "Andaman & Nicobar Islands"/"Dadra & Nagar Haveli"/"Daman & Diu" with an
    ampersand; Master JSON spells all three with "and") -- an explicitly authorized "consistent
    punctuation" case, not a spelling change, and applied uniformly, never per-record. Same
    normalize-for-comparison, never-for-storage philosophy as
    scripts/audit_india_master_locations.py's own normalize_name()."""
    s = unicodedata.normalize("NFKC", name or "")
    s = re.sub(r"\s*&\s*", " and ", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def resolve_master_json_path(cli_arg: str | None) -> Path:
    if cli_arg:
        return Path(cli_arg).expanduser()
    if os.environ.get("MASTER_JSON_PATH"):
        return Path(os.environ["MASTER_JSON_PATH"]).expanduser()
    candidates = [
        Path("/data/Qumanity_Master.json"),
        ROOT / "Qumanity_Master.json",
        Path("~/Desktop/0_Earth/Qumanity_Master.json").expanduser(),
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "Could not find Qumanity_Master.json. Pass --master-json-path explicitly, or set "
        "MASTER_JSON_PATH, or place it at one of: " + ", ".join(str(c) for c in candidates)
    )


def load_india_states(master_json_path: Path) -> list[dict]:
    """Read-only. Returns [{"name","id","zone_name","district_records":[{"name","id"},...]}, ...]
    for every record under India > Zones > States. Defensive: tolerates a missing/malformed
    Districts key, never crashes on it."""
    with open(master_json_path, "r", encoding="utf-8") as f:
        master = json.load(f)
    asia = next((c for c in master.get("Continents", []) if c.get("name") == "Asia"), None)
    if not asia:
        raise ValueError("No 'Asia' continent found in Master JSON -- schema may have changed")
    india = next((c for c in asia.get("Countries", []) if c.get("name") == "India"), None)
    if not india:
        raise ValueError("No 'India' country found under Asia in Master JSON -- schema may have changed")
    states = []
    for zone in india.get("Zones", []):
        for state in zone.get("States", []):
            districts = state.get("Districts") or []
            states.append({
                "name": state.get("name", "<unnamed>"),
                "id": state.get("id", "<no id>"),
                "zone_name": zone.get("name", "<unnamed zone>"),
                "district_records": [{"name": d.get("name", "<unnamed>"), "id": d.get("id", "<no id>")} for d in districts],
            })
    return states


def load_constituency_reference(csv_path: Path) -> tuple[dict, dict]:
    """Returns (by_state, meta). by_state[state_name] = list of {"name","number","raw_row"}.
    meta carries the file's own checksum and row/unique-constituency counts for the report."""
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Constituency reference CSV not found at {csv_path}. This script requires it -- "
            f"see static/data/reference/README.md for provenance and how to regenerate it. "
            f"Refusing to classify without it rather than silently falling back to a weaker method."
        )
    with open(csv_path, "rb") as f:
        raw_bytes = f.read()
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    required_cols = {"state_ut", "constituency_name", "constituency_number"}
    if rows and not required_cols.issubset(rows[0].keys()):
        raise ValueError(f"Reference CSV missing required columns {required_cols}; found {set(rows[0].keys())}")

    empty_names = [r for r in rows if not r["constituency_name"].strip()]
    empty_states = [r for r in rows if not r["state_ut"].strip()]
    if empty_names or empty_states:
        raise ValueError(f"Reference CSV has {len(empty_names)} empty constituency name(s) and "
                          f"{len(empty_states)} empty state name(s) -- refusing to use malformed data")

    seen_state_number = defaultdict(int)
    for r in rows:
        seen_state_number[(r["state_ut"], r["constituency_number"])] += 1
    dupes = {k: v for k, v in seen_state_number.items() if v > 1}
    if dupes:
        raise ValueError(f"Reference CSV has duplicate (state, constituency_number) pairs: {dupes}")

    unique_numbers = set(r["constituency_number"] for r in rows)
    by_state = defaultdict(list)
    for r in rows:
        # Keyed by NORMALIZED state name (case-insensitive only -- e.g. this source's "Jammu And
        # Kashmir" vs. Master JSON's own "Jammu and Kashmir") -- a state-name casing difference is
        # exactly the kind of harmless formatting variation normalize_name() exists for; it is
        # never used to paper over a genuine state-identity question (that's the separate,
        # explicitly-documented ALIAS_MAP mechanism, e.g. the DNH/DD merger below).
        by_state[normalize_name(r["state_ut"])].append({"name": r["constituency_name"], "number": r["constituency_number"]})

    meta = {
        "csv_path": str(csv_path),
        "csv_sha256": checksum,
        "total_rows": len(rows),
        "unique_constituency_numbers": len(unique_numbers),
        "unique_states_in_reference": len(by_state),
    }
    return dict(by_state), meta


def match_district_record(record_name: str, state_name: str, reference_by_state: dict) -> dict:
    """One record's match result: {"match_type": "exact"|"normalized"|"alias"|"unmatched",
    "matched_constituency": {...}|None, "confidence": str}. Never fuzzy/substring -- see module
    docstring."""
    candidates = reference_by_state.get(normalize_name(state_name), [])
    for c in candidates:
        if record_name == c["name"]:
            return {"match_type": "exact", "matched_constituency": c, "confidence": "high"}
    norm_record = normalize_name(record_name)
    for c in candidates:
        if norm_record == normalize_name(c["name"]):
            return {"match_type": "normalized", "matched_constituency": c, "confidence": "high"}
    alias_target = ALIAS_MAP.get((state_name, record_name))
    if alias_target:
        for c in candidates:
            if normalize_name(alias_target) == normalize_name(c["name"]):
                return {"match_type": "alias", "matched_constituency": c, "confidence": "medium"}
    return {"match_type": "unmatched", "matched_constituency": None, "confidence": None}


def classify_state(state: dict, reference_by_state: dict) -> dict:
    name = state["name"]
    district_count = len(state["district_records"])
    district_names = [d["name"] for d in state["district_records"]]

    record_matches = [match_district_record(d["name"], name, reference_by_state) for d in state["district_records"]]
    exact = sum(1 for m in record_matches if m["match_type"] == "exact")
    normalized = sum(1 for m in record_matches if m["match_type"] == "normalized")
    alias = sum(1 for m in record_matches if m["match_type"] == "alias")
    unmatched = sum(1 for m in record_matches if m["match_type"] == "unmatched")
    total_matched = exact + normalized + alias
    match_ratio = (total_matched / district_count) if district_count else 0.0

    official_constituency_count = len(reference_by_state.get(normalize_name(name), []))

    revenue_entry = REVENUE_DISTRICTS_APPROX.get(name)
    revenue_note = None
    count_matches_revenue = False
    if revenue_entry:
        value, revenue_note = revenue_entry
        if isinstance(value, tuple):
            lo, hi = value
            count_matches_revenue = lo <= district_count <= hi
        else:
            count_matches_revenue = district_count == value

    directional_hits = [n for n in district_names if DIRECTIONAL_SUFFIX_RE.search(n)]

    evidence = [
        f"{exact}/{district_count} district records are EXACT name matches to a real Lok Sabha "
        f"constituency in this state's own reference list ({official_constituency_count} official "
        f"constituencies on record for this state)",
    ]
    if normalized:
        evidence.append(f"{normalized}/{district_count} more matched only after case/whitespace/"
                         f"Unicode normalization (still a real match, not a spelling guess)")
    if alias:
        evidence.append(f"{alias}/{district_count} matched via a documented, sourced alias")
    if unmatched:
        evidence.append(f"{unmatched}/{district_count} records did not match any known constituency "
                         f"name in this state -- this does NOT by itself prove they are genuine "
                         f"revenue districts (the reference list could be incomplete, or these could "
                         f"be real revenue districts, or something else entirely)")
    if directional_hits:
        evidence.append(f"[secondary diagnostic only, not used for the classification decision] "
                         f"{len(directional_hits)}/{district_count} district names use a directional/"
                         f"urban-split suffix (West/East/.../City/Rural): {', '.join(directional_hits[:5])}")
    if count_matches_revenue:
        evidence.append(f"district-record count ({district_count}) is also consistent with the "
                         f"approximate revenue-district reference ({revenue_note})")

    if name in SPECIAL_CASE_STATES:
        classification, confidence = "SPECIAL_ADMINISTRATIVE_CASE", "high"
        evidence.append("single-district UT -- electoral-vs-revenue classification is not a "
                         "meaningful question at n=1")
    elif match_ratio >= 0.5:
        classification = "LIKELY_ELECTORAL_GEOGRAPHY"
        confidence = "high" if match_ratio >= 0.8 else "medium-high"
    elif match_ratio == 0 and count_matches_revenue:
        classification, confidence = "LIKELY_REVENUE_GEOGRAPHY", ("medium" if revenue_note and revenue_note.startswith("high") else "low")
    elif match_ratio == 0:
        classification, confidence = "UNRESOLVED", "low"
        evidence.append("zero constituency-name matches, but no revenue-district reference exists "
                         "for this state either -- genuinely insufficient evidence either way")
    else:
        classification, confidence = "MIXED_GEOGRAPHY", "low"
        evidence.append(f"match ratio ({match_ratio:.0%}) is neither clearly electoral (>=50%) nor "
                         f"clearly zero -- a partial match can mean a genuine name collision for a "
                         f"handful of districts, not full electoral-geography adoption; needs "
                         f"record-by-record review (see the per-record report)")

    return {
        "state_name": name,
        "qumanity_state_id": state["id"],
        "zone_name": state["zone_name"],
        "master_district_record_count": district_count,
        "official_constituency_count": official_constituency_count,
        "exact_matches": exact,
        "normalized_matches": normalized,
        "alias_matches": alias,
        "unmatched": unmatched,
        "match_ratio": round(match_ratio, 3),
        "revenue_district_reference": revenue_entry[0] if revenue_entry else None,
        "revenue_district_reference_note": revenue_note,
        "directional_suffix_hits_diagnostic_only": len(directional_hits),
        "classification": classification,
        "confidence": confidence,
        "evidence": evidence,
        "record_matches": [
            {
                "qumanity_record_id": d["id"],
                "qumanity_record_name": d["name"],
                "match_type": m["match_type"],
                "matched_constituency_name": (m["matched_constituency"] or {}).get("name"),
                "matched_constituency_number": (m["matched_constituency"] or {}).get("number"),
                "confidence": m["confidence"],
            }
            for d, m in zip(state["district_records"], record_matches)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--master-json-path", default=None, help="Path to Qumanity_Master.json (read-only)")
    parser.add_argument("--constituency-csv", default=str(ROOT / "static/data/reference/lok_sabha_constituencies_543.csv"),
                         help="Path to the verified 543-constituency reference CSV")
    parser.add_argument("--output-dir", default=None, help="Where to write report files (required; never a new repo folder)")
    args = parser.parse_args()

    if not args.output_dir:
        parser.error("--output-dir is required (point it at a scratch directory, never a new "
                     "folder inside the repository without separate approval)")

    master_path = resolve_master_json_path(args.master_json_path)
    constituency_csv_path = Path(args.constituency_csv).expanduser()

    print(f"Reading Master JSON (read-only): {master_path}")
    with open(master_path, "rb") as f:
        master_json_sha256 = hashlib.sha256(f.read()).hexdigest()
    states = load_india_states(master_path)
    print(f"Found {len(states)} state/UT records under India in the Master JSON.")

    print(f"Reading constituency reference (read-only): {constituency_csv_path}")
    reference_by_state, ref_meta = load_constituency_reference(constituency_csv_path)
    print(f"Reference: {ref_meta['total_rows']} rows, {ref_meta['unique_constituency_numbers']} "
          f"unique constituencies, {ref_meta['unique_states_in_reference']} states/UTs.\n")

    results = [classify_state(s, reference_by_state) for s in states]
    results.sort(key=lambda r: (-r["master_district_record_count"], r["state_name"]))

    counts_by_classification: dict[str, int] = {}
    for r in results:
        counts_by_classification[r["classification"]] = counts_by_classification.get(r["classification"], 0) + 1

    print(f"{'State/UT':30s} {'Districts':>9s} {'OffPC':>6s} {'Exact':>6s} {'Norm':>5s} {'Alias':>6s} "
          f"{'Unmat':>6s} {'Ratio':>6s}  Classification (confidence)")
    print("-" * 115)
    for r in results:
        print(f"{r['state_name']:30s} {r['master_district_record_count']:>9d} "
              f"{r['official_constituency_count']:>6d} {r['exact_matches']:>6d} {r['normalized_matches']:>5d} "
              f"{r['alias_matches']:>6d} {r['unmatched']:>6d} {r['match_ratio']*100:>5.0f}%  "
              f"{r['classification']} ({r['confidence']})")

    print("\nCounts by classification:")
    for k, v in sorted(counts_by_classification.items()):
        print(f"  {k}: {v}")

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "master_json_path": str(master_path),
        "master_json_sha256": master_json_sha256,
        "master_json_never_modified": True,
        "constituency_reference": ref_meta,
        "total_states_ut_records": len(states),
        "counts_by_classification": counts_by_classification,
    }

    json_path = out_dir / "india_electoral_revenue_classification.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"meta": run_meta, "states": results}, f, ensure_ascii=False, indent=2)

    csv_path = out_dir / "india_electoral_revenue_classification.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["state_name", "qumanity_state_id", "master_district_record_count",
                    "official_constituency_count", "exact_matches", "normalized_matches",
                    "alias_matches", "unmatched", "match_ratio", "classification", "confidence"])
        for r in results:
            w.writerow([r["state_name"], r["qumanity_state_id"], r["master_district_record_count"],
                        r["official_constituency_count"], r["exact_matches"], r["normalized_matches"],
                        r["alias_matches"], r["unmatched"], r["match_ratio"], r["classification"], r["confidence"]])

    record_csv_path = out_dir / "india_electoral_revenue_classification_records.csv"
    with open(record_csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["state_name", "qumanity_record_id", "qumanity_record_name", "match_type",
                    "matched_constituency_name", "matched_constituency_number", "confidence"])
        for r in results:
            for rm in r["record_matches"]:
                w.writerow([r["state_name"], rm["qumanity_record_id"], rm["qumanity_record_name"],
                            rm["match_type"], rm["matched_constituency_name"], rm["matched_constituency_number"],
                            rm["confidence"]])

    md_path = out_dir / "india_electoral_revenue_classification.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# India Electoral-vs-Revenue Geography Classification (name-by-name matching)\n\n")
        f.write(f"Generated {run_meta['generated_at_utc']} from `{master_path}` "
                f"(SHA-256 `{master_json_sha256}`, read-only) against the verified reference "
                f"dataset `{constituency_csv_path}` (SHA-256 `{ref_meta['csv_sha256']}`).\n\n")
        f.write("**No village backfilling, reclassification, renaming, reparenting, or Master JSON "
                "modification occurred while producing this report.**\n\n")
        f.write("| State/UT | Districts | Official PCs | Exact | Normalized | Alias | Unmatched | Ratio | Classification | Confidence |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---|---|\n")
        for r in results:
            f.write(f"| {r['state_name']} | {r['master_district_record_count']} | "
                    f"{r['official_constituency_count']} | {r['exact_matches']} | {r['normalized_matches']} | "
                    f"{r['alias_matches']} | {r['unmatched']} | {r['match_ratio']*100:.0f}% | "
                    f"{r['classification']} | {r['confidence']} |\n")
        f.write("\n## Evidence per state\n\n")
        for i, r in enumerate(results):
            f.write(f"### {r['state_name']} -- {r['classification']} ({r['confidence']})\n\n")
            for e in r["evidence"]:
                f.write(f"- {e}\n")
            if i < len(results) - 1:
                f.write("\n")

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text.rstrip("\n") + "\n")  # exactly one trailing newline, no extra blank line at EOF

    print(f"\nWrote: {json_path}\nWrote: {csv_path}\nWrote: {record_csv_path}\nWrote: {md_path}")
    print(f"\nMaster JSON SHA-256: {master_json_sha256} (read-only -- verify this matches before/after)")
    print("No villages, tehsils, or districts were added, renamed, or reparented.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
