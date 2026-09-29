"""Qoin denominations, currencies, top-up splits, post rewards and post prices (pure functions, no DB).

Spec: docs/qoins_wallet_system.md (same file in Qumanity_App/docs). Amounts are whole numbers of the local
currency; a Qoin is worth one of DENOMINATIONS only. A wallet stores an amount and shows it as the fewest Qoins
(highest first), so 289 -> 200+50+20+10+5+2+2.
"""
from __future__ import annotations

DENOMINATIONS = (1, 2, 5, 10, 20, 50, 100, 200, 500)
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


def to_qoins(amount: int) -> list[int]:
    """Fewest Qoins, highest first. 289 -> [200, 50, 20, 10, 5, 2, 2]."""
    amount = int(amount)
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    out = []
    for d in sorted(DENOMINATIONS, reverse=True):
        while amount >= d:
            out.append(d)
            amount -= d
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


# Reward when a positive-score post freezes at a level (value of the Qoin(s) credited to the author).
FREEZE_REWARD = {"village": 1, "tehsil": 2, "district": 5, "state": 10, "zone": 20, "country": 50, "continent": 100}
EARTH_WINNER = 500
EARTH_PARTICIPANT = (100, 100)


def post_reward(freeze_level: str, score: int, earth_winner: bool = False) -> list[int]:
    """Qoin values credited to the author. Score <= 0 -> nothing (the post is removed to the author's Private timeline)."""
    if score <= 0:
        return []
    if freeze_level == "earth":
        return [EARTH_WINNER] if earth_winner else list(EARTH_PARTICIPANT)
    return [FREEZE_REWARD[freeze_level]]


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
