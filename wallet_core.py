"""Karma Qoins wallets — one per user, and one per location at every tier
from Earth down to Village (see location_elements/elemental_core.py for the
same (location_id, location_type) convention this reuses).

Simplification vs. the old Qumanity prototype: 1 Qoin = ₹1 flat, stored as a
plain integer balance. The old prototype broke every wallet into an
encrypted list of denominated "coins" (₹2000/500/.../1); nothing in this
pass's scope needs that, so it's deliberately not carried over.

Qoins are earned, never purchased: there is no payment or donation path. The only mint at
registration is the free one (`apply_free_registration`): a single ₹1-reference Qoin shared 10
paise at a time across the location tiers, the referrer and the new member. The new member's own
share is credited as *locked* -- held out of their wallet balance until they cast their first
election vote (see `unlock_user_share`, called from election_core.cast_vote).
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import cycle_middleware
import elemental_core

LOCATION_TIERS = ("earth", "continent", "country", "zone", "state", "district", "tehsil", "village")


def _ensure_paisa_column(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(wallets)")}
    if "paisa_balance" not in cols:
        conn.execute("ALTER TABLE wallets ADD COLUMN paisa_balance INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def ensure_wallet(conn, owner_type: str, owner_id: str) -> int:
    """Get-or-create a wallet row; returns its id."""
    row = conn.execute(
        "SELECT id FROM wallets WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)
    ).fetchone()
    if row:
        return row["id"]
    _ensure_paisa_column(conn)
    cur = conn.execute(
        "INSERT INTO wallets (owner_type, owner_id, balance_qoins) VALUES (?, ?, 0)",
        (owner_type, owner_id),
    )
    return cur.lastrowid


def wallet_balance(conn, owner_type: str, owner_id: str) -> int:
    row = conn.execute(
        "SELECT balance_qoins FROM wallets WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)
    ).fetchone()
    return row["balance_qoins"] if row else 0


def wallet_transactions(conn, owner_type: str, owner_id: str, limit: int = 25) -> list[dict]:
    wallet = conn.execute(
        "SELECT id FROM wallets WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)
    ).fetchone()
    if not wallet:
        return []
    rows = conn.execute(
        """SELECT amount_qoins, reason, locked, created_at FROM wallet_transactions
           WHERE wallet_id = ? ORDER BY id DESC LIMIT ?""",
        (wallet["id"], limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _credit_paisa(conn, owner_type: str, owner_id: str, paisa: int, reason: str,
                   locked: bool = False, related_user_id: int | None = None) -> None:
    """A sub-rupee credit (used only for the free ₹1 registration split, where 10 paise each go
    to 10 wallets). Paise below a whole rupee sit in `wallets.paisa_balance`; once a wallet's
    paisa reaches 100 it is converted into whole Qoins (via `_credit`) and the remainder kept."""
    if paisa == 0:
        return
    _ensure_paisa_column(conn)
    wallet_id = ensure_wallet(conn, owner_type, owner_id)
    row = conn.execute("SELECT paisa_balance FROM wallets WHERE id = ?", (wallet_id,)).fetchone()
    total = (row["paisa_balance"] or 0) + paisa
    whole, remainder = divmod(total, 100)
    conn.execute("UPDATE wallets SET paisa_balance = ? WHERE id = ?", (remainder, wallet_id))
    if whole:
        _credit(conn, owner_type, owner_id, whole, reason, locked=locked, related_user_id=related_user_id)


def apply_free_registration(conn, user_id: int, present_location: dict, referrer_user_id: int | None) -> None:
    """No donation at registration: a single ₹1 Qoin is still minted and split, per the founder's
    ruling, 10 paise to each of the 10 shares -- the 8 location tiers, the referrer and the new
    user. With no referrer, their 10 paise folds into the new user's share (20 paise)."""
    for location_id, location_type in elemental_core.location_levels_for(present_location):
        _credit_paisa(conn, location_type, location_id, 10, "free_registration_location")
    new_user_paisa = 10
    if referrer_user_id is not None:
        _credit_paisa(conn, "user", str(referrer_user_id), 10, "free_registration_referrer", related_user_id=user_id)
    else:
        new_user_paisa += 10
    _credit_paisa(conn, "user", str(user_id), new_user_paisa, "free_registration_self", locked=True, related_user_id=user_id)
    conn.commit()


def _credit(conn, owner_type: str, owner_id: str, amount_qoins: int, reason: str,
            locked: bool = False, related_user_id: int | None = None) -> None:
    if amount_qoins == 0:
        return
    wallet_id = ensure_wallet(conn, owner_type, owner_id)
    conn.execute(
        """INSERT INTO wallet_transactions (wallet_id, amount_qoins, reason, locked, related_user_id, cycle_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (wallet_id, amount_qoins, reason, 1 if locked else 0, related_user_id, cycle_middleware.get_active_cycle_id(conn)),
    )
    if not locked:
        conn.execute(
            "UPDATE wallets SET balance_qoins = balance_qoins + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (amount_qoins, wallet_id),
        )


# ---- Persisted, denominated Qoins (2026-10-17) ----------------------------------------------
# Everything above this point (balance_qoins as a plain integer, _credit() writing only a net
# wallet_transactions delta) is UNCHANGED and keeps working exactly as before -- balance_qoins
# remains the maintained cache every existing reader (dashboard, pipeline_core, the free-
# registration split) already relies on. What follows is additive: a `qoins` table of physical,
# denominated Qoins kept IN SYNC with that same cache, for callers (board_core's reward path)
# that need to reason about actual Qoins, not just a balance.
#
# Rebalancing is LAZY throughout (Decision 1, 2026-10-17): a wallet holds exactly the Qoins it
# was credited with. Qoins are only split or merged at the moment a specific operation (a debit
# that can't be made exactly from what's already held) needs it -- never automatically, and never
# just because a smaller representation would be possible. merge_qoins() exists as an explicit,
# separately-invoked operation for exactly that reason: consolidation is a choice, not a default.

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def public_wallet_view(conn, owner_type: str, owner_id: str) -> dict:
    """The ONLY thing a non-owner may ever be shown: how many physical Qoins a wallet holds.
    Never the rupee value -- that stays behind wallet_balance()/weekly_history(), which callers
    must gate to the owner, the collective wallet's own council members, or an admin (same
    pattern as reports_core.mask_identity()). A wallet with no qoins rows yet (nothing credited
    through the new path) correctly reports 0, independent of any legacy balance_qoins value."""
    row = conn.execute("SELECT id FROM wallets WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)).fetchone()
    if not row:
        return {"qoin_count": 0}
    count = conn.execute("SELECT COUNT(*) FROM qoins WHERE wallet_id = ?", (row["id"],)).fetchone()[0]
    return {"qoin_count": count}


def credit_qoins(conn, owner_type: str, owner_id: str, amount: int, reason: str,
                  rupee_value: int | None = None, related_post_id: int | None = None,
                  related_user_id: int | None = None) -> list[int]:
    """Credits `amount` Qoins to a wallet as a freshly-minted physical breakdown (via
    qoin_core.to_qoins), ADDED to whatever the wallet already holds -- lazy, no rebalance of
    existing rows. Also updates the balance_qoins cache and writes a wallet_transactions row
    carrying the originating rupee value and post, if any. Returns the denominations inserted."""
    import qoin_core
    if amount == 0:
        return []
    wallet_id = ensure_wallet(conn, owner_type, owner_id)
    now = _now_iso()
    denoms = qoin_core.to_qoins(amount)
    for d in denoms:
        conn.execute("INSERT INTO qoins (wallet_id, denomination, created_at) VALUES (?, ?, ?)", (wallet_id, d, now))
    conn.execute(
        """INSERT INTO wallet_transactions (wallet_id, amount_qoins, reason, locked, related_user_id, rupee_value, related_post_id, cycle_id)
           VALUES (?, ?, ?, 0, ?, ?, ?, ?)""",
        (wallet_id, amount, reason, related_user_id, rupee_value, related_post_id, cycle_middleware.get_active_cycle_id(conn)),
    )
    conn.execute(
        "UPDATE wallets SET balance_qoins = balance_qoins + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (amount, wallet_id),
    )
    return denoms


def debit_qoins(conn, owner_type: str, owner_id: str, amount: int, reason: str,
                 related_post_id: int | None = None, related_user_id: int | None = None) -> list[int]:
    """Removes `amount` worth of Qoins from a wallet. Lazy: first tries to assemble the exact
    amount from the wallet's EXISTING physical Qoins (greedy, largest-first over what's actually
    held) -- no rebalance at all if today's holdings already happen to cover it exactly. Only when
    that can't land on an exact match does it fall back to a full rebalance of THIS ONE wallet
    (delete everything, re-materialize the paid-out amount and the remainder separately via
    qoin_core.to_qoins) -- still "split only when required", just a coarser fallback than a
    minimal single-Qoin split, since nothing in this task exercises a real spend/debit path yet
    (no caller uses this function today -- it's provided for the next task that needs one).
    Returns the denominations removed (what was "paid")."""
    import qoin_core
    if amount == 0:
        return []
    wallet_id = ensure_wallet(conn, owner_type, owner_id)
    rows = conn.execute(
        "SELECT id, denomination FROM qoins WHERE wallet_id = ? ORDER BY denomination DESC", (wallet_id,)
    ).fetchall()
    total = sum(r["denomination"] for r in rows)
    if amount > total:
        raise ValueError("Not enough Qoins")

    remaining = amount
    to_remove_ids = []
    paid_denoms = []
    for r in rows:
        if r["denomination"] <= remaining:
            to_remove_ids.append(r["id"])
            paid_denoms.append(r["denomination"])
            remaining -= r["denomination"]
            if remaining == 0:
                break

    now = _now_iso()
    if remaining == 0:
        for qid in to_remove_ids:
            conn.execute("DELETE FROM qoins WHERE id = ?", (qid,))
    else:
        # Fallback: a full rebalance of this one wallet, triggered only because this specific
        # debit couldn't be made from what it already holds -- not a system-wide eager policy.
        conn.execute("DELETE FROM qoins WHERE wallet_id = ?", (wallet_id,))
        paid_denoms = qoin_core.to_qoins(amount)
        for d in qoin_core.to_qoins(total - amount):
            conn.execute("INSERT INTO qoins (wallet_id, denomination, created_at) VALUES (?, ?, ?)", (wallet_id, d, now))

    conn.execute(
        """INSERT INTO wallet_transactions (wallet_id, amount_qoins, reason, locked, related_user_id, related_post_id, cycle_id)
           VALUES (?, ?, ?, 0, ?, ?, ?)""",
        (wallet_id, -amount, reason, related_user_id, related_post_id, cycle_middleware.get_active_cycle_id(conn)),
    )
    conn.execute(
        "UPDATE wallets SET balance_qoins = balance_qoins - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (amount, wallet_id),
    )
    return paid_denoms


def split_qoin(conn, qoin_id: int) -> list[int]:
    """Explicit operation, never called automatically: breaks ONE physical Qoin into the fewest
    strictly-smaller Qoins of the same total value (e.g. a 500 -> 200+200+100). Used by
    debit_qoins()'s fallback path conceptually, but exposed here as its own callable operation
    too, per Decision 1 ("an explicit operation, not a default")."""
    import qoin_core
    row = conn.execute("SELECT wallet_id, denomination FROM qoins WHERE id = ?", (qoin_id,)).fetchone()
    if not row:
        raise LookupError("Qoin not found")
    smaller = tuple(d for d in qoin_core.DENOMINATIONS if d < row["denomination"])
    if not smaller:
        raise ValueError("This is already the smallest denomination -- nothing to split it into")
    pieces = qoin_core.to_qoins(row["denomination"], denominations=smaller)
    now = _now_iso()
    conn.execute("DELETE FROM qoins WHERE id = ?", (qoin_id,))
    for d in pieces:
        conn.execute("INSERT INTO qoins (wallet_id, denomination, created_at) VALUES (?, ?, ?)", (row["wallet_id"], d, now))
    return pieces


def merge_qoins(conn, owner_type: str, owner_id: str) -> list[int]:
    """Explicit operation, never called automatically (Decision 1): rebalances a wallet's entire
    physical Qoin set into the fewest possible Qoins representing the same total, via
    qoin_core.to_qoins(). Only runs when something deliberately asks a wallet to consolidate --
    credit_qoins()/debit_qoins() never call this themselves."""
    import qoin_core
    wallet_id = ensure_wallet(conn, owner_type, owner_id)
    rows = conn.execute("SELECT denomination FROM qoins WHERE wallet_id = ?", (wallet_id,)).fetchall()
    total = sum(r["denomination"] for r in rows)
    conn.execute("DELETE FROM qoins WHERE wallet_id = ?", (wallet_id,))
    now = _now_iso()
    denoms = qoin_core.to_qoins(total)
    for d in denoms:
        conn.execute("INSERT INTO qoins (wallet_id, denomination, created_at) VALUES (?, ?, ?)", (wallet_id, d, now))
    return denoms


def has_locked_share(conn, user_id: int) -> bool:
    row = conn.execute(
        """SELECT 1 FROM wallet_transactions wt
           JOIN wallets w ON w.id = wt.wallet_id
           WHERE w.owner_type = 'user' AND w.owner_id = ? AND wt.locked = 1
           LIMIT 1""",
        (str(user_id),),
    ).fetchone()
    return bool(row)


def unlock_user_share(conn, user_id: int) -> int:
    """Applies every locked wallet_transactions row for this user's wallet
    to their balance, and flips them unlocked. Returns the total unlocked.
    Idempotent — a user with nothing locked just gets 0 back."""
    wallet_id = ensure_wallet(conn, "user", str(user_id))
    rows = conn.execute(
        "SELECT id, amount_qoins FROM wallet_transactions WHERE wallet_id = ? AND locked = 1",
        (wallet_id,),
    ).fetchall()
    if not rows:
        return 0
    total = sum(r["amount_qoins"] for r in rows)
    conn.execute(
        "UPDATE wallet_transactions SET locked = 0 WHERE wallet_id = ? AND locked = 1", (wallet_id,)
    )
    conn.execute(
        "UPDATE wallets SET balance_qoins = balance_qoins + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (total, wallet_id),
    )
    conn.commit()
    return total


# ---- Weekly transaction history (private wallets and every location wallet) ----
# The Monday-00:00 boundary matches the founder's own spec ("updates when Sunday ends and Monday
# begins"); ISO weeks already start on Monday, so grouping by isocalendar() week gives that for free.
HISTORY_MONTHS = 3


def _week_key(created_at: str) -> tuple[int, int]:
    d = dt.datetime.fromisoformat(created_at.replace(" ", "T")).date()
    iso = d.isocalendar()
    return iso[0], iso[1]


def _week_range(year: int, week: int) -> tuple[dt.date, dt.date]:
    monday = dt.date.fromisocalendar(year, week, 1)
    return monday, monday + dt.timedelta(days=6)


def weekly_history(conn, owner_type: str, owner_id: str, include_older: bool = False) -> dict:
    """Every unlocked transaction, grouped into ISO weeks (Monday-Sunday), newest first.
    Only the last HISTORY_MONTHS are returned unless `include_older` (council members only, per spec)."""
    wallet = conn.execute("SELECT id FROM wallets WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)).fetchone()
    if not wallet:
        return {"balance_qoins": 0, "weeks": [], "older_weeks_hidden": 0}
    rows = conn.execute(
        "SELECT amount_qoins, reason, created_at FROM wallet_transactions WHERE wallet_id = ? AND locked = 0 ORDER BY created_at DESC",
        (wallet["id"],),
    ).fetchall()
    cutoff = dt.date.today() - dt.timedelta(days=30 * HISTORY_MONTHS)
    weeks: dict[tuple[int, int], dict] = {}
    older_weeks = set()
    for r in rows:
        key = _week_key(r["created_at"])
        start, end = _week_range(*key)
        if end < cutoff and not include_older:
            older_weeks.add(key)
            continue
        wk = weeks.setdefault(key, {"year": key[0], "week": key[1], "start": start.isoformat(), "end": end.isoformat(), "rows": [], "change": 0})
        wk["rows"].append({"amount": r["amount_qoins"], "reason": r["reason"], "at": r["created_at"]})
        wk["change"] += r["amount_qoins"]
    ordered = sorted(weeks.values(), key=lambda w: (w["year"], w["week"]), reverse=True)
    return {"balance_qoins": wallet_balance(conn, owner_type, owner_id), "weeks": ordered, "older_weeks_hidden": len(older_weeks)}


# ---- Referral volume bonus (2026-10-25) ----
# One-time Qoins for a referrer who crosses a threshold of free-registration referrals in a
# single ISO week -- on top of the 10 paise `apply_free_registration` already credits per
# referral, never a replacement for it. (threshold, Qoins) pairs; the highest threshold reached
# wins each time this is checked. Approved by the founder as-is -- not meant to be tuned casually.
BONUS_TIERS = ((3, 1), (7, 3), (15, 7))


def check_and_award_bonus(conn, referrer_user_id: int | None) -> int | None:
    """Call once per registration that named a referrer, right after `apply_free_registration`.
    Counts how many users this referrer referred in the current ISO week and, if a new
    BONUS_TIERS threshold has just been reached, mints that tier's bonus once.
    Safe to call every time a referral lands in the same week -- `referral_bonus_awards`'
    UNIQUE(referrer_user_id, period_type, period_key, tier) makes a repeat award a no-op, not a
    double mint. Returns the tier number (1-based) just awarded, or None if nothing was awarded
    (no referrer, no wallet yet, below the lowest threshold, or this tier was already awarded)."""
    if referrer_user_id is None:
        return None
    # UTC, not local dt.date.today() -- users.created_at is stored via SQLite's CURRENT_TIMESTAMP
    # (UTC). Near UTC midnight (~5:30am IST) local-today and the stored date disagree, so a
    # local-today boundary here would miscount referrals right at the week edge.
    iso_year, iso_week, _ = dt.datetime.now(dt.timezone.utc).date().isocalendar()
    period_key = f"{iso_year}-W{iso_week:02d}"
    monday, sunday = _week_range(iso_year, iso_week)
    # Counts users.referred_by_user_id directly (each referred member's OWN registration
    # timestamp), not wallet_transactions -- a single 10-paisa referral credit is sub-rupee and
    # often never reaches wallet_transactions at all (it only lands there once paisa_balance
    # rolls over 100), so it's not a reliable per-referral signal to count.
    count = conn.execute(
        """SELECT COUNT(*) FROM users
           WHERE referred_by_user_id = ? AND date(created_at) BETWEEN date(?) AND date(?)""",
        (referrer_user_id, monday.isoformat(), sunday.isoformat()),
    ).fetchone()[0]
    tier = None
    for i, (threshold, _) in enumerate(BONUS_TIERS, start=1):
        if count >= threshold:
            tier = i
    if tier is None:
        return None
    qoins_awarded = BONUS_TIERS[tier - 1][1]
    try:
        conn.execute(
            """INSERT INTO referral_bonus_awards
               (referrer_user_id, period_type, period_key, tier, qoins_awarded, cycle_id)
               VALUES (?, 'week', ?, ?, ?, ?)""",
            (referrer_user_id, period_key, tier, qoins_awarded, cycle_middleware.get_active_cycle_id(conn)),
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        return None  # this tier was already awarded for this referrer this week
    _credit(conn, "user", str(referrer_user_id), qoins_awarded, "referral_volume_bonus")
    conn.commit()
    return tier
