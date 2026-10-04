# Karma Points: finalizing individual + collective display (2026-10-04)

First step of the go-live push (see `docs/visibility_gating_2026_10.md` for the decisions made
right before this). Researched the existing Karma system before touching anything — it was further
along than expected:

- **Individual Karma**: fully built and displayed — `karma_core.individual_karma_score()` (a
  ledger summed on read, `karma_entries` table), shown on the private dashboard's Karma card
  (`GET /api/karma/me`) and on candidate cards during elections (`GET /api/karma/user/<id>`).
  Nothing changed here.
- **Collective Karma**: the schema, the write path (`karma_core.bump_collective_karma`, triggered
  from `board_core.py` when a post freezes positively above village level, plus a hardcoded "EARTH"
  bump), and the read API (`GET /api/karma/collective/<level>/<location_id>`) all already existed
  and worked — but **nothing on the frontend ever called that endpoint**. That was the actual gap.

## What was added

A "🏅 Collective Karma" block in the existing per-location stats panel (`stat_block` macro,
`templates/dashboard.html`) — right next to the Wallet block that was already there, reusing the
exact same pattern. Wired in `static/js/dashboard.js`: new `loadCollectiveKarmaFor(prefix,
locationType, locationId)` (mirrors `loadWalletBalanceFor`), called everywhere `loadWalletBalanceFor`
already was — Earth, and every node selected in the Global/Public location explorer (continent,
country, zone, state, district, tehsil, village). This reuses the explorer/stats UI that already
existed (dashboard redesign Phase 1) rather than building a new location page from scratch.

Verified: `GET /api/karma/collective/earth/EARTH` returns `{"points": 0, ...}` live; an unknown
level still 404s exactly as before; `/dashboard` renders with both new `*-karma` elements present
for a real logged-in user (checked via Flask's test client with Founder's own session, catching any
template error directly rather than guessing from reading the HTML).

## Left exactly as designed (not bugs)

- **Village-level collective Karma is a permanently-zero bucket.** A village-level post freeze
  credits the author's *individual* Karma, not a collective bucket — a deliberate 2026-09-29 call
  documented at `board_core.py:189-194` ("the author's OWN good work"). The new UI shows "0" at
  village level, which is the correct, truthful number, not a bug to fix.
- **Karma is earned from exactly two actions repo-wide**: a board post freezing positively, and a
  business star rating. No vote/referral/donation path feeds Karma. Adding more earning triggers
  would be new design, not something this pass found half-built — left untouched pending an
  explicit ask.
- **Karma and Qoins stay fully separate** (per the Founder's 2026-09-29 decision, documented in
  `karma_core.py`'s own module docstring and `docs/karma.md`) — point *values* are numerically
  borrowed from `qoin_core.FREEZE_REWARD` as a shared magnitude curve, but there is no conversion
  path between the two, and this pass didn't touch that boundary.
- Mobile app parity for any of this: still web-only, not started.
