# Private Account fixes (2026-10-04)

First slice of a much larger 10-part request (locations table, Vedic chart, election history,
scoreboard, GitHub+Railway deploy, i18n, tutorial, referral/registration fee,
Postgres migration, a full civic-tech voting/declaration system, weekly statements with account
tracking) — the Founder picked **Private Account fixes** as what to build first; the rest stays
scoped-but-deferred (see "Deferred" below).

## 1. Locations table

`profile.birth_location_struct` (new) + the existing `present_location_struct` feed a 7-row ×
2-column table (Continent → Village, Birth/Present) in the Private tab's Locations card
(`templates/dashboard.html`, `.pv-loc-table` in `dashboard.css`), replacing the old single-line
breadcrumb text. Collapses to a stacked label/value layout under 560px.

## 2. Vedic Chart (Kundali) — Moon-based, with analysis

New module `kundali_analyser.py`, built on top of the ephemeris data `zodiac_core.generate_kundali()`
already computes (nothing here touches `pyswisseph`):

- **Moon-based (Chandra Lagna) houses**: House 1 = the sign the Moon occupies, not the Ascendant's
  sign (that's a *different*, equally valid chart the Founder explicitly asked to use here instead
  — "My Private Account Vedic chart image should display Libra as first house [Moon's sign]").
  `moon_based_houses()`.
- **North Indian style SVG chart**, `chart_svg()` — a square + both diagonals + the diamond formed
  by joining edge midpoints, which is the standard construction and produces exactly 12 regions (4
  kite-shaped Kendra houses at the edge midpoints, 8 corner triangles); vertices were derived from
  the actual line equations, not guessed, and verified against the Founder's own worked example
  (Moon in Libra → House 1 = Libra … House 12 = Virgo) and against a reference chart image (Rahu in
  Capricorn, Shravana nakshatra, 13°37′, House 4 — matched exactly).
- **Planetary table**: all 10 points (Ascendant + Sun/Moon/5 visible planets/Rahu/Ketu), each with
  sign, element, nakshatra, nakshatra lord, pada, degree, and Moon-based house. `planetary_table()`.
- **Drishti (aspects)**: every point aspects its own 7th house; Mars also 4th/8th, Jupiter also
  5th/9th, Saturn also 3rd/10th, Rahu also 4th/8th/12th, Ketu also 3rd/10th — the standard Vedic
  aspect table. `aspects()`.
- **House strength**: a house with only benefic occupants (Jupiter/Venus/Mercury/Moon) is "strong";
  only malefic occupants (Saturn/Mars/Rahu/Ketu) or no occupants is "weak"; Sun-only or mixed is
  neutral. `house_strength()`.
- **Elemental balance**: Fire/Earth/Air/Water counts across the 9 planets (Ascendant excluded, it's
  a point in space, not a planet) + dominant element. `elemental_balance()`.
- **Vimshottari Dasha**: the Moon's nakshatra lord starts the cycle, with the correct
  balance-of-dasha-at-birth (the fraction of that nakshatra already elapsed at birth shortens the
  first period); full 9-period sequence, which one is current, and the next 3 ahead.
  `vimshottari_dasha()`.

`analyse(dob_iso, kundali, today=None)` returns everything above in one call, including the chart
SVG — this is what `app._profile_for()` now stores as `profile.kundali_view` (replacing the old
Ascendant-based `_kundali_view()`, which has been deleted along with its now-unused
`_nakshatra_of()` helper) and what `GET /api/user/zodiac/<user_id>` now adds as
`moon_based_analysis`. Rendered in the dashboard's Kundali modal (`static/js/dash_extras.js`) — the
chart SVG is injected directly (server-generated from numeric ephemeris data, not user text, so
safe), with new sections for elemental balance, house strength, aspects, and the Dasha timeline.

The chart's cell vertices also fixed a real bug in the client's OLD chart-drawing code
(`dash_extras.js`'s previous `chartSvg()`): it numbered houses counter-clockwise (2/3 to the left of
house 1), the reverse of the correct clockwise Vedic convention. That function has been removed.

## 3. Election History — correct options, lock rule, working analytics

- India's 4 options are now exactly: **BJP / NDA Alliance**, **INC / INDIA Alliance**, **Other**,
  **Not Voted / NOTA** (`election_core.PARTIES_BY_COUNTRY["IND"]`, `NOT_VOTED`). The other 9
  countries keep their own researched 3-party + NOTA lists — the Founder's own scoping answer only
  named India's exact wording.
- **Lock rule**: every past Lok Sabha year (all but the newest/upcoming one) and Vidhan Sabha's
  "last" slot lock forever the first time they're saved — a further attempt to change (or clear) one
  raises an error and nothing in that save is written. Only the newest Lok Sabha year and Vidhan
  Sabha's "next" slot can be changed and re-saved at any time. `save_party_history()`.
- **Fixed a real, previously-broken bug**: `loksabha_aggregate()`/`vidhansabha_aggregate()` queried a
  table (`election_history`, column `loksabha_2029`) that doesn't exist anywhere in this codebase —
  dead code left over from an earlier schema design. They now query the real
  `election_history_entries` table (kind/slot/choice), aggregating the upcoming-election slot (the
  one every user can still change, so this is a live-sentiment figure, not a record of past votes).
  This aggregate is **already wired into the UI** — `static/js/board.js`'s `loadSentiment()` calls
  `GET /api/election-sentiment/<level>/<location_id>` and renders percentage bars on Country (Global
  tab) and State (Public tab) pages; it was silently failing before this fix.

## 4. Referral ID → Account ID, "Donation" → "Registration Fee"

- The registration form's free-text "Referral code" field (and its paired volunteer-PIN-confirm
  block) is **removed entirely** — there is no other place in the UI that surfaces or lets a user
  share their own referral code, so it was reachable only through that one now-removed field.
- The existing **assisted registration** flow (`/register?assist=1`, a signed-in member registering
  someone else) already auto-used the signed-in member's own id as the referrer
  (`api_auth_register`'s `helper_user_id`) — that logic is untouched, just simplified (the now-dead
  manual-code branch was removed from `api_auth_register`). The register page now also shows "You
  are being registered by: `<name>` (Account ID: `<id>`)" when visited while signed in.
  The formal admin-approved "referrer program" (`board_core.py`'s `referrers`/`referrer_applications`
  tables, `my_referrer_code()`, the share-based donation split) is **untouched** — it's a separate,
  deliberately-built feature (approved referrers earn a cut of OTHER people's donations by sharing a
  code through channels outside the app), not what this fix targeted.
- "Donate"/"Donation" is now labelled **"Registration Fee"** everywhere in the registration UI
  (`templates/register.html`, `static/js/register.js`); internal class/variable names
  (`qm-donate-panel`, `donateState`, etc.) were left as-is — only user-visible text changed.

## Deferred (per the Founder's own priority answer, 2026-10-04)

Not touched this pass — explicitly scoped for later, with direction already captured for when we
get there:

- **Scoreboard** (homepage India/Zone/State live rankings) and **Tutorial redesign** — straightforward
  UI additions, just not this pass's priority.
- **GitHub + Railway deployment, Postgres migration**: *"Yes please migrate and deploy now after you
  complete all the required changes... First finish remaining editing/updating work."* — i.e. after
  the remaining feature backlog (scoreboard, tutorial, i18n, and whatever else), not before.
- **Payments**: dropped (2026-10). Qumanity has no payment processor; Qoins are earned, never
  purchased (see `docs/qoins_earn_reference.md`).
- **Multi-language (i18n)**: not started.
- **The separate "civic-tech" voting/declaration system** (candidate duties/rights declarations, an
  oath, a performance dashboard with evidence tracking) is a different, much larger system than the
  existing Zodiac Council Voting ([[zodiac_council_voting]]) — not started. If/when it is: an
  "immutable ledger" means a SHA-256 hash-chained audit log in SQLite (each entry's hash includes the
  previous entry's hash, so tampering is detectable), not a blockchain; "biometric confirmation"
  means the existing PIN-based auth, not real fingerprint/face hardware integration.
