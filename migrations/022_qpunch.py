"""Adds Q-Punch council addresses (2026-10-18): an extension of Qmail that addresses a LOCATION
rather than a member -- [level]-[location_id]@qumanity.in, e.g. village-CS.DL.3.4.1A@qumanity.in.
See docs/QMAIL.md's Q-Punch section for the full design.

Three tables, one migration (they're all part of the same feature activation):

- qpunch_addresses: one PERMANENT row per (level, location_id) that has ever crossed its level's
  member-count threshold (qmail_core.QPUNCH_THRESHOLDS). Unlike qmail_addresses, this is not
  history -- there is no second row per location, ever. Created once by
  qmail_core.sync_qpunch_addresses() (called from elemental_core.recompute_location_elements()),
  never retired, never reactivated: a location that later drops back below threshold keeps its
  address, deliberately (see docs/QMAIL.md -- a council mailbox that vanishes because two members
  left is worse than one that keeps serving a shrunk community).

- qpunch_queue_messages: a council address's shared, location-scoped inbox. NOT a row in
  qmail_messages -- a council message's recipient is a location with no fixed set of users (the
  heads change at every election), which qmail_messages' single-recipient-user shape can't
  represent without either a nullable recipient or per-head fan-out rows that a newly-elected head
  would never see. sender_id is kept so a member's own /api/qmail/sent can show their own outgoing
  copy without exposing the council's internal reply/action history.

- qpunch_queue_actions: an append-only action log for the queue -- who viewed, replied to, or
  closed which message, and when. Modeled directly on id_recovery_reveals: every touch on a
  shared queue is attributable, the same posture this codebase already applies to revealing
  someone else's Private ID.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qpunch_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            location_id TEXT NOT NULL,
            full_address TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (level, location_id)
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_qpunch_addresses_full ON qpunch_addresses(full_address)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS qpunch_queue_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            location_id TEXT NOT NULL,
            sender_id INTEGER NOT NULL,
            subject TEXT,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qpunch_queue_messages_location "
        "ON qpunch_queue_messages(level, location_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qpunch_queue_messages_sender ON qpunch_queue_messages(sender_id)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS qpunch_queue_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            actor_user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES qpunch_queue_messages(id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qpunch_queue_actions_message ON qpunch_queue_actions(message_id)"
    )

    conn.commit()
    print("    qpunch_addresses, qpunch_queue_messages and qpunch_queue_actions ready.")
