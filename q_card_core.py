"""Q-Cards (2026-11-15): the server-side resolution of a physical card's QR token to a real
account, and the minimal issuance primitive Stage 2's own tests need to create a legitimate card
to scan against. See migrations/039_q_cards.py for the full schema rationale and
docs/qcard_phase1_2026_11_15.md for the design this implements.

Stage 2 scope only: `ensure_tables()`, `issue_card()` (the minimum "a card can come into
existence" primitive), and `resolve_token()` (the enumeration-safe scan). The Admin-facing
management actions (mark paid, mark free, mark delivered, revoke, replace, list pending) are
Stage 3's own deliverable, not built here. The batch PDF/QR-rendering flow is Stage 4's.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

ACTIONABLE_STATUS = "active"


def ensure_tables(conn) -> None:
    """Defensive mirror of migrations/039_q_cards.py, same convention every other *_core.py
    module in this codebase already follows -- a throwaway test DB (or a database a migration
    hasn't reached yet) self-heals instead of crashing on a missing table."""
    conn.execute("""CREATE TABLE IF NOT EXISTS q_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending_payment', issued_at TEXT NOT NULL, revoked_at TEXT,
        replaced_by_card_id INTEGER, payment_status TEXT NOT NULL DEFAULT 'unpaid',
        payment_method TEXT, payment_reference TEXT, free_reason TEXT, delivered_at TEXT,
        card_display_id TEXT)""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_q_cards_token_hash ON q_cards(token_hash)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_q_cards_display_id ON q_cards(card_display_id)")
    conn.commit()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    """(raw, hash) -- same shape as family_recovery_core.py's own _new_token(): the raw value is
    returned to the caller exactly once (here: to be encoded into the printed QR and shown to the
    Admin at issuance) and never stored; only the hash is persisted."""
    raw = secrets.token_urlsafe(24)
    return raw, _hash(raw)


def issue_card(conn, user_id: int, free_reason: str | None = None) -> dict:
    """Creates one q_cards row for user_id. free_reason ('admin'|'family'|'council'), when given,
    means the FREE-ELIGIBILITY DECISION has already been made by the caller (Stage 3's own
    derivation from existing tables -- this function never makes that decision itself, it only
    records the outcome) -- the card starts 'active'/'free' immediately, no payment gate. Without
    free_reason, the card starts 'pending_payment'/'unpaid' -- Phase 1's explicit decision that an
    unpaid, non-free card does not activate until an Admin marks it paid (Stage 3).

    Returns {"card_display_id", "raw_token"} -- raw_token is shown/encoded exactly once, here;
    only its hash is ever stored (see module docstring)."""
    raw_token, token_hash = _new_token()
    now = _now_iso()
    is_free = free_reason is not None
    cur = conn.execute(
        """INSERT INTO q_cards (user_id, token_hash, status, issued_at, payment_status, payment_method, free_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, token_hash, "active" if is_free else "pending_payment", now,
         "free" if is_free else "unpaid", "free" if is_free else None, free_reason),
    )
    card_display_id = f"QC-{cur.lastrowid:06d}"
    conn.execute("UPDATE q_cards SET card_display_id = ? WHERE id = ?", (card_display_id, cur.lastrowid))
    conn.commit()
    return {"card_display_id": card_display_id, "raw_token": raw_token}


def resolve_token(conn, raw_token: str) -> dict | None:
    """The enumeration-safe scan: None for EVERY non-actionable case alike -- unknown token,
    malformed/empty input, and a card that exists but isn't 'active' (pending_payment, revoked,
    or replaced) -- never distinguishing which. A 'replaced' token is refused outright, never
    forwarded to replaced_by_card_id (Phase 2's explicit decision: forwarding a found lost card's
    token to its own replacement would let whoever found it keep logging in until the
    replacement itself gets reported lost too -- refusing outright is the safer default).

    Returns {"card_id", "user_id", "name"} only for a genuinely active card. Callers needing the
    scanning person's own first name (the card-resolve route's own "confirm this is your card"
    display) derive it from `name` themselves -- this function doesn't assume what a caller wants
    to show."""
    if not raw_token:
        return None
    row = conn.execute(
        """SELECT q.id AS card_id, q.user_id, u.name FROM q_cards q
           JOIN users u ON u.id = q.user_id
           WHERE q.token_hash = ? AND q.status = ? AND u.is_removed = 0""",
        (_hash(raw_token), ACTIONABLE_STATUS),
    ).fetchone()
    if not row:
        return None
    return {"card_id": row["card_id"], "user_id": row["user_id"], "name": row["name"]}
