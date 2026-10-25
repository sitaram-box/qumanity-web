"""Verifies the Referral & Qoin Engine (2026-10-25): the "Referred By (Public ID)" field on the
ordinary registration form, and the weekly referral-volume bonus.

Covers:
  - api_auth_register resolves `referred_by_public_id` (a 12-digit account_ids.search_code) to a
    referrer_user_id when present and valid, feeding the EXISTING, UNCHANGED
    wallet_core.apply_free_registration() split (80% location / 10% referrer / 10% new user).
  - A blank or unrecognized Public ID is never an error -- the new user gets the full 20 paise
    (10 location-referrer-fold-in + 10 own), exactly as when there is no referrer today.
  - wallet_core.check_and_award_bonus(): 3 referrals to the same referrer in the same ISO week
    awards tier 1 (+1 Qoin) exactly once, via the referral_bonus_awards table.

Standalone script, no test framework (none installed in this project), PASS/FAIL printing, exit 1
on failure -- same pattern as every other tests/test_*.py file in this project.

Run with: python3 tests/test_referral_engine.py (not -I -- isolated mode hides this machine's
Flask install).
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import wallet_core  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

VILLAGE_A = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def register(name_prefix, referred_by_public_id=""):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A, "present_location": VILLAGE_A, "assisted": False,
        "referred_by_public_id": referred_by_public_id,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def search_code_for(user_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT search_code FROM account_ids WHERE user_id = ? AND is_current = 1", (user_id,)).fetchone()
    conn.close()
    return row["search_code"]


def paisa_balance(owner_type, owner_id):
    conn = dbmod.get_db()
    row = conn.execute("SELECT paisa_balance FROM wallets WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id)).fetchone()
    conn.close()
    return row["paisa_balance"] if row else 0


print("=" * 70)
print("1. Registration with a valid referrer Public ID")
print("=" * 70)

referrer = register("Referrer One")
referrer_code = search_code_for(referrer["user_id"])

new_user = register("Referred User", referred_by_public_id=referrer_code)

conn = dbmod.get_db()
row = conn.execute("SELECT referred_by_user_id FROM users WHERE id = ?", (new_user["user_id"],)).fetchone()
conn.close()
check("the new user's referred_by_user_id was set to the resolved referrer", row["referred_by_user_id"] == referrer["user_id"])
# The referrer's own wallet already holds 20 paisa from ITS OWN registration (no referrer of its
# own, so its self-share folded in) -- the referral credit adds another 10 on top of that.
check("the referrer's wallet was credited another 10 paise (free_registration_referrer)", paisa_balance("user", str(referrer["user_id"])) == 30)
check("the new user's own wallet got the plain 10 paise (not the 20-paise no-referrer fold-in)", paisa_balance("user", str(new_user["user_id"])) == 10)

print()
print("=" * 70)
print("2. Registration with no referrer (blank or unrecognized Public ID)")
print("=" * 70)

solo_blank = register("Solo Blank", referred_by_public_id="")
conn = dbmod.get_db()
row = conn.execute("SELECT referred_by_user_id FROM users WHERE id = ?", (solo_blank["user_id"],)).fetchone()
conn.close()
check("a blank Public ID leaves referred_by_user_id NULL", row["referred_by_user_id"] is None)
check("the new user's own wallet got the full 20 paise (10 self + the folded-in referrer share)", paisa_balance("user", str(solo_blank["user_id"])) == 20)

solo_bad = register("Solo Bad Code", referred_by_public_id="000000000000")
conn = dbmod.get_db()
row = conn.execute("SELECT referred_by_user_id FROM users WHERE id = ?", (solo_bad["user_id"],)).fetchone()
conn.close()
check("an unrecognized 12-digit Public ID is silently ignored, not an error", row["referred_by_user_id"] is None)
check("...and still gets the full 20 paise", paisa_balance("user", str(solo_bad["user_id"])) == 20)

print()
print("=" * 70)
print("3. Weekly referral-volume bonus (wallet_core.check_and_award_bonus)")
print("=" * 70)

bonus_referrer = register("Bonus Referrer")
bonus_code = search_code_for(bonus_referrer["user_id"])

register("Bonus Target", referred_by_public_id=bonus_code)
register("Bonus Target", referred_by_public_id=bonus_code)
check("balance is still 0 Qoins after 2 referrals (below the 3-referral tier)",
      wallet_core.wallet_balance(dbmod.get_db(), "user", str(bonus_referrer["user_id"])) == 0)

register("Bonus Target", referred_by_public_id=bonus_code)
check("tier-1 bonus (+1 Qoin) landed after the 3rd referral this week",
      wallet_core.wallet_balance(dbmod.get_db(), "user", str(bonus_referrer["user_id"])) == 1)

conn = dbmod.get_db()
award_rows = conn.execute(
    "SELECT tier, qoins_awarded FROM referral_bonus_awards WHERE referrer_user_id = ?", (bonus_referrer["user_id"],)
).fetchall()
conn.close()
check("exactly one referral_bonus_awards row exists for this referrer this week", len(award_rows) == 1)
check("it's tier 1, awarding 1 Qoin", award_rows[0]["tier"] == 1 and award_rows[0]["qoins_awarded"] == 1)

# A 4th referral (still below tier 2's threshold of 7) must not re-award tier 1.
register("Bonus Target", referred_by_public_id=bonus_code)
check("a 4th referral (still below tier 2) does not re-award tier 1",
      wallet_core.wallet_balance(dbmod.get_db(), "user", str(bonus_referrer["user_id"])) == 1)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
