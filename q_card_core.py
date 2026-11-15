"""Q-Cards (2026-11-15): the server-side resolution of a physical card's QR token to a real
account, the issuance primitive, and (Stage 3) the Admin-facing management actions and the
free-eligibility derivation. See migrations/039_q_cards.py for the full schema rationale and
docs/qcard_phase1_2026_11_15.md for the design this implements.

Stage 3 adds: the six admin actions (mark_paid, mark_free, mark_delivered, revoke, replace,
list_pending), each enforcing the four status values and legal transitions in Python -- there is
no SQL CHECK constraint on `status` (see migrations/039_q_cards.py's own docstring), so this is
the ONLY enforcement point, and every writer below goes through it. Also adds free_eligibility(),
which derives WHY a user may get a free card (never an admin-supplied string) from three existing
sources: _is_admin_user() (this module's own Flask-independent mirror of app.py's _is_admin(), see
its own docstring for why it isn't a shared import), family_core.recursive_member_node_ids() (the
Family Tree cascade -- reused, not reimplemented, see that function's own docstring), and
announcements_core.is_council_member() against election_core.PILOT_VILLAGE_ID (the one existing
village-council-membership check, already used by the Announcements feature). The batch
PDF/QR-rendering flow remains Stage 4's.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import secrets

import announcements_core
import election_core
import family_core

ACTIONABLE_STATUS = "active"
_STATUSES = {"pending_payment", "active", "revoked", "replaced"}
_PAYMENT_METHODS = {"cash", "upi_static"}


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


# ---- Stage 3: free-eligibility derivation ----

# Deliberately duplicates app.py's _is_admin() by design -- see that function's own definition
# in app.py for the source of truth this mirrors. Not a stale copy: if app.py's _is_admin() ever
# changes its env var or column, this one must change to match.
def _is_admin_user(conn, user_id) -> bool:
    """Flask-independent mirror of app.py's own _is_admin() -- SAME env var
    (QM_ADMIN_PRIVATE_IDS), SAME users.private_id_9digit comparison -- but parameterized by a
    user_id rather than reading session["user_id"], since free_eligibility() below must be able to
    ask "is this card's owner the Admin" for ANY user_id, not only the currently logged-in one.

    A duplicate of app.py's own five lines, not a shared import, because app.py's version is
    irreducibly Flask-session-coupled (it has no user_id parameter at all) and q_card_core.py, like
    every other *_core.py module in this codebase, imports no Flask machinery. This is the Admin
    *identity* check (one person, one env var) -- not a second family-membership rule, which is
    the thing Phase 2 was told not to reinvent; that one is recursive_member_node_ids() below."""
    allowed = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not allowed:
        return False
    row = conn.execute("SELECT private_id_9digit FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and row["private_id_9digit"] in allowed)


def _admin_root_group_ids(conn) -> set[int]:
    """The family_groups.id of every unit where an Admin account is a FOUNDER (husband_node_id or
    wife_node_id) -- the root(s) family-eligibility cascades down from. Reading: 'root' means the
    group the Admin themself FOUNDED (married into), matching the worked example (Pardeep+Neelam,
    where Pardeep is husband_node_id) -- not any group where the Admin is merely a plain child
    node under their OWN parents. If the Admin's own node is also a child in some ascendant group
    (a living grandparent unit), this does not ascend to it; eligibility cascades only DOWNWARD
    from the Admin's own founder group(s), per Rule 1's own wording ("a son's household cascades
    into his FATHER's unit" -- the Admin is being treated as the father, the top, here)."""
    allowed = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not allowed:
        return set()
    admin_user_ids = [r["id"] for r in conn.execute(
        f"SELECT id FROM users WHERE private_id_9digit IN ({','.join('?' * len(allowed))})", tuple(allowed),
    ).fetchall()]
    group_ids = set()
    for admin_user_id in admin_user_ids:
        node_row = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (admin_user_id,)).fetchone()
        if not node_row:
            continue
        for g in conn.execute(
            "SELECT id FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?",
            (node_row["id"], node_row["id"]),
        ).fetchall():
            group_ids.add(g["id"])
    return group_ids


def family_eligible_user_ids(conn) -> set[int]:
    """Every user_id inside the Admin's cascade, per family_core.recursive_member_node_ids() --
    reusing the Family Tree cascade rules (the Cascade, the Daughter Rule, the Death Rule) exactly
    as they are, never a second, independent membership rule written here. Resolves each node_id
    the cascade returns to a user_id via family_nodes.claimed_user_id (an unclaimed placeholder
    node contributes nothing -- only a real account can be free-eligible)."""
    node_ids = set()
    for group_id in _admin_root_group_ids(conn):
        node_ids |= family_core.recursive_member_node_ids(conn, group_id)
    if not node_ids:
        return set()
    rows = conn.execute(
        f"SELECT claimed_user_id FROM family_nodes WHERE id IN ({','.join('?' * len(node_ids))}) AND claimed_user_id IS NOT NULL",
        tuple(node_ids),
    ).fetchall()
    return {r["claimed_user_id"] for r in rows}


def _council_eligible(conn, user_id) -> bool:
    """Reuses announcements_core.is_council_member() -- the one existing village-council-
    membership check in this codebase (already powering the Announcements feature) -- scoped to
    election_core.PILOT_VILLAGE_ID, the one village this whole platform currently pilots on."""
    return announcements_core.is_council_member(conn, user_id, election_core.PILOT_VILLAGE_ID, "village")


def free_eligibility(conn, user_id) -> str | None:
    """The single source of truth for WHY (if at all) user_id may get a free Q-Card -- 'admin',
    'family', or 'council' -- or None. mark_free() below MUST derive free_reason from this
    function's own return value, never from an admin-supplied string, so this is the only place
    the three category strings are decided."""
    if _is_admin_user(conn, user_id):
        return "admin"
    if user_id in family_eligible_user_ids(conn):
        return "family"
    if _council_eligible(conn, user_id):
        return "council"
    return None


# ---- Stage 3: admin actions. Every writer enforces the four status values and legal
# transitions in Python -- the only enforcement that exists, since migrations/039_q_cards.py
# deliberately has no SQL CHECK constraint (matching this codebase's existing convention). ----

def _get_card(conn, card_id) -> dict:
    row = conn.execute("SELECT * FROM q_cards WHERE id = ?", (card_id,)).fetchone()
    if not row:
        raise ValueError("Card not found")
    return row


def _set_status(conn, card_id: int, new_status: str, **extra_cols) -> None:
    """The one place every writer below funnels its status change through -- since there is no
    SQL CHECK constraint on q_cards.status (migrations/039_q_cards.py), this is the only
    enforcement of the four legal values that exists anywhere. Any caller (present or future)
    passing a fifth value is refused here, not at the database."""
    if new_status not in _STATUSES:
        raise ValueError(f"Illegal status '{new_status}' -- must be one of {sorted(_STATUSES)}")
    cols = ", ".join(f"{k} = ?" for k in extra_cols)
    sql = f"UPDATE q_cards SET status = ?{', ' + cols if cols else ''} WHERE id = ?"
    conn.execute(sql, (new_status, *extra_cols.values(), card_id))


def mark_paid(conn, card_id: int, method: str, reference: str | None = None) -> None:
    """unpaid -> paid, pending_payment -> active. Refuses any card not currently
    'pending_payment' -- including an already-active or already-free card (there is no
    paid-on-top-of-paid), and both terminal states (revoked/replaced, per 'no transition out of
    revoked or replaced')."""
    if method not in _PAYMENT_METHODS:
        raise ValueError(f"Unknown payment method '{method}' -- must be one of {sorted(_PAYMENT_METHODS)}")
    card = _get_card(conn, card_id)
    if card["status"] != "pending_payment":
        raise ValueError(f"Cannot mark paid: card is '{card['status']}', not 'pending_payment'")
    _set_status(conn, card_id, "active", payment_status="paid", payment_method=method, payment_reference=reference)
    conn.commit()


def mark_free(conn, card_id: int) -> str:
    """unpaid -> free, pending_payment -> active. free_reason is ALWAYS derived from
    free_eligibility(), never accepted as a parameter -- an admin cannot mark a non-eligible
    user's card free; this function refuses the call outright and says why. No override path
    exists; if one is ever needed, it must be proposed explicitly (a reason string like
    'override:manual' plus an audit log entry), not built silently here. Returns the free_reason
    that was recorded."""
    card = _get_card(conn, card_id)
    if card["status"] != "pending_payment":
        raise ValueError(f"Cannot mark free: card is '{card['status']}', not 'pending_payment'")
    reason = free_eligibility(conn, card["user_id"])
    if reason is None:
        raise ValueError("This card's owner is not eligible for a free card (not Admin, not in the Admin's family cascade, not on the pilot village council)")
    _set_status(conn, card_id, "active", payment_status="free", payment_method="free", free_reason=reason)
    conn.commit()
    return reason


def mark_delivered(conn, card_id: int) -> None:
    """Writes delivered_at. Idempotent -- a card already marked delivered is a pure no-op, never a
    second write (same convention as revoke() below, and as qmail_core.auto_activate()'s own
    repeat-call no-op)."""
    card = _get_card(conn, card_id)
    if card["delivered_at"]:
        return
    conn.execute("UPDATE q_cards SET delivered_at = ? WHERE id = ?", (_now_iso(), card_id))
    conn.commit()


def revoke(conn, card_id: int) -> None:
    """pending_payment|active -> revoked, writes revoked_at. Revoking an already-revoked card is a
    no-op (idempotent, no second write to revoked_at) -- not an error, so a caller doesn't need to
    check status first. Revoking a 'replaced' card directly is refused: that card's own replacement
    already carries the current revoked_at/replaced_by_card_id story; act on the replacement
    instead (same 'no transition out of replaced' rule as every other writer)."""
    card = _get_card(conn, card_id)
    if card["status"] == "revoked":
        return
    if card["status"] == "replaced":
        raise ValueError("Cannot revoke a replaced card directly -- act on its replacement (replaced_by_card_id) instead")
    _set_status(conn, card_id, "revoked", revoked_at=_now_iso())
    conn.commit()


def replace(conn, card_id: int) -> dict:
    """The old row: status -> replaced, writes revoked_at, sets replaced_by_card_id. A new row is
    issued with a fresh token, status 'pending_payment' -- even if the old card was free, the
    replacement is NOT automatically re-granted free; mark_free() must be called again on it,
    so a fresh eligibility check always runs rather than silently trusting a prior grant that may
    no longer hold. Refuses a card that is already 'revoked' or 'replaced' (no transition out of
    either terminal state). Returns issue_card()'s own {"card_display_id", "raw_token"} dict for
    the new card."""
    card = _get_card(conn, card_id)
    if card["status"] in ("revoked", "replaced"):
        raise ValueError(f"Cannot replace a '{card['status']}' card")
    new = issue_card(conn, card["user_id"])
    new_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (new["card_display_id"],)).fetchone()["id"]
    _set_status(conn, card_id, "replaced", revoked_at=_now_iso(), replaced_by_card_id=new_id)
    conn.commit()
    return new


def list_pending(conn) -> list[dict]:
    """Read-only listing of every card still awaiting a payment/free decision."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM q_cards WHERE status = 'pending_payment' ORDER BY issued_at"
    ).fetchall()]
