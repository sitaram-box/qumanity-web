"""Adds Qmail attachments (2026-10-18): one small file per message, for both member-to-member
mail and Q-Punch council mail. See docs/QMAIL.md's attachments section for the full reasoning.

Stored as a SQLite BLOB, not on disk. This is a deliberate prototype choice, not a permanent
architecture: the database already carries the volume-persistence guarantee Railway requires a
separate, deliberately-configured path for (QM_DB_PATH's own docs/INSTALL.md warning shows how
easily that gets forgotten), so a BLOB inherits that guarantee for free -- no new env var, no new
"did I mount this right" failure mode. Migrating to real object storage later is a separable
decision this table doesn't make any harder.

`kind` + `message_id` is a loose, polymorphic reference -- 'member' points at qmail_messages.id,
'council' at qpunch_queue_messages.id. Not a real foreign key, because it points at two different
tables depending on `kind`; every query against this table filters on both columns together,
never message_id alone, so a member message id and a council message id that happen to collide
numerically can never resolve to the wrong attachment.

Attachments are compose-time only in this pass -- a reply or an action-log entry never carries
one (qmail_core.MAX_ATTACHMENT_BYTES and the enforcement are in qmail_core.py, not here; this
migration is schema-only).
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qmail_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            uploader_user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qmail_attachments_message ON qmail_attachments(kind, message_id)"
    )
    conn.commit()
    print("    qmail_attachments ready.")
