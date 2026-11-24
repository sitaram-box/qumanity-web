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

## 0. Reading map for a new conversation (A–J)

**Added 2026-11-09, final handover pass before the Phone App phase.** If you are a new chat
picking this project up cold, read this section first — each letter below either states the fact
directly or points at the exact numbered section with the full, source-cited detail. Do not
reconstruct project history from earlier chat transcripts; everything load-bearing is here or in
the section it points to.

**A. Project overview.** Qumanity is a free, worldwide, open-source civic platform: one
permanent identity per person (9-digit Private ID + 5-character PIN), a nested Space/Time/
Consciousness record from Village to Earth, village-level elections (Q-Punch), a Collective
Board where posts rise by vote, an internal Qoin economy earned through civic activity (never
purchased), Family Tree, Qmail (internal-only messaging), and a Q-Map. No government, company,
or outside body operates it; one founder does, with the Admin Panel as the only privileged role.
The website (`Qumanity_DPG`) is the single backend and business-logic source; the phone app
(`Qumanity_App`) is a client of its `/api` routes, nothing more — see §G below and §15.

**B. Current website status.** Production: `https://web-production-126c3f.up.railway.app`,
branch `main`. Latest known deployed/pushed commit at the time of this handover pass:
`a3afcb4a161f981c073760ef01ac01cca28ab2f8` (§14 has the full commit history and the exact
verification evidence — don't assume this is still `HEAD` without re-checking `git log`/
`git ls-remote`, since further approved work may have landed after this pass). Major implemented
features: identity/registration (Public + Global Account, §9.3), Family Tree (§8,
`12_family_tree_evidence.md`), Collective Boards, Q-Punch elections (§9.2), Qoins/Karma, Qmail,
Q-Map, the Referral Engine (`13_referral_engine_evidence.md`), Admin Panel, 13-language interface.
Known limitations: §13. Entry points: `/`, `/register`, `/login`, `/dashboard`, `/about`,
`/future` (§E), `/qmap`, `/qmail`.

**C. Core architecture.** Flask + SQLite, one module per subsystem at the repository root — full
module map in `docs/ARCHITECTURE.md` (§2 below links it). API convention: session cookie for the
website, `Authorization: Bearer <token>` for the app (`client: "app"` on login/register), both
converging on the same route handlers. Identity/account architecture, geography hierarchy, Global
Account, Family Tree, Referral Engine, Collective Boards/Q-Punch, Qoins/Karma, Qmail/notifications,
Q-Map, and privacy/security/consent rules are each covered in their own section below (§4, §6, §9,
§8, §12) and/or their own `dpg_evidence/*_evidence.md` supplement — only what's been verified
against current code is stated as fact anywhere in this document.

**D. Geography and provisional locations.** §4 and §6 have the full detail: the authoritative
source is `Qumanity_Master.json` (outside this repo, on the owner's machine), stable dotted IDs,
the provisional-location crowdsourcing system (24-user activation threshold), GPS consent. **Known
geographical data-quality issue, deferred by explicit owner decision (2026-11-09): two tehsils
both named "Tri Nagar" under district "Chandni Chowk" (`CS.DL.7.4`, 12 villages, and `CS.DL.7.14`,
23 villages) are different, real administrative units that happen to share a display name — not a
duplicate record. Both are retained unchanged; this is a known naming/data-quality issue, not a
launch blocker, and is closed for this development phase.** Navi Mumbai (Ghansoli, Vashi, Nerul,
and 11 other nodes) is fully present in the master data, derived data, database, and registration
API — confirmed live on production 2026-11-09, no further action needed.

**E. Explore the Future.** `/future` (`templates/future.html` + `static/js/future.js` +
`static/css/future.css`) — a persistent Three.js + GSAP scroll-driven narrative, expanded
2026-11-09 from 4 to 8 scenes (2026 fragmentation → unequal access → the Qumanity Tree →
connected communities → civic participation → shared ecological responsibility → 2126 → the
CTA). Engine unchanged from its original build; new scenes reuse the same primitives (crack
lines, geodesic arcs, point sprites, GSAP tweens) — no new dependency, no new rendering
technique. WebGL-capability check with a CSS/SVG fallback; `prefers-reduced-motion` respected;
mobile reduces point/segment counts. Reachable only via a homepage hero CTA and an About-page hero
CTA (§5/§6 below) — intentionally not a top-nav item. To add a scene: add a `.qmf-scene` section
in `future.html`, a progress dot, and one more index's worth of entries in `future.js`'s
per-scene state arrays (`CAMERA_POS`, `CRACK_OPACITY`, etc.) — the pattern is table-driven
specifically so this doesn't require touching `play()`/`focus()`'s own logic.

**F. DPG evidence.** `docs/dpg_evidence/` (11 numbered indicator documents + `API.md`/
`ARCHITECTURE.md`/`DATA_MODEL.md` copies + 4 feature supplements). Reconciled 2026-11-09: Family
Tree and Referral Engine were found to already be well-documented (not missing, as an earlier,
now-superseded research pass had claimed); Resend-vs-SMTP corrected in 4 files; the
election-test-scheduler's status corrected from "planned" to "implemented"; a new
`15_global_account_evidence.md` added. See §10 for the full account, including what was
deliberately **not** touched (frozen, no DPG resubmission implied by any of this).

**G. Phone App integration contract.** Full detail in §15. In short: the app must reuse the
website's identity (Private ID + PIN), its server-derived Global/Public account classification
(`GET /api/me`'s `is_global_account`), its geography IDs, its GPS-consent model, and its Q-Punch
eligibility rules — never reinvent any of these independently. `docs/phone_app_api.md` (identical
copy in both repos) is the living, lower-level API-contract reference; this document does not
duplicate its route tables.

**H. Phone App development status — verified live this session, not assumed.** Repository:
`~/Desktop/Qumanity_App` (`qumanity-app` on GitHub), branch `main`. **Actual current HEAD,
checked via `git log`/`git status` on 2026-11-09: `40b854d4d34312a1143c6cdb8402df2dc9177984`**
("feat(mobile): synchronize phone app with latest website backend") — working tree clean, no
uncommitted changes. This is a separate chat's own work, already landed: it syncs the app with
the website's Global Account release (`af01272`) — the 5-character PIN rule, Global members'
account-ID requests outside the Sub-continent, Qmail reply counts on notifications, and own-post
voting checks — and its own commit message records its cross-repo checker result (166 passed, 0
failed, against a local database copy; production not independently verified by that commit) and
one known, explicitly flagged issue it did **not** fix: a retired account's existing app token
remains valid against production today. *Correction, 2026-11-11: this is now fully resolved. The
website-side fix is committed (`e045cf1`), deployed, and — as of 2026-11-11 — directly verified
against a real retired production account: a retired account's old bearer token now returns HTTP
401, and its old browser session is now treated as anonymous. See
`## Retired-Account Authentication Security — November 2026` below for the full verification
record.* **Do not assume any app commit hash from an earlier conversation is still current** — the
Phone App Chat may have continued past this point; re-check `git log` there before planning new
work.

**I. Development and release safeguards.** §12 (privacy/security/consent) and §14 (git rules) are
the canonical sources. Headline rules: no `git add -A`/`git add .`; stage named files only; never
force-push; one commit per approved task; `docs/dpg_evidence/` is reconciled narrowly, never
silently rewritten wholesale; `Qumanity_Master.json` and its derived files are never
machine-edited without an explicit, separately-authorized task; the retired-account work and any
other unrelated uncommitted change in this repo is preserved exactly as found until its own owner
authorizes it.

**J. Next steps for the Phone App Chat.** Given §H above, the most useful next step is likely to
continue from `40b854d` in `Qumanity_App` directly (re-verify its own test/checker status fresh,
don't assume it's still accurate), with one carry-over item from the website side to keep in mind:
the deferred Tri Nagar naming issue (§D) needs no app-side handling, it's a data-display nuance
only. The retired-account token-invalidation gap that commit flagged is now fully fixed, deployed,
and production-verified (`## Retired-Account Authentication Security — November 2026` below) — no
further action needed on it from the Phone App side. No website blocker is currently known.

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

**Repository state at this handover** (verified fresh, not carried over; **superseded by §14**,
which reflects this document's current, later `HEAD` — `main` has moved on since the paragraph
below was written, and §14 is the authoritative current release state, not this one):
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
one of these levels — **except** a Global Account (§9.3), whose Present Location deliberately
stops at Country; this is intentional, not a data gap, and every reader of
`present_location_json` in this codebase already handles a missing Village/Tehsil/District/
State/Zone gracefully (`.get(level) or {}` throughout).

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
| Global Account (worldwide registration outside the 10 Public Account countries) | ✅ Implemented, tested, **committed and pushed to `origin/main`** (`a7d43a7`/`a157d7a`) | See §9.3 |
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

### 9.1 Multi-religion Marquee — **discontinued 2026-11-08 (owner legal decision)**

**The entire Poems Marquee feature has been removed from the application.** Gita Press denied
permission for the Hindi Vinaya Patrika translation; rather than remove only that one collection,
the owner chose to discontinue the whole Marquee and every public religion-based identity symbol
that went with it (a Shivalinga/Cross/Crescent/Dharma Wheel component that had briefly existed in
an uncommitted pass earlier the same day was removed in the same change, before ever being
committed). No religious text of any tradition, and no religion-based public identity decoration
of any kind, is displayed anywhere on the live site.

**What was removed**: `templates/_poems_marquee.html`, `static/js/poems.js`,
`static/css/poems.css`, the `Poems/` directory's own content, the four routes that served or
controlled it (`GET /api/poems/meta`, `GET /api/poems/<lang>/<index>`, `POST /api/marquee/hide`,
`POST /api/marquee/show`), the `QM_MARQUEE_ENABLED` feature flag and its context-processor, the
Private Account "Hide/Show Marquee" control, and the `{% include %}` of the Marquee partial from
all twelve templates that had carried it. `tests/test_poems_marquee.py` (226 checks) was deleted
with it; `tests/test_copyright_pages.py`'s own now-meaningless "feature flag independence" check
was removed, its other 37 checks (covering the two preserved rights-notice pages) are unaffected.

**What was deliberately preserved**:
- `users.religion_belief` (the database column) and the Private Account's own religion
  selector/editor — a member can still set and change their spiritual path privately; this was
  never a Marquee-only feature and the owner explicitly required it to remain.
- `religious_text_core.py` and its four tables (`religious_traditions`, `text_collections`,
  `text_collection_languages`, `text_entries`) — left in place, dormant (still seeded at boot by
  `tools/run_migrations.py`, no longer read by any active route) rather than destructively dropped.
- The two public rights/legal pages, `/copyright/gita-press` and `/copyright/religious-texts` —
  both updated in place to describe the Marquee in the past tense and record the discontinuation,
  while preserving every tradition's own rights-research findings (including the Gita Press
  denial itself) as the historical audit trail. Neither page was deleted.
- `docs/marquee_religious_text_sources.md` and `docs/marquee_rights_roadmap.md` — the full research
  trail, unchanged as historical record.
- The `docs/dpg_evidence/` pack's own existing description of the Marquee (already stale relative
  to several later changes, as prior passes of this document have already noted) was **not**
  rewritten — the frozen evidence pack is not edited to track a feature's current status; this
  section of `HANDOVER.md` is that current-status record instead.

**No individual religion is ever disclosed publicly.** Verified directly: `religion`/
`religion_belief` is never read by `social_core.py`, `board_core.py`, `elemental_core.py`, or
`karma_core.py` — the only places it is read at all are the Private Account's own profile-display
and profile-change-request code paths in `app.py` (both already private, both already
council-approval-gated for an edit) and `identity_core.py`'s `religion_change` request type (same
private, council-approval flow). About page's "Is Qumanity a religion, or does it require belief?"
FAQ entry is about the platform's own philosophy, not any individual's data.

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

### 9.3 Global Account (2026-11-08) — ✅ implemented, tested, committed and pushed to `origin/main`

A user whose **Present Location's** country is outside Qumanity's 10 Public Account Activation
countries (`SUBCONTINENT_COUNTRY_IDS` in `app.py`: India, Nepal, Bhutan, Bangladesh, Myanmar, Sri
Lanka, Pakistan, **Balochistan** — a separate country-level record in the location master, not a
Pakistan province — Afghanistan, Maldives) registers as a **Global Account** instead of a Public
Account. Mauritius (`O_AF_MUS`) is a real country in the canonical world database
(`static/data/global_countries.json`) but is **not** one of the 10 and is therefore Global, same
as every other country outside the list (Japan, Kenya, etc.).

**Classification is derived, never persisted**: `account_access_type(present_location)` returns
`"public"`/`"global"` by reading `present_location.country.id` fresh every time, never a stored
column — see that function's own docstring for why (it can never drift out of sync with a later
council-approved location correction). Nothing in the client — an `is_global_account` flag, an
`account_type` field, anything — is trusted; the server always re-derives this from the validated
location. As of the 2026-11-08 hardening pass (below), this function and
`SUBCONTINENT_COUNTRY_IDS` live in their own module, **`account_core.py`** — not `app.py` — so
`election_core.py` can import the classification directly without a circular import (`app.py`
already imports `election_core`); `app.py` re-exports both names unchanged for every existing call
site. There is now exactly one copy of this logic in the codebase.

**Registration** (`api_auth_register` in `app.py`): the existing present-location validation
branches on `present_country_id in SUBCONTINENT_COUNTRY_IDS`. For a Global country, the location
must stop at Continent + Country — any submitted `state`/`zone`/`district`/`tehsil`/`village` is
**rejected outright** (never silently dropped), and the continent/country pair is checked against
the real 7-continent/229-country world database (`_is_valid_global_country()`) rather than trusted
as two independent client-supplied facts. Birth Location was never restricted to the 10 countries
and is unaffected. `templates/register.html` / `static/js/register.js`: the Present Location
continent/country dropdowns now offer every country on Earth (previously Asia + the 10 only); a
non-Subcontinent selection shows a plain informational note ("🌍 Global Account — …"), never a
blocking modal, and the wizard's own existing step-skip logic
(`goToStep(updatePublicAccountEligibility() ? "public" : "review")`) already sends a Global
registrant straight to Review, needing no new branching logic of its own.

**Dashboard**: `profile.is_global_account` (from `account_access_type()`) wraps both the Public
tab button and its entire panel (`#qm-dash-public`, including the Village Council Election card
nested inside it) in `templates/dashboard.html` — not a CSS hide, the markup simply isn't rendered.
Every JS consumer (`dashboard.js`, `board.js`) already null-guards on that element's absence.

**Backend enforcement is not new code** — this is the central finding of this feature's
implementation. `board_core.py`'s `chain_of(present_location)` only produces chain entries for
geography levels actually present in a user's own location, plus a universal `{"level": "earth",
"id": "EARTH"}` for everyone; `board_view()`/`create_post()`/`cast_vote()` all resolve against the
*caller's own* present_location (read from their DB row, via `_board_user()` — never a
client-supplied location), never an arbitrary target. A Global Account's location has no
village/tehsil/district/state/zone entries, so:
- `GET /api/board/village` (or any level below Country) → `board_view()` returns `None` → 404,
  "no group at this level" — the same response path an India resident with no Tehsil set would
  already get. No Global-specific branch was added.
- `POST /api/board/post` at Village (free) or any paid tier (Tehsil–Zone) → `create_post()`
  already raises `ValueError` for a caller with no matching chain entry at that level.
- `election_core.nomination_eligible()`/`voting_eligible()` already gate on
  `_present_village_id(user_row) == cycle["village_id"]`, reading the DB row directly — `None` for
  a Global Account's normal, unmodified row, so Q-Punch's Village Council election
  (`election_core.py`, see §9.2's own terminology note below) was already closed to them through
  this path alone. **One real gap was found and closed in the 2026-11-08 hardening pass** — see
  below; `_present_village_id()` itself now also re-checks `account_access_type()`, not just the
  presence of a village key.
- `family_core.activate_timeline()` has no location dependency at all — Family Tree, Personal and
  Private features work identically for both account types.

**Global voting on posts that reached Country/Continent/Earth level is real, but scoped by shared
geography, not a worldwide free-for-all** — verified by `tests/test_global_account.py` with
synthetic rows standing in for ones `settle()`'s own elevation would have produced (the real
thresholds at these levels are 1M/10M/100M votes, infeasible to simulate by casting that many real
votes):
- **Country-level** posts are visible/voteable only to residents of that *one* country (a Japan
  account cannot vote on an India country-level post — different `country.id`).
- **Continent-level** posts are shared by everyone whose own location has that same continent —
  e.g. Japan (`O_AS`) can vote alongside India/Nepal/etc. (also `O_AS`); Kenya (`O_AF`) cannot,
  since no Public Account country is currently in Africa.
- **Earth-level** is the only tier that is genuinely universal, for every account type.
- Casting a second vote on the same post **replaces** the first (score moves by the delta) — this
  is the existing `cast_vote()` contract for every account type, not a duplicate-vote rejection.

**Paid/monetized collective-board posting does not exist at Country/Continent/Earth level at all**
— for any account type. `board_core.PAID_LEVELS = ("tehsil", "district", "state", "zone")`; the
module's own comment calls Country/Continent/Earth "broadcast + voting only." A Global Account is
therefore automatically excluded from the existing paid-posting tiers the same way it's excluded
from free Village posting (no matching chain entry), with no new financial code written or needed.

**2026-11-08 Q-Punch security hardening** — a real, API-reachable gap (not just a direct-SQL
thought experiment) was found and closed:

- **The gap.** `api_dashboard_edit_request()` (the self-service "request a profile change"
  ticket) accepted a `present_location` field with **zero validation** — not even the
  state-belongs-to-country check registration has always had — and queued it verbatim.
  `api_admin_profile_decide()` then applied whatever a council/Admin approved straight into
  `users.present_location_json` via `social_core.regenerate_account_id()`, also with no
  re-check. This was the realistic route (unlike a direct SQL edit, which no self-service flow
  can reach) by which an internally inconsistent location — e.g. a Global country paired with a
  Subcontinent village id — could have landed on a real row, and from there, by itself, satisfied
  the old, ungated `_present_village_id()`.
- **The fix, two layers.** (1) `election_core._present_village_id()` (the single function
  `nomination_eligible()`/`voting_eligible()`/`member_guide()` all go through) now refuses to
  return a village id at all unless `account_core.account_access_type()` independently
  recomputes `"public"` from that same `present_location_json` — a village key can no longer, by
  itself, grant Q-Punch eligibility, regardless of how it got into the row. (2) A new shared
  validator, `app._validate_present_location_change()`, is now called both when a profile-change
  ticket is **submitted** and again when it is **approved** (defense in depth) — it enforces the
  same Global/Public shape rules registration already has (Global: Continent+Country only, valid
  pair; Public: state must belong to country, and any provisional Tehsil/Village must belong to
  that state), and additionally **refuses any change that would cross the Global/Public account
  boundary** in either direction.
- **The Global↔Public transition is a documented gap, not a bug.** No approved workflow for
  converting a Global Account to Public (or vice versa) exists anywhere in this product today.
  Building one was out of scope for this hardening pass, so `_validate_present_location_change()`
  simply refuses any ticket that would cross that boundary, with an explicit error message
  pointing the member to Admin. A genuine relocation across that line needs its own, separately
  authorized feature.
- **Verified by test** (`tests/test_global_account.py`, section 10 rewritten + new section 14):
  the exact fabricated-village-id-plus-Japan-country scenario from the original report, re-run
  against the fixed code, now correctly rejected at every Q-Punch endpoint (`/api/election/status`,
  `/nominate`, `/vote`), with zero `election_candidates`/`election_votes` rows created and the
  locked free-registration Qoin share confirmed never unlocked; a malformed edit-request is
  rejected at submission; a Global↔Public boundary crossing is rejected in both directions at
  submission; a ticket inserted directly (standing in for one queued before this fix existed) is
  rejected at approval time too, left `pending`, with the user's row provably untouched; and a
  legitimate, same-classification present_location edit (section 15, new) still succeeds
  end-to-end through the real submit→approve flow, proving the new validation doesn't block real
  edits.
- **Reward issuance** (`wallet_core.unlock_user_share()`, the locked free-registration Qoin share
  that unlocks on a member's first-ever election vote) needed no separate fix: its only call site
  is inside `election_core.cast_vote()`, after `voting_eligible()` — already covered by the single
  `_present_village_id()` fix above. No other Q-Punch reward or claim endpoint exists.
- **Independent-review follow-up (same date): ancestry-chain validation was incomplete.** A
  second, independent adversarial review found that the first validator above only checked
  state-belongs-to-country for a Public-country change — not that a submitted
  Zone/District/Tehsil/Village chain actually nests the way the real geography data says it
  must. A Public Account staying Public (so the account-boundary check never fires) could have
  submitted a real, *existing* village id belonging to a completely different Tehsil/District,
  letting a member falsely claim residency of — and become Q-Punch-eligible for — a village they
  never actually selected through real geography. Closed with exactly the existing data, no new
  hierarchy level or migration: Zone→State and District→Tehsil ancestry checked against
  `subcontinent_states.json`/`subcontinent_districts.json` (always-populated static data, hard
  reject on mismatch); Village→Tehsil ancestry checked against `india_villages.tehsil_id` (the
  same table `GET /api/india-villages/<tehsil_id>` already serves from). **Superseded by the Task
  1A fix below** — the "soft-fail on not found" village policy described here was itself found to
  be an incomplete fix and has since been replaced with a hard rejection.
- **Independent-review follow-up: the admin-only simulation endpoints were checked for a
  bypass, and found safe.** `election_core.auto_nominate()`/`auto_vote()` (triggered only by
  `/api/admin/election/auto-nominate`/`auto-vote`, admin-only) build their own candidate/voter
  pool with a raw SQL query on `present_location_json`'s village key, independent of
  `_present_village_id()`. Verified directly (bypassing the admin HTTP routes' real-world-date
  dependency with an explicit `today=` override, the same technique `election_test_scheduler.py`
  itself uses): the fabricated-village-id row does match that raw pool query, but
  `auto_nominate()` still excludes it (its own `nomination_eligible()` re-check, which calls
  `_present_village_id()`, filters it before picking anyone) and `auto_vote()` still never casts
  a vote for it (routes every vote through the same `cast_vote()`/`voting_eligible()` gate,
  catching the resulting `ValueError` as a no-op "skipped", never a crash and never a vote row).
- **Pre-existing, unrelated duplication noted, not touched.** `perception_core.py` (a separate,
  pre-existing feature — the Perception Calculator) carries its own independent copy of the same
  10-country tuple, currently byte-identical to `account_core.py`'s but with no shared source —
  a future change to one could silently drift from the other. Flagged for awareness; consolidating
  it was explicitly out of scope ("do not consolidate unrelated code merely for cleanliness").
- **Mobile dashboard overflow** (noted but not yet fixed in the original report): reproduced —
  `#logout-btn`'s own `margin-left: 4px` (desktop-only breathing room) was exactly the 4px that
  overflowed the 375px viewport once `.qm-header-actions`' mobile gap left no spare room. Fixed
  narrowly inside the existing `@media (max-width: 720px)` block in `static/css/dashboard.css`
  (`.qm-logout-btn { margin-left: 0; }`, mobile-only) — desktop spacing, the button's label, and
  logout behavior are all untouched. Verified at 375px and 390px for both a Global and a Public
  Account Dashboard: no horizontal overflow, logout button fully visible and unchanged otherwise.

**Phase 1 (2026-11-08) — Task 1A: the district-omission ancestry gap, closed at the root.** A
third-round owner-approval audit found that the Task-1A-era `_validate_present_location_change()`
still had a real, confirmed bypass: `_validate_zone_district_tehsil_ancestry()`'s predecessor only
ran the Tehsil-belongs-to-District check when a District had *also* been submitted
(`if tehsil_id and district_entry:`) — so simply never submitting District skipped it entirely,
letting a genuinely-real Tehsil+Village pair belonging to a completely different State pass. Fixed
by making District mandatory whenever a REAL (non-provisional) Tehsil is submitted — the omission
itself is now rejected (`"A Tehsil requires its District to also be submitted"`), not merely the
case where a wrong District happens to be present. This rule is now enforced identically at BOTH
entry points that can ever write `present_location_json` — `api_auth_register()`'s Public-account
branch now runs the exact same `_validate_zone_district_tehsil_ancestry()` helper
`_validate_present_location_change()` uses, closing registration's own, separate, pre-existing gap
(it had never validated anything beyond state-belongs-to-country). A parallel, symmetric rule now
also applies to Village: a Village id requires an immediate parent (Tehsil, or District for a
`direct_villages` district) to be submitted alongside it, at both entry points.

**Village-level policy, tightened**: the earlier "soft-fail on not found in `india_villages`"
policy (described above) was itself found to conflate "unverifiable" with "confirmed valid" —
exactly the distinction an audit said must never be collapsed. `_validate_present_location_change()`
now hard-rejects a Village id that cannot be found in `india_villages` at all, not just a
confirmed mismatch — that table is this product's complete authoritative village registry for all
9 Public Account countries (confirmed by real row counts under every one of the 9 countries' own
id prefixes, not an India-only dataset), and the live default database (`qumanity_prototype.db`,
`db.py`'s own `DB_PATH` default) already holds all 721,237 of them.

**Corrective follow-up (same date): registration's own Village check was still weaker than
profile-change's.** An owner-approval review correctly flagged that the stricter policy above had
been deliberately *not* extended to `api_auth_register()`'s own Public-account branch, leaving
registration able to accept an arbitrary, fabricated Village id as long as it didn't look
provisional. Closed by reusing the **existing** `provisional_location_core.verified_village_exists()`
helper (no new lookup mechanism) inside registration's own provisional-check loop: a
non-provisional Village id is now required to be a real row whose `tehsil_id` matches the
submitted Tehsil (or District, for a `direct_villages` district) — the exact same relationship
`_validate_present_location_change()` already enforces. A PROV-shaped id with no matching row, or
a string that merely starts with `"PROV-"` without matching the real pattern, both still fail
correctly (the existing `from_present_location_id()`/`get_provisional()` checks, unmodified).
A genuine database-query failure during verification was confirmed, by direct test, to raise
rather than silently return a valid result — Python's own exception propagation already satisfies
"never silently accept as valid" here; no new error-suppression code was added or was needed.
This closes registration's side of the gap without touching the provisional-location system's own
activation thresholds, promotion rules, or data model in any way.

**Test-infrastructure consequence**: closing this at registration meant every throwaway test DB
(which starts with `india_villages` empty) now needs its real village rows seeded before
registering through the real route with a real Village — 19 existing test files across the suite
were updated with a short, consistent seed block; two newly added test files
(`tests/test_global_account.py` and `tests/test_election_winner_tally.py`) independently include
the same seed setup as part of their own content, bringing the total number of test files
containing this seed setup to 21 (the same `INSERT OR REPLACE INTO india_villages`
pattern already used for the profile-change tests above), none of them touching unrelated test
logic.

**Robustness fix, found during the same pass**: every location-field check in this file reads a
level with `(location.get(lvl) or {}).get("id")`, which crashed with an unhandled
`AttributeError` — not a clean 400 — on a malformed payload such as `"district": "CS.DL.3"` (a
plain string instead of `{"id": "CS.DL.3"}`). A new `_location_subfields_well_formed()` guard,
called at the top of both `_validate_present_location_change()` and `api_auth_register()`'s
location handling, now turns this into a clean 400 for both birth and present location.

**Phase 1 — Task 1B: the Q-Punch winner-tally bug, root-caused and fixed.** Confirmed, by directly
running `tools/website-check/check_app_api.py` against a disposable copy of the real database (not
assumed from an earlier report), that a full simulated Libra 2026 election cycle — 3 candidates
per gender, real votes cast (15 male, 11 female) — closed with `election_summary()` reporting
`winners: {male: None, female: None, male_votes: 0, female_votes: 0}`. Traced the entire lifecycle
(candidate creation, vote persistence, cycle-status derivation, tally query, winner determination,
summary serialization) and isolated the defect to exactly one place:
`election_core._ensure_tallied()` tallied a cycle's winners **once ever** per
`(village_id, zodiac_sign, year)` — skipping recomputation forever once a `village_council` row
existed for that key, regardless of whether `election_votes` had changed since. The real
`qumanity_prototype.db` confirms this exactly: its `village_council` row for Libra 2026 / Rohini
Sector 24 was tallied on 2026-10-17 with **zero** `election_votes` rows on record at the time (the
real-world clock crossed `voting_end` before the demo-seed script's votes were in place) —
permanently freezing a null tally that no later vote could ever correct. The fix: `_ensure_tallied()`
now always recomputes winners from the *current* `election_votes` and UPSERTs the result into
`village_council`/`election_cycles`, instead of skipping when a row already exists. This is safe
because tallying has no side effect that must only run once — no reward or Qoin payout is tied to
*becoming* a winner anywhere in this codebase (confirmed by grep; the only Q-Punch-adjacent reward,
`wallet_core.unlock_user_share()`, fires on a *voter's* first-ever vote, inside `cast_vote()`,
entirely independent of tallying). Candidate eligibility, voter eligibility, voting windows,
tie-handling (`ORDER BY votes DESC, MIN(id) ASC` — earliest vote wins a tie, unchanged), the
pilot-village configuration, and `QPUNCH_REACHABLE_LEVELS` were all read, not modified, and are
confirmed byte-identical in the diff.

**New test file**: `tests/test_election_winner_tally.py` (25 checks) — multiple candidates/votes,
persistence, closure, correct per-candidate vote counts, correct winner identification, a genuine
zero-vote election, a genuine tie resolved by the existing tie-break rule, two independent
election cycles with no cross-cycle leakage, ineligible voters (wrong sign, wrong gender-for-seat)
never affecting totals, and — the actual regression — a cycle tallied once with zero votes that
self-corrects once real votes exist, reproducing the exact real-database failure before proving it
fixed. (Election-lifecycle testing here required real pilot-village residents throughout, voting
under different zodiac-sign cycles rather than fabricated villages — `cast_vote()`/`nominate()`
are hardcoded to `PILOT_VILLAGE_ID`, not parameterized by village, confirmed while writing this
suite.) `tests/test_global_account.py` grew to **127 checks** (108 + 19 new, section 18) proving
the Task 1A fix at both registration and profile-change, including registration's own new
district-required and village-needs-a-parent rules, the type-guard fix, and the 14-point
adversarial matrix the owner's audit required (some checks cover both a registration-path and a
profile-change-path variant of the same relationship, hence more than 14 individual assertions),
then to **136 checks** (127 + 11 new, section 19) proving the corrective follow-up above: real
official-Village ancestry checks isolated specifically at registration (wrong Tehsil, wrong
District+State), fabricated and malformed-PROV-shaped ids, the genuine database-failure behavior,
the malformed-Village-field case, and confirmation that none of the rejected attempts left behind
a partial user record.

**Terminology note**: the product brief for this feature used "Q-Punch" to mean the Village
Council *election* system (`election_core.py`, §9.2 above describes the actual, distinct
qmail-council-*addressing* feature this codebase itself calls Q-Punch). Both are now correctly
scoped to Global Accounts being excluded — this note exists only so a future reader isn't confused
by the two different things sharing a name in conversation versus in code.

**Test file**: `tests/test_global_account.py` — **136 checks** (75 original + 21 from the
2026-11-08 hardening pass + 12 from a same-day independent adversarial review + 19 from the
Phase 1/Task 1A pass + 11 from the registration-Village corrective follow-up) — registration
(Japan, Kenya, client-flag-spoofing, fabricated-village rejection), India/Public regression,
Dashboard tab assertions against actual rendered HTML, direct backend rejection of Public routes,
the Country/Continent/Earth voting-scope behavior above, Q-Punch/election rejection (including the
fabricated-village-id scenario re-verified post-fix against the real endpoints, not just the pure
function), the profile-change-request hardening (sections 14–15), the full ancestry-chain
validation and admin-simulation bypass checks found by the independent review (sections 16–17),
the Task 1A district-required-at-registration matrix (section 18), the registration-Village
corrective follow-up (section 19), Family Tree activation, and the paid-posting code-level audit.

**C1 (2026-11-08): the account-ID-request flow ("Path A") was a second, unvalidated route to the
exact same present_location state the hardening above protects — found by an independent
adversarial pre-merge audit, fixed the same day.** Every check described above
(`_validate_present_location_change()`'s shape/ancestry/village-existence checks and the
Global/Public account-boundary lock) was wired into `app.py`'s profile-change-request flow only
("Path B": `api_dashboard_edit_request` / `api_admin_profile_decide`). `social_core.py`'s
dedicated "request a new Account ID" flow ("Path A": `request_new_account()` / `POST
/api/people/account-ids/request`, and `decide_account_request()` / `POST
/api/admin/account-ids/<id>/decide`) called none of it — its only check was a bare truthiness
test (`present_location.get("village") or present_location.get("state")`). The audit reproduced
this live: a Global Account (Japan) submitted a fabricated India/Rohini Sector 24
`present_location` through this flow, and approving it flipped the account's classification from
`global` to `public` and resolved to the real pilot village under
`election_core._present_village_id()` — the Global↔Public boundary and every ancestry/existence
check were bypassed entirely.

**The fix moves the validation itself, not just its call sites, into the shared layer.**
`_validate_present_location_change()` and the five helper functions it depends on
(`_location_subfields_well_formed`, `_public_state_ids`, `_is_valid_global_country`,
`_validate_zone_district_tehsil_ancestry`) now live in **`account_core.py`** — the same
dependency-light module `SUBCONTINENT_COUNTRY_IDS`/`account_access_type()` already live in — as
`account_core.validate_present_location_change()` and its own-named helpers; `app.py` keeps the
original underscored names as plain aliases (`_validate_present_location_change =
account_core.validate_present_location_change`, etc.), so every existing call site
(`api_auth_register`, `api_dashboard_edit_request`, `api_admin_profile_decide`) is unchanged. This
was necessary, not just convenient: `social_core.py` cannot import `app.py` (circular —
`app.py` already imports `social_core`), so the validation had to move to a module both can reach
without a cycle, exactly the reason `account_core.py` was split out of `app.py` in the first
place. `social_core.request_new_account()` now calls
`account_core.validate_present_location_change()` before queuing a request; `decide_account_request()`
calls it again before `regenerate_account_id()` — re-reading the user's CURRENT
`present_location_json` at approval time, not trusting whatever passed at submission, which is
what makes it safe for a request that sat pending while the user's own account state changed in
the meantime. A rejected approval raises before any mutation — no `account_id` regeneration, no
`present_location_json` change, no status update — leaving the request exactly `pending`.

**Both Path A and Path B now enforce the identical present-location validation and Global/Public
boundary protection**, from one shared implementation, with no duplicated logic.

**Verified by test** (`tests/test_account_id_request_security.py`, new, 31 checks): the exact
original exploit reproduced through the real HTTP routes (`POST
/api/people/account-ids/request` then `POST /api/admin/account-ids/<id>/decide`) and confirmed
rejected at both steps; a forged/directly-inserted pending request (standing in for one that
reached `pending` before this fix, or through any future submission-route bug) rejected at
approval too, by the same re-validation, independent of submission; a request valid at submission
whose user's account state changes before approval, correctly re-validated and rejected at
decision time; a legitimate same-classification move accepted and applied end-to-end at both
submission and approval; and `_present_village_id()` confirmed `None` throughout every exploit
attempt — checked independently of the account's age/zodiac/voting-cycle state, so the earlier
report's incidental zodiac mismatch is not what is protecting this path. Full regression:
**33 test files, 1,370 checks, 0 failures** (re-run fresh this session, superseding the
previously reported 1,380/30 figure above, which predates both the Phase 0–3 work and this fix).

**Mobile UI exploitation surface (found during the independent post-fix audit, 2026-11-08):** the
mobile app's own "Account IDs → request a new one" screen
(`Qumanity_App/mobile/src/app/account-ids.tsx`) calls these exact two routes
(`requestNewAccount()` / `POST /api/people/account-ids/request` at submission,
`decideAccountRequest()` / `POST /api/admin/account-ids/<id>/decide` at approval), and its entry
row in `(tabs)/private.tsx` is not gated on `is_global_account` the way the Public tab is — so a
Global Account holder could reach this completely normal, un-fabricated screen and, before this
fix, queue a request through its own `onlySubcontinent` location picker that an admin's approval
could turn into an illegitimate Global-to-Public crossing, with no crafted payload needed at all.
**The mobile screen was never the security boundary, and no mobile code change was made or is
needed to close this** — the fix is the backend validation described above: the server now
validates the proposed present_location at submission and independently revalidates it against
the user's CURRENT account state at approval, which closes this path regardless of which client
(web, the account-ids.tsx screen, or a raw API call) reaches it. The screen's existing generic
`try`/`catch` error handling already displays the backend's rejection message correctly, with no
mobile-side change required. Backend authorization and validation remain the sole, authoritative
gate — hiding or restyling the mobile screen would not, by itself, have been a fix.

**Status as of this writing: implemented, tested, committed, and pushed to `origin/main`.** The
work landed as two commits, in this order (backend before UI, since the UI depends on the backend
validation and the `is_global_account` field): **`a7d43a7` "Harden Global Account authorization
and election handling"** — `app.py`, `election_core.py`, `social_core.py`, the new
`account_core.py`, the updated `tests/test_global_account.py`, the new
`tests/test_election_winner_tally.py`, the new `tests/test_account_id_request_security.py`, and 19
existing `tests/*.py` files that each gained a short `india_villages` seed block (the two newly
added test files above independently include the same seed setup); and **`a157d7a` "Add Global
Account registration and dashboard UI"** — `templates/dashboard.html`, `templates/register.html`,
`static/js/register.js`, `static/js/tutorial.js` (a pre-existing onboarding-tour step's body text
named all four tabs unconditionally; now computed live so it only names tabs the viewer actually
has), `static/css/dashboard.css` (the mobile logout-button overflow fix). Combined release: 33
files, 3,043 insertions, 77 deletions, pushed as a clean fast-forward — `origin/main` is at
`a157d7af01e1e5791de6e2449cde2945652c8659`, confirmed by a live `git ls-remote` immediately before
and after the push. **Production verification**: fetching the live production site directly
(`GET /register`, `GET /static/js/register.js`) confirms the new Global Account markup and script
are being served — direct, read-only evidence that this release (or a later one) is live. Railway's
own deployment metadata (build status, exact deployed SHA, health check) was **not** independently
confirmed in that session, because the Railway CLI's OAuth token had expired
(`railway whoami`/`railway status` both returned "Unauthorized"); re-authenticating or checking the
Railway dashboard directly remains an owner action, not something an assistant session did or
could verify here. Do not treat "the live site serves the new code" as equivalent to "Railway's
deployment record was inspected and found healthy" — the two are different kinds of evidence.

**Final regression at this release, re-run against the pushed `HEAD` (not assumed from an earlier
report)**: full backend suite, every `tests/test_*.py` run individually — **33 files, 1,370
checks, 0 failures**. The mobile app's cross-repo checker
(`Qumanity_App/tools/website-check/check_app_api.py`, against a disposable copy of the real
database, never production) — **156 passed, 1 failed**. That one failure,
`"board shows the post, score and vote state"`, is pre-existing and unrelated to Global Account or
C1 (tracked separately); it is **not** fixed, and this checker run should not be described as
"all passing."

---

## 10. DPG evidence and documentation

The DPG Standard evidence pack lives at `docs/dpg_evidence/` (11 numbered indicator documents +
a Forward Plan + application-form-answers compilation + copies of `API.md`/`ARCHITECTURE.md`/
`DATA_MODEL.md`). Its master working copy is a non-git directory on the owner's own machine;
`docs/dpg_evidence/` inside this repository is a copy, changed only when the owner asks for it.

**What "frozen" means here**: 5 of the pack's 17 documents (the ones touched by the 2026-11-01
correction pass — `01_sdg_relevance.md`, `08_standards.md`, `12_family_tree_evidence.md`,
`13_referral_engine_evidence.md`, `ARCHITECTURE.md`) carry an explicit banner reading
*"DPG Evidence Refresh — internal correction pass, not a DPGA resubmission."* (verified by grep
across the full pack this session — not every one of the 17 files carries this exact banner, so
describing it as universal would itself be an overstatement). **No document in this repository, in
or out of that banner, claims formal Digital Public Goods certification, DPG Registry acceptance,
or external endorsement anywhere** (independently re-confirmed by a second grep for
certification/registry-acceptance language, this session, with zero hits) — the pack is internal
evidence-preparation and
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

**Reconciliation pass completed 2026-11-09** — the claims below are **superseded**; they came from
an earlier, untracked research document (`docs/audit_dpg_unfinished_features_2026_11.md`,
2026-11-01) whose findings were re-verified against the actual current pack this session, not
re-stated from that document or from this handover's own prior text:
- **Family Tree and the Referral Engine are NOT absent** — `docs/dpg_evidence/12_family_tree_evidence.md`
  (339 lines) and `13_referral_engine_evidence.md` (225 lines) already exist, are substantial, and
  were spot-checked against the current code this session (a sample of their file:line citations
  all still resolve correctly) — the 2026-11-01 research document's claim was accurate only as of
  that date; both files were added the same day, after that research pass ran.
- **The election-test-cron "planned, not built" claim was genuinely stale and has now been
  corrected** (`09_do_no_harm.md`, 2026-11-09): `election_test_scheduler.py` registers a daily
  automated tick, confirmed wired up via `init_scheduler()` called unconditionally from `app.py`.
- **The SMTP/Resend claim was genuinely stale in four files, now corrected** (2026-11-09):
  `04_platform_independence.md`, `07_privacy_and_applicable_laws.md`,
  `11_application_form_answers.md`, and `docs/dpg_evidence/ARCHITECTURE.md` all still described
  SMTP/`smtplib`/`SMTP_HOST`; corrected to describe Resend's HTTPS API, which is what
  `email_core.py` has actually used since 2026-10-20. **`08_standards.md` itself was already
  correct** (fixed in its own 2026-11-01 pass, confirmed by re-reading it this session) — the
  2026-11-01 research document's claim that it still described SMTP was itself inaccurate even at
  the time it was written, or described a different file; either way, it's moot now.
- `docs/dpg_evidence/ARCHITECTURE.md`'s module-map divergence from the main `docs/ARCHITECTURE.md`
  is now down to exactly one row (`account_core.py`, added to the evidence-pack copy this
  session too) — the `family_core.py`/`profile_picture_core.py` rows the 2026-11-01 document said
  were missing are both present.
- **New this session**: Global Account (§9.3) had zero mentions anywhere in the evidence pack —
  added as `docs/dpg_evidence/15_global_account_evidence.md`.

This pass **did** correct the `dpg_evidence/` pack itself, narrowly: the five specific, verified
inaccuracies above, plus the new Global Account supplement. Nothing else in the pack was rewritten
— see the pack's own files for the exact diffs. `docs/audit_dpg_unfinished_features_2026_11.md`
remains untracked, read-only research and was not itself edited.

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
- **The two previously flagged phone-app API-contract discrepancies have now both been verified
  and closed, with evidence, not merely re-asserted** (checked against `check_app_api.py`'s actual
  current source and the real test runs, this session):
  - **Missing `donation` object in the registration response**: this was **not a backend defect**
    to begin with. `apply_free_registration()` has never returned a `donation` object — Qoins are
    minted server-side with no field reporting it back, which is correct, intended behavior since
    the 2026-10 payment removal (see `docs/qoins_earn_reference.md`). The checker's own assertion
    used to also expect a `donation.kind == "free"` key that the backend never sent; that stale
    expectation was removed from the check (`check_app_api.py` line ~199), which now correctly
    asserts only `s == 201 and reg.get("token") and "donation_pending_amount" not in reg`. Nothing
    in the backend changed; the check's incorrect assumption did.
  - **Vote-tally display bug after an election closes**: this **was** a genuine backend defect —
    `election_core._ensure_tallied()` tallied a cycle's winners once ever per
    `(village_id, zodiac_sign, year)`, never recomputing even after real votes arrived (Task 1B,
    §9.3/above). Fixed by always recomputing from current `election_votes` and UPSERTing the
    result. Verified by: `check_app_api.py`'s own `"week 4: winners have the most votes"` check
    (line ~365), confirmed passing in the checker run above (156 passed, 1 unrelated, pre-existing
    failure); and the dedicated
    `tests/test_election_winner_tally.py` (25/25 passing), which reproduces the exact real-database
    failure (a cycle tallied with zero votes on record) before proving it self-corrects.
- **Qumanity Lok LLP is still in registration** — the IP has not yet been formally assigned;
  copyright assignment, trademark filing, and domain transfer are all gated on that completing.

---

## 14. Git and release state

- Branch `main`. Local `HEAD` = `origin/main` = **`a157d7af01e1e5791de6e2449cde2945652c8659`**
  (`a157d7a`), confirmed by a live `git ls-remote origin refs/heads/main` in this session (not a
  cached ref) immediately after the push, and re-confirmed again in the documentation-reconciliation
  pass that produced this update.
- Two commits landed this release, in this order, both already described in full in §9.3 above:
  `a7d43a7` ("Harden Global Account authorization and election handling" — backend) then `a157d7a`
  ("Add Global Account registration and dashboard UI" — website UI), on top of the prior tip
  `d5383971a246af39dc587945fcb4924e02e890a0` (the Q-Map/3D-future-vision commit). Combined release:
  **33 files, 3,043 insertions, 77 deletions**, pushed as a single clean fast-forward (`git push
  origin main`, no force, no rebase) — confirmed via `git merge-base` that the prior remote tip was
  a direct ancestor of the new local `HEAD` before the push was attempted.
- **Pre-existing, unrelated uncommitted changes remain in the working tree**, deliberately excluded
  from both commits above and still untouched by this documentation pass: 9 modified tracked files
  (`db.py`, 6 `folder_export/Earth/*.json` mirror files, `static/js/dashboard.js` — an unrelated
  wallet-balance-modal refactor, ownership unresolved, see §13 — and `tests/test_post_kinds.py`,
  dated 2026-10-27 in its own content) plus 25 untracked paths (4 `docs/audit_*_2026_11.md`
  research documents, `docs/family_tree/`, `docs/identity_cards/`, 8 untracked
  `folder_export/Earth/*` export subtrees, 7 location-data maintenance scripts under `scripts/`,
  and 4 `static/data/*.before_regen_*.json` snapshot files). These represent other, independently
  scoped work in progress and should be picked up, reviewed, and committed on their own terms by
  whoever owns that work next — not bundled into any future commit without a deliberate decision to
  do so.
- **Standing git rules for this project**: no `git add -A`/`git add .` — stage named files only.
  Never force-push. Never amend without being explicitly asked. One commit per approved task.
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer on commits made by an
  assistant session.
- No access to Railway/production from an assistant session beyond read-only, unauthenticated
  inspection of the public site — hand the user exact commands to run themselves for anything that
  needs Railway CLI/dashboard access (the CLI's OAuth token was expired at the time of this
  release; re-authentication is an owner action). Never guess or use real member/admin credentials,
  even locally.

**Update (2026-11-16) — superseded by this note, not re-verified above:** local `HEAD` =
`origin/main` = **`7699cc6f336537cba1141020a20d96146ed31295`** (`7699cc6`), confirmed by
`git rev-parse HEAD` / `git rev-parse origin/main` matching immediately after the push. Everything
in this section above is the `a157d7a` release's own record and is left as-is; see §17 below for
what landed between `a157d7a` and `7699cc6` (Family Tree Cascade, Account Recovery, LBE, the
synthetic demo route, Q-Cards, and the family-invite/member-list fixes).

**Second update (2026-11-16, later the same day):** local `HEAD` = `origin/main` =
**`a6abe6859a71b7a6f6f10b805065070b5f1beef0`** (`a6abe68`), same confirmation method as above. See
§18 below for what landed between `7699cc6` and `a6abe68` (the Q-Punch cascade from Village to
Earth, Upper House Sovereignty / the People's Vote, `geography_core.py`, and the Contextual Help
System).

---

## 15. Next-phase handover instructions for the phone application

**The website feature-development phase is complete and closed as of this handover.** Current
website state: `Qumanity_DPG`, branch `main`, `origin/main` = **`a157d7af01e1e5791de6e2449cde2945652c8659`**
(see §14 for the full release detail). The next phase is the **phone application**
(`qumanity-app` / `Qumanity_App`, a separate repository, React Native/Expo). This section is
written so a new development conversation can start the phone-app phase from this document alone,
without depending on any prior chat history.

**This is a continuation, not a greenfield start.** The phone app already has substantial,
previously-shipped work against this same backend — do not re-implement any of the following,
only extend it: sign-in and registration (`mobile/src/app/register/*.tsx`), Global Account
registration (Present Location picker with no `onlySubcontinent` restriction, `is_global_account`
consumption — see below), the Dashboard's Public-tab filtering, Q-Punch election display
(`mobile/src/components/ElectionCard.tsx` + `electionCard.logic.ts`), and the "Account IDs" screen
(`mobile/src/app/account-ids.tsx`, which already calls the Path A account-ID-request flow
described below). The living plan for this work is `Qumanity_App/docs/WEB_TO_APP_MIGRATION_PLAN.md`.

### What is implemented on the website and verified, as of this release
- Global Account registration and classification (§9.3): a Public Account (present location in
  one of the 10 Sub-continent countries) vs. a Global Account (any other country) is decided
  **server-side only**, derived live from `present_location_json` by
  `account_core.account_access_type()` — never a client-supplied flag, never a persisted column.
- The shared present-location validator, `account_core.validate_present_location_change()`, now
  gates **every** path that can write `users.present_location_json` after registration — both the
  website's profile-change-request flow and the account-ID-request flow below (the C1 security
  correction, §9.3) — enforcing full geography-ancestry validation and a hard Global↔Public
  boundary lock in both directions.
- Election/Q-Punch winner-tally correctness (Task 1B, §9.3): a closed cycle's winners are now
  always recomputed from current votes, not frozen at first observation.
- All of the above verified by 1,370 passing backend checks (33 files) and the cross-repo checker
  (156 passed, 1 pre-existing unrelated failure — see "Known API/test limitations" below), and
  confirmed live on production by direct, read-only inspection of the deployed `/register` page
  and `register.js` (§9.3, §14).

### API contracts the phone app must reuse (not redefine)
- **Sign-in/registration**: `POST /login` and `POST /api/auth/register`, both with `client: "app"`
  to receive `{token}`; every subsequent call carries `Authorization: Bearer <token>`. See
  `docs/phone_app_api.md` (identical copy in both repos) for the full, currently-accurate contract
  table — it documents the sign-in flow, `GET /api/me`, the Account-IDs endpoints, and the Q-Punch
  election endpoints in detail; this handover does not duplicate that table.
- **Account classification**: `GET /api/me` returns `is_global_account: boolean`, derived
  server-side exactly as described above. The app must treat this as authoritative for UI
  decisions (e.g., hiding the Public tab) but must **never** assume it also grants or denies any
  specific permission — every backend permission check (board access, Q-Punch eligibility)
  re-derives its own authorization independently from `present_location_json`, not from this flag.
- **Account-ID requests ("Path A")**: `POST /api/people/account-ids/request` (submit) and
  `POST /api/admin/account-ids/<id>/decide` (admin approve/reject) — already called by
  `mobile/src/app/account-ids.tsx`. As of this release, **both** steps run the same shared
  validator described above: a request that would cross the Global↔Public boundary, or whose
  geography doesn't correctly nest, is rejected (400) at submission, and re-validated again
  (independently of what passed at submission) at approval. The app's existing generic
  `try`/`catch` error handling on this screen already surfaces a rejection correctly — no app
  change was needed for this fix and none is required now.
- **Q-Punch election data**: `GET /api/qpunch/village`, `GET /api/election/status`,
  `POST /api/election/nominate`, `POST /api/election/vote` — all already integrated
  (`ElectionCard.tsx`). `winners.male`/`.female` are **name strings**, never user ids, and
  `votes`/`winners` are `null` until the cycle's status is `"closed"` — the app must keep
  displaying these fields exactly as the backend sends them, never computing a winner or detecting
  a tie independently (there is no backend-exposed "tie" signal to read; ties are resolved inside
  `election_core._ensure_tallied()` before the response is built).

### Identity and account-type distinctions
- Identity is the 9-digit Private ID + 5-character PIN; this is the one identity system. The phone
  app must not introduce a parallel one.
- Account type (Public vs. Global) is a **derived classification**, not a stored account "kind" —
  see above. A Global Account has `present_location` stopping at Continent+Country; a Public
  Account has the full Zone→Village chain available (though not all levels are mandatory).

### Geography hierarchy and stable location-ID requirements
- Eight nested levels: Village → Tehsil → District → State → Zone → Country → Continent → Earth
  (§4) — except a Global Account, whose Present Location deliberately stops at Country. The app
  must read and write the same dotted location IDs this backend already uses (e.g.
  `CS.DL.3.4.1A`), never mint its own location identity scheme. `mobile/src/api/locations.ts`'s
  `childrenOf()`/`toStruct()`/`isComplete()` already implement this correctly for both a Public and
  a Global Present Location — reuse them, don't reimplement.

### Permission and authorization rules
- Every authorization check (Board access, Q-Punch nomination/voting) is enforced **server-side**
  and re-derives its own rule from the member's actual stored `present_location_json` — the app
  must never assume a client-side account-type flag is sufficient to gate a feature; always let the
  server's own response (200 vs. 400/403/404) be the real gate, and treat the client-side tab
  hiding as a convenience, not a security boundary.

### GPS consent and privacy requirements
- GPS/location consent follows the existing versioned-consent model already implemented
  server-side (§6, §7.1, §12) — the app must not introduce a separate, mobile-only consent flow.

### Q-Punch election restrictions
- Q-Punch (Village Council election) reachability remains **village-only** (§9.2) — a Global
  Account, and a Public Account with no resolved village, are never eligible, enforced by
  `election_core._present_village_id()`'s independent re-check of `account_access_type()`.

### Known API/test limitations (verified, not assumed)
- The cross-repo checker's one remaining failure, `"board shows the post, score and vote state"`,
  is pre-existing, unrelated to Global Account/Q-Punch, and tracked separately — it is **not**
  fixed and should not block phone-app work, but should not be mistaken for a Global-Account- or
  election-related regression if it's ever investigated.
- Railway's own deployment metadata (build logs, exact deployed SHA, health-check result) has
  **not** been independently verified by an assistant session for this release — only the live
  site's actual served content was checked. Confirming Railway's own record is an owner action.

### Deferred website improvements (not blockers to this phase, see §13 for the full list)
No Report/Block-member mechanism; no Privacy Policy/Terms of Service pages; no self-service data
export/delete; no minimum-age/parental-consent gate; some public demographic routes show village
member names pre-sign-in; `dpg_evidence/ARCHITECTURE.md` drift; stale route/table counts in
`API.md`/`ARCHITECTURE.md`/`DATA_MODEL.md`; India location deduplication unexecuted; OSM proximity
worker's Overpass usage not load-tested; councils above village can't yet receive/initiate
messages; Qmail has no delete-on-request path.

### Work intentionally paused by the owner
Qumanity Lok LLP's registration (and the resulting copyright/trademark/domain transfer) — pending,
unrelated to code, explicitly not a development task.

### Phone-app-specific next steps
Continue the existing `Qumanity_App/docs/WEB_TO_APP_MIGRATION_PLAN.md` plan from wherever it was
left — this handover does not re-litigate that plan's own phase numbering. Any new phone-app work
should be scoped and approved the same way the website work in §9.3 was (explicit, narrow task
authorization; no unilateral staging/commits/pushes).

### Where to start inspecting
`account_core.py` (the single source of truth for classification and present-location
validation), `app.py`'s `api_auth_register()`/`_profile_for()` (registration and the `/api/me`
shape), `social_core.py`'s `request_new_account()`/`decide_account_request()` (Path A),
`election_core.py`'s `_present_village_id()`/`_ensure_tallied()` (Q-Punch eligibility and
tallying), and, in the phone-app repository, `mobile/src/api/qumanity.ts` (the full typed API
client) and `docs/phone_app_api.md` (the living API-contract reference, identical in both repos).

**Open design/legal items the phone app project must respect, not re-decide on its own**: Q-Punch
reachability remains village-only (§9.2); the India location deduplication plan remains
unexecuted (§4); the DPG evidence pack has known, uncorrected drift (§10); Qumanity Lok LLP
registration (and the resulting copyright/trademark/domain transfer) is still pending (above).

---

## 16. Pre-Launch Fixes — November 2026

A separate, narrowly-scoped pre-launch task (six owner-identified issues) on top of the Global
Account/C1 release above. Three files changed; everything else below was investigated and found
either already correct or deliberately left alone.

### Registration styling — root cause found and fixed
**Root cause**: `static/css/style.css`'s global `html, body { height: 100%; background: var(--qm-bg); }`
caps `body`'s painted box at the viewport height. On any page taller than one screen — every
cosmic-themed page, registration most visibly — the content below that point falls through to
`<html>`'s own background (the original light cream, `var(--qm-bg)`), which is exactly the
reported "white background at the bottom." Confirmed live, not assumed: `body.offsetHeight` was
221px against a real `scrollHeight` of 2348px.
**Correction**, in `static/css/cosmic.css`'s existing shared selector
(`body.qm-about, body.qm-cosmic-dashboard, body.qm-cosmic-register`): `height: auto;
min-height: 100vh;`. This is the one targeted fix — `<html>`'s own background was deliberately
left untouched, since with `body` now full-height it is never visible regardless of its color.
**Verified**: desktop and 375px mobile visual checks (local dev server, screenshotted at the
bottom of the page after scrolling) both confirmed the white area was gone; `body.offsetHeight`
now equals `scrollHeight` exactly at both widths.

### Provisional locations — already implemented; one styling bug fixed
The Tehsil/Village "Can't find my Tehsil?/Village?" crowdsourced submission workflow
(`templates/register.html` + `static/js/register.js`'s `QMProvisionalLocations` module,
backed by `provisional_location_core.create_provisional_tehsil()`/`create_provisional_village()`)
was **already fully implemented** before this task — not built here. The existing geography-
ancestry validation, duplicate-prevention (normalized-name + parent match, with a clear rejection
message), `status='provisional'` (never auto-verified), and existing activation-threshold rules
were all read and confirmed correct, and were **not** modified. The only defect found was
cosmetic: the confirmation message's hardcoded `color: #6a5200` (register.css, written for a
light page) was confirmed live to render as near-unreadable dark brown against this dark theme.
Fixed with one rule in `cosmic.css`: `body.qm-cosmic-register .qm-provisional-confirm-msg { color:
var(--qm-accent-gold); }`. **No backend or JavaScript change was required or made for this task.**

### Tri Nagar — owner decision: leave both entries unchanged
`scripts/audit_india_master_locations.py` (read-only, already in the repository) confirms exactly
one Tri Nagar name collision in `Qumanity_Master.json`: two **different** tehsils under district
"Chandni Chowk" — `CS.DL.7.4` (12 villages) and `CS.DL.7.14` (23 villages) — sharing a display
name. This is not a duplicate record; both contain real, distinct geographical data. A pre-existing
script, `scripts/add_ganesh_pura_tri_nagar.py`, already documents this exact situation and quotes
the Founder's own prior ruling: *"The duplicate names are a known issue, but they are not this
task."* **Owner decision (2026-11-09): both entries are retained exactly as they are.** Neither
was merged, renamed, or deleted; their villages, ids, parent relationships, and references were
not touched; no location-cleanup or migration script was run against them. **This is recorded
here as a known, deferred geographical naming/data-quality issue — explicitly not a launch
blocker.**

### Navi Mumbai — already complete, re-verified
Ghansoli, Vashi, Nerul, and the other Navi Mumbai nodes added by `scripts/add_navi_mumbai_locations.py`
were already present, from a previous session, in: the real `Qumanity_Master.json`
(`~/Desktop/0_Earth/Qumanity_Master.json`), the committed derived file
`static/data/subcontinent_districts.json` (confirmed via `git diff` — zero changes), the live
`india_villages` SQLite table, and the actual registration API (`GET /api/subcontinent/districts`).
**No location data was changed in this task** — the insertion script was read, not re-run.

### Navigation — two items removed from exactly where they existed, no broader redesign
The site has two separate, unrelated navigation patterns — `home.html`'s own `#hm-links` nav
(Vision/How it works/Identity/Governance/Qoins/Roadmap/Explore the Future/About) and the shared
`qm-header-actions` component used by `about.html` and five other pages (which, on `about.html`,
was Home/Elements/Login/Register). Neither matched a literal "Home/Login/Register/About"
four-item target as a whole, so rather than redesign either pattern, exactly the two named items
were removed from exactly where they existed:
- **"Explore the Future"** removed from `home.html`'s nav (the single `#hm-links` markup reused
  for desktop, mobile, and the collapsed/burger menu via CSS/JS toggle — one edit covers all
  three). Retained as a homepage hero content CTA, next to "See who's here."
- **"Elements"** removed from `about.html`'s `qm-header-actions` nav, leaving
  Home/Login/Register. "Explore the Future" was added there too, as an About-page hero content
  CTA next to "Read the story." The `elements_dashboard` route/page and the one unrelated
  "Elements" footer link on the homepage were left untouched.
**No broader navigation redesign was performed** — the other five `qm-header-actions` pages
(dashboard, qmap, qmail, founders_message, the two copyright pages) never had Elements or
Explore the Future in them and were not touched.

### Deferred work, confirmed not attempted
No redesign of the 3D Explore the Future slides/engine/assets. No address-parser or pincode-lookup
code. No broader India-geography cleanup beyond the (deliberately deferred) Tri Nagar item above.

### Verification and release
- **Implementation commit**: `7840ebb` — `fix: complete pre-launch styling and navigation
  updates` — exactly `static/css/cosmic.css`, `templates/home.html`, `templates/about.html`.
- **Handover commit**: this documentation update, committed separately immediately after the
  implementation commit (see `git log` for its exact hash — not self-referenced here, since a
  commit cannot record its own hash in its own content).
- **Regression**: re-run in full against the implementation commit (`7840ebb`), not assumed from
  an earlier report — **35 test files, 1,467 checks, 0 failures**, every file exiting 0. The
  specifically-named suites all independently confirmed: `tests/test_provisional_locations.py`
  (76/76), `tests/test_global_account.py` (136/136), and the two unrelated, pre-existing
  retired-account suites `tests/test_app_token_auth.py` (25/25) and
  `tests/test_browser_session_auth.py` (72/72) — run only to confirm they still pass, never
  staged or committed as part of this release.
- **Production verification**: local dev-server verification (desktop + 375px mobile, screenshot-
  confirmed) is **not** the same claim as production verification. Whether this release was pushed
  and deployed, and what was confirmed live on `https://web-production-126c3f.up.railway.app`
  afterward, is recorded in the task's own final report, not here — this document records what
  the code does and why, not a point-in-time deployment status that a later reader could mistake
  for current.

---

## Retired-Account Authentication Security — November 2026

### Implementation

The fix itself was written by a parallel session on 2026-11-09, found already present and
uncommitted in the working tree; this release inspected it, confirmed it was correct and
complete, and committed it unchanged. Two parts, both in `app.py`:

- `_app_token_auth()` (the `@app.before_request` hook that signs a request in from a `Bearer`
  token) now also selects `is_removed` alongside `pin_hash`, and refuses the request with the
  same generic `{"error": "Please sign in again"}`, HTTP 401 used for any other invalid token —
  a malformed token, a tampered signature, an expired token, and a retired account's
  previously-valid token are all indistinguishable to the caller. No hint is given that the
  account exists or was retired.
- `_retired_session_guard()`, a new `@app.before_request` hook registered immediately after it,
  drops `session["user_id"]` on every request (except `static` and requests already carrying a
  `Bearer` header, which `_app_token_auth()` already handled) when the signed-in session's account
  has since been retired. This closes the browser-session case: a signed cookie the browser
  already holds can't be revoked server-side, so the account's `is_removed` flag is re-checked on
  every request instead. Dropping `user_id` makes the request anonymous, so `login_required`
  answers with its ordinary redirect to `/login` — again, no hint of retirement.

**Critical check, resolved by analysis, not a new fix.** The task that authorized this release
asked specifically whether a malformed or invalid `Authorization` header could let a retired
account's still-valid browser-session cookie slip past `_retired_session_guard()`. Traced by hand
through every header variant: `_app_token_auth()` is registered earlier in the file, and Flask
runs `before_request` hooks in registration order; it either rejects the request outright
(short-circuiting the chain, so `_retired_session_guard()` never runs at all) or re-establishes
`session["user_id"]` to the bearer token's own already-validated identity. No bypass is possible.
This was confirmed empirically, not just reasoned about: `tests/test_browser_session_auth.py`
Section E exhaustively tries the retired account's real pre-retirement cookie against 10 distinct
`Authorization` header values (absent, its own old valid token, invalid, `"Bearer "` with nothing
after it, bare `"Bearer"`, lowercase `"bearer <token>"`, a `"Basic ..."` scheme, expired, valid for
an unknown user id, and valid for a different active account) — every one passed. No narrow
correction was needed or made, consistent with the task's own instruction to change only what the
tests showed was actually broken.

- **Security commit**: `e045cf1` — `fix(security): reject app tokens and sessions for retired
  accounts` — exactly `app.py`, `tests/test_app_token_auth.py`, `tests/test_browser_session_auth.py`.

### Regression

Full suite re-run against the committed security fix: **35 test files, 1,467 checks, 0
failures**, every file exiting 0. The four specifically-named suites: `tests/test_app_token_auth.py`
(25/25), `tests/test_browser_session_auth.py` (72/72), `tests/test_global_account.py` (136/136),
`tests/test_provisional_locations.py` (76/76) — the latter two confirmed unaffected by this
change, as expected, since neither touches token or session authentication.

### Production verification

Pushed to `origin/main` and deployed via Railway's auto-deploy. Confirmed against
`https://web-production-126c3f.up.railway.app`, in two passes — the first incomplete, the second
conclusive.

**First pass (initial deploy):** active-account bearer-token and browser-session auth both
verified working post-deploy. Retired-account rejection could not be verified yet: retiring a test
account requires writing `is_removed = 1` for it, and the only code in this repository that ever
does this, `scripts/retire_stray_demo_accounts.py`, is deliberately hardcoded to two specific
historical ids (25, 26) and refuses any other account — there is no general-purpose retirement
route or script. An assistant session has no direct production database access and no
authenticated Railway CLI session, so no unsafe database write was attempted; the owner was asked
to perform the retirement directly.

**Second pass (owner-performed retirement, same day):** the owner created one further disposable
Global Account test registration — `user_id 97`, name "QA Verify Retired", Japan — and, after an
assistant session persisted its bearer token in the browser tab's `localStorage` (so it could
still be replayed after the account was retired) and confirmed both the token and a parallel
browser session authenticated normally (`GET /api/me` → HTTP 200 for both), the owner ran
`UPDATE users SET is_removed = 1 WHERE id = 97` directly against the production database via
Railway's SQL console.

The first attempt at this surfaced a separate, important finding before it reached a real result:
the deployment active at that moment was still `f02fe6e3`, a build that predates this security fix
entirely (`e045cf1`/`278f54a` had been pushed but not actually redeployed) — replaying the token
against stale code understandably still returned 200. **This is the reason this section states
explicitly, for any future release, that deployment must be confirmed by commit hash on the
Railway dashboard, not inferred from a successful `git push` or a bounded time-based wait** (the
technique used earlier in this release, which this incident shows is not sufficient on its own for
a change with no visible static-asset fingerprint). Once the owner redeployed from `main` and
re-ran the retirement SQL, the real test was performed:

- **Bearer-token rejection — CONFIRMED.** Replaying user 97's original pre-retirement token
  against `GET /api/me` returned **HTTP 401**, body `{"error": "Please sign in again"}` — no
  profile data, no hint the account exists or was retired.
- **Browser-session rejection — CONFIRMED, by its actual (not literal) contract.** Replaying user
  97's original pre-retirement session cookie against `GET /api/me` did not return a literal `401`
  JSON body; `/api/me` is decorated `@login_required` (session-based), and `_retired_session_guard()`
  drops `session["user_id"]`, which makes the request anonymous to `login_required` — so the
  server issued an HTTP redirect to `/login` (confirmed with `fetch(..., {redirect: "manual"})`,
  which reported `type: "opaqueredirect"`, i.e. a real redirect occurred). This is exactly the
  documented, intended design (§ Implementation above), identical to what any signed-out visitor
  gets, with no account data and no retirement hint disclosed either way.
- **Registration**: confirmed still operational throughout (ten disposable test registrations
  across this whole verification effort, see below).

**Residual test data**: ten disposable Global Account test registrations were created on
production across this verification effort, every one using Japan as both birth and present
location specifically to avoid touching any real India/Q-Punch data: user ids 94–103. Of these,
only **user id 97** ("QA Verify Retired") was actually retired (`is_removed = 1`), by the owner, as
test evidence for this section — its retired status is left intact deliberately, not reversed. The
other nine (94, 95, 96, 98–103) remain ordinary, unretired Global Accounts with no further
significance; none was modified beyond its own registration, and no real member account was
touched at any point.

### Email delivery — an incidental finding, not part of this fix

While registering disposable test accounts for the check above, `send_registration_notification()`
(unrelated to authentication — see [email_core.py](../email_core.py)) was found to be completely
silent in production: `RESEND_API_KEY` was missing from Railway's environment, so every
registration's admin-notification email was a silent no-op. Fixing this took three attempts, each
diagnosing a real, independent cause rather than guessing twice at the same one:

1. Resend's HTTPS API (the module's original transport) — once the missing key was added, every
   request was rejected by **Resend itself** with a 403 from Railway's egress IP (an IP-level
   restriction on Resend's side).
2. Resend's SMTP relay (`smtp.resend.com:587`, STARTTLS) — switched to on the reasoning that an
   HTTPS-specific restriction wouldn't apply to SMTP; instead, this failed differently, with a
   `TimeoutError` connecting to port 587, because **Railway's own network firewall blocks outbound
   SMTP entirely**, independent of which provider is on the other end.
3. **SendGrid's HTTPS API** (port 443, the same port every other outbound call this app makes
   already uses) — committed as `147f833` (SMTP attempt, superseded) and `3a6ecd3` (SendGrid,
   final). Verified live: a test registration (`user_id 103`) produced, in Railway's logs,
   `EMAIL_SEND_ATTEMPT operation=registration to=f***@qumanity.in` followed by
   `EMAIL_SEND_SUCCESS operation=registration status=202 message_id=je7-PGkAQ0CdWKuJ46haVA`, and
   the notification email was confirmed received by the owner in `founder@qumanity.in`.

`tests/test_email_core.py` was rewritten alongside each transport change (now mocking
`urllib.request.urlopen` against SendGrid's endpoint/payload shape) and currently covers 38 checks,
0 failures. This whole thread was never part of the retired-account security fix's own acceptance
criteria — it surfaced only because disposable test registrations for the security check happened
to trigger it — and is recorded here for completeness, not as a reason this release was blocked.

### Phone App implications

The website backend remains the sole source of truth for authentication and account-retirement
state; the Phone App must not invent its own token-expiry or account-status logic. The Phone App
Chat can treat a locally cached token exactly as it already does for any other 401 — no app-side
change is required, since the app only ever consumes `/api/me` and the existing 401 contract, both
confirmed unchanged (for an active account) and now confirmed correctly enforced (for a retired
one) by this release. The email-delivery fix above has no Phone App implication at all — it is a
website-side admin notification the app never calls or depends on.

### Final website status

**Qumanity Website Development Phase: COMPLETE.** The retired-account authentication fix is
committed (`e045cf1`), regression-tested (97 dedicated checks plus the full 1,467-check suite, 0
failures), deployed, and — per this release's own explicit closing condition — directly verified
against a real retired production account (`user_id 97`): its original bearer token now returns
HTTP 401, and its original browser session is now treated as anonymous, both with no data or
retirement hint disclosed. Active-account authentication, registration, and (incidentally) admin
email notifications are all confirmed working on the same production deployment. No further
retired-account work is anticipated; the email-transport history above is recorded for context,
not as an open item.

---

## 17. Family Tree Cascade, Account Recovery, LBE, the Synthetic Demo, Q-Cards, and Family-Invite/
    Member-List Fixes — November 2026

Backend work continued on `Qumanity_DPG` after §16's "Website Development Phase: COMPLETE"
declaration above — not a reopening of that phase, but ongoing Phone App backend support plus
independent Family Tree correctness work. Nine commits, `a157d7a..7699cc6`, summarized here;
§14's own git-state record above is left as the `a157d7a` release's own point-in-time snapshot,
not rewritten.

### Family Tree Cascade (`21d4016` — *family tree cascade, recursive count, and nuclear-only
recovery*)
- `family_core.recursive_member_count(conn, group_id)`: the actual "how many people does this
  unit's cascade reach" figure — founders, sons' households recursively (via
  `husband_parent_group_id`, the Daughter Rule), and unmarried daughters. This is what the Family
  Tree screen's unit card shows, and (per §17's own later fixes below) is now also what the
  Members modal's list length matches.
- **The gender-blind sync fix**: `_sync_family_membership()` used to auto-leave every married
  child out of their birth unit regardless of gender. Corrected to the real-world rule — a married
  **son** stays an active member of his birth unit (patrilocal); a married **daughter** still
  leaves hers (she joins her husband's).
- `founder_is_deceased` (`{"husband": bool, "wife": bool}`) added to the unit brief
  (`_group_brief()`), read live off `family_nodes.is_deceased` per founder — the Family Tree card's
  own 🕊️ marker source. Dormancy itself (both founders deceased) is unchanged — still
  gender-symmetric.
- `family_recovery_core.py` (new, 639 lines) + migration `037_family_recovery.py`: Rule 5 of the
  account-recovery-by-relationship flow, amended to accept a claimed relationship of parent, child,
  sibling, or spouse only — **grandparent and grandchild are refused**. Only the grandparent case
  had a dedicated test in this commit (the commit message says so explicitly); grandchild coverage
  landed later, as its own task (§17's Task 4 cross-reference: `tests/test_family_recovery.py`).

### LBE (`99106ce` — *add LBE with location search, full-screen boards, bottom dock, and audit
logging*)
Location-Based Exploration for the Admin Panel dashboard: a location search box, full-screen board
views, a bottom dock for switching between open boards, and audit logging of what an admin
viewed. `app.py` (+213), `static/js/multiview.js` (rewritten, 298 lines touched),
`static/css/dashboard.css`, `templates/dashboard.html`, plus migration `036_admin_location_views.py`
(the audit log table). The pre-existing Admin Panel itself (`e4750e4`, council-scoped queue — see
the module table in §5) predates this handover's own `a157d7a` baseline and was already documented
there; LBE is additive to it, not a replacement.

### Phase C Account Recovery (`4fef612` — *add account recovery intake and admin panel recovery
workflow*)
A member-facing recovery intake flow plus the Admin Panel's own recovery-request workflow to act
on it: `admin_queries_core.py` extended, `app.py` (+487), migration
`038_account_recovery_fallback.py`, and `docs/phone_app_api.md` gained its own recovery section
(the Phone App's contract for this flow). `tests/test_account_recovery_fallback.py` (505 lines, new).

### The Synthetic Demo Route (`cee7356` — *add public synthetic demo at /demo/rohini-sector-24*)
A public, unauthenticated demo page at `/demo/rohini-sector-24` built entirely from synthetic data
(`demo_data.py`, new, 213 lines) — no real member data is reachable through it. New template
(`templates/demo_rohini_sector_24.html`), stylesheet (`static/css/demo.css`), and its own test file
(`tests/test_demo_rohini_sector_24.py`, 270 lines). Intended for pitch/demo purposes, not a feature
real members use.

### Q-Card Backend (`15bccc8`, `fbb5546`)
A physical card carrying a QR-encoded, unguessable token that lets a member sign in without typing
their 9-digit Private ID — full design reasoning in `docs/qcard_phase1_2026_11_15.md`.
- **`15bccc8` — scan-to-login, token-hash at rest, enumeration-safe resolve.** Migration
  `039_q_cards.py` (the `q_cards` table: `token_hash`, `status` ∈ {`pending_payment`, `active`,
  `revoked`, `replaced`}, payment fields, `delivered_at`, `free_reason`). `q_card_core.resolve_token()`
  is a single indexed query with an identical code path for a valid and an invalid token — timing
  safety by construction, not by table size. `GET /api/card/<token>` returns a first name only for
  a valid active card, an identical generic refusal otherwise. `POST /api/card-login` takes the
  token plus the member's existing PIN, reusing `verify_user_pin_and_login()` — no second PIN
  scheme introduced. A replaced card's old token is refused outright (never forwarded to the
  replacement), so a found lost card can't be used to keep logging in.
- **`fbb5546` — admin actions, free-eligibility derivation, status-transition enforcement.** Six
  admin routes under `/api/admin/q-cards/` (mark paid, mark free, mark delivered, revoke, replace,
  list pending), gated by the global `_is_admin()` Founder/Admin check, not the broader
  council-scoped panel gate — money and free-grants stay with the Founder. Free eligibility is
  derived, never admin-supplied, across three categories: the Admin themself, the Admin's own
  family (reusing the Family Tree cascade above — `family_core.recursive_member_node_ids()`, a new
  sibling of `recursive_member_count()` returning the actual node-id set instead of a count, so a
  specific person's membership can be tested), and the pilot village council
  (`announcements_core.is_council_member()`). Status transitions are enforced at one Python
  `_set_status()` choke point — there is deliberately no SQL `CHECK` constraint, so this is the
  only enforcement, present in every writer (no un-revoke, no un-replace, no paid → unpaid).

### Family-Invite and Member-List Fixes (`3cfc20b`, `fd241f9`, `7699cc6`)
Three related fixes, found during Phone App integration testing against the Family Tree API:
- **`3cfc20b` — structured, consent-gated `family_relation_invite`.** When the Family Tree wizard
  matches a name to an existing Qumanity account, `family_core.notify_to_activate()` no longer
  sends a plain chat message that silently links the match with no approval step. It now queues a
  structured `people_requests` row (`kind='family_relation_invite'`) carrying `from_user_id`, the
  matched unit's `group_id`, a `target_node_id` pointing at a **fresh placeholder** (never the
  matched person's real node), and the slot's relationship label. Nothing claims or links the real
  node until the matched person explicitly accepts via the existing
  `/api/people/inbox/<id>/decide` route; declining leaves the placeholder untouched. `social_core`
  gained `inbox_history()` (`GET /api/people/inbox?include=history`) so an answered request no
  longer just disappears from the recipient's view.
- **`fd241f9` — the cascade members list and the 'admin'/'member' role fix.**
  `family_core.group_members_for()` now walks `recursive_member_node_ids()` instead of the flat
  `family_group_members` chat roster, so the Members modal's list length always matches
  `recursive_member_count()` on the same unit (previously a card could read "8 members" while its
  own Members sheet showed 3). Unclaimed tree placeholders are now included in the list, returned
  with `claimed: false` and `user_id: null`. The old three-way `'founder'/'admin'/'member'` role
  label is retired — `role` is now strictly `'admin'` or `'member'`, from
  `family_core._is_admin_of_group()` for that specific unit, never the raw `is_admin` column or
  founder-node membership alone. **Confirmed, deliberate trade-off**: a chat member added via the
  generic "Add Member by Public ID" invite who was never placed in the tree graph (no self-node) no
  longer appears in this cascade-based list — the Family Tree is the source of truth; they must be
  linked in the tree to be counted. **Confirmed, deliberate interaction**: a user who created their
  own parents' unit (common — whoever activates first founds it and gets `create_group()`'s
  creator-admin grant) correctly shows `role: 'admin'` there too, even though they are not a
  founder of that unit — `_is_admin_of_group()` is unchanged and is the intended single source of
  truth for this field.
- **`7699cc6` — `is_deceased` for unclaimed placeholders.** The one gap the above surfaced:
  `_unclaimed_member_row()` now also selects and returns `is_deceased` from `family_nodes`, so the
  Phone App's 🕊️ marker renders for a deceased founder even before anyone has claimed their node —
  matching what the Family Tree card already showed via `founder_is_deceased` above.

### Regression and release
Full suite re-run clean after every commit above (most recently 40 test files, 0 failures, after
`7699cc6`). All nine commits pushed to `origin/main`; see the §14 update note above for the
confirmed `HEAD`/`origin/main` match (`7699cc6`). Not yet reflected in `docs/MASTER_STATUS.md`,
which still records the `a157d7a` release as current — due for its own refresh pass.

---

## 18. Q-Punch Cascade, Upper House Sovereignty, the Geography Helper, and the Contextual Help
System — November 2026

Ten more commits landed between `7699cc6` (§17's own closing point) and the current `HEAD`
(`a6abe68`) — summarized here in the same spirit as §17: what shipped, why, and what's still open.
**Q-Card Backend is not repeated here** — it's already fully documented in §17 above
(`15bccc8`/`fbb5546`); nothing about it changed in this window.

### Small, self-contained fixes (`c6cb6b3`, `be22ac4`, `95dccc6`, `dd18516`)
- **`c6cb6b3` — the "Groups" rename.** The Collective Board's "Groups" button/drawer now reads
  "Local Areas" at Village level and "Sub-Groups" at Tehsil and above — wired into `board.js`'s
  own `applyLevel()`, the single existing place that already reacted to a level change.
- **`be22ac4` — `GET /api/app-version`.** A hand-maintained `LATEST_APP_VERSION` constant plus a
  public route returning `{"latest_version", "download_url"}`, for the Phone App's own
  (separately built) update-check UI to poll.
- **`95dccc6` — the missing grandchild test for Rule 5.** `21d4016`'s own commit message had
  flagged this as a follow-up; `tests/test_family_recovery.py` now asserts a grandchild is
  refused as a recovery verifier, the exact inverse of the existing grandparent case.
- **`dd18516` — the Statistics Dashboard upgrade.** Fixed a real bug — Flask's `jsonify()`
  alphabetizes dict keys on the wire, confirmed directly (`jsonify({"male":11,"female":7,
  "both":0})` → `{"both":0,"female":7,"male":11}`), which is why "Third gender" rendered before
  "Female"/"Male" — and replaced the raw-list Gender/Age/Element/Zodiac panels with a horizontal
  bar chart, a vertical column chart, and two SVG donut charts (a ~30-line stacked-circle helper,
  no new dependency). Small-count suppression (`"<5"`) is handled honestly throughout: a
  suppressed slice gets a fixed placeholder wedge size, never a fabricated percentage, and the
  whole panel hides outright (not just the numbers) when `total_humans` itself is suppressed.

### Q-Punch Cascade: Village-only to Tehsil-through-Earth (`5fbf229`, `60bbde7`, `2ae7cb6`, `b3369b0`)
Four commits, each shown as a diff and approved as its own phase before the next began.

**Schema and the geography helper (`5fbf229`).** `election_cycles` gained a `level` column
(`NOT NULL DEFAULT 'village'`, so every pre-existing row keeps meaning exactly what it already
did). Two new tables, `qpunch_councils` (one row per location/level/term) and
`qpunch_council_members` (the 8 seats under it — 1 Male + 1 Female per element), hold the
Tehsil-and-up council data; `village_council` itself is untouched, still its own 12-sign-seat
shape. **`geography_core.py`** (new module) answers "what are the direct child locations of X" —
`get_children(conn, level, location_id)` — needed because a Tehsil's own Lower House is "every
currently-serving council member across the villages under it," which first requires knowing
which villages those are. Two different lookup mechanisms live inside it, because the real data
genuinely differs: Continent→Country, Country→Zone, Zone→State and State→District all read the
same static JSON files the registration dropdowns already use (reused, not duplicated);
Tehsil→Village is a direct SQL lookup against `india_villages.tehsil_id`, the dedicated indexed
foreign key already built for exactly this — not a string match against the id, even though
today's ids happen to share a dot-prefix that could tempt one. (One place this module *does* rely
on that dot-prefix: recovering a district's own owning state from its id, since
`subcontinent_districts.json` nests districts under their state with no flat index of its own.)

**Election logic (`60bbde7`).** `get_lower_house(conn, level, location_id)` — the voting pool one
level up, computed live every time, never stored. `nomination_eligible()`/`voting_eligible()`/
`nominate()`/`cast_vote()` are all generalized in place (branching on `cycle["level"]`), with
`level='village'` (the default everywhere) taking the exact original code path unchanged — no
existing caller needed to change. A Tehsil-and-up cycle elects all 8 seats at once in a single
multi-year term (not 12 staggered per-sign cycles like village), tallied by plurality per
(element, gender) into `qpunch_councils`/`qpunch_council_members`. Votes land in a **new** table,
`qpunch_cascade_votes`, not the existing `election_votes` — a Lower House voter casts up to 8
ballots per cycle (1 Male + 1 Female, per each of 4 elements, with no "your own element"
restriction), which `election_votes`'s own `UNIQUE(cycle_id, voter, gender)` constraint was never
built to allow, and SQLite cannot widen a `UNIQUE` constraint on a live table in place. A
quarterly rotation engine (`_quarter_bounds()`/`_current_quarter()`/
`ensure_head_approval_current()`) splits each council's own term into 4 equal(-ish) quarters, one
element active at a time in Fire→Earth→Air→Water order, and resolves that quarter's Head: the
active element's Male candidate needs ≥51% of an Upper-House approval vote
(`qpunch_head_approvals`/`qpunch_head_approval_votes`, a new, separate yes/no referendum table —
again not a reuse of an existing votes table, since this is a single-candidate referendum, not a
pick-one-of-N election); short of 51%, the Female holds Head for that quarter by default.

**A real, caught-and-fixed bug**: the first draft of `current_cycle_for_location()` copied
village's own "recompute the window fresh every call" pattern — safe for village only because
`_sign_window()` is a pure function of the calendar (the same sign + today always gives the same
window). A first-ever Tehsil+ cycle's `nomination_start` has no such anchor; recomputing it from
`today` on every later call silently pushed a live nomination window forward every time the
function was read with a later date, making the cycle impossible to ever close. Found while
writing the verification script (votes kept failing "not open" after the window should have
passed) — fixed by reading a live cycle's *stored* dates once it exists, only creating a new
cycle once the previous council's own term has actually ended.

**Upper House Sovereignty / the People's Vote (`2ae7cb6`).** A correction mid-build: the Upper
House isn't just a one-time 51%-approval gate on the Male Nayak — it's the ultimate sovereign at
every level, and Head Approval is one *specific, standing instance* of that general power, not
the whole of it. `initiate_people_vote()`/`cast_people_vote()`/`tally_people_vote()` (new tables
`qpunch_people_votes`/`qpunch_people_vote_ballots`) let any member of a location's own population
call a direct referendum on anything; a PASSED vote (≥51% of ballots *cast*, the same share Head
Approval uses, not a turnout/quorum rule — a quorum would make a large population's own People's
Vote functionally impossible to pass) is recorded as binding on that location's council. Vote
counts stay hidden while a vote is open, matching `election_summary()`'s own existing
`show_votes` convention (no running tallies mid-vote, to avoid bandwagon effects). **Enforcing a
passed vote against the council's own actions is explicitly a separate, later task** — this phase
only builds the record.

**Frontend (`b3369b0`).** The Q-Punch modal's `openQp()` now fetches the cascade status/candidates
endpoints for any level above village and renders the 8-seat election, the active council and its
rotation roster, and the Head-Approval ballot; a separate, level-agnostic People's Vote card
(referendum text, Yes/No ballot, or the resolved outcome, plus a "Start a People's Vote" form)
appears for every level, village included. `tests/test_qpunch_cascade.py` and
`tests/test_people_vote.py` are both committed, covering the full election/tally/rotation/
approval and initiate/cast/tally/hidden-counts/residency-refusal flows respectively.

**New API routes**: `GET /api/election/status` / `GET /api/election/candidates` (both generalized
with optional `?level=&location_id=`, falling straight through to the original village response
when omitted — no existing caller affected), `POST /api/election/nominate`, `POST
/api/election/vote` (dispatches on payload shape: `council_id` present means a Head-Approval
ballot, otherwise a cascade seat vote), `POST /api/people-vote/initiate`, `POST
/api/people-vote/cast`, `GET /api/people-vote/status`.

**Known gaps, not yet built** — named explicitly in the task briefs that authorized this work,
not discovered later: enforcement of a passed People's Vote against the council's own decisions;
the Mentor/Manager/Agent record-keeping layer; `announcements_core.is_council_member()`,
`qmail_core.QPUNCH_REACHABLE_LEVELS`, and the Admin Panel's own council-scoping are all still
hardcoded to village-only (pre-existing, already-documented gaps — see §9.2 above — not touched
by this phase, since wiring Tehsil+ councils into them is its own, separate task).

### Contextual Help System (`a6abe68`)
Hovering a major dashboard widget (the Q-Punch button, the Qoin Wallet card, the Family Tree
intro card) now reveals a small "?" linking to `/about?from=dashboard#<anchor>`; the About page
detects `?from=dashboard`, shows a "← Back to Dashboard" button (using `history.back()`, not a
fixed `href`), and auto-expands whichever `<details>` contains the target anchor before scrolling
to it. Two of the three new anchors (`#karma`, `#family-tree`, `#qmail`) needed to be placed on
the specific existing card/bullet that actually defines that topic, not a new top-level
`<section>`, since About's own content has no standalone section for Karma or Qmail; `#punch`
(the pre-`a157d7a` Governance section, linked from `home.html`'s own nav twice) was deliberately
left unrenamed rather than broken for the sake of matching an illustrative example string.
**Known limitation, accepted as a later task**: `history.back()` returns to `/dashboard` at its
default tab, not literally the exact tab the user left — the dashboard's tab selection is pure
client-side state, never encoded in the URL.

### About page additions (same day, documenting the architecture above)
Two new sections, `#q-punch` and `#q-card`, inside the existing "The governance model, in full"
and "The mechanics, in full" `<details>` blocks respectively — the real, as-built cascade (8-seat
councils, the 4-quarter rotation, Upper/Lower House, the People's Vote) alongside the original
vision's own "Recursive levels" table (whose term lengths differ from what's actually running —
both are kept, with an explicit note pointing out the discrepancy rather than silently editing
the Founder's own earlier text). The dashboard's own Q-Punch help icon now points at `#q-punch`
instead of the older `#punch`, since that's the section that actually describes what the widget
shows above village level. The "Where Qumanity stands today" status list moved "Full Quantum
Punch" and the Q-Card's backend from "Ahead" into "Live," and added a one-line mention of the
Contextual Help System itself.

### Regression and release
Full suite re-run clean after every commit in this window (most recently 43 test files, 0
failures, after `a6abe68`). Not yet reflected in `docs/MASTER_STATUS.md`, which still records the
`a157d7a` release as current (see §17's own note — unchanged, still due for its own refresh pass).

## 19. Phone App Catch-Up, the APK Release-Hosting Move, and the Tehsil Cycle-Creation Race Fix —
November 2026

Two more commits land on top of `a6abe68` (§18's own closing point) before this one: `19d2eb4`
(the About-page `#q-punch`/`#q-card` sections and this document's own §18, both already described
in §18 above) and `5bc88af` (the APK release-hosting move, §19.3 below). This section's own commit
adds one more backend fix (§19.4) alongside itself.

### 19.1 Q-Punch Cascading Elections — no change, see §18
Nothing about the cascade architecture itself moved in this window beyond the one bug fixed in
§19.4 — the full design (the 8-seat, 4-element councils from Tehsil through Earth; the
Fire→Earth→Air→Water quarterly Head rotation; the Lower House, computed live from a location's own
child-location council members, versus the Upper House, that location's entire resident
population, sovereign over it; the 51% Head Approval ballot as one standing instance of the Upper
House's general power; and the People's Vote as that power's general form — any member can call a
referendum on anything, and a PASSED vote, ≥51% of ballots *cast* rather than of turnout, is
recorded as binding, though enforcing it against the council's own decisions is still a separate,
later task) is documented in full in §18 above and is not repeated here.

### 19.2 Phone App Catch-Up (separate repo, `Qumanity_App` — read-only verification only; this
session did not touch that repo)
Three commits landed there since this document's last word on the phone app (§15), bringing it in
step with everything §16-§18 built on the website:
- **`90e10a4` — the Family Recovery screen and verifier notifications.** A locked-out member's own
  screen (`recover-family.tsx`): the request form, a tracking code, a status checker, the new-PIN
  form, and the Private ID reveal once approved. The verifying relative's Notifications screen
  gained its own "Family recovery requests" section with Approve/Deny buttons. The same commit
  corrected the "Who are they to you?" relationship-direction question to match the asymmetric
  verification logic `family_core.py` already enforces (see §17).
- **`070e069` — the in-app Update Checker.** Fetches `GET /api/app-version` (§18's `be22ac4`) on
  launch and shows a banner when a newer version is available; "Update Now" opens the download URL
  in the browser. `app.json`'s own version was bumped to 1.0.1 to match.
- **`8104645` — the phone Q-Punch UI mirroring the web's cascade.** `CascadeElection.tsx` (the
  8-seat council, the quarterly rotation, the Head-Approval ballot, candidacy) and
  `PeopleVoteCard.tsx` (the Upper House referendum), with `QPunchSheet.tsx` switching between the
  Village (zodiac) and Tehsil+ (element) displays by level. Notable for §19.4 below: this commit's
  own message says the app "sequences the status and candidates API calls to avoid a backend race
  condition during the first Tehsil election cycle" — the phone app had already built its own
  client-side workaround for the exact bug §19.4 now fixes at the source. That workaround is
  harmless to leave in place and is still a reasonable call order on its own merits, but is no
  longer load-bearing.

### 19.3 APK Hosting Strategy (`5bc88af`)
The 1.0.1 APK is 101.44 MB — over GitHub's 100 MB per-file repository limit (the 1.0.0 build,
committed directly to `static/downloads/qumanity.apk`, had been under it). Rather than Git LFS or
shrinking the build, 1.0.1 is hosted as a **GitHub Release asset** instead — release `v1.0.1`,
asset `application-c9e06518-4acb-44cb-85dc-a9a852025ae9.apk` — uploaded directly to GitHub, outside
git history entirely. `/app` in `app.py` no longer serves `static/downloads/qumanity.apk` via
`url_for("static", ...)`; it's a plain `redirect()` straight to that Release asset's URL. The old
APK file was removed from the repo (`git rm`) so it stops bloating every future clone. **Do not
commit an APK to this repository again** — any future build goes to a new GitHub Release, with
only `/app`'s redirect URL (and `LATEST_APP_VERSION` in `app.py`) updated to point at it.

### 19.4 The Tehsil Cycle-Creation Race Fix
`current_cycle_for_location()` (the subject of §18's own cycle-anchoring fix) still had one more
bug: creating a location's first-ever election cycle read `election_cycles` for an existing row
and only inserted a new one if none was found — an unguarded read-then-write. Two concurrent
requests for the same location's first cycle (e.g. two members opening the Q-Punch sheet for the
same freshly-promoted Tehsil at once) could both read "no row," both attempt the `INSERT`, and the
second would hit `election_cycles`'s own `UNIQUE (village_id, zodiac_sign, year)` constraint
(`zodiac_sign` is always `''` for a cascade-level cycle) and crash with an uncaught
`IntegrityError` → 500. Fixed by changing the `INSERT` to `INSERT OR IGNORE`, then always
re-reading the row immediately afterward regardless of which request's insert actually landed —
both requests end up agreeing on the one real cycle. A `try/except sqlite3.IntegrityError` around
the insert is defense in depth for a failure `OR IGNORE` itself doesn't suppress (e.g. a
`FOREIGN KEY` violation): logged via `logging.getLogger(__name__)` — this module's first use of
Python's `logging` module, chosen over `flask.current_app.logger` so the database layer doesn't
need a Flask app-context dependency; it still reaches stderr with zero extra configuration — then
falling back to the same re-read. If that also finds nothing, a `RuntimeError` is raised rather
than letting `None` propagate into a confusing `TypeError` several lines later. Both
`tests/test_qpunch_cascade.py` and `tests/test_people_vote.py` still pass unchanged against the
fix; neither exercises genuinely concurrent requests, so neither hit the pre-fix bug directly, but
both confirm the single-caller path is unaffected.

### Regression and release
Full suite re-run clean after this fix: 42 test files, 0 failures. Not yet reflected in
`docs/MASTER_STATUS.md` (see §17's and §18's own notes — unchanged, still due for its own refresh
pass).

---

## 20. Chat-as-Dashboard: the Rail Pivot and the 3-Strike Temporary Access System — November 2026

**Documentation gap, flagged rather than silently bridged:** between §19's own closing point
(`a6abe68`) and this section's starting point, several real commits landed that are not separately
described anywhere in this document — registration shortening and auto-issued Q-Cards, the 4-circle
zodiac chart redesign, and the Unified Chat Architecture's first two steps (`2c27111`: `chat_core.py`
itself — the read-side aggregator across six pre-existing messaging systems, live-computed
presence, and the dual Account ID design for temporary cross-location access; `b590a01`: the
original standalone, 3-column `/chat` page). None of that is repeated or reconstructed here. This
section covers only the three commits that follow `b590a01` — `734e0cf`, `d15769c`, `dd91306` — a
pivot that builds directly on `chat_core.py` rather than replacing it.

### 20.1 The Pivot: Chat Becomes the Dashboard's Home Tab
The standalone `/chat` page is retired. `templates/chat.html`, `static/js/chat.js`, and
`static/css/chat.css` are deleted outright — their content now lives inside `templates/dashboard.html`
/ `static/js/dashboard.js` / `static/css/dashboard.css`, as a new tab rather than a second page.
`/chat` itself is kept as a plain redirect to `/dashboard` for one release (bookmarks, any stale
client-side link), meant to be deleted entirely once that's elapsed.

The old `dashboard.html`'s horizontal 4-tab bar (`qm-dash-tabs`: Global/Public/Personal/Private) is
replaced by a left icon rail (`qm-dash-rail`) with five icons — **Home** (new, now the default tab),
**Private**, **Personal**, **Public**, **Global** — reusing the exact same `qm-dash-tab`/`data-tab`
class and attribute the old tab bar used, so `dashboard.js`'s own tab-switching logic (a `panels`
object mapping tab name to DOM element, toggling `.hidden`) needed only one new map entry
(`home`), not a rewrite. Notifications, the language switcher, the time/weather/Vedic-calendar
button, and Logout all move from the old top header into the rail's own bottom cluster — same ids,
same existing `dash_extras.js`/`i18n.js` logic, relocated rather than rebuilt. A new Settings gear
in that cluster has no second settings surface behind it; it simply clicks the Private tab (reusing
its own existing click handler) and expands the `pv-settings` card that already lives there. The
`<header class="qm-header">` element itself is kept, stripped down to logo + title only, rather
than removed outright — `multiview.js`'s `measureDockOffsets()` reads `.qm-header`'s own rendered
height for the admin-only full-screen board dock's positioning, and a real header of roughly the
same height is lower-risk than relying on that function's `72px` CSS fallback for every admin
session.

**What the Home tab actually is:** the promoted content of the old `/chat` page, unchanged in
behavior — `chat_core.list_my_conversations()`'s aggregator feeding a middle conversation list
(Private chats/Family/Personal Groups vs. Governance Channels, grouped by location) and a right-hand
feed (messages, presence dots, the Members panel, the Governance-pane-only Karma badge). The one
thing dropped in the move is `/chat`'s own icon rail (Activity/Chat/Channels/Karma/Profile) — it was
always non-functional placeholders (its own module docstring said so), now superseded by the
dashboard's real one.

**What was deliberately NOT touched:** the Public and Global tabs' existing 3-column governance
panels (location-explorer sidebar, a center column with the Collective Board's post-and-vote feed,
Country/Zone Perception voting, Village Council election nomination/voting, and the Sub-Groups
create form, plus a Statistics sidebar) are kept exactly as they were. These are real, in-use
governance tools — not a chat surface this pivot could responsibly fold into "just another channel
list" without deleting live functionality nobody asked to lose. The same is true of the Private
tab's Identity/Qmail/Locations/Qoins Wallet/Karma/Election-history cards and the Personal tab's
Family Tree (zoom/scroll/edit) and Friend/Business Groups — all relocated under the new rail with
zero content changes. The only additions to the Public/Global panels are the two described in
§20.2 below: each explorer-tree node now shows its own Location ID, and the Stats modal gained a
"Request to Join" section.

### 20.2 The 3-Strike Temporary Access System
A user can request temporary access to a location they don't live in (e.g. "I coordinate a
trekking group that operates in this state each summer"), from the Stats modal reached via any
explorer-tree node, Public or Global. The request is decided by that location's own council first;
if rejected, it escalates one level up the geography hierarchy and is decided again, up to three
times total, before being closed out for good.

**Schema** (`chat_core.py`, `temporary_location_access` table, extended this pass):
- `strike_count` — rejections so far (0–3).
- `decision_level` / `decision_location_id` — whose council is being asked *right now*. These
  start equal to the request's own `location_level`/`location_id` (strike 1 is always decided by
  the target's own level) and walk upward one geography level per rejection
  (`geography_core.get_parent()`, new this pass — village→tehsil→district→state→zone→country→
  continent→earth, built from the same static JSON files and `india_villages` table the existing
  `get_children()` already reads, never a second copy of the hierarchy).
- `reason` — free text from the requester, shown to whoever decides each strike.
- `status` gained a new terminal value, `denied_final` — set on the third rejection. The
  pre-existing `revoked` status keeps its original, narrower meaning (an *active*, already-approved
  grant being pulled), never reused for an exhausted escalation.
- A new child table, `temporary_access_strikes` — one immutable row per decision (approve or
  reject), at whatever level actually decided it, who decided it and when. The parent row only
  ever holds current state; this table is the audit trail, the same "live row + append-only
  history" split `karma_entries` already uses elsewhere in this codebase.

**Who decides:** `chat_core._can_approve_temporary_access()` — the Founder always; a Village's own
Q-Punch Nayak/Nayika at Village level; at Tehsil-and-up, a seated member of that level's real,
elected Q-Punch cascade council (`election_core.is_cascade_council_member()`, new this pass — the
Tehsil+ equivalent of the Village-only `announcements_core.is_council_member()`, reading the
`qpunch_council_members`/`qpunch_councils` tables §18 built). A `GET /api/chat/temporary-access/
pending` route (`chat_core.pending_requests_for_approver()`) lists every pending request a given
user can currently decide, surfaced as a new "🔑 Access Requests" section in the existing
notifications dropdown, with Approve/Deny buttons.

**Enforcement, found to already be mostly in place rather than built fresh:** a temporary member
can chat in the foreign location's Governance Channel (`board_core._can_chat()` gained one
OR-branch for an active grant) but cannot vote, post, comment, or rate a business there — not
because new restriction code was written, but because `board_core.cast_vote()`/`create_post()`/
`add_comment()` and `karma_core.rate_business()` already gate purely on the user's own *real,
live* `present_location`, which a temporary grant never changes. The UI shows a gold "Temporary
Member" badge in the chat feed header (`chat_core.list_my_conversations()`'s new `membership`
field, `'active'` vs `'temporary'`) as a UX cue on top of that server-side gate, not a replacement
for it.

**Two bugs this pass found and fixed, not introduced by it:** (1) the `PENDING-` placeholder
`foreign_account_id` used while a request is pending only had second-resolution uniqueness
(`user_id` + timestamp), so the same user requesting two different locations within the same
wall-clock second collided on the column's own `UNIQUE` constraint — fixed by folding
`location_level`/`location_id` into the placeholder. (2) `chat_core.ensure_tables()` was only ever
called from `migrations/045_unified_chat_architecture.py`, which runs at most once per database —
a column added to that same function's body after a database had already applied that migration
would silently never reach it. Fixed by calling `ensure_tables(conn)` defensively at the top of
every public function that touches `temporary_location_access`, the same convention
`board_core.ensure_sub_tables()` and `local_area_core.ensure_tables()` already use throughout
`app.py`.

### Regression and release
Full suite re-run clean after all three commits: 44 test files, 0 failures, including 32 new
checks added to `tests/test_chat_core.py` across this arc (its sections 8–11) — the full
geography-parent traversal, the cascade council checker, the complete 3-strike escalation path
(reject → escalate ×2 → `denied_final` → blocked re-request, plus a separate request proving a
later strike can still approve), and Step 3's reason storage, Approver View, and
temporary-channel-visibility behavior. All three steps were also verified live against a seeded
local server via the Browser pane before being committed — the CSS flyout-collapse bug described
in §20.2 was found this way, not by code review alone. Not yet reflected in
`docs/MASTER_STATUS.md` (same standing note as §17–§19).

---

*This document supersedes all prior versions of `docs/HANDOVER.md`. For the concise, frequently
updated status tracker, see `docs/MASTER_STATUS.md`. For a partner- and public-facing overview of
the project, see `docs/QUMANITY_WHITEPAPER.md`.*
