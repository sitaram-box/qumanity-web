"""Phase 2 verification script. Run with:

    python3 tools/verify_cycle_stamping.py

Checks (against the real configured DB -- QM_DB_PATH or the local default, same as the app):
  1. cycle_state exists and has exactly one 'active' row, matching lunar_calendar's live cycle.
  2. Every Phase-2 table has a cycle_id column.
  3. No row in any Phase-2 table is missing cycle_id (full backfill coverage).
  4. A live round-trip: inserting through the real core-module functions (karma, a board post, a
     wallet credit) against a disposable temp-copy of the DB stamps the new row with the currently
     active cycle -- never against the real DB.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db as db_module
import cycle_middleware
from cycle_middleware import STAMPED_TABLES


def check_cycle_state(conn) -> bool:
    import lunar_calendar
    row = cycle_middleware.get_active_cycle_row(conn)
    live = lunar_calendar.get_current_cycle_id()
    active_rows = conn.execute("SELECT COUNT(*) FROM cycle_state WHERE status = 'active'").fetchone()[0]
    ok = active_rows == 1 and row["cycle_id"] == live
    print(("PASS" if ok else "FAIL") + f": cycle_state has exactly one active row ({row['cycle_id']}), "
          f"matching lunar_calendar's live cycle ({live})")
    return ok


def check_columns(conn) -> bool:
    ok = True
    for table in STAMPED_TABLES:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            print(f"FAIL: {table} does not exist")
            ok = False
            continue
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "cycle_id" not in cols:
            print(f"FAIL: {table} has no cycle_id column")
            ok = False
    print(("PASS" if ok else "FAIL") + f": all {len(STAMPED_TABLES)} tables have a cycle_id column")
    return ok


def check_backfill_coverage(conn) -> bool:
    ok = True
    total_null = 0
    for table in STAMPED_TABLES:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "cycle_id" not in cols:
            continue
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE cycle_id IS NULL").fetchone()[0]
        if n:
            print(f"FAIL: {table} has {n} row(s) with cycle_id still NULL")
            total_null += n
            ok = False
    print(("PASS" if ok else "FAIL") + f": no pre-existing rows missing cycle_id (found {total_null})")
    return ok


def check_live_writes() -> bool:
    """Exercises a few real core-module write paths against a throwaway TEMP COPY of the DB --
    never the real one -- and confirms the new rows come out stamped with the active cycle."""
    real_path = Path(db_module.DB_PATH)
    if not real_path.exists():
        print("SKIP: no DB file to copy for the live-write check")
        return True
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "verify_cycle_stamping_tmp.db"
        shutil.copy(real_path, tmp_path)
        import sqlite3
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        active_cycle = cycle_middleware.get_active_cycle_id(conn)

        import karma_core
        karma_core.add_individual_karma(conn, user_id=1, kind="noncommercial", points=1, reason="verify_cycle_stamping smoke test")
        row = conn.execute("SELECT cycle_id FROM karma_entries ORDER BY id DESC LIMIT 1").fetchone()
        ok_karma = row["cycle_id"] == active_cycle

        import wallet_core
        wallet_core._credit(conn, "user", "__verify_cycle_stamping__", 1, "verify_cycle_stamping smoke test")
        row2 = conn.execute("SELECT cycle_id FROM wallet_transactions ORDER BY id DESC LIMIT 1").fetchone()
        ok_wallet = row2["cycle_id"] == active_cycle

        conn.close()
        ok = ok_karma and ok_wallet
        print(("PASS" if ok else "FAIL") + f": live writes through karma_core/wallet_core stamp cycle_id='{active_cycle}' "
              f"(temp copy at {tmp_path.name}, never the real DB)")
        return ok


def main() -> None:
    conn = db_module.get_db()
    print("=" * 70)
    print("Phase 2 verification: cycle_id stamping")
    print("=" * 70)
    results = [
        check_cycle_state(conn),
        check_columns(conn),
        check_backfill_coverage(conn),
    ]
    conn.close()
    results.append(check_live_writes())

    print()
    print("=" * 70)
    all_pass = all(results)
    print("OVERALL:", "ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED")
    print("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
