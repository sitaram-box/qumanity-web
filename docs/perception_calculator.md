# Perception Calculator — annual Pro/Anti sentiment voting

Its own separate section, distinct from the existing private, optional Election History feature
(`docs/election_history.md`) — that one is filled out privately and only the same user ever sees it
again; Perception is cast straight onto a **Public** page and its aggregate is what everyone sees
there (Founder, 2026-09-29).

## Scope (Founder's own UI answer, 2026-09-29)

*"Add Perception as its own separate section. It is only available on India country and zone pages.
For other 9 countries have only country perception option."*

- **Country Perception**: any of the 10 Sub-continent countries (`app.SUBCONTINENT_COUNTRY_IDS` /
  `perception_core.SUBCONTINENT_COUNTRY_IDS`) — shown on the **Global tab**'s Country page for that
  country (selecting it via Earth → continent → country, the continent's own country list, or the
  user's own present-country tab).
- **Zone Perception**: **India's zones only** — shown on the **Public tab**'s Zone page, only when
  the selected zone belongs to India (`O_AS_IND`).
- The original spec also described a State-level sentiment table; the Founder's own scoping answer
  mentions only "country and Zone" pages, so **State Perception is dropped** from this build.

Eligibility is always based on **birth** location (`users.birth_location_json`), never present
location — *"Even if a user temporarily lives abroad, their voting rights remain tied to their birth
location"* (original spec, verbatim). A user can never vote Perception on their own birth
country/zone.

## The annual cycle

- **Voting window**: October 1 – December 31 of a `voting_year`. Casting a vote outside this window
  is rejected.
- **One vote per person per `voting_year`**: once cast, it cannot be changed that year (the spec's
  "one vote change per year" is read as one write per year, not unlimited toggling).
- **Freeze**: the instant Jan 1 of the following year is reached, that year's raw votes are tallied
  once into `country_sentiment_stats`/`zone_sentiment_stats` and never recomputed — compute-on-read,
  the same pattern `election_core._ensure_tallied()` already uses, so no cron job is needed.
- **Display**: on any given date, the results shown are always the **prior** year's frozen tally —
  `displayed_year = today.year - 1`, continuously, all year round. That covers the spec's literal
  "displayed Jan 1 – Sep 30" AND its "a new cycle opens Oct 1 while old results keep displaying
  until next Jan 1" — a brand-new voting window can be open (Oct-Dec) while the page still shows the
  previous year's frozen numbers, right up until the next Jan 1 flips `displayed_year` forward.
- Votes are hidden from the public tally while the window for that `voting_year` is still open —
  only the frozen, prior-year tally is ever shown to anyone; a user can always see their own
  just-cast vote.

## Schema (`perception_core.py`)

- `country_sentiment` (`user_id`, `country_id`, `voting_year`, `vote`, timestamps) — one row per
  person per country per year.
- `country_sentiment_stats` (`country_id`, `voting_year`, `pro_count`, `anti_count`, `frozen_at`).
- `zone_sentiment` / `zone_sentiment_stats` — same shape, keyed by `zone_id`.

## Routes (`app.py`)

- `GET /api/perception/country/<country_id>` — current results + the caller's own eligibility
  (works logged-out too, just without `my_vote`/`can_vote`).
- `POST /api/perception/country/<country_id>/vote` — body `{vote: "pro"|"anti"}`.
- `GET /api/perception/zone/<zone_id>` / `POST /api/perception/zone/<zone_id>/vote` — same shape.

## UI

Website: `templates/dashboard.html` (`#qm-perception-country-card` in the Global tab,
`#qm-perception-zone-card` in the Public tab) + `static/js/dashboard.js` (`loadCountryPerception()`,
`loadZonePerception()`, `wirePerceptionVoting()`), gated in `selectLocation()` on the selected
node's level/id, mirroring the same 10-country id list as `perception_core.py`.

## Not yet built

- App (React Native) equivalent.
- State-level Perception (dropped from this pass, see Scope above).
