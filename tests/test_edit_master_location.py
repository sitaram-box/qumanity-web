#!/usr/bin/env python3
"""Tests for scripts/edit_master_location.py -- duplicate prevention, reference prevention,
dry-run vs --apply, backup/hash verification, and safe-to-re-run behavior. Never touches the
real Qumanity_Master.json or the real application database -- every test uses a fixture Master
JSON file and a disposable throwaway SQLite database, both created fresh per test run.

Standalone script (project convention, not pytest): run directly.
    python3 tests/test_edit_master_location.py
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import edit_master_location as em  # noqa: E402

FAILS = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILS.append(label)


def fixture_master() -> dict:
    return {
        "name": "Earth", "id": "O",
        "Continents": [{
            "name": "Asia", "id": "O_AS", "code": "AS",
            "Countries": [{
                "name": "India", "id": "O_AS_IND", "code": "IND",
                "Zones": [{
                    "name": "Test Zone", "id": "ZZ/TZ",
                    "States": [{
                        "name": "Test State", "id": "ZZ.TS",
                        "Districts": [{
                            "name": "Test District", "id": "ZZ.TS.1",
                            "tehsils": [{
                                "name": "Test Tehsil", "id": "ZZ.TS.1.1",
                                "villages": [
                                    {"name": "Alpha Village", "id": "ZZ.TS.1.1.1"},
                                    {"name": "Beta Village", "id": "ZZ.TS.1.1.2"},
                                ],
                            }],
                        }],
                    }],
                }],
            }],
        }],
    }


def write_fixture(tmpdir: Path) -> Path:
    p = tmpdir / "Qumanity_Master.fixture.json"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(fixture_master(), ensure_ascii=False))
    return p


_db_counter = [0]


def make_test_db(tmpdir: Path) -> Path:
    _db_counter[0] += 1
    db_path = tmpdir / f"test_{_db_counter[0]}.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY, present_location_json TEXT, birth_location_json TEXT, is_demo INTEGER DEFAULT 0, is_removed INTEGER DEFAULT 0);
        CREATE TABLE account_ids (user_id INTEGER, present_location_json TEXT);
        CREATE TABLE qpunch_addresses (location_id TEXT);
        CREATE TABLE qpunch_queue_messages (location_id TEXT);
        CREATE TABLE announcements (location_id TEXT);
        CREATE TABLE collective_karma (location_id TEXT);
        CREATE TABLE collective_karma_log (location_id TEXT);
        CREATE TABLE election_cycles (village_id TEXT);
        CREATE TABLE location_elements (location_id TEXT);
        CREATE TABLE profile_change_requests (location_id TEXT);
        CREATE TABLE recognition_stars (location_id TEXT);
        CREATE TABLE reports (location_id TEXT);
        CREATE TABLE subgroups (village_id TEXT);
        CREATE TABLE village_council (village_id TEXT);
        CREATE TABLE zone_sentiment (zone_id TEXT);
        CREATE TABLE zone_sentiment_stats (zone_id TEXT);
        CREATE TABLE admin_export_log (location_id TEXT);
        CREATE TABLE india_villages (id TEXT, tehsil_id TEXT);
    """)
    conn.commit()
    conn.close()
    return db_path


with tempfile.TemporaryDirectory() as tmp:
    tmpdir = Path(tmp)

    # -- find_record / validate_id_format --------------------------------------------------------

    master = fixture_master()
    rec, parent, siblings, _ = em.find_record(master, "Village", "ZZ.TS.1.1.1")
    check("find_record locates an existing village", rec is not None and rec["name"] == "Alpha Village")
    check("find_record returns the correct parent tehsil", parent["id"] == "ZZ.TS.1.1")
    check("find_record returns siblings including itself", len(siblings) == 2)

    rec2, _, _, _ = em.find_record(master, "Village", "ZZ.TS.1.1.999")
    check("find_record returns None for a nonexistent id", rec2 is None)

    check("validate_id_format accepts a correct child id", em.validate_id_format("ZZ.TS.1.1.3", "ZZ.TS.1.1") is None)
    check("validate_id_format rejects a wrong parent prefix", em.validate_id_format("ZZ.TS.1.1.3", "ZZ.TS.1.2") is not None)
    check("validate_id_format rejects a leading-zero-style suffix", em.validate_id_format("ZZ.TS.1.1.0", "ZZ.TS.1.1") is not None)
    check("validate_id_format accepts a hex-letter suffix", em.validate_id_format("ZZ.TS.1.1.A", "ZZ.TS.1.1") is None)

    # -- check_duplicate_would_result ------------------------------------------------------------

    dup = em.check_duplicate_would_result(siblings, "alpha village")  # case/space-only difference
    check("duplicate check catches a case-insensitive match", dup is not None)
    no_dup = em.check_duplicate_would_result(siblings, "Gamma Village")
    check("duplicate check passes a genuinely new name", no_dup is None)
    self_ok = em.check_duplicate_would_result(siblings, "Alpha Village", exclude_id="ZZ.TS.1.1.1")
    check("duplicate check excludes the record's own id (for rename)", self_ok is None)

    # -- plan_add / plan_rename / plan_remove (dry, in-memory) ------------------------------------

    class Args:
        pass

    a = Args(); a.category = "Village"; a.id = "ZZ.TS.1.1.3"; a.name = "Gamma Village"; a.parent = "ZZ.TS.1.1"
    plan = em.plan_add(master, a)
    check("plan_add succeeds for a valid new village", plan["ok"])

    a2 = Args(); a2.category = "Village"; a2.id = "ZZ.TS.1.1.1"; a2.name = "Whatever"; a2.parent = "ZZ.TS.1.1"
    plan2 = em.plan_add(master, a2)
    check("plan_add refuses a duplicate id", not plan2["ok"])

    a3 = Args(); a3.category = "Village"; a3.id = "ZZ.TS.1.1.3"; a3.name = "Alpha Village"; a3.parent = "ZZ.TS.1.1"
    plan3 = em.plan_add(master, a3)
    check("plan_add refuses a name that would duplicate a sibling", not plan3["ok"])

    r = Args(); r.category = "Village"; r.id = "ZZ.TS.1.1.1"; r.name = "Alpha Village Renamed"
    planr = em.plan_rename(master, r)
    check("plan_rename succeeds for a valid rename", planr["ok"])

    r2 = Args(); r2.category = "Village"; r2.id = "ZZ.TS.1.1.1"; r2.name = "Beta Village"
    planr2 = em.plan_rename(master, r2)
    check("plan_rename refuses a rename that would duplicate a sibling", not planr2["ok"])

    # -- reference-blocking remove -----------------------------------------------------------------

    db_path = make_test_db(tmpdir)
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO users (present_location_json, is_demo, is_removed) VALUES (?, 0, 0)",
                 (json.dumps({"village": {"id": "ZZ.TS.1.1.1", "name": "Alpha Village"}}),))
    conn.commit()
    conn.close()

    rem = Args(); rem.category = "Village"; rem.id = "ZZ.TS.1.1.1"
    plan_rem = em.plan_remove(master, rem, db_path)
    check("plan_remove refuses removal when a real, eligible user references the village", not plan_rem["ok"])

    rem2 = Args(); rem2.category = "Village"; rem2.id = "ZZ.TS.1.1.2"  # Beta Village, no references
    plan_rem2 = em.plan_remove(master, rem2, db_path)
    check("plan_remove allows removal when zero references exist", plan_rem2["ok"])

    rem3 = Args(); rem3.category = "Tehsil"; rem3.id = "ZZ.TS.1.1"  # has children
    plan_rem3 = em.plan_remove(master, rem3, db_path)
    check("plan_remove refuses removal of a record that still has children", not plan_rem3["ok"])

    # -- demo/removed users are reported separately, never block removal ---------------------------

    db_path2 = make_test_db(tmpdir)
    conn = sqlite3.connect(db_path2)
    conn.execute("INSERT INTO users (present_location_json, is_demo, is_removed) VALUES (?, 1, 0)",
                 (json.dumps({"village": {"id": "ZZ.TS.1.1.2", "name": "Beta Village"}}),))
    conn.commit()
    conn.close()
    rem4 = Args(); rem4.category = "Village"; rem4.id = "ZZ.TS.1.1.2"
    plan_rem4 = em.plan_remove(master, rem4, db_path2)
    check("plan_remove allows removal when only a demo user references it", plan_rem4["ok"])
    check("plan_remove still reports the demo reference in its detail",
          plan_rem4["reference_detail"]["total_ineligible_references"] == 1)

    # -- end-to-end CLI: dry-run writes nothing, --apply backs up + writes atomically --------------

    fixture_path = write_fixture(tmpdir)
    before_bytes = fixture_path.read_bytes()
    before_hash = hashlib.sha256(before_bytes).hexdigest()

    dry = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "edit_master_location.py"), "add",
         "--category", "Village", "--id", "ZZ.TS.1.1.3", "--name", "Gamma Village",
         "--parent", "ZZ.TS.1.1", "--master", str(fixture_path), "--db-path", str(db_path2)],
        capture_output=True, text=True,
    )
    check("dry-run exits 0", dry.returncode == 0)
    check("dry-run does not modify the fixture file", fixture_path.read_bytes() == before_bytes)
    check("dry-run output says nothing was written", "No file was modified" in dry.stdout)

    applied = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "edit_master_location.py"), "add",
         "--category", "Village", "--id", "ZZ.TS.1.1.3", "--name", "Gamma Village",
         "--parent", "ZZ.TS.1.1", "--master", str(fixture_path), "--db-path", str(db_path2), "--apply"],
        capture_output=True, text=True,
    )
    check("--apply exits 0", applied.returncode == 0)
    check("--apply changes the fixture file", fixture_path.read_bytes() != before_bytes)
    after_master = json.loads(fixture_path.read_text(encoding="utf-8"))
    added_rec, _, _, _ = em.find_record(after_master, "Village", "ZZ.TS.1.1.3")
    check("--apply actually added the new village", added_rec is not None and added_rec["name"] == "Gamma Village")

    backups = list(tmpdir.glob("Qumanity_Master.fixture.before_edit_master_location_*.json"))
    check("--apply created exactly one backup file", len(backups) == 1)
    if backups:
        check("the backup is byte-identical to the pre-apply original", hashlib.sha256(backups[0].read_bytes()).hexdigest() == before_hash)

    # -- safe to re-run: the same add again now fails cleanly (id already exists), no crash --------

    rerun = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "edit_master_location.py"), "add",
         "--category", "Village", "--id", "ZZ.TS.1.1.3", "--name", "Gamma Village",
         "--parent", "ZZ.TS.1.1", "--master", str(fixture_path), "--db-path", str(db_path2), "--apply"],
        capture_output=True, text=True,
    )
    check("re-running the same add exits non-zero (refuses, does not crash)", rerun.returncode == 1)
    check("re-running the same add reports the id already exists", "already exists" in rerun.stdout)
    after_rerun_bytes = fixture_path.read_bytes()
    check("the refused re-run did not modify the file further", after_rerun_bytes == fixture_path.read_bytes())

    # -- reparent is never supported ----------------------------------------------------------------

    check("this module exposes no 'reparent' operation", not hasattr(em, "plan_reparent"))

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
