"""Verifies scripts/import_india_villages.py's do_verify() orphan-detection logic (2026-10-25
fix): a district that carries villages DIRECTLY (no tehsil tier, or a few villages not yet
assigned to any of its real tehsils -- Afghanistan/Balochistan/Pakistan/Maldives all do this, see
scripts/build_subcontinent_data.py's own module docstring) must NOT be flagged as "orphaned" just
because its own id, not a tehsil id, appears in india_villages.tehsil_id for those rows.

Builds a throwaway SQLite DB and a throwaway subcontinent_districts.json under a temp directory
-- never the real ~/Desktop/0_Earth/Qumanity_Master.json, the real qumanity_prototype.db, or the
real static/data/subcontinent_districts.json. do_verify() reads its districts file from
REPO_ROOT/static/data/subcontinent_districts.json, a path baked in at import time, so this
monkey-patches import_india_villages.REPO_ROOT to the temp directory for the duration of the
test and restores it afterwards -- the only way to point it at fixture data without touching the
real file.

Standalone script, no test framework (none installed in this project), PASS/FAIL printing, exit 1
on failure -- same pattern as every other tests/test_*.py file in this project.

Run with: python3 tests/test_import_india_villages_verify.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import import_india_villages as iiv  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def build_fixture(tmp: Path):
    """A throwaway DB + districts file, fully isolated under tmp -- the real repo files are
    never opened for writing by this test."""
    (tmp / "static" / "data").mkdir(parents=True)
    db_path = tmp / "fixture.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE india_villages (id TEXT, tehsil_id TEXT, name TEXT)")
    conn.executemany(
        "INSERT INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
        [
            ("v1", "NS.HR.1.1", "Village under a real tehsil"),  # tehsil-parented, normal case
            ("v2", "AF.1.1", "Village directly under a district"),  # district-direct-villages case
            ("v3", "ZZ.9.9", "Village under a genuinely unknown parent"),  # should still be flagged
        ],
    )
    conn.commit()
    conn.close()

    districts_json = {
        "states": {
            "NS.HR": {"name": "Haryana", "districts": [
                {"id": "NS.HR.1", "name": "Ambala", "tehsils": [{"id": "NS.HR.1.1", "name": "Ambala City"}]},
            ]},
            "AF.1": {"name": "Badakhshan", "districts": [
                {"id": "AF.1.1", "name": "Arghanj Khwah", "tehsils": [], "direct_villages": 1},
            ]},
        }
    }
    (tmp / "static" / "data" / "subcontinent_districts.json").write_text(
        json.dumps(districts_json, ensure_ascii=False), encoding="utf-8")
    return db_path


print("=" * 70)
print("1. do_verify(): a direct-villages district id is no longer a false-positive orphan")
print("=" * 70)

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    db_path = build_fixture(tmp)

    original_root = iiv.REPO_ROOT
    iiv.REPO_ROOT = tmp
    try:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            result = iiv.do_verify(db_path)
        output = buf.getvalue()
        print(output, end="")
    finally:
        iiv.REPO_ROOT = original_root

check("do_verify() returns False -- v3's parent (ZZ.9.9) is a genuinely unknown id, correctly still flagged", result is False)
check("village_count reported correctly (3 fixture rows)", "village_count: 3" in output)
check("distinct tehsil_id count reported correctly (3 distinct parents: a real tehsil, a direct-villages district, an unknown id)",
      "distinct tehsil_id count: 3" in output)
check("exactly 1 orphan remains -- the GENUINELY unknown parent (ZZ.9.9), not the direct-villages district (AF.1.1)",
      "NOT in subcontinent_districts.json: 1" in output)

print()
print("=" * 70)
print("2. do_verify(): PASSES cleanly when every tehsil_id is either a real tehsil or a direct-villages district")
print("=" * 70)

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    (tmp / "static" / "data").mkdir(parents=True)
    db_path = tmp / "fixture.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE india_villages (id TEXT, tehsil_id TEXT, name TEXT)")
    conn.executemany(
        "INSERT INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
        [("v1", "NS.HR.1.1", "Normal"), ("v2", "AF.1.1", "Direct-under-district")],
    )
    conn.commit()
    conn.close()
    districts_json = {
        "states": {
            "NS.HR": {"name": "Haryana", "districts": [
                {"id": "NS.HR.1", "name": "Ambala", "tehsils": [{"id": "NS.HR.1.1", "name": "Ambala City"}]},
            ]},
            "AF.1": {"name": "Badakhshan", "districts": [
                {"id": "AF.1.1", "name": "Arghanj Khwah", "tehsils": [], "direct_villages": 1},
            ]},
        }
    }
    (tmp / "static" / "data" / "subcontinent_districts.json").write_text(
        json.dumps(districts_json, ensure_ascii=False), encoding="utf-8")

    original_root = iiv.REPO_ROOT
    iiv.REPO_ROOT = tmp
    try:
        result2 = iiv.do_verify(db_path)
    finally:
        iiv.REPO_ROOT = original_root

check("do_verify() PASSES (True) when every tehsil_id is accounted for, including direct-villages districts", result2 is True)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
