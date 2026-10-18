"""Adds Qmail (2026-10-18): an internal-messaging identity layered on top of each member's
Account ID. Not a real inbound/outbound mailbox -- @qumanity.in is an addressing convention for
messages that stay inside Qumanity; nothing here receives real internet mail (no Postfix, no
Mailgun, nothing inbound). See docs/qmail_design.md for the full design.

Three pieces, one migration (they're all part of the same feature activation, and
qmail_messages/qmail_addresses have no meaning without users.qmail_username existing first):

- users.qmail_username: the stable, globally-unique handle a member chooses once at activation.
  Lives on `users`, NOT in the address-history table below -- if it did, the uniqueness
  constraint would break the very first time any user's account_id changed (a second row with
  the same username, for the same person, would collide with their own first row). Nullable --
  not every member activates Qmail. A length CHECK is the DB-level backstop for the 8-15
  character rule; the full character-set rule (letters, numbers, '.', '_', '-' only) can't be
  expressed as a CHECK without a loaded regex extension, so that part stays Python-only
  (qmail_core.validate_username).

- qmail_addresses: address HISTORY -- one row per account_id epoch, since the account_id half of
  an address changes whenever social_core.regenerate_account_id() runs. forward_until is a
  genuine departure from account_ids' own "kept forever" pattern: an old (is_current=0) address
  only resolves while forward_until is still in the future (qmail_core.resolve_address) --
  after that it's dead, by design (the 30-day forwarding rule).

- qmail_messages: the actual message content, modeled on personal_messages' simplicity -- no
  threading, no attachments.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "qmail_username" not in cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN qmail_username TEXT "
            "CHECK (qmail_username IS NULL OR length(qmail_username) BETWEEN 8 AND 15)"
        )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_qmail_username ON users(qmail_username)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS qmail_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id TEXT NOT NULL,
            full_address TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            forward_until TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_qmail_addresses_full ON qmail_addresses(full_address)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qmail_addresses_user ON qmail_addresses(user_id)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS qmail_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            subject TEXT,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qmail_messages_to ON qmail_messages(to_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qmail_messages_from ON qmail_messages(from_user_id)")

    conn.commit()
    print("    users.qmail_username, qmail_addresses and qmail_messages ready.")
