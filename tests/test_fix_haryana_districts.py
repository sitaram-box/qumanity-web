"""Verifies scripts/fix_haryana_districts.py's PURE transformation logic (apply_promotions(),
apply_split()) against a small SYNTHETIC Master.json-shaped fixture built in memory here -- never
the real ~/Desktop/0_Earth/Qumanity_Master.json (120MB, outside this repo, real user-facing
location data). No file on disk is read or written by this test; it only imports the script's
functions and calls them directly on an in-memory dict, exactly the same way main() does
internally before anything is written to disk (main() itself is never called here, so --apply's
backup/write/manifest-file path is untouched, consistent with the standing instruction that the
real location fix only runs against a throwaway copy, as a separate, explicitly-approved step).

The fixture includes every district/tehsil PROMOTIONS and SPLIT_BHIWANI_MAHENDRAGARH reference by
name, plus one untouched "control" district (Hisar) and one untouched "control" tehsil inside an
affected district, to prove the transformation only touches what it's supposed to.

Standalone script, no test framework (none installed in this project), PASS/FAIL printing, exit 1
on failure -- same pattern as every other tests/test_*.py file in this project.

Run with: python3 tests/test_fix_haryana_districts.py (not -I -- isolated mode hides this
machine's installed packages, not needed here anyway since this script has no third-party deps).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import fix_haryana_districts as fhd  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def village(name):
    return {"name": name}


def tehsil(id_, name, n_villages):
    return {"id": id_, "name": name, "villages": [village(f"{name} Village {i}") for i in range(n_villages)]}


def district(id_, name, tehsils):
    return {"id": id_, "name": name, "tehsils": tehsils}


def build_fixture():
    """A minimal Master.json-shaped dict carrying only what Haryana's audit needs: the 9 original
    districts PROMOTIONS moves a tehsil out of (each also keeping one untouched control tehsil),
    one untouched control district (Hisar), and the merged Bhiwani-Mahendragarh entry with all 10
    of its real tehsils (matching the real Master.json's own tehsil names and shape)."""
    haryana_districts = [
        district("NS.HR.1", "Ambala", [
            tehsil("NS.HR.1.1", "Ambala City", 5),
            tehsil("NS.HR.1.2", "Panchkula", 7),
            tehsil("NS.HR.1.3", "Yamunanagar", 9),
        ]),
        district("NS.HR.2", "Kurukshetra", [
            tehsil("NS.HR.2.1", "Thanesar", 4),
            tehsil("NS.HR.2.2", "Kaithal", 6),
        ]),
        district("NS.HR.3", "Karnal", [
            tehsil("NS.HR.3.1", "Karnal", 3),
            tehsil("NS.HR.3.2", "Panipat City", 2),
            tehsil("NS.HR.3.3", "Panipat Rural", 8),
        ]),
        district("NS.HR.4", "Sonipat", [
            tehsil("NS.HR.4.1", "Sonipat", 5),
            tehsil("NS.HR.4.2", "Jind", 11),
        ]),
        district("NS.HR.5", "Hisar", [  # untouched control district -- PROMOTIONS/SPLIT never reference it
            tehsil("NS.HR.5.1", "Hisar", 6),
            tehsil("NS.HR.5.2", "Hansi", 4),
        ]),
        district("NS.HR.6", "Sirsa", [
            tehsil("NS.HR.6.1", "Sirsa", 5),
            tehsil("NS.HR.6.2", "Fatehabad", 7),
        ]),
        district("NS.HR.7", "Bhiwani-Mahendragarh", [
            tehsil("NS.HR.7.1", "Loharu", 2),
            tehsil("NS.HR.7.2", "Badhra", 3),
            tehsil("NS.HR.7.3", "Dadri", 4),
            tehsil("NS.HR.7.4", "Bhiwani", 5),
            tehsil("NS.HR.7.5", "Tosham", 1),
            tehsil("NS.HR.7.6", "Ateli", 0),
            tehsil("NS.HR.7.7", "Mahendragarh", 6),
            tehsil("NS.HR.7.8", "Narnaul", 9),
            tehsil("NS.HR.7.9", "Nangal Chaudhry", 0),
            tehsil("NS.HR.7.A", "Siwani", 2),
        ]),
        district("NS.HR.8", "Rohtak", [
            tehsil("NS.HR.8.1", "Rohtak", 4),
            tehsil("NS.HR.8.2", "Jhajjar", 6),
        ]),
        district("NS.HR.9", "Gurgaon", [
            tehsil("NS.HR.9.1", "Gurgaon", 3),
            tehsil("NS.HR.9.2", "Nuh", 8),
            tehsil("NS.HR.9.3", "Rewari", 10),
        ]),
        district("NS.HR.A", "Faridabad", [
            tehsil("NS.HR.A.1", "Faridabad", 2),
            tehsil("NS.HR.A.2", "Palwal", 5),
        ]),
    ]
    return {
        "Continents": [{"name": "Asia", "Countries": [{"name": "India", "Zones": [
            {"States": [{"name": "Haryana", "Districts": haryana_districts}]}
        ]}]}]
    }


print("=" * 70)
print("1. apply_promotions(): the 10 single/grouped-tehsil promotions")
print("=" * 70)

master = build_fixture()
haryana = fhd.find_haryana(master)
before_count = len(haryana["Districts"])
before_villages = sum(fhd._village_count(d) for d in haryana["Districts"])

working = copy.deepcopy(master)
haryana_working = fhd.find_haryana(working)
promo_manifest = fhd.apply_promotions(haryana_working)

check("find_haryana() locates Haryana inside the full Continents/Countries/Zones/States shape",
      haryana["name"] == "Haryana")
check("apply_promotions() returns exactly 11 manifest entries -- one per TEHSIL moved, not per "
      "PROMOTIONS row (10 rows, but Panipat's row moves 2 tehsils -- City and Rural -- into one new district)",
      len(promo_manifest) == 11)
check("village count is unchanged by promotions (nothing invented or dropped)",
      sum(fhd._village_count(d) for d in haryana_working["Districts"]) == before_villages)

new_district_names = {d["name"] for d in haryana_working["Districts"]}
for expected in ("Fatehabad", "Jhajjar", "Jind", "Kaithal", "Nuh", "Palwal", "Panchkula", "Panipat", "Rewari", "Yamunanagar"):
    check(f"promoted district {expected!r} now exists as its own top-level entry", expected in new_district_names)

panipat = next(d for d in haryana_working["Districts"] if d["name"] == "Panipat")
check("Panipat (a 2-tehsil promotion) carries BOTH Panipat City and Panipat Rural, not just one",
      {t["name"] for t in panipat["tehsils"]} == {"Panipat City", "Panipat Rural"})
check("Panipat's tehsils were re-ided under its own new district id, not left with their old Karnal-prefixed ids",
      all(t["id"].startswith("NS.HR.I") for t in panipat["tehsils"]))

karnal = next(d for d in haryana_working["Districts"] if d["name"] == "Karnal")
check("Karnal (the old parent) kept its OWN tehsil (Karnal) and lost the two that were promoted",
      {t["name"] for t in karnal["tehsils"]} == {"Karnal"})

hisar = next(d for d in haryana_working["Districts"] if d["name"] == "Hisar")
check("the untouched control district (Hisar) is byte-for-byte unaffected by promotions",
      hisar == next(d for d in haryana["Districts"] if d["name"] == "Hisar"))

print()
print("=" * 70)
print("2. apply_split(): Bhiwani-Mahendragarh -> Bhiwani + Mahendragarh + Charkhi Dadri")
print("=" * 70)

split_manifest = fhd.apply_split(haryana_working, fhd.SPLIT_BHIWANI_MAHENDRAGARH)
check("apply_split() returns exactly 10 manifest entries (one per real tehsil under the merged entry)",
      len(split_manifest) == 10)
check("the old merged 'Bhiwani-Mahendragarh' entry is GONE -- nothing survives under that name",
      not any(d["name"] == "Bhiwani-Mahendragarh" for d in haryana_working["Districts"]))

final_names = {d["name"] for d in haryana_working["Districts"]}
for expected in ("Bhiwani", "Mahendragarh", "Charkhi Dadri"):
    check(f"{expected!r} now exists as its own real top-level district (not a fabricated placeholder)", expected in final_names)

charkhi_dadri = next(d for d in haryana_working["Districts"] if d["name"] == "Charkhi Dadri")
check("Charkhi Dadri carries its REAL tehsils (Dadri, Badhra) with their real villages -- never an empty placeholder",
      {t["name"] for t in charkhi_dadri["tehsils"]} == {"Dadri", "Badhra"})
check("Charkhi Dadri's villages are the REAL ones carried over, not zero/fabricated",
      sum(len(t["villages"]) for t in charkhi_dadri["tehsils"]) == 4 + 3)  # Dadri=4, Badhra=3 from the fixture

bhiwani = next(d for d in haryana_working["Districts"] if d["name"] == "Bhiwani")
check("Bhiwani carries its real 4 tehsils (Bhiwani, Tosham, Loharu, Siwani)",
      {t["name"] for t in bhiwani["tehsils"]} == {"Bhiwani", "Tosham", "Loharu", "Siwani"})

mahendragarh = next(d for d in haryana_working["Districts"] if d["name"] == "Mahendragarh")
check("Mahendragarh carries its real 4 tehsils, including the two zero-village ones (Ateli, Nangal Chaudhry) -- not dropped for being empty",
      {t["name"] for t in mahendragarh["tehsils"]} == {"Mahendragarh", "Narnaul", "Ateli", "Nangal Chaudhry"})

check("total village count across all Haryana districts is unchanged end-to-end (promotions + split combined)",
      sum(fhd._village_count(d) for d in haryana_working["Districts"]) == before_villages)
check("final district count is 22, Haryana's real count: 10 original districts (one of them, "
      "Bhiwani-Mahendragarh, removed by the split) + 10 newly promoted districts (one per "
      "PROMOTIONS row -- Panipat's 2 tehsils still land in a single new district) + 3 from the split",
      len(haryana_working["Districts"]) == before_count + len(fhd.PROMOTIONS) - 1 + 3 == 22)

print()
print("=" * 70)
print("3. apply_split() refuses to silently drop a tehsil nobody's split list claims")
print("=" * 70)

bad_master = build_fixture()
bad_haryana = fhd.find_haryana(bad_master)
incomplete_split = {
    "old_district_id": "NS.HR.7", "old_district_name": "Bhiwani-Mahendragarh",
    "splits": [("NS.HR.L", "Bhiwani", ["Bhiwani", "Tosham", "Loharu", "Siwani"])],  # Mahendragarh/Charkhi Dadri's tehsils omitted on purpose
}
try:
    fhd.apply_split(bad_haryana, incomplete_split)
    check("an incomplete splits list raises instead of silently losing tehsils/villages", False)
except ValueError as e:
    check("an incomplete splits list raises ValueError instead of silently losing tehsils/villages", True)
    check("...naming the leftover tehsils in the error", "Dadri" in str(e) or "Mahendragarh" in str(e))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
