"""Q-Cards (2026-11-15, Phase 1/Phase 2 design): a physical card carrying a QR code that lets a
member sign in without remembering their 9-digit Private ID. The QR encodes a random, unguessable
TOKEN -- never the Private ID, the account_id, or the username (see the Phase 1 report,
docs/qcard_phase1_2026_11_15.md, for the full reasoning: a QR is public, anyone who photographs
the card reads it instantly, so a QR that encoded the Private ID would turn "something you know"
into "something you can photograph"). Only `token_hash` (SHA-256 of the raw token) is ever stored
-- the exact hash-at-rest convention `family_recovery_core.py`'s `tracking_code_hash` and
`recovery_core.py`'s OTP `code_hash` already established in this codebase, reused here rather
than inventing a second scheme. The raw token exists only in the printed QR code and briefly in
memory during a resolve call; a database dump alone can never reconstruct a working card.

Scanning the token resolves to a user_id; the PIN (checked via the existing, unchanged
pin_hash/pin_fails/pin_locked_until columns on `users`, through app.py's shared
verify_user_pin_and_login() helper) is the only secret -- this table adds no second credential.

Status lifecycle (`status`): 'pending_payment' (issued, not yet payable-for or free-eligible --
does not activate; Phase 1's explicit decision) -> 'active' (the only state a scan can succeed
against) -> 'revoked' (disabled, e.g. lost, no replacement issued) or 'replaced' (disabled because
`replaced_by_card_id` now points at the new, current card for this same user -- the old token is
refused outright, never forwarded; Phase 1's explicit decision, since forwarding a found lost
card's token to its replacement would let whoever found it keep logging in until the replacement
is itself reported).

payment_status/payment_method/payment_reference are a separate axis from `status` -- what
actually happened with the ₹11 fee (or why it didn't apply), independent of whether the card is
currently usable. free_reason ('admin' | 'family' | 'council') records WHY a card was free,
derived from the existing Admin/Family-Tree-cascade/village_council data at issuance time (Phase 1
section 3) -- never a manually-set override.

card_display_id ('QC-000142'-shaped, same zero-padded-reference convention already used for
recovery_core.py's 'REQ-'/app.py's 'REC-' references) is for Admin-facing tracking only -- it is
never the thing that grants access, and is safe to show on the printed card itself alongside the
QR as human-readable fallback text.

Schema-only, replays against every database through tools/run_migrations.py.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS q_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_payment',
            issued_at TEXT NOT NULL,
            revoked_at TEXT,
            replaced_by_card_id INTEGER,
            payment_status TEXT NOT NULL DEFAULT 'unpaid',
            payment_method TEXT,
            payment_reference TEXT,
            free_reason TEXT,
            delivered_at TEXT,
            card_display_id TEXT
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_q_cards_token_hash ON q_cards(token_hash)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_q_cards_display_id ON q_cards(card_display_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_q_cards_user ON q_cards(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_q_cards_status ON q_cards(status)")
    conn.commit()
    print("    q_cards ready.")
