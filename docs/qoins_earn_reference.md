# Qoins: how they are earned (reference, 2026-10)

Qoins are the internal currency of Qumanity. They are **earned through civic activity, never
purchased**. There is no payment processor in the platform, no real money changes hands, and no
card, UPI or other financial data is collected.

This file replaces the old `docs/donation_distribution.md` and `docs/qoins_payment_2026_10.md`,
which described a Razorpay donation flow that was removed in October 2026.

## How Qoins are earned

| Activity | Status in the code | Where |
|---|---|---|
| **Post elevation rewards** | Live. A post that freezes with a positive score pays its author by the level it reached: Village 1, Tehsil 2, District 5, State 10, Zone 20, Country 50, Continent 100. At Earth, the top post wins 500 and every other positive post gets 100 + 100. | `qoin_core.FREEZE_REWARD`, `qoin_core.post_reward`, `board_core._reward_author` |
| **Voting participation** | Live. A new member's welcome share is held locked until they cast their first election vote, which unlocks it into their wallet. | `wallet_core.unlock_user_share`, called from `election_core` |
| **Joining (free registration)** | Live. Every new account mints one ₹1-reference Qoin, shared 10 paise each to the eight location tiers (Earth to Village), the member who registered them (if any) and the new member. | `wallet_core.apply_free_registration` |
| **Karma actions** (teaching, planting, volunteering) | Karma is recorded today. Converting karma into Qoins is planned and not yet computed. | `karma_core` (see its module note) |
| **Community service** | Planned, alongside karma. | — |

Qoins are spent inside the platform only, for example to post above Village level
(`qoin_core.post_price`).

## Rupee reference value (display only)

Each Qoin carries a reference value in the member's local currency (for India, rupees), so people
can understand what their civic contribution is worth: for example "1 Qoin = ₹1" in the wallet, or
"₹500" for the Earth post winner. Wallets show an amount as the fewest Qoin denominations
(1, 2, 5, 10, 20, 50, 100, 200, 500). The conversion tables live in `qoin_core.py`
(`DENOMINATIONS`, `CURRENCY`, `to_qoins`, `describe`).

This value is informational arithmetic. No currency is bought, sold or exchanged, and nothing is
paid in or out.

## Out of scope

Exchanging Qoins for real currency is out of scope for this prototype. If it is ever added, it will
need its own design, privacy and legal review.
