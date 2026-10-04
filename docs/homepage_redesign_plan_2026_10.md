# Homepage redesign — researched and planned, NOT YET BUILT (2026-10-05)

The Founder asked for a substantial homepage redesign in the same message that also asked for the
Founder's Message translation and go-live prep. The translation work (see
`docs/founders_message_i18n_2026_10.md`) and go-live hardening (see
`docs/go_live_hardening_2026_10.md`) were completed; this redesign was fully researched and
designed but **implementation has not started** — flagging clearly here rather than leaving it
undocumented, since the research findings below are the grounding a future pass needs and
shouldn't be re-derived from scratch.

## The ask, broken into parts

1. **Remove the existing "Live from Qumanity" section** (`templates/home.html:121-174`, populated
   by `static/js/earth.js` via `/api/subcontinent/stats` + `/api/country/stats/<id>` +
   `/api/world-data`) and **replace it with a small, grey, compact search box fixed near the top of
   the screen**: click it, pick one of Earth / the 7 continents / the 10 Indian Sub-continent
   countries, see that selection's stats. Other countries' data stays disabled (UI-level scoping
   only — the backend already has all 229 countries' data; only 7 continents + 10 countries are
   ever offered in the picker).
2. **Move "India - Live Scoreboard" into the hero section** (currently
   `templates/home.html:176-204`, populated by `static/js/scoreboard.js` via
   `/api/scoreboard/india`), remove the current hero paragraph ("Qumanity is a nested, transparent
   ledger of Space, Time and Consciousness...", `templates/home.html:58-62`), keep the "Quantum +
   Humanity" chip and the H1 ("The operating system for a conscious civilization.") exactly as they
   are. Add pie/donut charts for Gender / Age-Category / Zodiac 4-Elements / 12-Signs breakdowns.
   Default view is India; a "check more" expansion reveals ranked lists of all 7 continents and all
   10 Sub-continent countries (by registered-member count), each selectable to show its own charts.
   Section name should not read as India-only, since it expands beyond India.
3. General instruction to use Claude's own judgment for "the best possible UI" — no further
   constraints given beyond the above.

## What's already confirmed true in the codebase (the research)

- **All the backend data endpoints already exist and are public** (no auth required):
  `/api/earth/stats`, `/api/location/stats/<level>/<id>` (generalizes over continent/country/etc.),
  `/api/world-data` (continents + 229 countries), `/api/scoreboard/india`
  (`elemental_core.india_scoreboard`, zone/state ranks by member count). **No new backend routes
  are needed for the compact search widget** — it's pure frontend, reusing what dashboard.js
  already proved works for exactly this "pick a region, see a stats panel" pattern (built the same
  day for the dashboard's own location explorer).
- **One new backend route is needed for the hero's "see all 7 continents / 10 countries" ranking**:
  nothing currently ranks continents against each other or ranks the 10 Sub-continent countries
  against each other by member count (only India's zones/states are ranked today, via
  `elemental_core.india_scoreboard`). The fix is small and low-risk: `location_elements` already
  carries a `total_users` count at every level (continent, country, zone, state, ... — written by
  `elemental_core.update_location_stats` for every registration), so a new query exactly analogous
  to `india_scoreboard`'s own pattern (`SELECT location_id, total_users FROM location_elements
  WHERE location_type = 'continent' ORDER BY total_users DESC`, and the same filtered to the 10
  `SUBCONTINENT_COUNTRY_IDS` for `location_type = 'country'`) gives both rankings directly, no new
  aggregation logic to invent.
- **No charting library exists in this codebase yet.** Every current visualization (the 3D globe,
  the scoreboard bars, the stat bars) is hand-rolled CSS/Canvas/three.js — introducing something
  like Chart.js (via a CDN script tag, matching the existing external-script convention already
  used for three.js/leaflet) would be new, not an extension of an existing pattern.
- The existing 3D globe (three.js, in the hero's right column today) would need to move somewhere
  else once the India scoreboard takes over the hero's main visual slot — the natural new home is
  next to the new compact search widget, since both are "explore the world" features.

## Why this wasn't built in this pass

The scope (new hero layout, a new chart-driven stats widget shared between two entry points, a new
backend ranking route, relocating the 3D globe, and "best possible UI" creative latitude on top of
all of it) is a substantial, highly visual rebuild that benefits from iterative browser-based
verification (screenshots, interaction testing) rather than being written blind in one pass. The
Founder's own message said to prioritize finishing the Founder's Message translation and go-live
prep first given session constraints — this is queued as the next homepage-focused pass.

## Suggested next steps (not started)

1. New backend: `GET /api/scoreboard/global` — continent ranking + the 10-country ranking, per the
   query pattern above.
2. New shared frontend module (e.g. `static/js/region_stats.js`) implementing "pick a
   continent/country, render its total + 4 donut charts" — used by BOTH the compact nav search box
   and the hero's expanded rank lists, so the logic is written once.
3. Hero markup/CSS rework: remove the lead paragraph, insert the India scoreboard + chart panel
   directly below the H1/CTA, relocate the globe.
4. Compact top-of-page search control: a small grey pill/dropdown in or just under the nav bar.
5. Verify in the browser at each step (not just Flask-level checks) given how visual this is.
