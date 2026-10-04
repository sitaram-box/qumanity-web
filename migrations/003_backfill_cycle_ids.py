"""Phase 2 backfill: fills cycle_id on every pre-existing row of every Phase-2-stamped table that
doesn't have one yet (migration 002 only adds the column; this is the data pass). Additive-only --
every row is UPDATEd in place, nothing is deleted, no other column changes.

Rule: compute cycle_id from the row's own write timestamp via lunar_calendar.get_current_cycle_id()
when that table has a usable timestamp column (see cycle_middleware.STAMPED_TABLES); when it
doesn't (board_votes), or the stored value doesn't parse, fall back to whatever cycle is active
right now (cycle_middleware.get_active_cycle_id(), which self-seeds cycle_state if nothing has
asked yet).

Run via tools/run_migrations.py -- it calls run(conn) after migrations 001/002 have already been
applied (both idempotent, so running them first is always safe). Can also be run standalone for
testing: `python3 migrations/003_backfill_cycle_ids.py`.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cycle_middleware
import lunar_calendar
from cycle_middleware import STAMPED_TABLES

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _parse_timestamp(value) -> dt.datetime | None:
    """Handles both formats seen across these tables (see docs/phase_2_report.md): SQLite's own
    DEFAULT CURRENT_TIMESTAMP ("YYYY-MM-DD HH:MM:SS", naive UTC) and this app's own _now()-style
    isoformat ("YYYY-MM-DDTHH:MM:SS+00:00", timezone-aware)."""
    if not value:
        return None
    try:
        text = value if "T" in value else value.replace(" ", "T", 1)
        parsed = dt.datetime.fromisoformat(text)
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(IST)


def run(conn) -> None:
    fallback_cycle = cycle_middleware.get_active_cycle_id(conn)
    total_rows = 0
    for table, ts_col in STAMPED_TABLES.items():
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            print(f"  [skip] {table}: table does not exist yet")
            continue
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "cycle_id" not in cols:
            print(f"  [skip] {table}: no cycle_id column (run migration 002 first)")
            continue
        # Aliased explicitly: SQLite reports a bare "rowid" column under the table's own PK column
        # name instead (e.g. "id") when the table has an INTEGER PRIMARY KEY, so an unaliased
        # SELECT rowid is not reliably readable back as row["rowid"].
        select = "SELECT rowid AS _rid" + (f", {ts_col}" if ts_col else "") + f" FROM {table} WHERE cycle_id IS NULL"
        rows = conn.execute(select).fetchall()
        n = 0
        for row in rows:
            cycle_id = fallback_cycle
            if ts_col:
                parsed = _parse_timestamp(row[ts_col])
                if parsed is not None:
                    cycle_id = lunar_calendar.get_current_cycle_id(parsed)
            conn.execute(f"UPDATE {table} SET cycle_id = ? WHERE rowid = ?", (cycle_id, row["_rid"]))
            n += 1
        conn.commit()
        total_rows += n
        print(f"  {table}: backfilled {n} row(s)")
    print(f"Backfill complete -- {total_rows} row(s) across {len(STAMPED_TABLES)} table(s).")


if __name__ == "__main__":
    from db import get_db
    _conn = get_db()
    run(_conn)
    _conn.close()
