"""Karma Qoins wallets — one per user, and one per location at every tier
from Earth down to Village (see location_elements/elemental_core.py for the
same (location_id, location_type) convention this reuses).

Simplification vs. the old Qumanity prototype: 1 Qoin = ₹1 flat, stored as a
plain integer balance. The old prototype broke every wallet into an
encrypted list of denominated "coins" (₹2000/500/.../1); nothing in this
pass's scope needs that, so it's deliberately not carried over.

Donation-split rules are ported from the product notes (Qbox-Notes.txt,
"Please write cursor prompt to edit the logic of referrals system and qoins
distribution", ~lines 3340-3398), simplified to whole-Qoin arithmetic:

- With a referrer: up to ₹10, split 40/60 self/referrer (the notes' own
  ₹1/₹2 examples used 50/50 and its ₹5/₹10 examples used 60/40 — genuinely
  inconsistent in the source; 60/40 is applied uniformly above ₹2 since
  that's what most of the worked examples show). From ₹11 up, a per-tier
  amount (₹1/₹2/₹5/₹10 depending on the bracket) is credited to EACH of the
  8 location tiers first, then the remainder splits 60/40 self/referrer.
  Donations are capped at ₹200 per the notes ("maximum amount of donation
  is 200 only per member").
- Without a referrer: 80% of the amount splits evenly across the 8 location
  tiers, the remaining 20% goes to the donor's own (locked) share.

In both cases the donor's own share is credited as *locked* — held out of
their wallet balance until they cast their first election vote (see
`unlock_user_share`, called from election_core.cast_vote), matching the
notes: "the amount credit for new user-B only after completing first Karma
Action... the moment new user participate in election... Voting first time
will activate reward qoins."
"""

from __future__ import annotations

import datetime as dt

import elemental_core

LOCATION_TIERS = ("earth", "continent", "country", "zone", "state", "district", "tehsil", "village")

MAX_DONATION_RUPEES = 200


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
        """INSERT INTO wallet_transactions (wallet_id, amount_qoins, reason, locked, related_user_id)
           VALUES (?, ?, ?, ?, ?)""",
        (wallet_id, amount_qoins, reason, 1 if locked else 0, related_user_id),
    )
    if not locked:
        conn.execute(
            "UPDATE wallets SET balance_qoins = balance_qoins + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (amount_qoins, wallet_id),
        )


def calculate_donation_distribution(amount_rupees: int, has_referrer: bool) -> dict:
    """Returns {"location_share_per_tier", "self_share", "referrer_share"} —
    all non-negative ints, and location_share_per_tier * 8 + self_share +
    referrer_share == amount_rupees exactly (any rounding remainder from the
    60/40 or 80/20 split is folded into self_share)."""
    if amount_rupees <= 0 or amount_rupees > MAX_DONATION_RUPEES:
        raise ValueError(f"Donation must be between ₹1 and ₹{MAX_DONATION_RUPEES}")

    if not has_referrer:
        location_total = round(amount_rupees * 0.8)
        per_tier = location_total // 8
        self_share = amount_rupees - per_tier * 8
        return {"location_share_per_tier": per_tier, "self_share": self_share, "referrer_share": 0}

    if amount_rupees <= 2:
        referrer_share = amount_rupees // 2
        return {"location_share_per_tier": 0, "self_share": amount_rupees - referrer_share, "referrer_share": referrer_share}
    if amount_rupees <= 10:
        referrer_share = round(amount_rupees * 0.6)
        return {"location_share_per_tier": 0, "self_share": amount_rupees - referrer_share, "referrer_share": referrer_share}

    if amount_rupees <= 20:
        per_tier = 1
    elif amount_rupees <= 50:
        per_tier = 2
    elif amount_rupees <= 100:
        per_tier = 5
    else:
        per_tier = 10
    remainder = amount_rupees - per_tier * 8
    referrer_share = round(remainder * 0.6)
    self_share = remainder - referrer_share
    return {"location_share_per_tier": per_tier, "self_share": self_share, "referrer_share": referrer_share}


def apply_donation(conn, user_id: int, present_location: dict, amount_rupees: int,
                    referrer_user_id: int | None) -> dict:
    """Credits the split from calculate_donation_distribution to the donor's
    (locked) wallet, the referrer's wallet (if any), and every location tier
    from Earth down to wherever present_location reaches. Returns the
    breakdown for the confirmation UI."""
    has_referrer = referrer_user_id is not None
    split = calculate_donation_distribution(amount_rupees, has_referrer)

    _credit(conn, "user", str(user_id), split["self_share"], "donation_self",
            locked=True, related_user_id=user_id)

    if has_referrer and split["referrer_share"]:
        _credit(conn, "user", str(referrer_user_id), split["referrer_share"], "donation_referrer",
                related_user_id=user_id)

    if split["location_share_per_tier"]:
        for location_id, location_type in elemental_core.location_levels_for(present_location):
            _credit(conn, location_type, location_id, split["location_share_per_tier"], "donation_location",
                    related_user_id=user_id)

    conn.commit()
    return split


def apply_registration_donation(conn, user_id: int, present_location: dict, amount_rupees: int, referrer_user_id: int | None) -> dict:
    """The registration-time donation, in the three shapes the founder confirmed (2026-09-27):
      - ₹0 (free): 1 Qoin split 10 paise to each of 10 shares (apply_free_registration).
      - with a referrer: the bracket table (calculate_donation_distribution / apply_donation) --
        per-tier location shares (₹0 below ₹11) + referrer + self.
      - no referrer, donation > 0 (an independent visitor topping up their own new wallet): the
        qoin_core "own wallet / own village wallet" table -- no other location tiers, no referrer.
    Returns a breakdown dict shaped for the registration confirmation screen."""
    import qoin_core
    if amount_rupees <= 0:
        apply_free_registration(conn, user_id, present_location, referrer_user_id)
        return {"kind": "free", "location_share_per_tier": 0, "self_share": 0, "referrer_share": 0}
    if referrer_user_id is not None:
        split = apply_donation(conn, user_id, present_location, amount_rupees, referrer_user_id)
        return {"kind": "referred", **split}
    topup = qoin_core.topup_split(amount_rupees)
    _credit(conn, "user", str(user_id), topup["own"], "registration_topup_self", locked=True, related_user_id=user_id)
    village = (present_location.get("village") or {})
    if village.get("id") and topup["village"]:
        _credit(conn, "village", village["id"], topup["village"], "registration_topup_village", related_user_id=user_id)
    conn.commit()
    return {"kind": "independent", "self_share": topup["own"], "village_share": topup["village"], "referrer_share": 0}


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
