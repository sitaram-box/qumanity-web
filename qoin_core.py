"""Qoin denominations, currencies, top-up splits, post rewards and post prices (pure functions, no DB).

Spec: docs/qoins_wallet_system.md (same file in Qumanity_App/docs). Amounts are whole numbers of the local
currency; a Qoin is worth one of DENOMINATIONS only. A wallet stores an amount and shows it as the fewest Qoins
(highest first), so 289 -> 200+50+20+10+5+2+2.
"""
from __future__ import annotations

DENOMINATIONS = (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000)
MAX_DONATION = 200
LEVELS = ("village", "tehsil", "district", "state", "zone", "country", "continent", "earth")

# country code (as in the location data) -> (ISO currency, symbol, name)
CURRENCY = {
    "IND": ("INR", "₹", "Indian Rupee"), "NPL": ("NPR", "Rs", "Nepalese Rupee"), "BGD": ("BDT", "৳", "Bangladeshi Taka"),
    "LKA": ("LKR", "Rs", "Sri Lankan Rupee"), "PAK": ("PKR", "Rs", "Pakistani Rupee"), "BAL": ("PKR", "Rs", "Pakistani Rupee"),
    "BLC": ("PKR", "Rs", "Pakistani Rupee"), "BTN": ("BTN", "Nu.", "Bhutanese Ngultrum"), "MDV": ("MVR", "Rf", "Maldivian Rufiyaa"),
    "AFG": ("AFN", "؋", "Afghan Afghani"), "MMR": ("MMK", "K", "Burmese Kyat"),
}
DEFAULT_CURRENCY = ("INR", "₹", "Indian Rupee")


def currency_for(country_code: str):
    return CURRENCY.get((country_code or "").upper(), DEFAULT_CURRENCY)


def to_qoins(amount: int, denominations: tuple[int, ...] | None = None) -> list[int]:
    """Fewest Qoins, highest first. 289 -> [200, 50, 20, 10, 5, 2, 2]. `denominations` lets a
    caller restrict the candidate set (wallet_core.split_qoin() breaks one Qoin into strictly
    smaller pieces by passing only the denominations below it) -- defaults to the full canonical
    list. Defensive: asserts the result actually sums back to the input, since a restricted or
    future non-canonical denomination set could in principle leave a remainder the greedy pass
    can't close (the full DENOMINATIONS list never does, by construction)."""
    amount = int(amount)
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    candidates = denominations if denominations is not None else DENOMINATIONS
    out = []
    remaining = amount
    for d in sorted(candidates, reverse=True):
        while remaining >= d:
            out.append(d)
            remaining -= d
    if sum(out) != amount:
        raise ValueError(f"to_qoins({amount}) could not represent the full amount with {candidates} -- got {out} (sums to {sum(out)})")
    return out


def describe(amount: int, symbol: str = "₹") -> str:
    q = to_qoins(amount)
    return f"{len(q)} Qoin{'s' if len(q) != 1 else ''} ({' + '.join(map(str, q))} = {symbol}{amount})" if q else f"0 Qoins ({symbol}0)"


# Independent visitor tops up (no referrer): amount -> (own wallet, own village wallet). Exactly as in the spec.
TOPUP_SPLIT = {1: (1, 0), 2: (1, 1), 5: (3, 2), 10: (6, 4), 20: (12, 8), 50: (34, 16), 100: (68, 32), 200: (136, 64), 500: (372, 128)}


def topup_split(amount: int) -> dict:
    """Split a top-up between the user's wallet and their village wallet (60/40 for amounts not in the table)."""
    amount = int(amount)
    if amount < 1:
        raise ValueError("Top-up must be at least 1")
    own, village = TOPUP_SPLIT.get(amount, (round(amount * 0.6), amount - round(amount * 0.6)))
    return {"own": own, "village": village, "own_qoins": to_qoins(own), "village_qoins": to_qoins(village)}


# Rupee reward range per level (2026-10-17 design): every positive-score post at a level, in a
# given lunar cycle, is ranked against its peers at that same (level, cycle) and paid somewhere in
# this range. The top tier (top_tier_count(n) posts, below) always earns the maximum; every rank
# after that scales down linearly to the minimum, which only the single lowest-ranked positive
# post actually receives. This REPLACES the old flat per-level FREEZE_REWARD/EARTH_WINNER/
# EARTH_PARTICIPANT scheme (score-blind, and Earth's old winner-takes-500/participant-gets-200
# special case) -- Earth is no longer special-cased; it just has the highest range, like every
# other level.
REWARD_RANGE_INR = {
    "village": (1, 10), "tehsil": (10, 50), "district": (50, 100), "state": (100, 250),
    "zone": (250, 500), "country": (500, 1000), "continent": (1000, 1500), "earth": (1500, 2000),
}


def top_tier_count(n: int) -> int:
    """How many of the `n` positive posts at a (level, cycle) earn the maximum reward (2026-10-17
    variable top-tier rule, replacing an earlier fixed top-5). Flat at 1 for n <= 10. Above that,
    divide by the largest power of ten strictly below n: the top tier grows from 1 up to 10 as n
    climbs through a decade (11..100, 101..1000, ...), then resets to 1 the moment n crosses the
    next power of ten -- a sawtooth, by design, not a bug: 99 -> 9, 100 -> 10, 101 -> 1."""
    if n <= 10:
        return 1
    divisor = 1
    while divisor * 10 < n:
        divisor *= 10
    return n // divisor


def rank_reward_inr(rank: int, n: int, level: str) -> int:
    """The rupee reward for the `rank`-th positive post (1 = highest score) out of `n` positive
    posts settling at `level` in the same lunar cycle. The top `top_tier_count(n)` posts all earn
    the level's maximum; every rank after that is spread linearly down to the minimum, which only
    rank `n` (the single lowest-scoring positive post) receives exactly -- rank (k+1), the first
    one below the top tier, is deliberately NOT pinned to the max; it starts the gradient one
    step down. Computed with exact integer arithmetic throughout (never floats), floored: e.g. a
    3-way split of Village's [1, 10] floors its middle value to 5, not a rounded-up 6."""
    if not 1 <= rank <= n:
        raise ValueError(f"rank {rank} out of range for n={n}")
    min_inr, max_inr = REWARD_RANGE_INR[level]
    k = top_tier_count(n)
    if rank <= k:
        return max_inr
    position = rank - k            # 1..(n-k)
    remaining = n - k
    numerator = min_inr * remaining + (remaining - position) * (max_inr - min_inr)
    return numerator // remaining


# ---- what a post costs ----
VILLAGE_PRICES = {"text": 0, "image": 1, "audio": {1: 2, 3: 5, 5: 10}, "video": {1: 20, 3: 50, 5: 100}}
PAID_PRICES = {  # level -> kind -> price or {minutes: price}
    "tehsil":   {"text": 100,  "image": 200,  "audio": {1: 500, 3: 700, 5: 1000},    "video": {1: 700, 3: 1000, 5: 2000}},
    "district": {"text": 200,  "image": 500,  "audio": {1: 700, 3: 1000, 5: 1500},   "video": {1: 1000, 3: 1500, 5: 2000}},
    "state":    {"text": 500,  "image": 700,  "audio": {1: 1000, 3: 1500, 5: 2000},  "video": {1: 5000, 3: 7000, 5: 10000}},
    "zone":     {"text": 1000, "image": 2000, "audio": {1: 5000, 3: 7000, 5: 10000}, "video": {1: 20000, 3: 50000, 5: 100000}},
}
MAX_TEXT_CHARS = 1000


def post_price(level: str, kind: str, minutes: int | None = None) -> int:
    """Cost (in local currency, paid from the poster's Qoins) to post `kind` at `level`. Country..Earth cannot be posted to."""
    table = VILLAGE_PRICES if level == "village" else PAID_PRICES.get(level)
    if table is None:
        raise ValueError("Posts cannot be made on this page")
    if kind not in table:
        raise ValueError("Unknown post type")
    price = table[kind]
    if isinstance(price, dict):
        if minutes not in price:
            raise ValueError("Choose 1, 3 or 5 minutes")
        return price[minutes]
    return price


def debit_plan(balance_qoins: list[int], cost: int):
    """Pay `cost` from a wallet's Qoins: spend the smallest set that covers it, returning (spent, change_qoins).
    Change is re-issued as new Qoins, so the wallet total always drops by exactly `cost`."""
    total = sum(balance_qoins)
    if cost > total:
        raise ValueError("Not enough Qoins")
    remaining = total - cost
    return {"before": to_qoins(total), "after": to_qoins(remaining), "cost": cost, "remaining": remaining}
