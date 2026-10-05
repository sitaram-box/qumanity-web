"""Phase 3 verification script. Builds its OWN isolated, synthetic DB in a temp directory --
never touches the real local DB -- because the real DB's entire Phase-2 backfill landed every row
in the SAME (current) cycle, so there is no real N-2-or-older cycle to test the pipeline against
yet. Run with:

    python3 tools/verify_pipeline.py

See docs/phase_3_report.md for the design this verifies.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import cycle_middleware
import pipeline_core
import seed_admin_only  # reuses its _apply_schema() so this test DB is built the exact same way
                         # app.py's ensure_database_ready() would, never a hand-rolled schema copy

VILLAGE_ID = "CS.DL.3.4.1A"  # the real pilot village -- its tehsil/district/state/zone ancestors
                              # are real, known-good India location ids (election_core.PILOT_VILLAGE_ID)
LOCATION = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": VILLAGE_ID, "name": "Rohini Sector 24"},
}

# Three synthetic cycles, oldest to newest, so "Chaitra_2026" is unambiguously N-2-or-older.
CYCLE_OLD, CYCLE_N_MINUS_1, CYCLE_N = "Chaitra_2026", "Vaishakha_2026", "Jyeshtha_2026"


def _build_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    seed_admin_only._apply_schema(conn)
    pipeline_core.ensure_tables(conn)
    return conn


def _seed_cycle_state(conn) -> None:
    # _apply_schema() runs migration 003, which calls cycle_middleware.get_active_cycle_id() and
    # self-seeds TODAY'S real cycle as active -- clear that out first so there is exactly one
    # (synthetic) active row, not two.
    conn.execute("DELETE FROM cycle_state")
    conn.commit()
    rows = [
        (CYCLE_OLD, "2026-03-20T00:00:00+05:30", "2026-04-05T00:00:00+05:30", "2026-04-19T00:00:00+05:30", "closed", "2026-03-20T00:00:00+00:00", "2026-04-19T00:00:00+00:00"),
        (CYCLE_N_MINUS_1, "2026-04-19T00:00:00+05:30", "2026-05-05T00:00:00+05:30", "2026-05-18T00:00:00+05:30", "closed", "2026-04-19T00:00:00+00:00", "2026-05-18T00:00:00+00:00"),
        (CYCLE_N, "2026-05-18T00:00:00+05:30", "2026-06-02T00:00:00+05:30", "2026-06-16T00:00:00+05:30", "active", "2026-05-18T00:00:00+00:00", None),
    ]
    for cycle_id, start, mid, end, status, activated_at, closed_at in rows:
        conn.execute(
            "INSERT INTO cycle_state (cycle_id, start_date, mid_date, end_date, status, activated_at, closed_at, activated_by) "
            "VALUES (?,?,?,?,?,?,?, 'verify_pipeline')",
            (cycle_id, start, mid, end, status, activated_at, closed_at),
        )
    conn.commit()


def _seed_users(conn) -> list[int]:
    loc_json = json.dumps(LOCATION)
    ids = []
    for i, (name, gender) in enumerate([("Test Alpha", "male"), ("Test Beta", "female"), ("Test Gamma", "male")]):
        cur = conn.execute(
            "INSERT INTO users (name, gender, dob, tob, birth_location_json, present_location_json, private_id, account_id) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (name, gender, "1995-01-01", "08:00", loc_json, loc_json, f"TEST-{i}", f"TESTACC-{i}"),
        )
        uid = cur.lastrowid
        element = ("Fire", "Water", "Earth")[i]
        conn.execute(
            "INSERT INTO user_zodiac (user_id, sun_sign, sun_element) VALUES (?, 'Aries', ?)",
            (uid, element),
        )
        ids.append(uid)
    conn.commit()
    return ids


def _seed_activity(conn, user_ids: list[int], cycle_id: str) -> dict:
    """Inserts a handful of rows across several tables, all at cycle_id/pipeline_level='village'.
    Returns the per-table counts inserted, for the manual-count cross-check later."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    inserted = {}

    for uid, points in zip(user_ids, (50, 30, 10)):
        conn.execute(
            "INSERT INTO karma_entries (user_id, kind, points, reason, created_at, cycle_id, pipeline_level) "
            "VALUES (?, 'noncommercial', ?, 'verify_pipeline seed', ?, ?, 'village')",
            (uid, points, now, cycle_id),
        )
    inserted["karma_entries"] = len(user_ids)

    chain = json.dumps([{"level": "village", "id": VILLAGE_ID, "name": "Rohini Sector 24"}])
    cur = conn.execute(
        "INSERT INTO board_posts (author_id, level, group_id, group_name, content, status, score, voting_start, voting_end, chain_json, created_at, cycle_id, pipeline_level) "
        "VALUES (?, 'village', ?, 'Rohini Sector 24', 'Test post for verify_pipeline', 'frozen', 5, ?, ?, ?, ?, ?, 'village')",
        (user_ids[0], VILLAGE_ID, now, now, chain, now, cycle_id),
    )
    post_id = cur.lastrowid
    inserted["board_posts"] = 1

    conn.execute(
        "INSERT INTO board_votes (post_id, user_id, value, cycle_id, pipeline_level) VALUES (?, ?, 1, ?, 'village')",
        (post_id, user_ids[1], cycle_id),
    )
    inserted["board_votes"] = 1

    wallet_cur = conn.execute(
        "INSERT INTO wallets (owner_type, owner_id, balance_qoins) VALUES ('user', ?, 25)", (str(user_ids[0]),)
    )
    wallet_id = wallet_cur.lastrowid
    conn.execute(
        "INSERT INTO wallet_transactions (wallet_id, amount_qoins, reason, cycle_id, pipeline_level) VALUES (?, 25, 'verify_pipeline seed', ?, 'village')",
        (wallet_id, cycle_id),
    )
    inserted["wallet_transactions"] = 1

    for uid in user_ids:
        conn.execute(
            "INSERT INTO account_ids (user_id, account_id, search_code, present_location_json, is_current, created_at, cycle_id, pipeline_level) "
            "VALUES (?, ?, ?, ?, 1, ?, ?, 'village')",
            (uid, f"TESTACC-{uid}", f"{900000000000 + uid}", json.dumps(LOCATION), now, cycle_id),
        )
    inserted["account_ids"] = len(user_ids)

    conn.commit()
    return inserted


def _raw_count(conn, cycle_id: str, pipeline_level: str) -> int:
    total = 0
    for table in cycle_middleware.STAMPED_TABLES:
        total += conn.execute(f"SELECT COUNT(*) FROM {table} WHERE cycle_id = ? AND pipeline_level = ?", (cycle_id, pipeline_level)).fetchone()[0]
    return total


def main() -> None:
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "verify_pipeline.db"
        print("=" * 70)
        print(f"Isolated test DB: {db_path} (never the real qumanity_prototype.db)")
        print("=" * 70)
        conn = _build_db(db_path)
        _seed_cycle_state(conn)
        user_ids = _seed_users(conn)
        seeded_counts = _seed_activity(conn, user_ids, CYCLE_OLD)
        print(f"Seeded {sum(seeded_counts.values())} activity rows across {len(seeded_counts)} tables, cycle_id={CYCLE_OLD}")

        n, n_minus_1 = pipeline_core._n_and_n_minus_1(conn)
        print(f"cycle_state: N={n}, N-1={n_minus_1}")
        results.append(("cycle_state identifies N/N-1 correctly", n == CYCLE_N and n_minus_1 == CYCLE_N_MINUS_1))

        eligible = pipeline_core.get_eligible_cycles_for_pipeline(conn)
        print(f"Eligible cycles (N-2 and older): {eligible}")
        results.append((f"{CYCLE_OLD} is eligible, N/N-1 are not", eligible == [CYCLE_OLD]))

        # --- Safety rule: N and N-1 must be rejected outright ---
        safety_ok = True
        for blocked_cycle in (CYCLE_N, CYCLE_N_MINUS_1):
            try:
                pipeline_core.transfer_level(conn, "village", "tehsil", blocked_cycle)
                safety_ok = False
                print(f"FAIL: transfer_level accepted {blocked_cycle} (should have raised PermissionError)")
            except PermissionError:
                pass
        results.append(("Safety rule rejects N and N-1", safety_ok))

        # --- Before counts ---
        before_village = _raw_count(conn, CYCLE_OLD, "village")
        print(f"Rows at pipeline_level='village' for {CYCLE_OLD} before any transfer: {before_village}")

        # --- Manual cross-check for one table before transferring, matching Decision 2's own
        # counts shape later ---
        manual_karma = conn.execute(
            "SELECT COUNT(*) FROM karma_entries WHERE cycle_id=? AND pipeline_level='village'", (CYCLE_OLD,)
        ).fetchone()[0]

        # --- Walk the chain village -> tehsil -> district -> state -> zone -> country -> continent -> earth ---
        print()
        print(f"{'Hop':<28} {'Records Moved':<15} {'Holdings Created':<18} {'Excluded':<10}")
        print("-" * 75)
        chain_ok = True
        for from_level, to_level in zip(pipeline_core.PIPELINE_LEVELS[:-1], pipeline_core.PIPELINE_LEVELS[1:]):
            still_at_from = _raw_count(conn, CYCLE_OLD, from_level)
            r = pipeline_core.transfer_level(conn, from_level, to_level, CYCLE_OLD)
            now_at_to = _raw_count(conn, CYCLE_OLD, to_level)
            now_at_from = _raw_count(conn, CYCLE_OLD, from_level)
            print(f"{from_level + ' -> ' + to_level:<28} {r['records_moved']:<15} {r['holdings_created']:<18} {r['excluded_no_chain']:<10}")
            if now_at_from != 0:
                chain_ok = False
                print(f"  FAIL: {now_at_from} rows still at {from_level} after the {from_level}->{to_level} transfer")
            if r["records_moved"] != still_at_from:
                chain_ok = False
                print(f"  FAIL: expected to move {still_at_from} rows, moved {r['records_moved']}")
        results.append(("Full chain village -> earth moves every row, none deleted", chain_ok))

        # --- Total row count never changed (nothing deleted, only pipeline_level updated) ---
        after_total = sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE cycle_id=?", (CYCLE_OLD,)).fetchone()[0] for t in cycle_middleware.STAMPED_TABLES)
        before_total = sum(seeded_counts.values())
        results.append(("Total row count unchanged end to end (no deletes)", after_total == before_total))
        print(f"\nTotal rows for {CYCLE_OLD}: seeded {before_total}, still present {after_total}")

        # --- level_holdings has a village-aggregate's immediate parent (tehsil) with the village's data ---
        holding = conn.execute(
            "SELECT * FROM level_holdings WHERE level='tehsil' AND cycle_id=? AND level_id=?",
            (CYCLE_OLD, LOCATION["tehsil"]["id"]),
        ).fetchone()
        results.append(("level_holdings has the expected tehsil row", holding is not None))
        if holding:
            summary = json.loads(holding["summary_json"])
            manual_ok = summary["counts"]["karma_entries"] == manual_karma
            results.append(("Aggregate karma_entries count matches manual SQL count", manual_ok))
            print(f"\nSample tehsil holding ({LOCATION['tehsil']['id']}, {CYCLE_OLD}):")
            print(json.dumps(summary, indent=2, ensure_ascii=False))

        # --- Idempotency: re-running the village->tehsil transfer (now a no-op, rows already moved
        # all the way to earth) should move 0 rows and not fail ---
        r2 = pipeline_core.transfer_level(conn, "continent", "earth", CYCLE_OLD)
        results.append(("Re-running continent->earth is idempotent (0 rows moved second time)", r2["records_moved"] == 0))
        print(f"\nRe-run continent -> earth: records_moved={r2['records_moved']} (expect 0)")

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
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
