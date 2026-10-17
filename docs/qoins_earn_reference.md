# Qoins: how they are earned (reference, 2026-10)

Qoins are the internal currency of Qumanity. They are **earned through civic activity, never
purchased**. There is no payment processor in the platform, no real money changes hands, and no
card, UPI or other financial data is collected.

This file replaces the old `docs/donation_distribution.md` and `docs/qoins_payment_2026_10.md`,
which described a Razorpay donation flow that was removed in October 2026.

## How Qoins are earned

| Activity | Status in the code | Where |
|---|---|---|
| **Post elevation rewards** | Live. A post that freezes with a positive score pays its author a rank-based rupee reward for the level it reached — see "How rewards are calculated now" below. | `board_core.settle`, `qoin_core.rank_reward_inr`, `wallet_core.credit_qoins` |
| **Voting participation** | Live. A new member's welcome share is held locked until they cast their first election vote, which unlocks it into their wallet. | `wallet_core.unlock_user_share`, called from `election_core` |
| **Joining (free registration)** | Live. Every new account mints one ₹1-reference Qoin, shared 10 paise each to the eight location tiers (Earth to Village), the member who registered them (if any) and the new member. | `wallet_core.apply_free_registration` |
| **Karma actions** (teaching, planting, volunteering) | Karma is recorded today. Converting karma into Qoins is planned and not yet computed. | `karma_core` (see its module note) |
| **Community service** | Planned, alongside karma. | — |

Qoins are spent inside the platform only, for example to post above Village level
(`qoin_core.post_price`).

## How rewards are calculated now

When a lunar cycle's voting window closes, `board_core.settle()` ranks every post at each
(level, cycle) that froze with a positive score, best first, and pays each one a rupee reward
for its rank via `qoin_core.rank_reward_inr(rank, n, level)`:

- **Rupee range per level** — `qoin_core.REWARD_RANGE_INR`:

  | Level | Range |
  |---|---|
  | Village | ₹1 – ₹10 |
  | Tehsil | ₹10 – ₹50 |
  | District | ₹50 – ₹100 |
  | State | ₹100 – ₹250 |
  | Zone | ₹250 – ₹500 |
  | Country | ₹500 – ₹1,000 |
  | Continent | ₹1,000 – ₹1,500 |
  | Earth | ₹1,500 – ₹2,000 |

  Earth is not special-cased any more — it is simply the level with the highest range, like
  every other level.

- **A variable top tier earns the level's maximum, not a fixed top 5.** `qoin_core.top_tier_count(n)`
  decides how many of the `n` positive posts earn the max: flat at 1 post when `n ≤ 10`; above
  that, it grows from 1 up to 10 as `n` climbs through a decade (11–100, 101–1,000, …), then
  resets to 1 the moment `n` crosses the next power of ten. This replaced an earlier fixed
  top-5 rule.
- **Every rank below the top tier is spread linearly down to the level's minimum**, computed
  with exact integer arithmetic (floored, never rounded). Only the single lowest-ranked positive
  post receives exactly the minimum.
- **The rupee reward is converted to Qoins** via `qoin_core.to_qoins()` and credited to the
  author's wallet by `wallet_core.credit_qoins()`, which also records a `recognition_stars` row
  for the post — a permanent record of the recognition, independent of the post's own lifecycle.
- **Test posts are not credited.** A post with `post_kind = 'test'` still has its reward computed
  and stored (`board_posts.test_reward_inr`), so the Post Testing cycle can verify the formula,
  but `settle()` never calls `credit_qoins` for it — no wallet, karma or recognition star is
  ever touched by a test post.
- **Test posts share the same ranking pool as real posts.** `settle()` ranks every positive post
  due at a (level, cycle) together, regardless of `post_kind` — a test post occupies a rank and
  counts toward `n` exactly like a real one, so it can affect a real post's rank-based reward
  amount. Only the crediting step is skipped for it (above). Demo users are excluded from the
  public-facing member counts this file's earlier sections describe (`is_demo=0 AND
  is_removed=0`), but that filter does not reach into `settle()`'s own ranking.

## Rupee reference value (display only)

Each Qoin carries a reference value in the member's local currency (for India, rupees), so people
can understand what their civic contribution is worth: for example "1 Qoin = ₹1" in the wallet, or
"₹2,000" for an Earth-level rank-1 reward. Wallets show an amount as the fewest Qoin denominations
(1, 2, 5, 10, 20, 50, 100, 200, 500, 1,000, 2,000). The conversion tables live in `qoin_core.py`
(`DENOMINATIONS`, `CURRENCY`, `to_qoins`, `describe`).

This value is informational arithmetic. No currency is bought, sold or exchanged, and nothing is
paid in or out.

---

This file describes the current system. For the design history, see
[docs/test_cycle_design.md](test_cycle_design.md).

## Out of scope

Exchanging Qoins for real currency is out of scope for this prototype. If it is ever added, it will
need its own design, privacy and legal review.
