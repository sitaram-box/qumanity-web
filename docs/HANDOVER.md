# Qumanity — Project Handover

**Refreshed 2 November 2026**, as the final documentation consolidation at the end of the current
website feature-development phase, before the project moves on to the phone application
(`qumanity-app`). This is a full rewrite, not an appended note — the prior version (last touched
25 October 2026) was reorganised and most of it rewritten so a new developer can understand the
*current* system without needing old chat transcripts. Historical architectural decisions and
"gotchas" that remain true were kept; stale claims were corrected or removed and are called out
explicitly where correcting them matters.

This is a snapshot, not a replacement for the detailed design docs already in this folder (linked
throughout). It will go stale as the code moves — treat it as a map, not a permanent source of
truth for exact current state. Where a figure in this document was taken from a fresh, live check
in this session, that is stated; where it is carried over from an earlier pass, that is stated too.

---

## 1. Project overview and current phase

Qumanity (**Quantum + Humanity**) is a civic participation platform organised around **eight
nested geography levels** — Village, Tehsil, District, State, Zone, Country, Continent, Earth (see
§4). Each level has a Collective Board where residents post and vote, and (where elections have
actually reached that level — currently village only, piloted in one location) a council elected
through zodiac-sign cycles. Members get a verified identity (a 9-digit Private ID + 5-character
PIN, no email required), a Qoin wallet earned through civic service, and a Karma score that is
never convertible to Qoins.

**Current phase**: this document marks the end of the current **website feature-development
phase** (`qumanity-web`, this repository). The next phase is the **phone application**
(`qumanity-app`), which must integrate with the backend documented here rather than redefining
identity, geography, consent, or location IDs on its own — see §15.

**Repository state at this handover** (verified fresh, not carried over):
- Branch `main`. Local `HEAD` and `origin/main` both at **`6b8e5b5`** — `feat: add Q-Map Leaflet
  rendering with OSM pilot data` — confirmed identical by `git fetch` + `git rev-parse` in this
  session, i.e. this is genuinely the tip of `main`, not an assumption carried over from an older
  note.
- **Fresh regression run, this session: 1,380 checks across 30 test files, 0 failures.** This
  supersedes the previously reported "1,378 across 30 files" figure — `tests/test_qmap.py` alone
  has 33 checks, not 31, and the other 29 files' counts were re-confirmed unchanged. See §11 for
  the full per-file table and how to reproduce it.
- The working tree also carries **pre-existing, unrelated uncommitted changes** from other,
  independently-scoped work (`db.py`, several `folder_export/Earth/*.json` mirror files,
  `tests/test_post_kinds.py`, and a number of untracked location-data scripts, `Poems/` content
  staging, and research docs). None of these were touched, staged, or committed by this
  documentation pass — see §14.

---

## 2. Technology stack and repository structure

- **Backend**: Python 3, **Flask**, **SQLite**. Business logic lives in modular `*_core.py` files
  at the repo root (e.g. `wallet_core.py`, `family_core.py`, `osm_proximity_core.py`), each with
  its own `SCHEMA` string and `ensure_tables(conn)`. `app.py` holds every page route, every
  `/api` route, startup wiring, and session/auth — it is large and central by design, not an
  oversight.
- **Frontend**: server-rendered **Jinja templates** (`templates/`), plain JavaScript
  (`static/js/`), plain CSS (`static/css/`). No front-end framework, no build step. The only
  third-party JS libraries in the project are **Leaflet** (maps) and **three.js** (the homepage
  globe), both loaded via pinned-version CDN `<script>` tags — the precedent for how any future
  library would be added, should one genuinely be needed.
- **Astronomy** (zodiac cycles, Kundali) is computed locally via `pyswisseph`'s built-in Moshier
  ephemeris — no external service, no data files to maintain.
- **Email**: Resend's HTTPS API (`email_core.py`) — not SMTP. (An earlier DPG evidence document
  still described SMTP; this is one of the stale claims corrected in §10.)
- **One backend serves both this website and the phone app** through the same `/api` routes — the
  app authenticates with a signed bearer token, the website with a signed session cookie, and a
  valid token is treated exactly like a session.
- Full architecture detail: `docs/ARCHITECTURE.md`. Every route: `docs/API.md`. Every table:
  `docs/DATA_MODEL.md`. **These three files are known to have drifted behind the actual code** as
  of this handover (confirmed in `docs/audit_dpg_unfinished_features_2026_11.md`, an untracked,
  not-yet-authorized research document from 2026-11-01) — do not treat their route/table counts as
  current without re-checking. Updating them is listed as unresolved work in §13.

### Repository structure (top level, relevant to this phase)

```
app.py                     All routes, session/auth, startup wiring
db.py                      SQLite connection handling (DB_PATH binds at import time)
*_core.py                  One module per subsystem's business logic + schema
migrations/                NNN_description.{sql,py}, applied by tools/run_migrations.py
templates/                 Jinja templates, one per page (no shared layout)
static/css/, static/js/    Plain CSS/JS, one file per page/feature, no bundler
static/data/               Geography master data and derived datasets (see §4)
tests/                     Standalone PASS/FAIL scripts, one per subsystem (see §11)
docs/                      This handover, status tracker, whitepaper, and ~70 other design docs
docs/dpg_evidence/         The DPG Standard evidence pack (see §10)
scripts/                   One-off data-maintenance and research scripts
Poems/                     Marquee religious-text content files (see §9)
```

---

## 3. Application architecture

- **Migrations**: `migrations/NNN_description.{sql,py}`, applied by `tools/run_migrations.py`,
  tracked in a `migrations` table. `app.py`'s `ensure_database_ready()` runs the base schema, each
  module's own tables, and every migration on every boot — no manual step. **Current range: 001–003,
  007–035** (verified by listing `migrations/` fresh this session; 035 is `osm_proximity.py`, the
  most recent).
- **Table count**: **96 tables on boot**, counted fresh this session against a freshly-migrated
  throwaway database (not estimated from an older doc — the previous handover's "74 on boot" figure
  is stale and superseded). A small number of additional tables are created on first use rather
  than on boot (e.g. `chat_read_state`, `election_cycle_config`) — not recounted individually this
  pass. Full list with purposes: `docs/DATA_MODEL.md` (itself drifted — see §2).
- **Scheduler jobs** (APScheduler, `BackgroundScheduler`): daily folder sync, daily lunar-pipeline
  tick, the Post Testing cycle's monthly post/weekly vote jobs, the election-test daily tick
  (`election_test_scheduler.py`), and the provisional-location reconciliation job
  (`provisional_location_core.init_scheduler`). `QM_DISABLE_SCHEDULER` turns all of them off —
  used in every test run.
- **The membership rule that matters most**: a user counts toward the total members of exactly one
  location — their **present residence** (`users.present_location_json`), set only by an explicit,
  user-initiated action, never GPS/IP/a scheduled job. `location_elements.total_users` is
  present-location-keyed. `location_elements.birth_users` is separate, metadata-only — never
  counted toward membership, voting, or participation. This rule is also the input to Q-Punch
  address generation (§9) and to the provisional-location activation threshold (§6) — a location's
  real member count is the single source every subsystem that counts "who lives here" depends on.

---

## 4. Geography hierarchy and master data

Eight nested levels, in order: **Village → Tehsil → District → State → Zone → Country → Continent
→ Earth.** Every member, post, council seat, and governance mechanism in the project is scoped to
one of these levels.

- **Canonical source**: `Qumanity_Master.json`, a non-git-tracked file on the owner's own machine
  (outside this repository, under `~/Desktop/0_Earth/`). It is the authoritative geography source
  — not a script-generated artifact — and derived datasets (`static/data/subcontinent_districts.json`,
  `static/data/india_districts_tehsils.json`, the `india_villages` table) are read-only reflections
  of it for the application to query quickly.
- **Geography IDs are stable, load-bearing identifiers** — dotted codes like `CS.DL.3.4.1A`. **No
  renumbering, reparenting, or deduplication without an approved migration and crosswalk.** This is
  a hard rule, not a style preference: these IDs are embedded in `users.present_location_json`,
  `users.birth_location_json`, board posts, council addresses, and more. A proposed
  `location_id_history` crosswalk table schema exists (`docs/location_id_crosswalk_schema.md`) but
  is **not built and not populated** — schema only.
- `Qumanity_Master.json` **is** authored by in-repository, one-off scripts
  (`scripts/add_navi_mumbai_locations.py`, `scripts/add_ganesh_pura_tri_nagar.py`, and similar),
  each with its own backup-then-write convention — this corrects an earlier documentation claim
  that no script in the repository writes to it.
- **India location deduplication remains proposal-only.** A full national audit
  (`scripts/audit_all_india_duplicates.py`) found **74 Tehsil-level and 15 Village-level duplicate
  groups nationally, 0 at State/District level**, across all 37 States/UTs. One pair (Bawana,
  `CS.DL.3.4`/`CS.DL.3.E`) has been resolved **only in the two derived JSON files**, not in
  `Qumanity_Master.json` itself — this was a narrow pilot correction, not a nationwide
  deduplication. `docs/india_dedup_migration_plan.md` is explicitly marked **AWAITING APPROVAL —
  DO NOT EXECUTE**. At least one open case (Tri Nagar) has real user references on both candidate
  survivor IDs, so the remaining groups cannot all be resolved the same way Bawana was. **No
  further deduplication is authorized.**
- `~/Desktop/0_Earth/` and its archived materials (`~/Desktop/0_Earth_Archive/`) have established
  preservation constraints — the live tree must never be restructured or deleted without being
  asked, and no filesystem changes were made to it during this documentation pass.
- `scripts/edit_master_location.py` is a safe, tested, but **uncommitted** single-record
  add/rename/remove tool (hex-suffix ID validation, duplicate prevention, a full 16-table reference
  audit before any removal, backup + SHA-256 + atomic write). It is a tool for making one
  controlled edit at a time, not a bulk deduplication mechanism.

---

## 5. Main application modules and their implementation status

Status as verified in this session (git state + direct code inspection), not carried over from an
older summary.

| Module | Status | Notes |
|---|---|---|
| Collective Board (post/vote/escalation) | ✅ Implemented | `board_core.py` |
| Citizen Reports | ✅ Implemented | 10-day SLA, `docs/reports_design.md` |
| Zodiac Council elections | 🟡 Piloted, one village | Rohini Sector 24 only; see §9 |
| Karma | ✅ Implemented | Never convertible to Qoins, by design |
| Qoins wallet | ✅ Implemented | Payments fully removed; `qoin_core.py` |
| Qmail (internal messaging) | ✅ Implemented | Retention/delete-on-request still pending |
| Q-Punch council addresses | ✅ Implemented, village-only reachable | See §9 |
| Admin Panel | ✅ Implemented | Council-scoped queue |
| Referral engine (registration attribution + bonus) | ✅ Implemented | Distinct from the separate, unfinished board-level referrer-code system — see `docs/dpg_evidence/13_referral_engine_evidence.md` |
| Family Tree (Nuclear Family Node model + cascade + grandparent backfill) | ✅ Implemented & committed | See §8 |
| Dashboard (multi-view layout, Stats Modal) | ✅ Implemented | Not touched by this documentation pass |
| Multi-religion Marquee | ✅ Infrastructure implemented; content partially rights-cleared | See §9 |
| Provisional Locations (crowdsourced location MVP) | ✅ Implemented | See §6 |
| OSM Proximity (backend) | ✅ Implemented | See §6 |
| Q-Map (public map UI) | ✅ Implemented & committed, `6b8e5b5` | See §7 |
| Perception Calculator | ✅ Implemented | 10 countries + an India zone, no State-level |
| Notifications | ✅ Implemented, read-time aggregation only | `notify_core.py` synthesizes notifications by querying existing unread-message/reply state — there is no durable, independently-written notification log |
| Report / Block member | ❌ Not built | Named gap; see §13 |
| Privacy Policy / Terms of Service pages | ❌ Not built | Registration links to `#`; named gap, see §13 |
| "Export my data" / "Delete my account" | ❌ Not built | Named gap; see §13 |

---

## 6. Provisional Locations and the Crowdsourced Location System

**Why it exists**: a member registering their birth or present location may find their real
Village or Tehsil missing from the verified directory (`static/data/subcontinent_districts.json`
and India's deeper tiers). Provisional Locations are a controlled fallback so that member can still
register, without inventing a fake verified ID or forcing a manual geography edit before they can
sign up.

**Module**: `provisional_location_core.py` (~700 lines), migration `034_provisional_locations.py`,
tests `tests/test_provisional_locations.py` (76 checks, confirmed current). The module's own
docstring describes three strictly separate data layers:

1. **Layer A, the VERIFIED directory** — `static/data/subcontinent_districts.json` /
   `india_districts_tehsils.json` / the `india_villages` table. Read-only here; the canonical
   Master JSON is never written to by this subsystem.
2. **Layer B, PROVISIONAL submissions** — `provisional_locations`, `provisional_location_members`,
   `location_submission_events`.
3. **Layer C, GPS observations** — `user_location_observations`, `location_centroid_observations`.

A provisional location's id is never a verified-style dotted code — it is always exposed as the
string `"PROV-<row id>"` wherever it needs to sit inside `present_location_json`, so the rest of
the app's location-reading code keeps working unmodified.

### The four distinct concepts, defined precisely

- **A user GPS observation** (`user_location_observations` row): one consented or declined capture
  of a member's device coordinates at one point in time, with its own `status`
  (`pending`/`accepted`/`rejected_outlier`/`denied`/`unavailable`/`withdrawn`). Only `accepted`
  rows ever carry a real, non-null coordinate.
- **An OSM feature match** (`user_osm_proximity` row, written by `osm_proximity_core.py`, §6
  continued below): a link between one *accepted* GPS observation and a nearby real-world OSM
  feature (road/building/POI) found within 200 metres — entirely independent of whether that
  observation is also tied to a provisional location.
- **A provisional location** (`provisional_locations` row): a candidate Village or Tehsil the
  verified directory does not yet contain, with a `status` lifecycle
  (`provisional → eligible_for_activation/pending_review → active`, or `rejected`/`merged`/`inactive`)
  and a count of qualifying present-resident members.
- **A canonical Qumanity location**: a row that exists in `Qumanity_Master.json` with a real,
  stable dotted ID (e.g. `CS.DL.3.4.1A`) — the only kind of location ID the rest of the platform
  (board posts, council addresses, Q-Punch, member counts) ultimately depends on being stable.

### What the "24-user threshold" actually does

`activation_threshold()` (`provisional_location_core.py:151`) returns the value of
`QM_PROVISIONAL_LOCATION_THRESHOLD`, defaulting to **24** qualifying present-resident members (a
"qualifying" member is a real, non-demo, non-removed account — `is_qualifying_user()`).

Once a provisional location's live qualifying-member count reaches this threshold,
**`evaluate_activation()`** (`provisional_location_core.py:462`) — the single, controlled place
that is ever allowed to set `status = 'active'` — runs two further checks before promoting it:

1. A **village** whose parent is itself only a provisional (not-yet-active) tehsil is held at
   `pending_review` rather than activated, so a village can never outrun its own tehsil.
2. A **duplicate check**: if another provisional location with the same normalized name under the
   same parent is already `active`, this one is held at `pending_review` instead (it should have
   been merged, not independently promoted).

If both checks pass, the row is updated to `status = 'active'`. **This is an automatic promotion
within the provisional-location system itself — it is explicitly NOT a promotion into the
canonical `Qumanity_Master.json` geography.** The schema's own `activated_as_verified_id` column
exists for a future manual step that would assign a real, stable, canonical ID once/if a
provisional location is folded into the authoritative master file — **no code anywhere currently
writes that column**. This separation is itself the control that prevents a provisional location
from silently becoming authoritative: reaching 24 members makes a location real and usable
*within the provisional system*, never an automatic edit to the canonical geography file.

`reconcile_all()` is the background half of this (a scheduled job, disabled under
`QM_DISABLE_SCHEDULER`) — it re-evaluates every non-terminal provisional location in bounded
batches, catching anything a single registration's immediate check might have missed.

**Relationship to OSM proximity**: GPS observations (`user_location_observations`) are shared
infrastructure between the provisional-location system and `osm_proximity_core.py`. Consent fields
on each observation (`consent_internal_storage`, `consent_centroid_aggregation`,
`consent_external_overpass_lookup`) gate what each subsystem is allowed to do with it
independently — a location-fallback submission does not automatically authorize an OSM proximity
lookup, and vice versa.

---

## 7. Location and mapping architecture

### 7.1 OSM Proximity (backend)

**Purpose**: link a consenting member's own accepted GPS observation to nearby real-world OSM
features (roads, buildings, points of interest such as hospitals), entirely server-side, with no
raw coordinates ever exposed in a public response.

- `osm_http_core.py` — the shared, rate-limited Overpass HTTP layer (backoff, User-Agent,
  `Retry-After` handling), reused (not duplicated) from the earlier `scripts/
  fetch_north_west_delhi_osm.py` pilot script.
- `osm_proximity_core.py` — schema (`osm_proximity_jobs`, `osm_feature_cache`,
  `user_osm_proximity`), consent-gated job enqueueing, the proximity-matching worker, withdrawal,
  and `get_user_nearby()` (the function that ultimately serves Q-Map's own data).
- `osm_proximity_worker.py` — a standalone CLI that claims pending jobs and processes them against
  the live Overpass API, in small batches with real throttling. **This worker is the only part of
  the whole OSM-proximity/Q-Map feature set that ever makes a live Overpass request.** It runs as
  its own scheduled/manual process, never inline with a user-facing request.
- **200-metre radius**: a matched feature must be within 200 metres of the accepted observation's
  coordinate (`_nearest_distance_meters()`), node- or way-geometry aware.
- **Fresh, re-confirmed consent required**: `provisional_location_core.CONSENT_VERSION` was bumped
  specifically so this feature never retroactively queries an observation accepted under an older
  consent wording — a stale "when this service becomes available" consent is never silently
  treated as covering a live Overpass lookup.
- **`GET /api/qmap/user-nearby/<user_id>`** (`@login_required`): `session.get("user_id") !=
  user_id → 403`. A member can only ever read their own proximity data; this is the real
  authorization boundary, independently re-verified by `tests/test_osm_proximity.py` and again by
  `tests/test_qmap.py`.
- **Raw GPS coordinates are never returned** by `get_user_nearby()` — only `osm_type`, `osm_id`,
  `category`, `distance_meters`, a safe tag subset, and attribution. This is a deliberate
  privacy-by-design choice, confirmed directly in the function's own code and by a dedicated test
  assertion that no response key is ever `lat`/`lon`/`latitude`/`longitude`.
- **Rate limiting / safeguards**: Overpass's own 429 responses are honored via `Retry-After`
  backoff in `osm_http_core.post_overpass()`; the worker processes small batches, never a burst.
  **Known, flagged operational risk**: querying the public Overpass API per user at production
  scale risks violating its fair-use policy — this should be revisited (possibly a self-hosted
  mirror) before this becomes a volume feature; not yet addressed.
- **Stored proximity results vs. live querying**: `user_osm_proximity` rows are the *stored*,
  already-matched result of a worker run. Nothing in the Q-Map page or its API ever triggers a new
  live Overpass query — see §7.2.

### 7.2 Q-Map (the public map UI) — ✅ Implemented & committed, `6b8e5b5`

**Route**: `GET /qmap` — public, no login required for the base pilot map. Files:
`app.py` (the `/qmap` route), `templates/qmap.html`, `static/css/qmap.css`, `static/js/qmap.js`,
`static/data/pilot/north_west_delhi_osm.geojson`, `tests/test_qmap.py` (33 checks). A nav link was
added to `templates/home.html`'s existing footer "Account" column — the Dashboard and its Stats
Modal were deliberately not touched.

**Pilot dataset**: `static/data/pilot/north_west_delhi_osm.geojson`, re-counted fresh this session
at **25,365 features, ~22.3 MB on disk** — 10,810 road features (LineString), 14,500 building
features (Polygon), 56 hospital features (49 Point + 7 Polygon). **This is a North West Delhi
pilot, explicitly not a complete India-wide OSM dataset** — the file is committed directly to git
(no LFS needed at this size) for production deployment.

**Rendering**: Leaflet 1.9.4 (the same version already used across the rest of the site via a
pinned unpkg CDN — no second Leaflet version was introduced), an OSM raster tile basemap, and three
independently toggleable `L.layerGroup()` overlays built from the pilot GeoJSON's own
pre-classified `properties.categories` (derived from real OSM tags — `highway=*`, `building=*`,
`amenity=hospital` — never geometry type alone). Roads and Hospitals are visible by default;
Buildings starts off (14,500 polygons is heavy to render immediately) and can be switched on via
the layer control. A hospital represented as a Polygon gets both its outline and a centroid marker
(`layer.getBounds().getCenter()`) so every hospital gets a consistent marker regardless of source
geometry.

**User GPS/proximity layer** (signed-in members only):
- The `/qmap` route itself reads the member's own most recent `status='accepted'` row from
  `user_location_observations` server-side and passes it into the page as the initial map center —
  a narrow, read-only exception to "no new data API route," matching this project's existing
  pattern for per-session personalization (compare `api_poems_meta()`). It is **not** a new JSON
  API endpoint.
- The page's own JS then calls the **existing** `GET /api/qmap/user-nearby/<user_id>` for the
  actual linked-feature list, using only the session's own id — never a client-editable value.
- The member's own marker never displays raw coordinate text; its popup summarizes linked feature
  categories only ("Linked nearby: 1 road, 1 building…"), confirmed live in this session's browser
  verification.
- No GPS/no linked-feature states show the exact friendly messages specified for this feature
  ("Register your present location and share GPS to see your map.", "Your OSM proximity data is
  being prepared. Please check again later.") — never a fabricated `0,0` center, and never a
  silently empty map.
- Confirmed live, this session: zero Overpass requests are ever made from the Q-Map page (network
  inspection); the pilot GeoJSON is fetched exactly once per page load from the local static URL.

### 7.3 Public base map vs. private user data — the privacy line

**The pilot base map (roads, buildings, hospitals) is public and visible to every visitor, signed
in or not.** A member's own GPS location and their own OSM-linked proximity features are private
and restricted to that member's own authenticated session — never exposed to another user, never
exposed to an anonymous visitor, and never queryable by a different user's id (independently
re-verified: a 403 for a mismatched `user_id`, confirmed again this session). Do not confuse public
map *visibility* with public access to personal location *data* — they are deliberately kept on
opposite sides of the login wall.

---

## 8. Family Tree architecture

Full design history: §4.12–§4.18 of the prior handover version (preserved in git history, retained
here in condensed form) and `docs/dpg_evidence/12_family_tree_evidence.md`.

- **A `family_groups` row is a marriage unit, not a generic container** — it names its two founders
  directly (`husband_node_id`/`wife_node_id`), plus each founder's own parent unit if known
  (`husband_parent_group_id`/`wife_parent_group_id`), plus `marriage_status`. `family_spouse_links`
  is deprecated (a marriage *is* the unit's own husband/wife pair now).
- **One unit's own immediate neighborhood is rendered at a time** (`GET
  /api/family/node/<group_id>/neighborhood`) — up to 2 parent units above, the current unit in the
  middle, its children below. No `d3.hierarchy()`/`d3.tree()` layout algorithm — a unit is already a
  couple, so there's no DAG left to flatten.
- **Automatic family membership cascade** (`_sync_family_membership()`): a person's active
  membership in the units around them (birth unit, in-laws, grandparent units) is a **live-computed
  function** of the tree's current shape, never a set of one-off grants — bounded to four fixed
  rules, not a general recursive walk.
- **Grandparent backfill (Option B)** — ✅ **committed**, `family_core.py` (commit `0a8ab5b`,
  confirmed clean/committed in this session's `git status`):
  - `GRANDPARENT_BACKFILL_MAX_GENERATIONS = 2` — a **strict, hard-coded cap**, not configurable.
  - `_backfill_parent_group_links()` performs a **breadth-first walk by hop count**, discovering and
    writing `husband_parent_group_id`/`wife_parent_group_id` wherever currently `NULL` but a real
    link can now be established, walking up to 2 additional hops above the starting unit.
  - **Cycle-safe**: a `_visited` set (shared across one call) means a group can never be processed
    twice, even across a pathological loop in the data.
  - **Idempotent**: safe to call repeatedly; a group already linked is a no-op.
  - **Direct-roster-only, by construction**: backfilling a parent-group *link* does not, on its
    own, grant anyone new membership beyond what the existing direct-roster cascade already
    exposes for each newly reached group — it was built and reviewed this way specifically to avoid
    being an unrestricted ancestor-crawling/discovery system. Its one real, documented consequence
    is that it extends `_is_admin_of_group()`'s own dormant-ancestor-succession reach one hop
    further once two groups become linked.
  - This is **not** unrestricted family-tree crawling: it walks at most two generations beyond the
    unit that triggered it, and only ever follows an existing, already-known parent-link path — it
    never invents a relationship.
- **Profile Card UI**: every person node is clickable (`ft-profile-modal`), combined name/gender/age
  editor. Backend routes for this were already committed earlier; by this handover the frontend
  pieces (`templates/dashboard.html`, `static/css/dashboard.css`, `static/js/family.js`,
  `static/js/family_tree.js`) are also part of the `e7490db` commit — confirmed clean in `git
  status` this session, i.e. no longer the "uncommitted" state an earlier status snapshot recorded.

---

## 9. Religious Marquee and content licensing; Q-Punch and nested governance

### 9.1 Multi-religion Marquee

**Architecture** (`religious_text_core.py`): **four tables**, not five —
`religious_traditions` → `text_collections` → `text_collection_languages` → `text_entries`. (An
earlier 4-workstream proposal also specified a fifth table, `religion_collection_access`, for a
future many-to-many religion↔collection relationship — it was deliberately not built; revisit only
if a real need for many-to-many access arises.)

- Each collection is individually gated by `rights_status`/`review_status`/`marquee_eligible`; only
  a `review_status='approved' AND marquee_eligible=1` row is ever resolvable
  (`resolve_collection()`). A collection with no eligible row returns `None`, surfaced to the
  client as `coming_soon` — never substituted or invented content.
- **Profile religion vs. reading preference**: a signed-in member's reading religion defaults to
  their own profile religion, but can be switched to any other approved, content-backed tradition
  via an allowlist-checked query parameter on the existing `/api/poems/meta` /
  `/api/poems/<lang>/<index>` routes — no new route was added. This reading choice is stored
  **client-side only** (`localStorage`) and **never writes `users.religion_belief`** — verified
  directly against the database.
- **Anonymous/default behavior**: every logged-out visitor, and any member with no profile religion
  set, sees Hindu/Hindi content by default (`DEFAULT_MARQUEE_RELIGION = "hindu"`).
- **Hide/Show Marquee**: a persisted per-user preference (`users.hide_marquee`, migration 033).
- **Original Qumanity content vs. externally sourced texts**: the Hindu tradition's default content
  is **original Qumanity Hindi poetry** (`Poems/hindu_original/poems_hindi.json`), not a Gita
  Press/Vinaya Patrika transcription — those original poems must never be attributed to Gita Press
  or labeled Vinaya Patrika.

**Currently live collections** (verified against the committed database-seeding code and the
`Poems/` directory this session):

| Tradition | Collection | Language(s) | Rights basis |
|---|---|---|---|
| Hindu | Original Qumanity Ram-bhakti poetry | Hindi | Original Qumanity content |
| Christian | Psalms | English (KJV, public domain) + Hindi (selected 8 verses, Biblica Open Hindi Contemporary Version, CC BY-SA 4.0 — a **derivative excerpt, not a complete Bible**) | Mixed — see licensing note below |
| Muslim | Quran, Surah Al-Fatiha | Arabic | Tanzil Project, CC BY 3.0 |
| Buddhist | Dhammapada ch. 1, vv. 1–5 | Pali + English (Max Müller, 1881, public domain/Project Gutenberg) | Public domain |

**Licensing note on the Christian Hindi collection**: it is treated as a derivative work under CC
BY-SA 4.0 (eight selected, reformatted verses — not an unmodified full copy). The Biblica®
trademark is never used in Qumanity's own UI/docs for this collection; the license's own
attribution wording is used instead: *"The original work by Biblica, Inc. is available for free at
www.biblica.com and open.bible."*

**Not yet available — pending rights review** (code-complete, content blocked — **do not present
any of these as approved or available**):

| Area | Status |
|---|---|
| Urdu Quran | Tanzil contact route not yet located; translator's own rights still under copyright through 2033 |
| Sikh Gurbani | A real contact route for Khalis Foundation was found; permission not yet requested/granted |
| Hindi Dhammapada | A plausible-public-domain 1933 translation found, but conflicting license tags on existing scans and the US/URAA question are unresolved |
| Jain texts | Dedicated source research required; no translation yet cleared for any Jain sub-tradition |
| Gita Press / Vinaya Patrika | `not_permitted` — no verified publication permission has been established; distinct from the four `pending_rights_review` items above |

Full research trail and prepared (unsent) outreach drafts: `docs/marquee_religious_text_sources.md`
and `docs/marquee_rights_roadmap.md`. **A religion or language is never marked content-complete
merely because the database infrastructure can support it.**

**Public notice page**: `/copyright/religious-texts` covers all six current rights questions,
clearly distinguishes available collections from pending ones, and links Qumanity's own verified
contact plus the verified third-party contact routes found during research. `/copyright/gita-press`
is a separate, pre-existing copyright/attribution notice — not a grant of publishing rights.

Tests: `tests/test_poems_marquee.py` (226 checks), `tests/test_copyright_pages.py` (37 checks,
covers both notice pages).

### 9.2 Q-Punch and nested geography

The eight-level hierarchy (§4) is also the governance structure: **Q-Punch council addresses**
(`<level>-<location_id>@qumanity.in`) let a resident write to their own level's council. A
location gets one **permanent** row in `qpunch_addresses` (`qmail_core.py`) the first time its real
member count reaches its level's threshold — never retired or reactivated afterward, even if the
count later drops.

**Current reachability is strictly village-only**, confirmed directly in code this session:

```python
# qmail_core.py:45
QPUNCH_REACHABLE_LEVELS = {"village"}
```

Address *rows* are created for village and tehsil once their member-count thresholds are crossed
(`QPUNCH_THRESHOLDS`, `qmail_core.py:30`), but **only an address at a reachable level can actually
receive a message** — `resolve_address()` and the board-line renderer both read
`QPUNCH_REACHABLE_LEVELS` as their one shared gate. Council addresses above village (and a tehsil
address, despite existing as a row) are created and shown, but cannot receive messages, because no
elected councils exist above village yet. Do not describe Q-Punch as already operating at all
eight levels — the architectural *vision* is eight levels; the current *implementation boundary* is
one.

A council message is never delivered into a member's personal Qmail inbox — it goes into a
separate, shared, location-keyed queue (`qpunch_queue_messages`), read only through the Admin
Panel's council-scoped view.

---

## 10. DPG evidence and documentation

The DPG Standard evidence pack lives at `docs/dpg_evidence/` (11 numbered indicator documents +
a Forward Plan + application-form-answers compilation + copies of `API.md`/`ARCHITECTURE.md`/
`DATA_MODEL.md`). Its master working copy is a non-git directory on the owner's own machine;
`docs/dpg_evidence/` inside this repository is a copy, changed only when the owner asks for it.

**What "frozen" means here**: every document in the pack explicitly marks itself, in its own
banner, as *"DPG Evidence Refresh — internal correction pass, not a DPGA resubmission."* **No
document in this repository claims formal Digital Public Goods certification, DPG Registry
acceptance, or external endorsement** — the pack is internal evidence-preparation and
self-assessment work, written so a reviewer *could* use it to assess the project against the DPG
Standard's 9 indicators, not a record of a completed registry submission or an award received.

**Application form answers** (`docs/dpg_evidence/11_application_form_answers.md`, verified fresh
this session): **40 of 45 fields marked "Ready"**; the 5 still open are the privacy policy URL,
data export/delete, and the moderation/harassment (Report, Block, minimum age) fields — these
track directly to the same unresolved gaps listed in §13.

**Forward Plan** (`docs/dpg_evidence/10_forward_plan.md`): a prioritized, dated gap-closure list
across code gaps, legal/entity gaps (LLP registration, trademark filing, copyright assignment —
still pending), and a repository public-flip checklist (completed). It is explicitly marked "not a
required DPG document" — a supplement for a reviewer's benefit, not part of the Standard itself.

**A known, material staleness finding — not corrected by this documentation pass, flagged for
separate authorization**: an untracked research document,
`docs/audit_dpg_unfinished_features_2026_11.md` (2026-11-01, read-only, not yet committed),
establishes that:
- `docs/dpg_evidence/ARCHITECTURE.md` has **diverged** from the main `docs/ARCHITECTURE.md` by 16
  lines (missing `family_core.py`/`profile_picture_core.py` rows and an understated migration
  range) — the pack's own claim that these copies match "byte for byte" is stale.
- **Family Tree and the Referral Engine are both absent from every `dpg_evidence/` document** —
  `01_sdg_relevance.md`'s feature inventory and `DATA_MODEL.md`'s table list do not mention either
  subsystem, even though both are substantial, committed features.
- `01_sdg_relevance.md` still describes the election-test cron as "planned, not built" — it is in
  fact wired and running (`election_test_scheduler.py`).
- `08_standards.md` still describes SMTP email delivery — the code uses Resend's HTTPS API
  exclusively.

**This documentation pass did not correct the `dpg_evidence/` pack itself** — per this task's own
operating rules, the frozen evidence pack is not silently rewritten to appear more complete; a
re-sync of the pack against current code is recommended as its own, separately authorized task
(see §13).

---

## 11. Testing and verification

**No single aggregate test-runner command exists in this repository.** Each file in `tests/` is a
standalone script using a shared convention: a disposable tempfile SQLite database set via the
`QM_DB_PATH` environment variable **before** importing `app` (required — `db.py`'s `DB_PATH` binds
at import time), a `check(label, cond)` helper that prints `[PASS]`/`[FAIL]`, and `sys.exit(1)` on
any failure. Run one file directly:

```bash
python3 tests/test_qmap.py
```

To run the full regression and get a real total, iterate every file and tally:

```bash
for f in tests/*.py; do python3 "$f" || echo "FAILED: $f"; done
```

**Fresh result, this session (2026-11-02): 30 files, 1,380 checks, 0 failures.** Per-file counts:

| File | Checks |
|---|---:|
| test_account_id_sync.py | 13 |
| test_admin_panel_council_scope.py | 40 |
| test_avatar_sweep.py | 14 |
| test_copyright_pages.py | 37 |
| test_council_updates.py | 17 |
| test_edit_master_location.py | 33 |
| test_election_test_scheduler.py | 31 |
| test_email_core.py | 46 |
| test_family_tree.py | 211 |
| test_family_tree_cascade.py | 115 |
| test_fetch_north_west_delhi_osm.py | 47 |
| test_fix_haryana_districts.py | 30 |
| test_group_members.py | 22 |
| test_identity_correction.py | 41 |
| test_import_india_villages_verify.py | 5 |
| test_india_geography_classification.py | 22 |
| test_osm_proximity.py | 44 |
| test_poems_marquee.py | 226 |
| test_post_kinds.py | 55 |
| test_provisional_locations.py | 76 |
| test_qmail.py | 32 |
| test_qmail_activation_diagnostics.py | 17 |
| test_qmail_attachments.py | 30 |
| test_qmail_drafts.py | 29 |
| test_qmail_format_extraction.py | 18 |
| test_qmail_page.py | 8 |
| test_qmap.py | 33 |
| test_qpunch.py | 25 |
| test_referral_engine.py | 12 |
| test_reply_read.py | 51 |
| **Total (30 files)** | **1,380** |

### Practical setup and development instructions

- **Environment**: Python 3 with Flask, no other framework. `.claude/launch.json` has working dev
  server configurations (`python3 app.py` on various ports); `QM_TEST_PIN` is the documented dev
  fixture PIN for locally created test accounts.
- **Running locally**: `python3 app.py` (respects `QM_DB_PATH` if set, otherwise the project's
  default DB path). Never point a dev run at a production database.
- **Disposable test database**: always set `QM_DB_PATH` to a fresh `tempfile.mkstemp()` path
  **before** any project import, in any throwaway script — this is the single most common mistake
  that silently corrupts a real database during ad hoc testing.
- **Migrations**: inspect `migrations/` directly; `tools/run_migrations.py` applies every
  `.sql`/`.py` file there against whatever DB the current `QM_DB_PATH` points at, in order.
- **Geography data**: read `static/data/subcontinent_districts.json` /
  `india_districts_tehsils.json` for the verified directory; never edit `Qumanity_Master.json`
  directly — use `scripts/edit_master_location.py` for a single controlled record change, and read
  §4 first regarding deduplication being proposal-only.
- **Working safely with GPS/consent data**: never fabricate a `0,0` coordinate; always check
  `status` before trusting a `user_location_observations` row's coordinate (`accepted` only); never
  bypass the consent-version check in `osm_proximity_core.py`/`provisional_location_core.py`.
- **Updating documentation and evidence**: the DPG evidence pack's master copy lives outside this
  repository; `docs/dpg_evidence/` here is a copy, updated only when asked. See §10 for the known,
  currently-uncorrected drift.

---

## 12. Privacy, security, consent, and data-integrity rules

These rules are load-bearing across multiple subsystems (§6, §7, §9) and must be preserved by any
future work, including the phone application:

- **Stable geography identifiers** — §4. No silent renumbering, reparenting, or deduplication.
- **Consent-based GPS collection and use** — a GPS observation is only ever stored with an explicit
  consent record (`consent_internal_storage`/`consent_centroid_aggregation`/
  `consent_external_overpass_lookup`), versioned (`consent_version`), and a change in consent
  wording requires a fresh, re-confirmed consent rather than retroactively reinterpreting an old
  one.
- **Authenticated access to personal location data only** — the Q-Map proximity endpoint's
  `session.get("user_id") != user_id → 403` pattern is the model for any future personal-data
  endpoint: never confirm or deny another user's data by varying the response shape.
- **Separation of public map data and private user data** — §7.3.
- **Rights-gated religious content** — §9.1. A collection is never served until it is explicitly
  `review_status='approved' AND marquee_eligible=1`.
- **OSM attribution and ODbL obligations are mandatory** wherever OSM-derived data is shown — the
  attribution text and link to `https://www.openstreetmap.org/copyright` must remain visible and
  clickable on Q-Map and any future map surface.
- **Controlled canonical geography changes only** — no bulk edit without an approved migration and
  crosswalk.
- **Evidence-based implementation status** — never describe a partial, pilot-only, or
  rights-pending feature as complete, certified, or fully operational (this document's own
  standard, applied throughout).
- **No sanitizer is installed anywhere in this codebase, deliberately** — Qmail/council message
  bodies use a narrow, explicit whitelist markup renderer
  (`static/js/qmail_format.js`) rather than raw HTML, precisely so no HTML-escaping layer is needed
  or expected; do not "fix" this into a generic HTML pipeline without understanding why it was
  built this way.
- **User GPS data is sensitive** and must never be exposed in a public response, a popup visible to
  another user, or a log accessible outside the owner's own operational tooling.

---

## 13. Known limitations and unresolved work

Not exhaustive — `docs/dpg_evidence/10_forward_plan.md` is the fuller tracked list. Headline items,
re-confirmed against the code this session where practical:

- **No Privacy Policy / Terms of Service pages published** — the registration link still goes to
  `#`.
- **No "export my data" / "delete my account" self-service** for a member.
- **No Report / Block member mechanism anywhere** — a member can be messaged via Qmail with no
  consent step and no reporting/blocking recourse.
- **No published community rules, no named grievance contact.**
- **No minimum-age or parental-consent gate** at registration.
- **Village member names are visible without sign-in** on some public demographic routes.
- **`dpg_evidence/ARCHITECTURE.md` has drifted from the main `docs/ARCHITECTURE.md`**, and Family
  Tree + the Referral Engine are undocumented in the evidence pack — see §10. Re-syncing the pack
  is recommended as its own task.
- **`docs/API.md`/`ARCHITECTURE.md`/`DATA_MODEL.md` route/table counts are stale** relative to the
  current codebase (confirmed drifted in `docs/audit_dpg_unfinished_features_2026_11.md`).
- **India location deduplication is proposal-only** — 73 of 74 Tehsil-level duplicate groups and
  all 15 Village-level groups remain unresolved; do not execute `docs/india_dedup_migration_plan.md`
  without separate, explicit approval.
- **The OSM proximity worker's production-scale Overpass usage has not been load-tested against
  Overpass's fair-use policy** — flagged as an operational risk to revisit before this becomes a
  volume feature.
- **Council addresses above village cannot yet receive messages** (no elected councils above
  village exist) and **a council cannot start a conversation, only reply.**
- **Qmail/council messages and attachments are retained indefinitely** — no delete-on-request path
  yet (ties to the data-export/delete gap above).
- **Test scripts hard-code or otherwise depend on the owner's own checkout conventions** in a few
  places — not fully portable to an arbitrary new checkout without adjustment.
- **The phone app's own API-contract check** (`Qumanity_App/tools/website-check/check_app_api.py`,
  per the prior handover) had found two live discrepancies against this backend (a missing
  `donation` object in the registration response, and a vote-tally display bug after an election
  closes) — status of these should be re-verified against the current `HEAD` before phone-app work
  resumes; not re-checked in this documentation pass.
- **Qumanity Lok LLP is still in registration** — the IP has not yet been formally assigned;
  copyright assignment, trademark filing, and domain transfer are all gated on that completing.

---

## 14. Git and release state

- Branch `main`. `HEAD` = `origin/main` = **`6b8e5b5`**, confirmed by `git fetch origin main` +
  `git rev-parse HEAD origin/main` in this session.
- `6b8e5b5` is the Q-Map commit (§7.2) — the most recent feature work on this branch. This
  documentation refresh is the commit immediately after it.
- **Pre-existing, unrelated uncommitted changes exist in the working tree** at the time of this
  handover and were **not** touched by this documentation pass: `db.py`, six
  `folder_export/Earth/*.json` mirror files, `tests/test_post_kinds.py` (all modified), plus a
  number of untracked files — `Poems/christian/README.md` and `psalms_kjv_en.json`,
  `Poems/hindu_original/`, several `docs/audit_*_2026_11.md` research documents,
  `docs/family_tree/`, `docs/identity_cards/`, several `folder_export/Earth/*` export directories,
  and a set of location-data maintenance scripts under `scripts/`. These represent other,
  independently scoped work in progress and should be picked up, reviewed, and committed on their
  own terms by whoever owns that work next — not bundled into any future commit without a
  deliberate decision to do so.
- **Standing git rules for this project**: no `git add -A`/`git add .` — stage named files only.
  Never force-push. Never amend without being explicitly asked. One commit per approved task.
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer on commits made by an
  assistant session.
- No access to Railway/production from an assistant session — hand the user exact commands to run
  themselves. Never guess or use real member/admin credentials, even locally.

---

## 15. Next-phase handover instructions for the phone application

The website feature-development phase is complete as of this handover. The next phase is the
**phone application** (`qumanity-app`, a separate repository, React Native/Expo), which already
authenticates against this same backend's `/api` routes via a signed bearer token (treated exactly
like a website session).

**The phone application must not independently redefine:**
- **Location IDs or the geography hierarchy** (§4) — it must read and write the same dotted IDs
  this backend already uses, never mint its own location identity scheme.
- **Consent rules** (§6, §7.1, §12) — GPS/location consent must follow the same versioned-consent
  model already implemented server-side, not a separate mobile-only consent flow.
- **User identity** — the 9-digit Private ID + PIN model, and the same bearer-token-as-session
  pattern, are the established identity contract; do not introduce a parallel identity system.

**Before resuming phone-app work**, re-verify the two previously flagged API-contract
discrepancies noted in §13 (the registration response's missing `donation` object, and the
post-election winner-tally display bug) against the current `HEAD`, since they may affect the
app's own existing integration code.

**Open design/legal items the phone app project must respect, not re-decide on its own**: Q-Punch
reachability remains village-only (§9.2); the India location deduplication plan remains
unexecuted (§4); the DPG evidence pack has known, uncorrected drift (§10); Qumanity Lok LLP
registration (and the resulting copyright/trademark/domain transfer) is still pending (§13).

---

*This document supersedes all prior versions of `docs/HANDOVER.md`. For the concise, frequently
updated status tracker, see `docs/MASTER_STATUS.md`. For a partner- and public-facing overview of
the project, see `docs/QUMANITY_WHITEPAPER.md`.*
