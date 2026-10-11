"""Phase 4 verification script. Builds its own isolated test DB AND its own fake 0_Earth folder
scaffold under a temp directory -- QM_EARTH_ROOT and QM_DB_PATH are both set to /tmp paths BEFORE
any import that reads them (db.py / folder_connector.py both bind their root path at module import
time, not call time -- the same footgun documented in docs/phase_3_report.md). Never touches the
real local DB or the real 0_Earth tree.

Run with:
    python3 tools/verify_archive_writer.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tmp_ctx = tempfile.TemporaryDirectory()
TMP = Path(_tmp_ctx.name)
DB_PATH = TMP / "verify_archive_writer.db"
EARTH_ROOT = TMP / "0_Earth_test"

os.environ["QM_DB_PATH"] = str(DB_PATH)
os.environ["QM_EARTH_ROOT"] = str(EARTH_ROOT)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sqlite3
import datetime as dt

import archive_writer
import cycle_middleware
import folder_connector
import pipeline_core
import seed_admin_only

VILLAGE_ID = "CS.DL.3.4.1A"
LOCATION = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": VILLAGE_ID, "name": "Rohini Sector 24"},
}
CYCLE_OLD, CYCLE_N1, CYCLE_N = "Chaitra_2026", "Vaishakha_2026", "Jyeshtha_2026"


def _scaffold_earth_tree() -> None:
    """Mimics folder_connector's real naming convention exactly: Continents/<c>/Countries/<c>/
    Zones/<c>:<zoneSuffix>/States/<c>:<id>/Districts/.../Tehsils/.../Villages/<c>:<villageId>."""
    cf = folder_connector._root_char_fix("O_AS")
    countryf = folder_connector._root_char_fix("O_AS_IND")
    base = EARTH_ROOT / "Continents" / cf / "Countries" / countryf
    path = base
    path.mkdir(parents=True, exist_ok=True)
    chain = [
        ("Zones", f"{countryf}:CS"),
        ("States", f"{countryf}:CS.DL"),
        ("Districts", f"{countryf}:CS.DL.3"),
        ("Tehsils", f"{countryf}:CS.DL.3.4"),
        ("Villages", f"{countryf}:CS.DL.3.4.1A"),
    ]
    for container, name in chain:
        path = path / container / name
        path.mkdir(parents=True, exist_ok=True)

    # A bare country-level folder for Nepal, matching the real tree's documented convention ("a
    # bare per-country skeleton for the rest of the world, no Zones/States below country level
    # outside India") -- exercises country_sentiment's real target depth, not a fallback.
    (EARTH_ROOT / "Continents" / cf / "Countries" / folder_connector._root_char_fix("O_AS_NPL")).mkdir(parents=True, exist_ok=True)
    # A second, bare India zone (no states beneath it) -- exercises zone_sentiment's own target
    # depth distinctly from the village's own zone (IND/CS), rather than falling back to country.
    (base / "Zones" / f"{countryf}:NS").mkdir(parents=True, exist_ok=True)


def _build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    seed_admin_only._apply_schema(conn)
    pipeline_core.ensure_tables(conn)
    conn.execute("DELETE FROM cycle_state")
    conn.commit()
    return conn


def _seed_cycle_state(conn) -> None:
    rows = [
        (CYCLE_OLD, "2026-03-20T00:00:00+05:30", "2026-04-05T00:00:00+05:30", "2026-04-19T00:00:00+05:30", "closed", "2026-03-20T00:00:00+00:00", "2026-04-19T00:00:00+00:00"),
        (CYCLE_N1, "2026-04-19T00:00:00+05:30", "2026-05-05T00:00:00+05:30", "2026-05-18T00:00:00+05:30", "closed", "2026-04-19T00:00:00+00:00", "2026-05-18T00:00:00+00:00"),
        (CYCLE_N, "2026-05-18T00:00:00+05:30", "2026-06-02T00:00:00+05:30", "2026-06-16T00:00:00+05:30", "active", "2026-05-18T00:00:00+00:00", None),
    ]
    for c, s, m, e, st, a, cl in rows:
        conn.execute(
            "INSERT INTO cycle_state (cycle_id,start_date,mid_date,end_date,status,activated_at,closed_at,activated_by) VALUES (?,?,?,?,?,?,?, 'verify_archive_writer')",
            (c, s, m, e, st, a, cl),
        )
    conn.commit()


def _seed_users(conn) -> list[int]:
    loc_json = json.dumps(LOCATION)
    ids = []
    for i, (name, gender, element) in enumerate([("Archive Alpha", "male", "Fire"), ("Archive Beta", "female", "Water"), ("Archive Gamma", "male", "Earth")]):
        cur = conn.execute(
            "INSERT INTO users (name,gender,dob,tob,birth_location_json,present_location_json,private_id,account_id) VALUES (?,?,?,?,?,?,?,?)",
            (name, gender, "1995-01-01", "08:00", loc_json, loc_json, f"PRIV-{i}", f"ACC-{i}"),
        )
        uid = cur.lastrowid
        conn.execute("INSERT INTO user_zodiac (user_id, sun_sign, sun_element) VALUES (?, 'Aries', ?)", (uid, element))
        ids.append(uid)
    conn.commit()
    return ids


def _seed_activity(conn, uids: list[int], cycle_id: str) -> int:
    """Seeds at least one row per archive file-group (see archive_writer._ARCHIVE_FILES)."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    n = 0
    loc_json = json.dumps(LOCATION)

    for uid, pts in zip(uids, (40, 20, 5)):
        conn.execute("INSERT INTO karma_entries (user_id,kind,points,reason,created_at,cycle_id,pipeline_level) VALUES (?, 'noncommercial', ?, 'seed', ?, ?, 'village')", (uid, pts, now, cycle_id)); n += 1

    chain = json.dumps([{"level": "village", "id": VILLAGE_ID, "name": "Rohini Sector 24"}])
    cur = conn.execute(
        "INSERT INTO board_posts (author_id,level,group_id,group_name,content,status,score,voting_start,voting_end,chain_json,created_at,cycle_id,pipeline_level) "
        "VALUES (?, 'village', ?, 'Rohini Sector 24', 'Archive test post', 'frozen', 5, ?, ?, ?, ?, ?, 'village')",
        (uids[0], VILLAGE_ID, now, now, chain, now, cycle_id)); n += 1
    post_id = cur.lastrowid
    conn.execute("INSERT INTO board_votes (post_id,user_id,value,cycle_id,pipeline_level) VALUES (?,?,1,?,'village')", (post_id, uids[1], cycle_id)); n += 1
    conn.execute("INSERT INTO board_comments (post_id,user_id,text,created_at,cycle_id,pipeline_level) VALUES (?,?,'Nice post',?,?,'village')", (post_id, uids[2], now, cycle_id)); n += 1

    wcur = conn.execute("INSERT INTO wallets (owner_type,owner_id,balance_qoins) VALUES ('user', ?, 25)", (str(uids[0]),))
    conn.execute("INSERT INTO wallet_transactions (wallet_id,amount_qoins,reason,cycle_id,pipeline_level) VALUES (?, 25, 'seed', ?, 'village')", (wcur.lastrowid, cycle_id)); n += 1

    conn.execute("INSERT INTO app_reviews (user_id,rating,text,allow_public,source,created_at,cycle_id,pipeline_level) VALUES (?, 5, 'Great app', 0, 'app', ?, ?, 'village')", (uids[0], now, cycle_id)); n += 1

    conn.execute("INSERT INTO profile_change_requests (user_id,fields_json,reason,created_at,cycle_id,pipeline_level) VALUES (?, '{}', 'test', ?, ?, 'village')", (uids[0], now, cycle_id)); n += 1

    conn.execute("INSERT INTO volunteers (user_id,level,group_id,kind,skill,created_at,cycle_id,pipeline_level) VALUES (?, 'village', ?, 'volunteer', 'testing', ?, ?, 'village')", (uids[1], VILLAGE_ID, now, cycle_id)); n += 1
    conn.execute("INSERT INTO referrer_applications (user_id,note,created_at,cycle_id,pipeline_level) VALUES (?, 'test note', ?, ?, 'village')", (uids[2], now, cycle_id)); n += 1

    sgcur = conn.execute("INSERT INTO subgroups (village_id,name,description,admin_label,created_by,created_at,cycle_id,pipeline_level) VALUES (?, 'Test RWA', '', 'RWA', ?, ?, ?, 'village')", (VILLAGE_ID, uids[0], now, cycle_id)); n += 1
    conn.execute("INSERT INTO subgroup_members (subgroup_id,user_id,status,requested_at,cycle_id,pipeline_level) VALUES (?, ?, 'approved', ?, ?, 'village')", (sgcur.lastrowid, uids[1], now, cycle_id)); n += 1

    conn.execute("INSERT INTO account_ids (user_id,account_id,search_code,present_location_json,is_current,created_at,cycle_id,pipeline_level) VALUES (?, ?, ?, ?, 1, ?, ?, 'village')", (uids[0], f"ACC-{uids[0]}", "900000000001", loc_json, now, cycle_id)); n += 1
    conn.execute("INSERT INTO people_requests (from_user_id,to_user_id,kind,first_message,created_at,cycle_id,pipeline_level) VALUES (?, ?, 'message', 'hi', ?, ?, 'village')", (uids[0], uids[1], now, cycle_id)); n += 1

    conn.execute("INSERT INTO country_sentiment (user_id,country_id,voting_year,vote,created_at,updated_at,cycle_id,pipeline_level) VALUES (?, 'O_AS_NPL', 2026, 'pro', ?, ?, ?, 'country')", (uids[0], now, now, cycle_id)); n += 1
    conn.execute("INSERT INTO zone_sentiment (user_id,zone_id,voting_year,vote,created_at,updated_at,cycle_id,pipeline_level) VALUES (?, 'IND/NS', 2026, 'anti', ?, ?, ?, 'zone')", (uids[1], now, now, cycle_id)); n += 1

    conn.execute("INSERT INTO collective_karma_log (location_id,location_level,points,reason,created_at,cycle_id,pipeline_level) VALUES (?, 'village', 10, 'seed', ?, ?, 'village')", (VILLAGE_ID, now, cycle_id)); n += 1

    pg_owner = uids[0]
    pgcur = conn.execute("INSERT INTO personal_groups (owner_user_id,category,name,created_at,cycle_id,pipeline_level) VALUES (?, 'custom', 'Test Group', ?, ?, 'village')", (pg_owner, now, cycle_id)); n += 1
    conn.execute("INSERT INTO personal_group_members (group_id,user_id,status,invited_by,created_at,cycle_id,pipeline_level) VALUES (?, ?, 'approved', ?, ?, ?, 'village')", (pgcur.lastrowid, uids[1], pg_owner, now, cycle_id)); n += 1

    lo, hi = sorted((uids[0], uids[1]))
    pccur = conn.execute("INSERT INTO private_chats (user_lo,user_hi,created_at,cycle_id,pipeline_level) VALUES (?, ?, ?, ?, 'village')", (lo, hi, now, cycle_id)); n += 1

    conn.commit()
    return n


def _raw_count(conn, cycle_id: str, pipeline_level: str) -> int:
    return sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE cycle_id=? AND pipeline_level=?", (cycle_id, pipeline_level)).fetchone()[0]
               for t in cycle_middleware.STAMPED_TABLES)


def main() -> None:
    results = []
    print("=" * 70)
    print(f"Isolated test DB: {DB_PATH}")
    print(f"Isolated 0_Earth: {EARTH_ROOT}")
    print("=" * 70)

    _scaffold_earth_tree()
    conn = _build_db()
    _seed_cycle_state(conn)
    uids = _seed_users(conn)
    seeded = _seed_activity(conn, uids, CYCLE_OLD)
    print(f"Seeded {seeded} activity rows, cycle_id={CYCLE_OLD}")

    # Climb the pipeline to earth first (Phase 3, already verified elsewhere -- just the setup
    # this phase needs).
    pipeline_core.run_full_pipeline(conn, CYCLE_OLD)
    at_earth = _raw_count(conn, CYCLE_OLD, "earth")
    print(f"Rows at pipeline_level='earth' after climbing: {at_earth}")
    results.append(("All seeded rows reached earth", at_earth == seeded))

    # --- dry run ---
    dry = pipeline_core.transfer_earth_to_archive(conn, CYCLE_OLD, dry_run=True)
    print(f"\nDry run result: {dry}")
    still_at_earth = _raw_count(conn, CYCLE_OLD, "earth")
    results.append(("Dry run writes files but does not delete", still_at_earth == seeded))

    village_dir = folder_connector.resolve_location_dir(archive_writer._location_dict_for("village", VILLAGE_ID))
    cycle_folder_name = __import__("lunar_calendar").archive_folder_name(CYCLE_OLD)
    archive_dir = village_dir / "archives" / cycle_folder_name

    print(f"\n{'File':<30} {'Exists':<8} {'Valid':<8} {'Records'}")
    print("-" * 60)
    all_files_ok = True
    meta = None
    for fname in sorted(p.name for p in archive_dir.iterdir()) if archive_dir.exists() else []:
        fpath = archive_dir / fname
        exists = fpath.exists()
        valid, n_records = False, "-"
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            valid = True
            if isinstance(data, list):
                n_records = len(data)
            elif fname == "cycle_metadata.json":
                meta = data
        except json.JSONDecodeError:
            pass
        all_files_ok = all_files_ok and exists and valid
        print(f"{fname:<30} {'✓' if exists else '✗':<8} {'✓' if valid else '✗':<8} {n_records}")
    results.append(("Every written file exists and is valid JSON", all_files_ok))

    lang_ok = bool(meta) and len(meta.get("display_names", {})) == 13
    results.append(("cycle_metadata.json has all 13 language display_names", lang_ok))
    if meta:
        recomputed = archive_writer._sha256_of_dir(archive_dir)
        results.append(("checksum_sha256 matches recomputation", recomputed == meta.get("checksum_sha256")))
        print(f"\nSample cycle_metadata.json:\n{json.dumps(meta, indent=2, ensure_ascii=False)[:1200]}")

    # --- real run ---
    real = pipeline_core.transfer_earth_to_archive(conn, CYCLE_OLD, dry_run=False)
    print(f"\nReal run result: {real}")
    after_delete = _raw_count(conn, CYCLE_OLD, "earth")
    results.append(("Raw records ARE deleted after the real run", after_delete == 0))
    results.append(("records_deleted matches what was seeded", real.get("records_deleted") == seeded))

    backup_path = archive_writer.BACKUPS_DIR / f"pre_archive_{CYCLE_OLD}.sql"
    results.append(("Backup SQL file was written before delete", backup_path.exists()))

    # --- idempotency ---
    again = pipeline_core.transfer_earth_to_archive(conn, CYCLE_OLD, dry_run=False)
    print(f"\nRe-run result: {again}")
    results.append(("Idempotency: re-run reports already_archived, no error", again.get("status") == "already_archived"))

    # --- integrity: read back the archive, compare counts to what was seeded ---
    status = archive_writer.archive_status(conn, CYCLE_OLD)
    print(f"\narchive_status(): {status}")
    results.append(("archive_status reports archived=True with a checksum match", status["archived"] and status["checksum_match"]))

    conn.close()

    print()
    print("=" * 70)
    print("Consistency checks")
    print("=" * 70)
    all_pass = True
    for label, ok in results:
        print(("PASS" if ok else "FAIL") + f": {label}")
        all_pass = all_pass and ok

    print()
    print("=" * 70)
    print("OVERALL:", "ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED")
    print("=" * 70)
    _tmp_ctx.cleanup()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
