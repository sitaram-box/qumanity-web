# Karma — a Social Credit / accountability score (never money)

Founder's decision, 2026-09-29: Karma is **never** money and is **never** automatically converted
to or from Qoins (the spendable currency, see `docs/qoin_core.md`/`docs/qoins_wallet.md`). "Karma
Score + Qoins together" as a reward is documented as a future *possibility*, not a formula — the
code here never computes or credits Qoins.

## Two kinds of individual karma

| Kind | Earned from | Scope |
|---|---|---|
| **Commercial** | A customer's star rating of a real, local business transaction (a `business`-category `personal_groups` row) | The rater and the provider must share the same **present village** — commercial karma is village-scoped only |
| **Non-commercial** | A person's own good work with no paid transaction — for now, wired to a village-level Collective Board post that freezes with a positive score (the same moment that already earns the author Qoins, see `board_core._reward_author()`) | Any level the post/action happened at |

Both are stored per-entry in `karma_entries` (`user_id`, `kind`, `points`, `reason`, `from_user_id`,
`created_at`) so the running total is always a sum, never a mutable field — the same "ledger, not a
counter" pattern `wallet_core` already uses for Qoins.

## Collective karma

Not owned by a person: a running score per **location** (village up to Earth), bumped by the
collective's own recognised actions — a Tehsil-and-above Collective Board post freezing positively
(a post that has risen past the village is credited to the wider group it now represents; the
village-level freeze on the same post already counted as *individual* karma for its author). Stored
in `collective_karma` (current total per `(location_id, location_level)`) + `collective_karma_log`
(audit trail), bumped via `karma_core.bump_collective_karma()`.

Shown on every Public/Global **location** page (`GET /api/karma/collective/<level>/<location_id>`),
never on a private profile.

## Star → karma points (`STAR_KARMA`)

A very good rating (4-5 stars) is the only case the Founder described as earning karma; a poor one
(1-2 stars) is treated symmetrically as an accountability cost, an average one (3) is neutral —
reasonable given "Social Credit / accountability score" is the whole point of the module. This
table is `karma_core`'s own extrapolation, not literally specified by the Founder:

| Stars | Points |
|---|---|
| 5 | +15 |
| 4 | +8 |
| 3 | 0 |
| 2 | -5 |
| 1 | -15 |

Re-rating a business replaces the old karma delta with the new one (`business_ratings` is one row
per `(group_id, rater_user_id)`, upserted) — it never double-counts.

## Where it's shown

- **Every individual Private account**: "Your Karma" card (total + commercial/non-commercial split
  + history) — `GET /api/karma/me` (own, with history), website `templates/dashboard.html` +
  `static/js/dashboard.js` (`loadKarma()`).
- **Every collective Group page, Public/Global**: the location's collective karma total —
  `GET /api/karma/collective/<level>/<location_id>`.
- **Someone else's public profile / an election candidate's report**: the running total only, never
  their private history — `GET /api/karma/user/<user_id>`. Wired into the Zodiac Council Voting
  candidate cards (`election_core.candidates_for_cycle()`), see `docs/zodiac_council_voting.md`.
- **A business page**: star-rating UI — `GET/POST /api/people/groups/<group_id>/rate`.

## Not yet built

- App (React Native) equivalents of all of the above.
- Any UI surfacing collective karma on the app's own location/group screens.
