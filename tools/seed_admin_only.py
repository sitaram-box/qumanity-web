#!/usr/bin/env python3
"""Produces a clean, minimal DB containing ONLY the Founder's real Admin account -- for uploading
to a Railway Volume that should start with no demo users.

This COPIES the Admin's real, already-verified row (and its real user_zodiac /
user_elemental_profile / account_ids / wallets rows) from an existing source DB, rather than
regenerating them through the normal registration pipeline. Regenerating would run the zodiac/
kundali calculation and id_generator fresh, which is not guaranteed to reproduce the exact same
private_id -- copying the real, already-correct row is strictly safer.

Schema is applied the same way app.py's own ensure_database_ready() does -- db/schema.sql, the
zodiac reference-data seed, founder/visibility/recovery's tables, every other *_core module's
tables, and the Phase 2 migrations -- by reusing those same functions, so a DB this script
produces boots identically to a real one and never drifts out of sync with the real schema.

Usage:
    python3 tools/seed_admin_only.py --db-path ./admin_only.db --private-id <your admin's 9-digit private_id_9digit>
    python3 tools/seed_admin_only.py --db-path ./admin_only.db --source-db ./qumanity_prototype.db --private-id <...>

Idempotent in spirit: refuses to overwrite an existing --db-path unless --force is passed, so a
re-run never silently duplicates anything.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Mirrors app.py's own _ensure_user_columns() column list exactly (duplicated, not imported --
# `import app` would execute app.py's full module-level boot sequence, including
# ensure_database_ready() and the scheduler, against whatever QM_DB_PATH happens to be set in
# THIS process's environment, not against the --db-path this script is building. Keep this list
# in sync with app.py's _ensure_user_columns() if that one changes.
_USER_COLUMNS = [
    ("daily_language", "TEXT"),
    ("private_id_9digit", "TEXT"), ("pin_hash", "TEXT"), ("pin_fails", "INTEGER DEFAULT 0"), ("pin_locked_until", "TEXT"),
    ("relationship_status", "TEXT"), ("has_children", "INTEGER"), ("sons_count", "INTEGER DEFAULT 0"), ("daughters_count", "INTEGER DEFAULT 0"),
    ("work_profile", "TEXT"), ("work_profile_other", "TEXT"),
    ("referred_by_user_id", "INTEGER"),
    ("preferred_language", "TEXT"),
    ("hide_identity", "INTEGER DEFAULT 0"),
]


def _ensure_user_columns(conn: sqlite3.Connection) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    for col, ddl in _USER_COLUMNS:
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_code ON users(private_id_9digit)")
    conn.commit()


def _apply_schema(conn: sqlite3.Connection) -> None:
    """Mirrors app.py's ensure_database_ready() + _ensure_user_columns(), applied against an
    arbitrary connection instead of the QM_DB_PATH-configured one, by reusing its exact building
    blocks (the *_core modules' own ensure_tables, the Phase 2 migrations)."""
    schema_sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    _ensure_user_columns(conn)

    db_dir = str(ROOT / "db")
    if db_dir not in sys.path:
        sys.path.insert(0, db_dir)
    import seed_zodiac_data
    seed_zodiac_data.seed(conn)

    import founder_core
    import recovery_core
    import visibility_core
    founder_core.ensure_tables(conn)
    visibility_core.ensure_tables(conn)
    recovery_core.ensure_tables(conn)
    conn.commit()

    tools_dir = str(ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import run_migrations
    run_migrations._ensure_migrations_table(conn)
    run_migrations._ensure_source_tables(conn)
    applied = run_migrations._applied(conn)
    files = sorted(list((ROOT / "migrations").glob("*.sql")) + list((ROOT / "migrations").glob("*.py")), key=lambda p: p.name)
    for f in files:
        if f.name in applied:
            continue
        if f.suffix == ".sql":
            run_migrations._run_sql_file(conn, f)
        else:
            run_migrations._run_py_file(conn, f)
        run_migrations._mark_applied(conn, f.name)

    import election_core
    import social_core
    election_core.ensure_history_table(conn)
    social_core.backfill_account_ids(conn)  # no-op here (no users yet) -- kept for parity with boot


def _copy_rows(src: sqlite3.Connection, dst: sqlite3.Connection, table: str, where_sql: str, params: tuple) -> int:
    """Copies matching rows, restricted to columns that exist on the TARGET table -- the source
    (a long-lived DB) can carry ad hoc columns a freshly-built schema doesn't have (e.g. `is_demo`,
    added only by scripts/seed_election_demo.py, never by the base schema) and those are silently
    dropped rather than crashing the copy."""
    dst_cols = {r["name"] for r in dst.execute(f"PRAGMA table_info({table})")}
    rows = src.execute(f"SELECT * FROM {table} WHERE {where_sql}", params).fetchall()
    for row in rows:
        cols = [c for c in row.keys() if c in dst_cols]
        placeholders = ",".join("?" * len(cols))
        dst.execute(f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({placeholders})", tuple(row[c] for c in cols))
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db-path", required=True, help="Target DB file to create")
    ap.add_argument("--source-db", default=str(ROOT / "qumanity_prototype.db"), help="Existing DB to copy the Admin account from (default: local dev DB)")
    ap.add_argument("--private-id", required=True, help="The Admin's private_id_9digit to copy -- no default (was a hardcoded real Private ID; always pass this explicitly now)")
    ap.add_argument("--force", action="store_true", help="Overwrite --db-path if it already exists")
    args = ap.parse_args()

    target, source = Path(args.db_path), Path(args.source_db)
    if not source.exists():
        print(f"Source DB not found: {source}")
        sys.exit(1)
    if target.exists():
        if not args.force:
            print(f"{target} already exists -- pass --force to overwrite, or pick a new --db-path.")
            sys.exit(1)
        target.unlink()

    dst = sqlite3.connect(target)
    dst.row_factory = sqlite3.Row
    dst.execute("PRAGMA foreign_keys = ON")
    _apply_schema(dst)

    src = sqlite3.connect(source)
    src.row_factory = sqlite3.Row
    admin = src.execute("SELECT id, name FROM users WHERE private_id_9digit = ?", (args.private_id,)).fetchone()
    if not admin:
        print(f"No user with private_id_9digit={args.private_id} found in {source}")
        src.close()
        dst.close()
        target.unlink()
        sys.exit(1)
    admin_id = admin["id"]

    n_users = _copy_rows(src, dst, "users", "id = ?", (admin_id,))
    n_zodiac = _copy_rows(src, dst, "user_zodiac", "user_id = ?", (admin_id,))
    n_elemental = _copy_rows(src, dst, "user_elemental_profile", "user_id = ?", (admin_id,))
    n_accounts = _copy_rows(src, dst, "account_ids", "user_id = ?", (admin_id,))
    n_wallets = _copy_rows(src, dst, "wallets", "owner_type = 'user' AND owner_id = ?", (str(admin_id),))
    dst.commit()
    src.close()

    n_ref_rows = dst.execute("SELECT COUNT(*) FROM zodiac_signs").fetchone()[0] + dst.execute("SELECT COUNT(*) FROM nakshatras").fetchone()[0]
    dst.close()

    print(f"Seeded {n_users} user ('{admin['name']}', private_id_9digit={args.private_id}), "
          f"{n_zodiac} zodiac row, {n_elemental} elemental profile row, {n_accounts} account_id row, "
          f"{n_wallets} wallet row, {n_ref_rows} zodiac/nakshatra reference rows -- no demo users. "
          f"Admin-only DB ready at {target}")


if __name__ == "__main__":
    main()
