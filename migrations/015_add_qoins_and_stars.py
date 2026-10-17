"""Persisted, denominated Qoins (2026-10-17): reverses wallet_core.py's original flat-integer
simplification, for the reward path only. Adds:

  - qoins: one row per physical Qoin a wallet holds (denomination from qoin_core.DENOMINATIONS).
    The wallet's rupee value is SUM(denomination) over its rows; the COUNT of rows is the public
    "number of Qoins" (wallet_core.public_wallet_view()).
  - recognition_stars: a permanent, independent record of a positively-recognised board post --
    written once at freeze/elevate time and never touched again, so it survives even after the
    lunar pipeline archives the originating board_posts row (archive_writer.py). Named for the
    author's karma, not the post, so a village or a profile can list "its" stars even once the
    post itself is long gone.
  - wallet_transactions gains two columns: rupee_value (the INR amount before conversion to
    Qoins, for the reward/penalty rows this pass introduces) and related_post_id (the board post
    that caused the movement, if any).

Backfill: every existing wallet's balance_qoins is materialized into qoins rows via
qoin_core.to_qoins(), so wallets created before this migration end up holding a real, physical
Qoin breakdown of their current balance. balance_qoins itself is left untouched -- it remains the
maintained cache wallet_core.py's credit/debit functions keep in sync with the qoins table, not
replaced by it (see wallet_core.py's own module docstring for why: every existing reader of
balance_qoins keeps working unmodified).

Run via tools/run_migrations.py (calls run(conn)).
"""
from __future__ import annotations

import datetime as dt


def run(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qoins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id INTEGER NOT NULL,
            denomination INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (wallet_id) REFERENCES wallets(id)
        );
        CREATE INDEX IF NOT EXISTS idx_qoins_wallet ON qoins(wallet_id);

        CREATE TABLE IF NOT EXISTS recognition_stars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            level TEXT NOT NULL,
            location_id TEXT NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            cycle_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_recognition_stars_location ON recognition_stars(location_id, level);
        CREATE INDEX IF NOT EXISTS idx_recognition_stars_author ON recognition_stars(author_id);
    """)
    conn.commit()

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(wallet_transactions)")}
    if "rupee_value" not in cols:
        conn.execute("ALTER TABLE wallet_transactions ADD COLUMN rupee_value INTEGER")
    if "related_post_id" not in cols:
        conn.execute("ALTER TABLE wallet_transactions ADD COLUMN related_post_id INTEGER")
    conn.commit()

    # Backfill: materialize every existing wallet's flat balance into physical Qoin rows, so
    # nothing created before this migration is left with a balance that has no corresponding
    # Qoins. Re-run safe: a wallet that already has qoins rows (e.g. this migration ran before,
    # or a reward was already credited through the new path) is skipped.
    import qoin_core

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    wallets = conn.execute("SELECT id, balance_qoins FROM wallets WHERE balance_qoins > 0").fetchall()
    inserted = 0
    touched = 0
    for w in wallets:
        existing = conn.execute("SELECT COUNT(*) FROM qoins WHERE wallet_id = ?", (w["id"],)).fetchone()[0]
        if existing:
            continue
        touched += 1
        for denom in qoin_core.to_qoins(w["balance_qoins"]):
            conn.execute(
                "INSERT INTO qoins (wallet_id, denomination, created_at) VALUES (?, ?, ?)",
                (w["id"], denom, now),
            )
            inserted += 1
    conn.commit()
    print(f"    qoins/recognition_stars tables ready; backfilled {inserted} Qoin row(s) across {touched} wallet(s) "
          f"({len(wallets) - touched} already had Qoins, skipped)")
