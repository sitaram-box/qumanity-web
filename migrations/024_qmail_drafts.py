"""Adds Qmail drafts (2026-10-18): unsent compose-form state, saved automatically when a member
closes the compose overlay on the new /qmail page with any field non-empty. See docs/QMAIL.md's
drafts section for the full reasoning (no cleanup job for abandoned drafts -- a stated, deliberate
prototype limitation, not an oversight; Gmail has the same behaviour).

One row per draft, scoped by user_id. No `kind`/attachment column -- a draft never carries an
attachment in this pass (deliberately trimmed scope: autosaving a BLOB on every compose-overlay
close would multiply write volume for a feature that wasn't asked to extend). `to_address` is
whatever the compose form's To field currently holds, unresolved and unvalidated -- a draft is
allowed to have a garbage or incomplete recipient while being edited; resolution only happens at
actual send time, the same as it always has for compose itself.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qmail_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            to_address TEXT,
            subject TEXT,
            body TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qmail_drafts_user ON qmail_drafts(user_id)")
    conn.commit()
    print("    qmail_drafts ready.")
