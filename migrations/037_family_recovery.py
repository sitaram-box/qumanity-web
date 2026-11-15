"""Adds Family Tree-based account recovery (2026-11-13; corrected 2026-11-14, pre-deployment): a
verified family member can help a requester recover their Private ID or reset their PIN,
delivered through the existing Qmail inbox as a first-class, non-forgeable message type.

Two pieces:

- `family_recovery_requests`: the authoritative state machine -- who's being recovered (discovered
  by walking the Family Tree graph, never trusted from client input), who's vouching, what the
  requester claimed vs. what the graph actually verified, which action was requested, and (once a
  PIN reset is approved) how long that approval stays redeemable. This is genuinely new state with
  no existing table shaped for it -- not a duplicate of `id_recovery_requests` (recovery_core.py),
  which is the separate, still-untouched Admin-ticket path this feature sits alongside, not
  replaces.

- `qmail_messages.message_type` / `.recovery_request_id`: two nullable additions to the EXISTING
  message table, not a new messages table -- a recovery request has to show up in the real Qmail
  inbox (existing UI, existing read/unread, existing routes), it just needs a tag so the inbox can
  render it as a Family Recovery Request (restricted actions) instead of an ordinary message an
  recipient could reply to freely, and a way to find its way back to the authoritative request row.
  `message_type` defaults to 'member' so every existing row is unaffected; NULL recovery_request_id
  is the ordinary case.

`tracking_code_hash` is not in the original spec's own field list -- it closes a real gap the spec
doesn't otherwise address: the requester who submits this form is, by definition, not logged in
(that's why they're here), so once the family member decides, there is no session, no confirmed
email/phone, and -- for a "forgot Private ID" request specifically -- not even a Private ID to
notify through. A random, single-use tracking code, shown to the requester exactly once right
after they submit the form and never stored in plain text (hashed the same way recovery_core.py's
own OTP codes already are), is how they come back later and actually receive the outcome. Flagged
explicitly in the handover report as a necessary addition, not a silent scope change.

2026-11-14 security-review corrections, made directly here since this migration had not yet been
deployed anywhere (no follow-up migration needed):
- Dropped `family_member_private_id` -- redundant plaintext sensitive data. `family_member_user_id`
  already identifies the exact same account for every actual use, and nothing ever read this
  column back; it was only ever needed transiently, during relationship verification.
- Dropped `auth_token_hash` / `auth_token_used_at`, replaced `auth_token_expires_at` with
  `pin_reset_approved_until`. The original design minted a second, separate authorization token
  on approval whose raw value was generated and then simply discarded -- never handed to the
  requester through any channel -- while completion actually ran on the tracking_code instead,
  making the hash column pure dead state. The tracking_code is this flow's one bearer credential,
  start to finish; `pin_reset_approved_until` is a plain timestamp (approval time +
  family_recovery_core.PIN_RESET_APPROVAL_TTL_HOURS) with no token of its own to go with it. See
  family_recovery_core.approve_pin_reset()/complete_pin_reset() for the full reasoning.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS family_recovery_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_user_id INTEGER NOT NULL,
            requester_claimed_name TEXT NOT NULL,
            family_member_user_id INTEGER NOT NULL,
            claimed_relationship TEXT NOT NULL,
            verified_relationship TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            qmail_message_id INTEGER,
            tracking_code_hash TEXT NOT NULL,
            pin_reset_approved_until TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            decided_at TEXT,
            decided_by_user_id INTEGER
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_family_recovery_tracking ON family_recovery_requests(tracking_code_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_family_recovery_requester ON family_recovery_requests(requester_user_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_family_recovery_family_member ON family_recovery_requests(family_member_user_id, status)"
    )

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(qmail_messages)")}
    if "message_type" not in cols:
        conn.execute("ALTER TABLE qmail_messages ADD COLUMN message_type TEXT NOT NULL DEFAULT 'member'")
    if "recovery_request_id" not in cols:
        conn.execute("ALTER TABLE qmail_messages ADD COLUMN recovery_request_id INTEGER")

    conn.commit()
    print("    family_recovery_requests ready; qmail_messages.message_type/recovery_request_id ready.")
