"""Adds the referral_bonus_awards table (2026-10-25): a one-time volume bonus for a referrer who
crosses 3/7/15 referrals in a single ISO week (see wallet_core.check_and_award_bonus()). The
UNIQUE constraint is the actual idempotency guard -- a given (referrer, period, tier) can only be
inserted once, so the award check is safe to run on every qualifying registration without a
separate "already awarded this one" lookup race.
"""
from __future__ import annotations


def run(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS referral_bonus_awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_user_id INTEGER NOT NULL,
            period_type TEXT NOT NULL,   -- 'week' today; 'month' left room for later
            period_key TEXT NOT NULL,    -- e.g. '2026-W43'
            tier INTEGER NOT NULL,       -- 1, 2, 3 -- index into wallet_core.BONUS_TIERS
            qoins_awarded INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cycle_id INTEGER,
            UNIQUE (referrer_user_id, period_type, period_key, tier),
            FOREIGN KEY (referrer_user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    print("    referral_bonus_awards ready.")
