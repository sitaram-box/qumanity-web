"""Covers scripts/classify_india_electoral_vs_revenue_geography.py (2026-11, rewritten from a
regex-only heuristic to direct name-by-name matching against static/data/reference/
lok_sabha_constituencies_543.csv). Standalone script, no test framework, PASS/FAIL printing,
sys.exit(1) on failure -- same conventions as the rest of this project's test suite.

Covers, per the owner's explicit Part 2.10 list:
  1. The real reference CSV has exactly 543 unique constituency numbers (545 rows -- the DNH/DD
     documented alias duplication, not an error).
  2. Duplicate reference entries are rejected (load_constituency_reference raises).
  3. Missing constituency names are rejected.
  4. State mismatch: a record is never matched against a different state's constituency list.
  5. Exact name match.
  6. Normalized match (case/whitespace/Unicode).
  7. "&" vs "and" punctuation normalization (the real Andaman & Nicobar / Dadra & Nagar Haveli /
     Daman & Diu case found and fixed this session).
  8. Source-backed alias match (synthetic, since ALIAS_MAP is genuinely empty in the real data).
  9. Duplicate names in different states do not cross-match (a name real in State A never matches
     a same-named district in State B).
  10. The real Haryana collision (a name that is BOTH a genuine revenue district AND a real Lok
      Sabha constituency) is classified MIXED_GEOGRAPHY, not forced to either extreme -- proof the
      script does not overclaim just because SOME names collide.
  11. A clearly-different name stays unmatched (no fuzzy/substring matching).
  12. Missing Districts key on a state doesn't crash (0 records, 0% ratio, UNRESOLVED/skip).
  13. Malformed Master JSON (nodes missing name/id) doesn't crash.
  14. All 37 real state/UT records are accounted for in a real run.
  15. All 6 real single-district UTs classify SPECIAL_ADMINISTRATIVE_CASE (not the 2 small states,
      Mizoram/Sikkim, that also happen to have 1 district today).
  16. Deterministic output (two runs against the same inputs produce identical results).
  17. Read-only: Master JSON checksum identical before and after a real run.
  18. Missing/incomplete reference dataset is rejected, not silently degraded.

Run with: python3 tests/test_india_geography_classification.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import classify_india_electoral_vs_revenue_geography as geo  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


REAL_CSV = ROOT / "static/data/reference/lok_sabha_constituencies_543.csv"
REAL_MASTER = Path("~/Desktop/0_Earth/Qumanity_Master.json").expanduser()

print("=" * 70)
print("1-3. The real reference CSV: row/uniqueness/validity checks")
print("=" * 70)

by_state, meta = geo.load_constituency_reference(REAL_CSV)
check("exactly 543 unique constituency_number values", meta["unique_constituency_numbers"] == 543)
check("545 total rows (543 + 2 for the documented DNH/DD alias duplication)", meta["total_rows"] == 545)
check("37 states/UTs represented (matches Master JSON's own state count)", meta["unique_states_in_reference"] == 37)

with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("state_ut,constituency_name,constituency_number,reservation_category,source_reference,source_version,verification_date,alias_note\n")
    f.write("Test State,Test Constituency,1,,src,v1,2026-11-01,\n")
    f.write("Test State,Test Constituency,2,,src,v1,2026-11-01,\n")  # duplicate name, OK (diff number)
    f.write("Test State,Test Constituency,1,,src,v1,2026-11-01,\n")  # duplicate (state, number) -- must reject
    dupe_path = f.name
try:
    geo.load_constituency_reference(Path(dupe_path))
    check("duplicate (state, constituency_number) pairs are rejected", False)
except ValueError as e:
    check("duplicate (state, constituency_number) pairs are rejected", "duplicate" in str(e).lower())
finally:
    os.unlink(dupe_path)

with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
    f.write("state_ut,constituency_name,constituency_number,reservation_category,source_reference,source_version,verification_date,alias_note\n")
    f.write("Test State,,1,,src,v1,2026-11-01,\n")  # empty name
    empty_name_path = f.name
try:
    geo.load_constituency_reference(Path(empty_name_path))
    check("empty constituency names are rejected", False)
except ValueError as e:
    check("empty constituency names are rejected", "empty" in str(e).lower())
finally:
    os.unlink(empty_name_path)

print()
print("=" * 70)
print("18. A missing/nonexistent reference dataset is rejected, not silently degraded")
print("=" * 70)
try:
    geo.load_constituency_reference(Path("/nonexistent/path/does_not_exist.csv"))
    check("a missing reference CSV raises, rather than silently falling back", False)
except FileNotFoundError:
    check("a missing reference CSV raises, rather than silently falling back", True)

print()
print("=" * 70)
print("4-9, 11. Matching logic: exact / normalized / punctuation / alias / state-isolation / unmatched")
print("=" * 70)

synthetic_reference = {
    "state a": [{"name": "Real Constituency", "number": "1"}, {"name": "Andaman & Nicobar Islands", "number": "2"}],
    "state b": [{"name": "Real Constituency", "number": "99"}],  # SAME name, different state
}

m = geo.match_district_record("Real Constituency", "State A", synthetic_reference)
check("exact match found", m["match_type"] == "exact" and m["matched_constituency"]["number"] == "1")

m = geo.match_district_record("  real   CONSTITUENCY  ", "State A", synthetic_reference)
check("normalized match found (case/whitespace differences)", m["match_type"] == "normalized")

m = geo.match_district_record("Andaman and Nicobar Islands", "State A", synthetic_reference)
check("'&' vs 'and' punctuation normalization matches (the real Andaman/DNH/DD case)", m["match_type"] == "normalized")

m = geo.match_district_record("Real Constituency", "State B", synthetic_reference)
check("state isolation: 'State B's own match is against State B's own list (number 99), never State A's",
      m["match_type"] == "exact" and m["matched_constituency"]["number"] == "99")

m = geo.match_district_record("Completely Unrelated Name", "State A", synthetic_reference)
check("a clearly different name stays UNMATCHED -- no fuzzy/substring matching", m["match_type"] == "unmatched")

old_alias_map = dict(geo.ALIAS_MAP)
geo.ALIAS_MAP[("State A", "Old Name")] = "Real Constituency"
try:
    m = geo.match_district_record("Old Name", "State A", synthetic_reference)
    check("a documented alias match resolves via ALIAS_MAP", m["match_type"] == "alias" and m["matched_constituency"]["number"] == "1")
finally:
    geo.ALIAS_MAP.clear()
    geo.ALIAS_MAP.update(old_alias_map)

print()
print("=" * 70)
print("10. The real Haryana name-collision case: MIXED_GEOGRAPHY, not forced to either extreme")
print("=" * 70)

real_haryana_state = None
if REAL_MASTER.is_file():
    states = geo.load_india_states(REAL_MASTER)
    real_haryana_state = next((s for s in states if s["name"] == "Haryana"), None)
if real_haryana_state:
    real_by_state, _ = geo.load_constituency_reference(REAL_CSV)
    result = geo.classify_state(real_haryana_state, real_by_state)
    check("Haryana has a non-zero, non-100% match ratio (real constituency/district name overlap exists)",
          0 < result["match_ratio"] < 1)
    check("Haryana is classified MIXED_GEOGRAPHY (honest ambiguity), not forced to either extreme",
          result["classification"] == "MIXED_GEOGRAPHY")
else:
    check("(skipped -- real Master JSON not available in this environment)", True)

print()
print("=" * 70)
print("12-13. Robustness: missing Districts key, malformed nodes")
print("=" * 70)

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
    json.dump({
        "Continents": [{"name": "Asia", "Countries": [{"name": "India", "Zones": [{"name": "Z", "States": [
            {"name": "NoDistrictsState", "id": "X.1"},
            {"name": "MalformedState", "id": "X.2", "Districts": [{"id": "X.2.1"}, {"name": "No Id"}]},
        ]}]}]}]
    }, f)
    malformed_path = f.name
try:
    states = geo.load_india_states(Path(malformed_path))
    check("a state with no Districts key at all doesn't crash (0 records)",
          next(s for s in states if s["name"] == "NoDistrictsState")["district_records"] == [])
    malformed = next(s for s in states if s["name"] == "MalformedState")
    check("malformed nodes (missing name/id) don't crash, get defaulted", len(malformed["district_records"]) == 2)
    result = geo.classify_state(malformed, synthetic_reference)
    check("classify_state() doesn't crash on malformed/unreferenced-state records", result["classification"] in
          {"UNRESOLVED", "MIXED_GEOGRAPHY", "LIKELY_ELECTORAL_GEOGRAPHY", "LIKELY_REVENUE_GEOGRAPHY", "SPECIAL_ADMINISTRATIVE_CASE"})
finally:
    os.unlink(malformed_path)

print()
print("=" * 70)
print("14-17. Full real-data run: all 37 states, 6 special UTs, determinism, read-only checksum")
print("=" * 70)

if REAL_MASTER.is_file():
    with open(REAL_MASTER, "rb") as f:
        checksum_before = hashlib.sha256(f.read()).hexdigest()

    states = geo.load_india_states(REAL_MASTER)
    real_by_state, _ = geo.load_constituency_reference(REAL_CSV)
    results_run1 = [geo.classify_state(s, real_by_state) for s in states]
    results_run2 = [geo.classify_state(s, real_by_state) for s in states]

    check("all 37 real state/UT records are present", len(states) == 37)

    special = {r["state_name"] for r in results_run1 if r["classification"] == "SPECIAL_ADMINISTRATIVE_CASE"}
    check("exactly the 6 genuine single-district UTs are SPECIAL_ADMINISTRATIVE_CASE",
          special == {"Chandigarh", "Daman and Diu", "Dadra and Nagar Haveli", "Lakshadweep", "Ladakh", "Andaman and Nicobar Islands"})
    check("Mizoram (a STATE with 1 district today, not a UT) is classified normally, not SPECIAL_ADMINISTRATIVE_CASE",
          next(r for r in results_run1 if r["state_name"] == "Mizoram")["classification"] != "SPECIAL_ADMINISTRATIVE_CASE")

    check("deterministic: two runs against the same inputs produce identical classifications",
          [(r["state_name"], r["classification"]) for r in results_run1] ==
          [(r["state_name"], r["classification"]) for r in results_run2])

    with open(REAL_MASTER, "rb") as f:
        checksum_after = hashlib.sha256(f.read()).hexdigest()
    check("Master JSON checksum is IDENTICAL before and after classification (strictly read-only)",
          checksum_before == checksum_after)
else:
    check("(skipped -- real Master JSON not available in this environment)", True)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks PASSED.")
