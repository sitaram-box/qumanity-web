#!/usr/bin/env python3
"""Applies every migration in migrations/ that hasn't been applied yet, tracked in its own
`migrations` table. Idempotent -- re-running does nothing once everything is applied, and a
half-applied .sql file (e.g. an ALTER that already landed) is skipped statement-by-statement
rather than aborting the whole file.

Usage:
    python3 tools/run_migrations.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
sys.path.insert(0, str(ROOT))

from db import get_db  # noqa: E402


def _ensure_source_tables(conn) -> None:
    """Phase 2's tables are owned by these core modules' own ensure_*() functions -- the same
    lazy "CREATE TABLE IF NOT EXISTS" pattern already used throughout this codebase. Run them
    first so migration 002's ALTER TABLE statements always find a real table underneath, whether
    this DB has exercised every feature already or is missing one that's only created lazily.

    wallet_transactions/election_candidates/election_votes/election_cycles/village_council live in
    db/schema.sql, applied once by db/init_db.py -- NOT recreated here (see docs/phase_2_report.md).
    A DB that has never run db/init_db.py has no `users` table either and isn't a real deployment
    target for this migration."""
    import board_core
    import election_core
    import karma_core
    import payment_core
    import perception_core
    import reactions_core
    import review_core
    import social_core

    board_core.ensure_tables(conn)
    board_core.ensure_sub_tables(conn)
    social_core.ensure_tables(conn)
    social_core.ensure_account_request_table(conn)
    karma_core.ensure_tables(conn)
    payment_core.ensure_tables(conn)
    perception_core.ensure_tables(conn)
    review_core.ensure_tables(conn)
    reactions_core.ensure_tables(conn)
    election_core.ensure_council_columns(conn)
    conn.execute("""CREATE TABLE IF NOT EXISTS profile_change_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, fields_json TEXT NOT NULL,
        reason TEXT, status TEXT NOT NULL DEFAULT 'pending', decided_by INTEGER, decided_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()


def _ensure_migrations_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS migrations (
        filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()


def _applied(conn) -> set[str]:
    return {r["filename"] for r in conn.execute("SELECT filename FROM migrations")}


def _mark_applied(conn, filename: str) -> None:
    conn.execute("INSERT INTO migrations (filename) VALUES (?)", (filename,))
    conn.commit()


def _run_sql_file(conn, path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    cleaned = "\n".join(re.sub(r"--.*$", "", line) for line in raw.split("\n"))
    for statement in (s.strip() for s in cleaned.split(";")):
        if not statement:
            continue
        try:
            conn.execute(statement)
        except Exception as e:
            msg = str(e).lower()
            if "duplicate column name" in msg or "already exists" in msg:
                print(f"    [skip, already applied] {statement.splitlines()[0][:70]}")
                continue
            raise
    conn.commit()


def _run_py_file(conn, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "run"):
        raise RuntimeError(f"{path.name} must define a run(conn) function")
    module.run(conn)


def main() -> None:
    conn = get_db()
    _ensure_migrations_table(conn)
    _ensure_source_tables(conn)
    applied = _applied(conn)
    files = sorted(list(MIGRATIONS_DIR.glob("*.sql")) + list(MIGRATIONS_DIR.glob("*.py")), key=lambda p: p.name)
    pending = [f for f in files if f.name not in applied]
    if not pending:
        print("No pending migrations.")
        conn.close()
        return
    for f in pending:
        print(f"Applying {f.name}...")
        if f.suffix == ".sql":
            _run_sql_file(conn, f)
        else:
            _run_py_file(conn, f)
        _mark_applied(conn, f.name)
        print("  done.")
    conn.close()
    print(f"Applied {len(pending)} migration(s).")


if __name__ == "__main__":
    main()
