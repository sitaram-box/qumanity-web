# Qumanity — Global Timeline, Registration & Kundali (standalone prototype)

Copyright (C) 2026 Rohit Mudgal (individual).
Qumanity Lok LLP is in registration. The IP will be
assigned to the LLP once it is registered.

Qumanity is licensed under the GNU Affero General Public
License v3.0. See LICENSE for details.

Homepage: a rotatable 3D Earth with **real continent shapes and country
borders** (not dots) — click a country directly on the globe to select it,
or use the "Search countries" fallback for tiny/hard-to-click nations.
India is saffron-highlighted by default. A breadcrumb (Earth › Continent ›
Country) tracks hover/selection, a click flies the camera to the country
and traces its outline, and a Global Timeline stats sidebar plus
Login/Register/Elements entry points round out the homepage.

## The Earth map (Three.js + real GeoJSON, not dots)

Chose **Option B (Three.js + GeoJSON)** over Cesium/Mapbox/Leaflet: the
existing globe (`earth-globe.js`) already had working drag-rotate,
scroll/pinch-zoom, and a click-pick pipeline shared by the homepage and
both registration wizard steps — switching engines would have meant
rebuilding all of that from scratch for a purely cosmetic-adjacent win.
Country shapes turned out to be additive on top of the existing raycasting
model, not a rewrite.

- **Data**: Natural Earth's 110m countries (`scripts/build_world_borders.py`
  fetches and re-tags it with *our own* continent/country ids from
  `global_countries.json` — not Natural Earth's own classification — so the
  map and the country-picker never disagree about which continent a country
  belongs to). 170/177 features matched (unmatched: Antarctica, W. Sahara,
  Greenland, and a few disputed territories not in the 229-country list).
- **Rendering**: `scripts/build_world_texture.py` rasterizes that GeoJSON
  into one equirectangular PNG (`static/images/earth_texture.png`, ~70KB) —
  country fills colored by continent, India always saffron, thin gold
  borders — applied as the sphere's material map. A canvas rasterize
  is dramatically cheaper than one Three.js mesh per country (thousands of
  polygon points, holes, tessellation) and looks identical from globe
  distance. Antimeridian-crossing countries (Russia, Fiji...) are handled
  by longitude-unwrapping each ring and drawing on a 3x-wide canvas before
  cropping — otherwise they render as a line straight across the map.
- **Hit-testing**: click/hover raycasts onto the sphere, converts the hit
  point to lat/lng, then does antimeridian-safe point-in-polygon against
  the *same* GeoJSON (bounding-box pre-check per feature first, since a
  naive test against all 170 features on every mousemove was measurably
  slower). Selecting a country calls `highlightCountry()` (traces its
  actual boundary as a `THREE.LineLoop` on the sphere surface — not just a
  pin) and `flyTo()` (eases rotation + zoom toward it over subsequent
  frames — there's no true camera-orbit flight on a simple sphere, but it
  reads as "zooming into that region").

## India Map & Location Selection Tool

Once India is picked (world globe or search), the wizard switches from the
3D globe to a flat **Leaflet** map of India — deliberately a different
engine than the world globe: India is a single flat region, so a real 2D
map (pan/zoom/hover/click, no basemap tiles, just the state GeoJSON on a
blank dark background) is the better fit than forcing it onto a sphere.

- **State shapes**: no ready-made *state*-level India GeoJSON existed that
  both (a) reflects the 2014 Telangana split / current J&K-Ladakh split and
  (b) isn't 15–25MB unsimplified. `scripts/build_india_states_geojson.py`
  dissolves a modern *district*-level source (760 districts) up to state
  level with `shapely.ops.unary_union`, simplifies each shape, and tags it
  with our own state/zone id from `india_states.json` — 37/37 states
  matched (one real merge: the source already combines Dadra & Nagar
  Haveli with Daman & Diu per their actual 2020 administrative merger; both
  of our separately-listed UT entries get that same polygon).
- **Zones**: the brief asked for 6 zones (adding "North-East" in teal) and
  28 states + 8 UTs. The real source (SITAXML.xml) has **5 zones** (the
  North-Eastern states are already grouped under Central Zone) and **37**
  states/UTs — used as-is rather than inventing a 6th zone the data doesn't
  support. South zone's color is `#4A90D9` (brightened from the brief's
  navy `#0A1929`, which is nearly invisible against this app's own dark-navy
  page background) — see `india_states.json`'s existing color choice.
- **District = Loksabha, Tehsil = Vidhan Sabha?** SITAXML.xml has no
  constituency data at all — no seat numbers, no MP/MLA fields, nothing
  distinguishing an electoral constituency from a revenue-administration
  division. Checked directly: Uttar Pradesh has 71 real "districts" in the
  source vs. 80 actual Lok Sabha seats; Bihar has 534 "tehsils" vs. 243
  actual Vidhan Sabha seats. These are the source's real administrative
  districts/tehsils (635 districts, 5,971 tehsils nationally — real names,
  e.g. Uttar Pradesh's 71 real districts, Pune's 14 real tehsils), extracted
  and labeled honestly as District/Tehsil rather than mislabeled as Lok
  Sabha/Vidhan Sabha. See `scripts/extract_india_districts_tehsils.py`'s
  docstring.
### The wizard: one step at a time, not everything at once

`location_select.js` (`QMLocationWizard`) redesigned the original all-at-once
nested-tabs+dropdowns layout into a genuine step-by-step flow, after
feedback that users couldn't tell what step they were on and the screen
was cluttered:

- **Zone** (map + card list) → **State** (same map, now zone-filtered —
  states outside the chosen zone are dimmed and unclickable via
  `map.setZoneFilter()`, and the view fits-bounds to just that zone's
  states) → **District** (search + card list, no map) → **Tehsil** (search
  + card list) → **Village** (search + card list, fetched on demand — see
  below).
- A numbered progress header (5 steps, connectors fill in as you go) sits
  above every step; **clicking any already-reached step jumps back to it**
  and clears everything after it, so re-picking a State properly re-clears
  District/Tehsil/Village rather than leaving stale, mismatched selections.
- After Village, a **summary screen** lists all 5 levels with a per-row
  **Edit** link (jumps back to that exact step) and the real **location
  path** (e.g. `CS.CH.1.1.1`) — this is the actual id chain through the
  selected levels, *not* the full Private/Account ID string (name
  initials, gender/age codes, zodiac codes) — that generator is still a
  separate, later phase.
- **Villages are fetched on demand, not shipped upfront**: 621,057
  villages nationally (vs. 635 districts / 5,971 tehsils) would be a
  15–20MB static file. `scripts/import_india_villages.py` loads them once
  into a SQLite table (`india_villages`, indexed by `tehsil_id`), and
  `GET /api/india-villages/<tehsil_id>` queries just the selected tehsil's
  villages (a few dozen to ~1,400) at request time. 482 village ids repeat
  in the source XML itself (~0.08% of rows, a real data-quality issue, not
  an import bug) — flagged in the endpoint's docstring rather than
  silently deduplicated away.
- Both components are reusable (`india_map.js`, `location_select.js`, same
  factory pattern as `earth-globe.js`) — used both standalone
  (`/india-map`, `/location-select` demo pages) and embedded in
  `/register`'s birth/present location steps, reusing the *same*
  `pendingSelection` → confirm-bar → `/api/auth/register` pipeline as
  every other location pick.
- Real bugs hit and fixed while building this (worth knowing about if you
  extend it):
  - The `[hidden]` attribute vs. an explicit `display` CSS rule conflict
    bit twice more here (`.qm-wizard-card-list` and `.qm-wizard-footer`
    both set `display: grid`/`flex` unconditionally, which — per normal
    cascade rules — beats the browser's own `[hidden] { display: none }`
    since author styles win over the UA stylesheet). Net effect: leaving
    a step showed a stale card grid from the *previous* step layered
    underneath the new one. Now checked systematically: every element
    this codebase toggles via `.hidden` that also has an unconditional
    `display` rule needs an explicit `[hidden] { display: none }` override
    alongside it.
  - The location path was originally built by joining *every* selected
    level's id with `.` — wrong, because each level's id is already the
    full hierarchical path (a village id like `CS.DL.1.1.10` already
    encodes zone/state/district/tehsil), so concatenating them produced
    nonsense like `IND/CS.CS.DL.CS.DL.1...`. Fixed to just use the
    deepest selected level's id directly.
  - A CSS selector (`.qm-india-map-wrap > div`) meant to size only
    the Leaflet map also matched the legend `<div>` (same parent), stretching
    it to the map's full height; the resulting oversized legend then
    intercepted clicks in the gaps between its chips before they reached the
    map underneath (fixed with `pointer-events: none` on the legend and a
    `.leaflet-container`-scoped height selector); and Leaflet, like the
    Three.js globe before it, computes its initial view against whatever
    container size exists at construction time — since that's `display:none`
  when the wizard step isn't active yet, `resize()` has to explicitly
  re-apply the default center/zoom, not just call `invalidateSize()`.

Registration (`/register`) is **open to anyone worldwide** — a 5-step wizard:

1. **Your details** — name, gender, date/time of birth, language/mother tongue.
2. **Birth location** — click a country directly on the same real-shape
   Earth globe (or search). This is the **Private ID** location.
3. **Present location** — the same globe again, reset and reused. This is
   the **Public / Account ID** location.
4. **Review** — summary of everything captured.
5. **Kundali** — real Vedic birth chart, computed on "Complete registration".

Selecting **India** at either location step additionally opens the
**Public Location Selection Tool** — a real 37-state, zone-colored picker
(Central/North/South/East/West, parsed from SITAXML) — before confirming.
Any other country stops at country level (e.g. "born in India → Delhi",
"living in Australia", per the brief's own example), since only India's
state data exists so far. District/Tehsil/Village drill-down and Private
ID / Account ID *string* generation are still next phases — but
registration itself now **persists to a real SQLite DB** and computes a
**real Vedic kundali**, not placeholders.

This is **deliberately disconnected** from the existing Qumanity platform
(`identity_core.py`, `global_core.py`, the `/api/locations/children` API,
17k-line `app.py` at qumanity.in) so the visual flow can be iterated on
quickly without touching the live schema or data. Conventions are kept
compatible on purpose:

- Location path format `Zone.State.District.Tehsil.Village` (e.g. `CS.DL.5.4.1E`)
  matches the real platform's `location_path` in `identity_core.py`.
- IDs follow the SITAXML convention exactly: continents are `O_<CODE>`
  (`O_AS`), countries are `O_<CONTINENT>_<ISO3>` (`O_AS_IND`), India's
  states are `<ZONE>.<STATE>` (`CS.DL`).

## Run it

```bash
pip install -r requirements.txt
python3 db/init_db.py     # first time: create + seed qumanity_prototype.db
python3 app.py
# open http://127.0.0.1:5050
```

## Zodiac & kundali architecture

**Two deliberately different zodiacs, for two different jobs** (see
`zodiac_core.py`'s module docstring for the full reasoning):

- **Sun-sign element (tropical / Western)** — the plain Gregorian date
  ranges from the brief's own table. Drives the Fire/Earth/Air/Water
  governance classification (`location_elements`), because it has to work
  from date of birth alone, for every user.
- **Kundali (sidereal / Lahiri ayanamsa)** — what a real Vedic birth chart
  and nakshatras actually are. Computed via `pyswisseph`'s Moshier
  analytical ephemeris (accurate to a few arcseconds, **no external data
  files needed**), with the birth time converted from local civil time to
  UTC using the birth location's *real* historical IANA timezone
  (`timezonefinder` + stdlib `zoneinfo` — not a longitude/15 guess).

Mixing these up would be wrong, not just inconsistent — verified against a
known case: May 14 1990, 14:35 IST, Delhi → tropical Sun is Taurus, sidereal
Sun is Aries 29.6° (the ~24° Lahiri ayanamsa gap), Moon in Sagittarius/Purva
Ashadha, Ascendant Virgo, whole-sign houses placing all 7 planets — cross-
checked internally consistent (correct UTC offset, correct sign/nakshatra
math) and its `lunar_core.py` sibling's eclipse predictions matched a real
one I could independently verify (the Aug 2 2027 total solar eclipse).

- **Ascendant/houses precision**: the wizard only collects continent/country
  (state, for India) — not an exact birthplace — so ascendant and houses use
  a *centroid* (state centroid for India, continent centroid otherwise) and
  are flagged `location_precision` in the API response accordingly. Sun and
  Moon are essentially unaffected by this (they're time-dominated, not
  place-dominated).
- **Elemental balance** (`elemental_core.py`) counts 8 chart points (tropical
  Sun + sidereal Moon/Ascendant/5 visible planets; Rahu/Ketu excluded as
  shadow points) into Fire/Earth/Air/Water. Space is always 0 for an
  individual — per the brief, Space/Akasha is the database itself, not a
  personal trait.
- **Lunar phases & eclipses** (`lunar_core.py`) are also real ephemeris
  computations — current phase via `swe.pheno_ut`, next New/Full Moon via
  root-finding the Sun-Moon elongation angle, next eclipse *visible from
  India* via `swe.lun_eclipse_when_loc`/`sol_eclipse_when_loc` at Delhi.

## What's here

**Backend**
- `app.py` — Flask app + all routes/APIs (see below).
- `db/schema.sql`, `db/seed_zodiac_data.py`, `db/init_db.py` — SQLite schema
  (`users`, `zodiac_signs`, `nakshatras`, `user_zodiac`,
  `user_elemental_profile`, `location_elements`, `lunar_events`) and real
  reference-data seeding (12 zodiac signs, 27 nakshatras with their actual
  Vimshottari dasha lords).
- `zodiac_core.py` — sun sign, full kundali generation, summary text.
- `elemental_core.py` — personal elemental balance, location-level
  aggregation (cascades Earth → Continent → Country → Zone → State →
  District → Tehsil → Village, for India selections).
- `lunar_core.py` — current phase, upcoming New/Full Moon + eclipses.
- `folder_sync.py` — hybrid DB↔folder export (`folder_export/Earth/...`,
  mirroring the brief's Part 4 elemental folder layout) — idempotent, safe
  to delete and regenerate. Wired to a daily APScheduler job in `app.py`.

**API** (Part 5 of the brief)

| Endpoint | What it does |
|---|---|
| `POST /api/auth/register` | Register, compute zodiac + kundali, update location stats |
| `GET /api/user/zodiac/<id>` | Full stored kundali |
| `GET /api/user/kundali/summary/<id>` | Just the summary fields |
| `GET /api/location/elements/<id>?type=state\|country\|...` | One location's elemental distribution |
| `GET /api/global/elements` | Earth-level totals + every location on record |
| `GET /api/zodiac/signs` | The 12 zodiac_signs rows |
| `GET /api/zodiac/current` | Today's tropical sign/element |
| `GET /api/lunar/phase` | Current phase + upcoming events |
| `POST /api/admin/sync-folders` | Trigger the DB→folder export |
| `GET /api/world-data`, `/api/india-states`, `/api/global-data` | Existing globe/location data |
| `GET /api/india-districts` | Real District/Tehsil names per state (SITAXML) |
| `GET /api/india-villages/<tehsil_id>` | Real villages for one tehsil, fetched on demand |

**Frontend**
- `templates/index.html` — homepage (Login/Register/Elements).
- `templates/register.html` + `static/js/register.js` — the 5-step wizard;
  Screen 5 is a real Kundali Display + Elemental Balance component built
  from `/api/auth/register`'s response.
- `templates/kundali_view.html` (`/kundali/<user_id>`) — the "private
  account" kundali view, revisitable independent of the wizard's in-memory
  state (there's no login/session system yet, so this is a bookmarkable
  link rather than an authenticated dashboard).
- `templates/elements.html` (`/elements`) — the Elemental Dashboard: a
  location-level selector (Earth/Continent/Country/Zone/State/District/
  Tehsil/Village) over real registration data, plus the live lunar timeline.
- `templates/india_map.html` (`/india-map`) — standalone demo of the India
  Zone/State map alone.
- `templates/location_select.html` (`/location-select`) — standalone demo
  of the full step-by-step wizard.
- `static/js/earth-globe.js` — the reusable Three.js globe: drag/zoom,
  `setEarthTexture()`, `setCountryBorders()` + point-in-polygon hit-testing,
  `highlightCountry()`/`clearCountryHighlight()`, `flyTo()`. Shared by the
  homepage and both wizard location steps.
- `static/js/india_map.js` — the reusable Leaflet India map (same
  create/reset/resize/destroy factory pattern as `earth-globe.js`):
  zone-colored states, hover tooltip, click-to-select, confirm bar, legend,
  plus `setZoneFilter()` (dims non-matching states + fits bounds) and
  `clearSelection()` for the wizard's Zone→State handoff.
- `static/js/location_select.js` (`QMLocationWizard`) — the step-by-step
  Zone → State → District → Tehsil → Village wizard: numbered progress
  header, click-a-completed-step-to-edit-and-clear-dependents, map+cards
  for Zone/State, search+cards for District/Tehsil/Village, and the
  summary screen with per-level Edit links.
- `static/css/register.css` — wizard + kundali display styles, using the
  brief's Visual Design Notes element colors (Fire `#FF9933`, Earth
  `#138808`, Air `#F8FAFC`, Water `#0A1929`, Space `#FFD700`/`#6B21A5`).
- `static/css/india_map.css` — the Leaflet map + step-wizard styling.

**Data**
- `static/data/global_countries.json` / `india_states.json` / `global.json`
  — see `scripts/parse_world_data.py` / `scripts/extract_india_states.py`.
- `static/data/world_borders.geojson` (170 countries, ~200KB) — see
  `scripts/build_world_borders.py`.
- `static/images/earth_texture.png` (2048×1024, ~70KB) — see
  `scripts/build_world_texture.py`. Re-run both scripts (borders, then
  texture) if `global_countries.json` or the Natural Earth source changes.
- `static/data/india_states.geojson` (37 states, ~190KB) — see
  `scripts/build_india_states_geojson.py`.
- `static/data/india_districts_tehsils.json` (635 districts, 5,971
  tehsils, ~250KB) — see `scripts/extract_india_districts_tehsils.py`.
- `india_villages` SQLite table (621,057 rows, indexed by `tehsil_id`) —
  see `scripts/import_india_villages.py`. Not a static file — queried
  per-tehsil on demand (see "India Map & Location Selection Tool" above).

## Known simplifications (flagged, not hidden)

- Ascendant/houses use a location *centroid*, not an exact birthplace —
  see "Zodiac & kundali architecture" above.
- 7 of 177 Natural Earth features didn't match a Qumanity country id
  (Antarctica, W. Sahara, Greenland, and disputed territories) — they
  render in a neutral gray on the texture but aren't clickable/selectable.
- "District" and "Tehsil" are SITAXML's real administrative divisions, not
  verified Lok Sabha/Vidhan Sabha constituencies — see "India Map &
  Location Selection Tool" above.
- Village names came through the Zone/State/District/Tehsil chain
  correctly, but 482 village ids repeat in the source XML itself (~0.08%
  of 621,057 rows) — a real source data-quality issue, not an import bug.
- No Private ID / Account ID *string* generation yet — the `users` table
  has the columns, left null. The format is specified in the original
  brief; `identity_core.py` on the real platform has a working reference.
  The real location *path* (e.g. `CS.CH.1.1.1`) is already produced
  end-to-end by the wizard and is the input that ID string would consume.
- No login/session/auth — `/kundali/<id>` is a bookmarkable link, not an
  authenticated account page. The Login button is still a stub.
- `location_elements` percentages are only as meaningful as the sample
  size — the seed data is whatever you register through the wizard.

## Next phases (not built here)

1. Private ID / Account ID string generation (name initials, gender/age
   codes, zodiac element/sign, location path) — adapt from the real
   platform's `identity_core.py`. The location *path* itself is already
   available end-to-end (e.g. `CS.CH.1.1.1` for Chandigarh → Behlana);
   only the ID string format (prefix/initials/codes) remains.
2. A real login/session system so `/kundali/<id>` becomes an authenticated
   "your account" page instead of a bookmarkable link.
3. Swap the static JSON files for a real `location.db` import (SITAXML +
   World Data), or point straight at the existing platform's
   `global_core.py` / `/api/locations/children` API.

## License

Qumanity is licensed under the GNU Affero General Public License v3.0. See LICENSE for details.
