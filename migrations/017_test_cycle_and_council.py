"""Post Testing cycle + Council Updates (2026-10-17, docs/test_cycle_design.md): the schema for
(a) a year-long, scheduler-driven demo-vote test of the Board's post -> vote -> reward ->
freeze/elevate path, and (b) a third kind of board content -- council updates -- that is never
voted on, never freezes or elevates, and only ever carries optional thumbs-up/thumbs-down
reactions. Renamed from 017_test_cycle.py (never applied anywhere outside this task's own
throwaway test runs, so the rename carries no migration-history risk).

Adds:
  - board_posts.post_kind TEXT NOT NULL DEFAULT 'member' -- 'member' | 'council_update' | 'test'.
    SQLite applies a column's DEFAULT to every existing row the instant ADD COLUMN runs (verified
    below), so every pre-existing post becomes post_kind='member' with no separate UPDATE
    needed -- correct, since every post before this migration ran IS an ordinary member post.
    This is now the single source of truth for what kind of post a row is; is_test/is_demo_post
    are maintained consistently with it by their one write site (board_core.py's create_post()
    path and test_cycle_scheduler.py's demo-post path), not computed independently.
  - board_posts.is_test / is_demo_post -- see design doc Section 3 for the four combinations and
    the invariant (is_demo_post=1 implies is_test=1, and both imply post_kind='test') that the
    write path alone maintains.
  - board_votes.voted_at -- NULLABLE, no SQL default. SQLite's ALTER TABLE ADD COLUMN only
    accepts a constant default; a function call like datetime('now') is rejected outright
    (verified against this project's SQLite directly -- see design doc Section 4). Every
    PRE-EXISTING row is backfilled below with one timestamp computed once in Python, the same
    technique migration 015 already uses to backfill existing wallets. Every row written AFTER
    this migration gets voted_at supplied explicitly by board_core.cast_vote()'s own INSERT --
    not by any schema-level default -- matching how every other timestamp column in this
    codebase already works.
  - testing_windows -- feature-scoped testing windows (design doc Section 2). 'post_testing' is
    the only feature using this table so far; the schema already supports others ('election_test',
    'wallet_test', 'karma_test', ...) without any future change to this table.

Does NOT touch message_reactions -- confirmed (A1 decision, 2026-10-17): that table's `scope`
column has no CHECK constraint and every function in reactions_core.py already parameterizes it
generically, so a third scope value ('board_post', for council-update reactions) needs no schema
change at all.

Run via tools/run_migrations.py (calls run(conn)).
"""
from __future__ import annotations

import datetime as dt


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(board_posts)")}
    if "post_kind" not in cols:
        conn.execute("ALTER TABLE board_posts ADD COLUMN post_kind TEXT NOT NULL DEFAULT 'member'")
    if "is_test" not in cols:
        conn.execute("ALTER TABLE board_posts ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0")
    if "is_demo_post" not in cols:
        conn.execute("ALTER TABLE board_posts ADD COLUMN is_demo_post INTEGER NOT NULL DEFAULT 0")
    if "test_reward_inr" not in cols:
        # The rupee reward a test post earned at a level it cleared, set by settle() instead of
        # a wallet_transactions row (test posts are never credit_qoins()'d -- Decision 2). NULL
        # for every real post, and for a test post that never earned a positive score.
        conn.execute("ALTER TABLE board_posts ADD COLUMN test_reward_inr INTEGER")
    conn.commit()

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(board_votes)")}
    if "voted_at" not in cols:
        conn.execute("ALTER TABLE board_votes ADD COLUMN voted_at TEXT")
        conn.commit()
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        backfilled = conn.execute(
            "UPDATE board_votes SET voted_at = ? WHERE voted_at IS NULL", (now,)
        ).rowcount
        conn.commit()
    else:
        backfilled = 0

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS testing_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            demo_user_count INTEGER NOT NULL,
            vote_distribution TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_testing_windows_feature_status ON testing_windows(feature, status);
    """)
    conn.commit()

    print(f"    board_posts.post_kind / is_test / is_demo_post / test_reward_inr ready; board_votes.voted_at ready "
          f"({backfilled} pre-existing vote(s) backfilled); testing_windows ready.")
