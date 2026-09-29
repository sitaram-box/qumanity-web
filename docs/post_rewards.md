# Rewards for posts

Posts are made in the **Village**. When a post finishes voting with a **positive score** and freezes, the author's **private wallet** is credited by the highest level the post reached ([voting_logic.md](voting_logic.md)):

| Post froze at | Reward (one Qoin of value) |
|---|---|
| Score ≤ 0 (any level) | **nothing** — the post is removed from the page and kept in the author's Private timeline; it is never shown as "frozen" |
| Village | 1 |
| Tehsil | 2 |
| District | 5 |
| State | 10 |
| Zone | 20 |
| Country | 50 |
| Continent | 100 |
| **Earth — winner** (highest score) | **500** |
| **Earth — participant** (positive, not the winner) | **100 + 100** = 200 (decided 2026-09-27; the brief's other draft said 100 + 50) |

Same values in every country, shown in the user's currency ([qoins_wallet_system.md](qoins_wallet_system.md)). Elevated posts pay nothing at the level they leave; only the **final freeze** pays.

Implemented: `qoin_core.post_reward`, called from `board_core.settle` when a post freezes. Earth "winner" is not decided yet, so Earth currently pays the participant reward.
