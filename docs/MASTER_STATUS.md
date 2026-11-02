# Qumanity Master Status Tracker

**Generated 2026-11-02, from live inspection this session** — `git log`, `git status`, real file
contents, and a fresh full test run (26 files, 1,065 checks, 0 failures, re-run just now; see
§Full Regression Baseline). Not from memory of prior sessions' own summaries. Where a prior
summary's claim was checked against the real repository and found inaccurate, that is called out
explicitly rather than quietly corrected.

**Repository**: `qumanity-web`, branch `main`. Local `HEAD` at the time this document was first
written: `93d7651` ("docs: refresh DPG evidence pack"). `origin/main`: `211480c` ("feat:
crowdsourced location MVP and OSM pilot script") — local is one commit ahead, not yet pushed.

This document is updated in place as later phases of the current task complete — see the
revision note at the bottom for what changed and when.

## Executive overview

- **Phase 2 complete**: the DPG commit (`93d7651`) and the new India-wide-audit commit (`1d91e63`,
  9 paths — 8 new files + 1 modified historical doc, reconciled against the real working tree
  before staging) are both pushed to `origin/main`, verified by re-fetching and confirming
  `origin/main` equals local `HEAD`.
- The single biggest **correction to a prior claim**, found by actually opening the files rather
  than trusting an earlier summary: the uncommitted changes to `templates/dashboard.html`,
  `static/css/dashboard.css`, `static/js/family.js`, and `static/js/family_tree.js` are **Family
  Tree Phase 2 Profile Card work** (a new `ft-profile-modal`, every person node becoming
  clickable) — **not** a "clickable stats stidebar" or "wallet transaction modal" as an earlier
  session's summary described. No stats-sidebar or transaction-modal code was found anywhere in
  this working tree. See the Dashboard and Family Tree entries below, and Phase 5 Part B's report
  for the full evidence trail.
- No launch blocker was found in any committed subsystem — the Wallet, Elections, QMail, and
  Admin Panel subsystems have no uncommitted changes at all right now and their own test suites
  pass cleanly.
- The real India-wide duplicate count is 74 Tehsil-level + 15 Village-level groups nationally (0
  State/District) — see the Location Data Integrity entry. None of this is a launch blocker on its
  own; it is scoped, measured, and awaiting a case-by-case survivor decision, not an emergency.
- **2026-11-02 (separate task, later the same day):** the Universal Multi-Religion Marquee
  infrastructure is implemented, tested (193 new Marquee checks, 1,277 suite-wide), and pushed —
  commit `a0bd6ca`. Five content areas (Urdu Quran, Sikh Gurbani, Hindi Bible, Hindi Dhammapada,
  Jain) remain `pending_rights_review`; see **"Marquee — Pending Rights (Content Only)"** below.
  This did not touch Family Tree, Dashboard, QMail, OSM/Q-Map, or any location data.

## Full regression baseline

**Final (Phase 6, after all implementation phases) -- re-baselined 2026-11-02, three times the same
day:** first after the Marquee infrastructure commit (`a0bd6ca`, `test_poems_marquee.py` 79 -> 193,
suite total 1,163 -> 1,277), then after the copyright-notice page and DPG documentation work added
`tests/test_copyright_pages.py` (34 checks, new, total -> 1,311 across 29 files), then again after
the Biblica Hindi Bible content import added 33 new checks to `test_poems_marquee.py` (193 -> 226),
moving the total to **1,347 across 29 files**. Every other suite's count is unchanged from the
Phase 6 baseline below -- re-run fresh this session, not copied from memory.

| Suite | Pass | Fail |
|---|---:|---:|
| test_account_id_sync.py | 13 | 0 |
| test_admin_panel_council_scope.py | 40 | 0 |
| test_avatar_sweep.py | 14 | 0 |
| test_copyright_pages.py (new, this pass) | 34 | 0 |
| test_council_updates.py | 17 | 0 |
| test_edit_master_location.py (new, Phase 3) | 33 | 0 |
| test_election_test_scheduler.py | 31 | 0 |
| test_email_core.py | 46 | 0 |
| test_family_tree.py | 211 | 0 |
| test_family_tree_cascade.py (+21 new, Phase 5) | 115 | 0 |
| test_fetch_north_west_delhi_osm.py | 47 | 0 |
| test_fix_haryana_districts.py | 30 | 0 |
| test_group_members.py | 22 | 0 |
| test_identity_correction.py | 41 | 0 |
| test_import_india_villages_verify.py | 5 | 0 |
| test_india_geography_classification.py | 22 | 0 |
| test_osm_proximity.py (new, Phase 4) | 44 | 0 |
| test_poems_marquee.py (226, up from 79 -- multi-religion marquee + Biblica Hindi Bible import, 2026-11-02) | 226 | 0 |
| test_post_kinds.py | 55 | 0 |
| test_provisional_locations.py | 76 | 0 |
| test_qmail.py | 32 | 0 |
| test_qmail_activation_diagnostics.py | 17 | 0 |
| test_qmail_attachments.py | 30 | 0 |
| test_qmail_drafts.py | 29 | 0 |
| test_qmail_format_extraction.py | 18 | 0 |
| test_qmail_page.py | 8 | 0 |
| test_qpunch.py | 25 | 0 |
| test_referral_engine.py | 12 | 0 |
| test_reply_read.py | 51 | 0 |
| **Total (29 files)** | **1,347** | **0** |

(Phase 1 baseline, before any implementation this task: 26 files, 1,065 checks, 0 failures.)

## Subsystem status

### 1. Marquee (Poems)
**✅ Implemented & Committed & Pushed** (commit `a0bd6ca`, "feat: multi-religion marquee with
rights-gated database architecture" — supersedes the earlier `82c5454` single-religion cut this
entry previously described). The Marquee is now a **Universal Multi-Religion, Multi-Language**
architecture, not a single hardcoded Hindu/Christian dict:

- **Database architecture** (`religious_text_core.py`, new): four tables —
  `religious_traditions` -> `text_collections` -> `text_collection_languages` -> `text_entries` —
  each collection individually gated by `rights_status`/`review_status`/`marquee_eligible`; only a
  `review_status='approved' AND marquee_eligible=1` row is ever resolvable
  (`resolve_collection()`). Seeded idempotently on every boot via `tools/run_migrations.py`
  (`religious_text_core.seed_builtin_collections()`, keyed by `slug`, re-running is a no-op).
  **Note on the earlier 4-workstream proposal** (`docs/audit_multi_religion_marquee_proposal_2026_11.md`
  §3.6): that proposal's schema also included a fifth table, `religion_collection_access`, for a
  future many-to-many religion<->collection relationship. It was deliberately **not** built —
  `text_collections.tradition_id` already gives every current collection a direct, sufficient
  mapping, and the many-to-many case (e.g. a shared "interfaith" collection) has no concrete use
  yet. Revisit only if a real need for many-to-many access actually arises.
- **Public default (unchanged from the prior entry):** Hindu/Hindi for every logged-out visitor
  and any member with no profile religion, via `app.py`'s `_marquee_religion_for_session()` ->
  `DEFAULT_MARQUEE_RELIGION = "hindu"`.
- **Independent Religion Selector + Language Selector** (`static/js/poems.js`,
  `templates/_poems_marquee.html`'s new "Reading tradition" accordion section): a signed-in
  member's reading religion defaults to their own profile religion when it has content, but can be
  switched to any other **approved, content-backed** tradition via an explicit, allowlist-checked
  `?religion=`/`&lang=` query parameter on the *same two existing routes*
  (`/api/poems/meta`, `/api/poems/<lang>/<index>` — no new route was added). This reading choice
  is stored client-side only (`localStorage`, scoped per signed-in member's own Private Code) and
  **never writes `users.religion_belief`** — verified directly against the database in
  `tests/test_poems_marquee.py` (§8) and live in-browser (a Muslim-profile test account was
  switched to Hindu reading content; `users.religion_belief` remained `'muslim'`).
- **Gold-box label is now fully server-driven** (`religious_traditions.default_label`), replacing
  the old hardcoded 5-entry `CHIP_BY_RELIGION` client table this entry previously flagged as a
  "known limitation" — a tradition with no `religious_traditions` row (jain/other/prefer_not_to_say)
  still correctly shows no chip at all, by design, no fallback.
- **Currently live content** (4 traditions, 5 language editions): Hindu (original Qumanity Hindi
  poetry, not Gita Press/Vinaya Patrika — see the Gita Press note below), Christian (Psalms KJV
  English + Psalms Biblica Open Hindi Contemporary Version, added 2026-11-02, owner-authorized),
  Muslim (Quran Surah Al-Fatiha, Arabic, Tanzil Project CC BY 3.0), Buddhist (Dhammapada ch. 1
  vv. 1-5, Pali + English/Max Müller). **4 content areas remain blocked pending rights review** —
  see **"Marquee — Pending Rights (Content Only)"** below; this is a content gap, not a code gap.
- Tests: `tests/test_poems_marquee.py`, **226 passing** (up from 79, then 193, then 226 after the
  Hindi Bible import's own tests, re-run fresh) — see the regression table below for the updated suite-wide
  total. No uncommitted Marquee changes remain.

### 2. Gita Press (copyright page)
**✅ Implemented & Committed** (commit `82c5454`). Route `/copyright/gita-press`,
`templates/copyright_gita_press.html`. This is a copyright/attribution notice page, **not** a
grant of publishing rights to any restricted content — distinguishing those two things explicitly,
per this tracker's own instructions. No uncommitted changes.

### 3. Family Tree
**🟡 Implemented & Uncommitted (partially)** — split status, see below.

- **Core Nuclear Family Node model, membership state machine, direct-roster cascade (Option A)**:
  ✅ Committed, commit `82c5454`. `family_core.py` (2,540 lines), `migrations/026_family_tree.py`,
  `migrations/027_family_nuclear_nodes.py`. Tests: `tests/test_family_tree.py` (211),
  `tests/test_family_tree_cascade.py` (94), both passing. Full evidence:
  `docs/dpg_evidence/12_family_tree_evidence.md` (committed `93d7651`, local only, not yet
  pushed).
- **Phase 2 Profile Card frontend** (every person clickable, new `ft-profile-modal` replacing the
  old `ft-edit-modal`, combined name/gender/age editor): 🟡 **uncommitted**. Files:
  `templates/dashboard.html`, `static/css/dashboard.css`, `static/js/family.js`,
  `static/js/family_tree.js` (confirmed by diff inspection this session — this is what an earlier
  session's summary mislabeled as "Dashboard clickable stats sidebar and transaction modal"; see
  the Dashboard entry below). Backend routes for this (`api_family_person_*`,
  `update_node_details`) are already committed in `82c5454`/earlier — only the frontend
  (templates/JS/CSS) is uncommitted.
- **Grandparent backfill (Option B)**: 🔵 **Researched & Waiting until this task's Phase 5** —
  deliberately deferred pending a privacy/consent review (see evidence doc). This task's Phase 5
  Part A implements it; see that section below for its own status once built.

### 4. Provisional Locations (Crowdsourced Location MVP)
**✅ Implemented & Committed**, commit `211480c`. `provisional_location_core.py`,
`migrations/034_provisional_locations.py`, MVP additions in `app.py`/`templates/register.html`/
`static/js/register.js`/`static/css/register.css`. Tests: `tests/test_provisional_locations.py`,
76 passing. No uncommitted changes to any of these files.

### 5. OSM Pilot (North West Delhi)
**✅ Implemented & Committed**, commit `211480c`. `scripts/fetch_north_west_delhi_osm.py`,
`tests/test_fetch_north_west_delhi_osm.py` (47 passing). Its own GeoJSON output,
`static/data/pilot/north_west_delhi_osm.geojson`, is intentionally **uncommitted** (🟡, by design
— the original task that built it explicitly excluded the data file from the commit). Standalone
research pilot; not wired into any route.

### 6. OSM Coordinate Linking / Q-Map
**🟡 Implemented & tested, uncommitted.** New: `osm_http_core.py` (shared Overpass HTTP layer,
extracted fresh rather than modifying the already-committed `scripts/fetch_north_west_delhi_osm.py`
— same proven backoff/User-Agent design, no risk to committed, tested code), `osm_proximity_core.py`
(schema, consent-gated job enqueueing, 200m worker, withdrawal, Q-Map data access),
`migrations/035_osm_proximity.py`, `osm_proximity_worker.py` (standalone CLI), two new routes
(`POST /api/location/observation/withdraw-overpass`, `GET /api/qmap/user-nearby/<user_id>`), and
`tests/test_osm_proximity.py` (44 checks, all passing, zero live Overpass calls).
**Consent correction made this phase**: `provisional_location_core.CONSENT_VERSION` was bumped
(`2026-11-mvp-v1` → `2026-11-osm-v2`) specifically so this feature never retroactively queries any
observation accepted under the old "when this service becomes available" wording — a fresh,
re-confirmed consent is required going forward; `templates/register.html`'s checkbox copy was
updated to match. **Known, flagged operational risk**: querying the public Overpass API per user
at production scale risks violating its fair-use policy; the worker is deliberately conservative
(small batches, real throttling, never a burst) but sustained growth should revisit this against
Overpass's own usage policy, possibly moving to a self-hosted mirror, before this becomes a
volume feature. **Scope note**: no "update present residence" feature exists anywhere in this
codebase to hook into — the existing `/api/location/observation` route was already generic and
`@login_required`, so it already serves as the "submit a fresh observation any time" mechanism;
building a new profile-settings UI for that is out of this phase's scope and not attempted.

### 7. DPG Documentation
**✅ Implemented & Committed & Pushed.** Commit `93d7651` — 5 files (`01_sdg_relevance.md`,
`08_standards.md`, `ARCHITECTURE.md`, `12_family_tree_evidence.md`,
`13_referral_engine_evidence.md`). Pushed to `origin/main` in this task's Phase 2, alongside
`1d91e63`. Verified: `origin/main` now equals local `HEAD` (`1d91e63`).

### 8. Dashboard
**✅ Fully resolved by direct evidence — both named features are ALREADY committed and pushed.**
The Dashboard's core (multi-view layout, location picker, scoped oversight) is committed in
`a2ec06d` and earlier. **The "clickable stats sidebar" and "wallet transaction modal" this task
assumed were "built but not committed" are, in fact, both already implemented AND already
committed** — in `fc93f7a` ("feat: UI fixes for Shivalinga, registration middle name, wallet
modal, and board labels", 2026-11-01), which is an ancestor of `211480c` and therefore already on
`origin/main`, pushed long before this consolidation task began. Confirmed by reading that
commit's actual diff: `static/js/dashboard.js`'s `openStatsModal()` now also calls the new
`loadWalletHistoryFor()` (the "transaction modal" — the stats modal, `#qm-stats-modal`, now shows
the wallet's weekly transaction history inline), and the always-on sidebar panels
(`qm-dg-stats`/`qm-dp-stats`) gained the `qm-stats-panel--clickable` class plus a delegated click
handler that opens that same modal (the "clickable stats sidebar"). **No new work was needed or
performed for this item.** Separately, the uncommitted `templates/dashboard.html`/
`static/css/dashboard.css`/`static/js/family.js`/`static/js/family_tree.js` changes found in this
session's working tree are a real but *different* piece of work — the Family Tree Phase 2 Profile
Card frontend (see Family Tree entry) — correctly reported there, not here. This correction
replaces an earlier session's inaccurate claim rather than building a feature that already
existed or silently going along with the mistaken premise.

### 9. Wallet
**✅ Implemented & Committed.** `wallet_core.py`, `qoin_core.py`. No uncommitted changes to either
file. Exercised indirectly by `tests/test_referral_engine.py` (12 passing, covers the per-referral
credit and bonus-tier logic) and other suites; no dedicated `test_wallet_core.py` was found as a
standalone file.

### 10. Elections
**✅ Implemented & Committed.** `election_core.py`, `election_test_scheduler.py`. No uncommitted
changes. Tests: `tests/test_election_test_scheduler.py`, 31 passing.

### 11. QMail
**✅ Implemented & Committed.** `qmail_core.py`, `email_core.py`. No uncommitted changes to either
file (both are on this project's protected-files list; confirmed untouched). Tests:
`tests/test_qmail.py` (32), `test_qmail_activation_diagnostics.py` (17),
`test_qmail_attachments.py` (30), `test_qmail_drafts.py` (29), `test_qmail_format_extraction.py`
(18), `test_qmail_page.py` (8), `test_email_core.py` (46), `test_reply_read.py` (51) — all
passing, 231 checks total across QMail's own suites.

### 12. Admin Panel
**✅ Implemented & Committed.** No uncommitted changes found. Tests:
`tests/test_admin_panel_council_scope.py`, 40 passing.

### 13. Referral Engine
**✅ Implemented & Committed** (registration attribution + bonus) — commit history includes
`1ea9aa2` ("feat: add referral engine with public ID autofill and bonus tiers") and
`33017cf` (UTC week-boundary fix). **🔴 The separate council-approved Referrer-code system
(`board_core.py`) is implemented at the backend/authorization level but has no redemption path,
no frontend, and no tests anywhere in the repository** — this was established and documented in
`docs/dpg_evidence/13_referral_engine_evidence.md` (committed `93d7651`). Do not conflate the two
systems; see that evidence doc for the full, careful distinction. Tests:
`tests/test_referral_engine.py`, 12 passing (covers only the first system).

### 14. India Location Data / Canonical Geography
**✅ Decision adopted; safe-edit tool built and tested (🟡 uncommitted).**
`Qumanity_Master.json` stays canonical (decision committed and pushed, `1d91e63`).
**Authoring workflow — corrected this phase**: the original claim in
`docs/location_architecture_decision.md` ("no script in this repository writes to it... unknown")
was checked against real evidence and found wrong. It IS authored by in-repository, one-off
scripts (`scripts/add_navi_mumbai_locations.py`, `scripts/add_ganesh_pura_tri_nagar.py`, etc.),
each with its own backup-then-write convention — not an external tool. The architecture decision
doc has been corrected in place (uncommitted change to an already-pushed file; left unstaged per
this task's authorization boundary). New: `scripts/edit_master_location.py` (add/rename/remove one
record, hex-suffix ID validation, duplicate-prevention reusing the audit's own `normalize_name`,
a full 16-table reference audit before any removal, backup+SHA-256+atomic-write+concurrent-edit
detection) and `tests/test_edit_master_location.py` (32 checks, all passing, against a fixture
Master JSON and a disposable SQLite DB — the real files were never touched by the tests).
`docs/location_id_crosswalk_schema.md` (new) proposes the `location_id_history` table — schema
only, not built, not populated with any real survivor mapping.

### 15. Location Data Integrity and Deduplication
**✅ Audit tooling & reports Implemented, Committed & Pushed** (commit `1d91e63`) — **🔵 the
duplicates themselves remain Researched & Waiting, not executed.** `scripts/
audit_all_india_duplicates.py`: **74 Tehsil-level + 15 Village-level duplicate groups nationally,
0 at State/District level**, across all 37 States/UTs. 61 of the 74 Tehsil groups are within
Delhi's 7 districts; 13 elsewhere (Andaman & Nicobar, Assam, Karnataka, Tamil Nadu, Mizoram,
Odisha). One pair (Bawana, `CS.DL.3.4`/`CS.DL.3.E`) already resolved in the two derived JSON
files only (commit `211480c`); `Qumanity_Master.json` itself still has both. The other 73 Tehsil
groups and all 15 Village groups are unresolved — `docs/india_dedup_migration_plan.md` is
explicitly marked AWAITING APPROVAL — DO NOT EXECUTE, and a concrete open case (Tri Nagar,
`CS.DL.7.4`/`CS.DL.7.14`) has real user references on **both** sides, so this is not a case where
every remaining group can simply be resolved the same way Bawana was. **No further deduplication
is authorized or performed by this task.**

### 16. Location Editing and ID Crosswalk
**🟡 Implemented & tested, uncommitted** (see entry 14 above for full detail) — the edit tool, its
tests, and the crosswalk schema proposal. **0_Earth backup archiving — DONE** (not a commit;
this was a direct filesystem action the owner explicitly pre-approved): the four timestamped
`Qumanity_Master.before_*_fix_*.json` backups were copied to a new sibling directory,
`~/Desktop/0_Earth_Archive/`, each verified byte-for-byte via SHA-256 before the original was
removed (all four matched, all four originals removed). `.DS_Store` at `~/Desktop/0_Earth/.DS_Store`
was removed (the only file deleted outright, per the exact approval). `O.json`, `Qumanity_Master.json`,
and `Continents/` are confirmed untouched (same file sizes/mtimes as before this action). Exact
hashes: see Phase 3's own report in the final completion report below.

---

## Marquee — Pending Rights (Content Only)

The Marquee's **infrastructure is complete and committed** (`a0bd6ca`, see entry 1 above): the
database architecture, Religion Selector, Language Selector, and rights-gating mechanism all work
and are fully capable of serving any tradition the moment its content clears rights review. **Four
content areas remain blocked** — this is content-only follow-up work, not an infrastructure gap.
None of the four is currently offered by the Religion/Language Selector or servable through the
existing API, by any query-parameter combination; `religious_text_core.resolve_collection()`
returns `None` for every one of them, which `api_poems_meta()` reports as `coming_soon`, never
substituted or invented content. Full research trail: `docs/marquee_religious_text_sources.md`.

> **Updated 2026-11-02 (deeper research pass, same day), then updated again the same day after
> owner authorization.** Every item below was re-investigated in more depth (named translators,
> direct contact routes, license-file checks rather than README prose) — see the research doc for
> full quotes and sources. **One item that was on this list, the Hindi Bible, has since moved OFF
> it entirely**: the owner reviewed and explicitly authorized the Biblica Open Hindi Contemporary
> Version candidate, which was imported and is now live (commit below) — see "Christian Hindi,
> now live" immediately after this list, not among the four still-pending items.

### 1. Urdu Quran

**Status:** `pending_rights_review — code complete, content blocked`

Findings this pass: Fateh Muhammad Jalandhry's translation is **confirmed still under copyright**
(Pakistan's Copyright Ordinance 1962, 50 years from the year after the author's 1982 death ->
protected through 1 Jan 2033); Abul A'la Maududi's *Tafheem-ul-Quran* publisher (Idara
Tarjuman-ul-Quran, Lahore) has no locatable website or contact route; Tanzil Project's own
redistribution clause remains unresolved and no contact route for Tanzil could be found this pass
either.

Next step:
- Contact the Tanzil Project for written clarification about the exact Urdu translation/edition
  and whether its text may be redistributed in Qumanity's JSON collection and displayed on a
  public website — no working contact route was found this pass; locating one (e.g. the live
  site's own footer) is itself the first step.
- A draft outreach message is prepared in `docs/marquee_religious_text_sources.md` §3b, for owner
  review before sending.
- Do not add Urdu Quran text until redistribution and display permission are clear.

### 2. Sikh Gurbani

**Status:** `pending_rights_review — code complete, content blocked`

Findings this pass: Khalis Foundation/BaniDB's GitHub repo has a real MIT LICENSE file, but it
covers the API code only — the README still explicitly withholds the Gurbani text dataset itself.
A new lead, `github.com/shabados/database`, self-asserts the Gurmukhi original is public domain
(not court-tested, and does not cover any English translation). SriGranth's "all rights reserved"
footer is unchanged. **A real contact route for Khalis Foundation was found**: a physical address,
phone/WhatsApp number, and contact form on `khalisfoundation.org`.

Next step:
- Send a permission request to Khalis Foundation via their contact form (draft prepared in
  `docs/marquee_religious_text_sources.md` §4a, for owner review before sending) and separately
  the relevant rights holders or publishers of any proposed Gurbani translation.
- Request explicit written permission for digital redistribution, public display, and any
  required modifications or segmentation.
- SriGranth's reported all-rights-reserved terms and BaniDB/Khalis Foundation's reported
  restrictions must not be bypassed.
- Do not publish Gurbani text or translations without a verified source and permission.

### Christian Hindi (Biblica) — moved from pending to Live, 2026-11-02

**Status:** `approved_with_conditions — imported and live` (commit `fbc0a5e`, full hash
`fbc0a5ed2ab0c55c183786be6e464f7f14eaec1f`, "feat: add Biblica Hindi Bible to Christian marquee
collection" — verified present on `origin/main` and containing the Hindi Bible collection files
before this reference was written). The owner reviewed and explicitly authorized importing the
Biblica Open Hindi
Contemporary Version candidate identified in the deeper research pass above. Eight Psalm verses
(the same references already used by the existing English KJV collection) were fetched live,
verse-by-verse, directly from `ebible.org/hincv/` and added as a second language (`hi`) on the
existing `christian_psalms_kjv` collection row — not a new collection, following the same
"one collection, multiple language editions" pattern already used for Buddhist's Pali+English
Dhammapada. English KJV remains the Christian default language, completely unaffected; Hindi is a
reader-selected addition only. Treated as a derivative work under CC BY-SA 4.0 (eight verses
selected and reformatted, not an unmodified full copy): the Biblica® trademark is never used in
Qumanity's own UI/docs for this collection, and the license's own derivative-work attribution
wording is used instead — *"The original work by Biblica, Inc. is available for free at
www.biblica.com and open.bible."* Files: `Poems/christian/hindi_biblica/poems_hindi.json` (8
verses), `Poems/christian/hindi_biblica/README.md`. See `docs/marquee_religious_text_sources.md`
§2b for the full re-verified license trail and `/copyright/religious-texts` for the public notice.
The 1914 BFBS Hindi Bible edition (Candidates 1-3 in the research doc) remains separately
unavailable — its rights are clean but no clean transcription exists; it is not part of this
import and would be a distinct, independent addition if ever pursued.

### 3. Hindi Dhammapada

**Status:** `pending_rights_review — code complete, content blocked`

Findings this pass: Rahul Sankrityayan's 1933 Hindi Dhammapada translation was located and its
publication facts confirmed directly (Mahabodhi Sabha, Sarnath, 1933) — a work of his would
plausibly be public domain in India from 1 January 2024 (life+60, d. 1963), but (a) archive.org
hosts two scans of the same book with conflicting license tags (CC0 vs. CC BY-NC-ND), neither
authoritative, and (b) the US/URAA restoration question is unresolved, which matters because
Qumanity is a US-reachable website. No clean verbatim text could be extracted from the OCR either.

Next step:
- Obtain a one-time legal/rights confirmation covering both the India life+60 and US/URAA
  questions for the Sankrityayan 1933 edition specifically.
- Separately, produce a clean transcription or a better OCR pass against the original page images.
- Do not generate or present an unverified machine translation as an established Hindi
  Dhammapada translation.

### 4. Jain texts

**Status:** `pending_rights_review — code complete, content blocked`

Findings this pass (first research cycle for this tradition): the Tattvartha Sutra is confirmed
cross-sect-accepted (Digambara, Svetambara, and minor sub-traditions), but its common English
translation (Nathmal Tatia/Institute of Jainology) is fully copyrighted, and the one
plausibly-public-domain English translation found (J.L. Jaini, 1920) is only accessible through a
rights-restricted `jainqq.org` wrapper. The Namokar Mantra (the tradition's universal prayer, with
real sect-specific wording variants) has a public-domain-by-age Prakrit original and a usable CC
BY-SA 4.0 Wikipedia translation as a fallback — the most promising lead of the two researched, not
yet fully clear.

Next step:
- Resolve JAINpedia's CC-BY-NC-SA-vs-"all rights reserved" footer discrepancy with the Institute
  of Jainology, or locate a clean HathiTrust/archive.org scan of J.L. Jaini's 1920 Tattvartha Sutra
  translation that bypasses `jainqq.org`'s restrictive wrapper.
- Establish the appropriate original language, edition, and reliable digital source for whichever
  candidate is pursued.
- Obtain permission where necessary before creating public collection files.
- Do not assume that one text or translation represents all Jain traditions.

### Gita Press / Vinaya Patrika (separate rights note, not one of the five items above)

- No verified publication permission has been established for the Gita Press Hindi Vinaya
  Patrika translation (re-confirmed this task — see `docs/marquee_religious_text_sources.md`
  §1b).
- The original Qumanity Hindu Hindi poetry collection (`Poems/hindu_original/`) remains the
  public default.
- The original poems must not be attributed to Gita Press or labeled Vinaya Patrika.
- Any future Gita Press content addition requires its own verified rights clearance and a
  separate, content-only commit.
- **Status:** `not_permitted` (distinct from the five `pending_rights_review` items above — this
  one was already investigated once, in an earlier phase, and found blocked; it is not a new gap).

### Code-complete vs. content-complete

| Area | Status |
|---|---|
| Multi-religion Marquee architecture | Implemented and committed |
| Religion Selector | Implemented and committed |
| Language Selector | Implemented and committed |
| Rights-gating mechanism | Implemented and committed |
| Quran Arabic collection | Available with documented conditions |
| Dhammapada Pali collection | Available with documented conditions |
| Dhammapada English collection | Available |
| Christian Hindi (Biblica) | **Available with documented conditions — imported 2026-11-02, owner-authorized** |
| Urdu Quran | Pending rights review — code complete, content blocked |
| Sikh Gurbani | Pending rights review — code complete, content blocked |
| Hindi Bible (1914 BFBS edition) | Pending rights review — rights clean, no usable clean text; distinct from the now-live Biblica edition above |
| Hindi Dhammapada | Pending rights review — code complete, content blocked |
| Jain collection | Pending rights review — code complete, content blocked |
| Gita Press Vinaya Patrika | Unavailable pending permission (not_permitted, pre-existing finding) |
| `/copyright/religious-texts` notice page | Implemented and committed — see entry below |

A religion is never marked content-complete merely because the infrastructure can support it.

### Public copyright notice page

**✅ Implemented & Committed** — `/copyright/religious-texts` (`app.py`'s
`copyright_religious_texts()`, `templates/copyright_religious_texts.html`), alongside the
pre-existing `/copyright/gita-press`. Covers all six current rights questions (Hindu/Gita Press,
Muslim/Urdu Quran, Christian/Hindi Bible, Sikh/Gurbani, Buddhist/Hindi Dhammapada, Jain), clearly
distinguishes the four currently-available collections from the pending ones, never claims
ownership of any scripture, and includes Qumanity's own verified public contact
(`founder@qumanity.in`, already used elsewhere on the live About page and in the existing Gita
Press outreach letter — not invented for this page) plus verified third-party contact links
(Tanzil Project, Khalis Foundation, Biblica) where found. Linked from the homepage footer, public
for both logged-in and logged-out visitors, responsive (no horizontal overflow at 375px, verified
live). Tests: `tests/test_copyright_pages.py` (new), covering both copyright pages — see the
regression table below.

### DPG evidence audit (this pass)

Three documents re-verified against the current repository rather than trusted from a prior
session's own summary:

- `docs/dpg_evidence/12_family_tree_evidence.md` — most `family_core.py` line citations from
  `_sync_family_membership()` onward had drifted +93 lines (the Option B grandparent-backfill code
  was inserted after this document was first written) — corrected. **Material correction:** the
  document's own claim that Option B remained "uncommitted, pending separate approval to commit"
  was stale — it is actually already committed, `0a8ab5b`, the same day it was implemented. No
  behavioral claim changed, only line numbers and the commit-status claim.
- `docs/dpg_evidence/13_referral_engine_evidence.md` — the test count was stated as 14 in two
  places; `tests/test_referral_engine.py` actually has 12 checks (re-run fresh). Most `app.py` line
  citations in its §1 had drifted ~42 lines; corrected. The underlying findings (no redemption path
  for the council Referrer code, zero test coverage for that system) were re-confirmed unchanged by
  direct repository search, not just re-stated.
- `docs/dpg_evidence/14_marquee_evidence.md` (new) — documents the Marquee's actual 4-table schema
  (explicitly correcting an earlier proposal document's 5-table design, which was never built),
  the religion-resolution chain, rights gating, and test coverage.
- `docs/dpg_evidence/ARCHITECTURE.md` and `docs/ARCHITECTURE.md` (main) — both gained a
  `religious_text_core.py` module-map row and a 4-table Marquee data-model row, with the same
  "not yet counted in the grand total" caveat the pre-existing `family_core.py`/
  `referral_bonus_awards` gaps already carried.

No application code, tests, migrations, or user data were changed as part of this audit — only
documentation.

---

## Complete working-tree inventory (at the start of this task)

| Path | Git status | Pre-existing or new this task | Subsystem | Planned action |
|---|---|---|---|---|
| `.gitignore` | M | Pre-existing | Unrelated | Leave untouched |
| `db.py` | M | Pre-existing (WAL-mode concurrency fix, dated 2026-10-28 in its own comment) | Unrelated | Leave untouched |
| `docs/location_dedup_report.md` | M | Pre-existing this task's Phase 2 predecessor (dated addendum already applied) | Location Data Integrity | Commit in Phase 2 |
| `folder_export/Earth/*.json` (6 files) | M | Pre-existing | `folder_sync.py`'s own daily mirror | Leave untouched |
| `static/css/dashboard.css` | M | Pre-existing | Family Tree Phase 2 (see correction above) | Leave uncommitted this task |
| `static/js/family.js` | M | Pre-existing | Family Tree Phase 2 | Leave uncommitted this task |
| `static/js/family_tree.js` | M | Pre-existing | Family Tree Phase 2 | Leave uncommitted this task |
| `templates/dashboard.html` | M | Pre-existing | Family Tree Phase 2 | Leave uncommitted this task |
| `tests/test_post_kinds.py` | M | Pre-existing | Unrelated (post-kind badge work) | Leave untouched |
| `Poems/` | ?? | Pre-existing | Marquee-adjacent rights-cleared content staging | Leave untouched |
| `docs/0_earth_cleanup_proposal.md` | ?? | Pre-existing (this task's Phase 2 predecessor) | Location Data Integrity | Commit in Phase 2 |
| `docs/0_earth_inventory_raw.json` | ?? | Pre-existing (same) | Location Data Integrity | Commit in Phase 2 |
| `docs/audit_dpg_unfinished_features_2026_11.md` | ?? | Pre-existing | Unclear — not inspected this task, out of scope | Leave untouched |
| `docs/audit_family_tree_cascade_proposal_2026_11.md` | ?? | Pre-existing | Family Tree research | Leave untouched |
| `docs/audit_india_location_data_2026_11.md` | ?? | Pre-existing | Location Data Integrity research | Leave untouched |
| `docs/audit_multi_religion_marquee_proposal_2026_11.md` | ?? | Pre-existing | Marquee research | Leave untouched |
| `docs/family_tree/` (3 files) | ?? | Pre-existing | Family Tree Phase 1/2 planning docs | Leave untouched |
| `docs/identity_cards/` (23 files) | ?? | Pre-existing | A separate, not-in-scope "Identity Cards" research effort | Leave untouched |
| `docs/india_dedup_migration_plan.md` | ?? | Pre-existing (Phase 2 predecessor) | Location Data Integrity | Commit in Phase 2 |
| `docs/india_duplicate_audit_2026-11-01.csv` | ?? | Pre-existing (same) | Location Data Integrity | Commit in Phase 2 |
| `docs/india_location_integrity_report.md` | ?? | Pre-existing (same) | Location Data Integrity | Commit in Phase 2 |
| `docs/location_architecture_decision.md` | ?? | Pre-existing (same) | Location Data Integrity | Commit in Phase 2 |
| `folder_export/Earth/AS/`, `CS_DL_3*/`, `CS_DL_5_4*/` | ?? | Pre-existing | `folder_sync.py` export tree | Leave untouched |
| `scripts/add_ganesh_pura_tri_nagar.py` | ?? | Pre-existing | Location data fix (unrelated to this task) | Leave untouched |
| `scripts/add_navi_mumbai_locations.py` | ?? | Pre-existing | Location data fix (unrelated) | Leave untouched |
| `scripts/audit_0_earth_usage.py` | ?? | Pre-existing (Phase 2 predecessor) | Location Data Integrity | Commit in Phase 2 |
| `scripts/audit_all_india_duplicates.py` | ?? | Pre-existing (same) | Location Data Integrity | Commit in Phase 2 |
| `scripts/audit_india_master_locations.py` | ?? | Pre-existing | Location data research (unrelated) | Leave untouched |
| `scripts/dedupe_bawana_tehsil.py` | ?? | Pre-existing | Location Data Integrity — the Bawana fix tool itself | Leave uncommitted (tool, not a named deliverable) |
| `scripts/make_gita_press_letter.py` | ?? | Pre-existing | Gita Press (unrelated correspondence draft) | Leave untouched |
| `scripts/migrate_haryana_location_ids.py` | ?? | Pre-existing | Location data fix (unrelated) | Leave untouched |
| `scripts/regenerate_location_data.py` | ?? | Pre-existing | Location data generator (unrelated to this task's edits) | Leave untouched |
| `static/data/*.before_regen_*.json` (4 files) | ?? | Pre-existing | Location data backups | Leave untouched |
| `static/data/pilot/` | ?? | Pre-existing | OSM Pilot output (deliberately uncommitted) | Leave untouched |

**Files this task's own Phase 1/2 will add**: `docs/MASTER_STATUS.md` (this file — stays
uncommitted per the global rules, folded into no commit unless separately authorized).

---

## Phase 3-5 files (new or modified this task, all uncommitted)

| Path | Status | Phase |
|---|---|---|
| `scripts/edit_master_location.py` | new | 3 |
| `tests/test_edit_master_location.py` | new (33 checks) | 3 |
| `docs/location_id_crosswalk_schema.md` | new | 3 |
| `docs/location_architecture_decision.md` | modified (authoring-workflow correction) | 3 |
| `osm_http_core.py` | new | 4 |
| `osm_proximity_core.py` | new | 4 |
| `osm_proximity_worker.py` | new | 4 |
| `migrations/035_osm_proximity.py` | new | 4 |
| `tests/test_osm_proximity.py` | new (44 checks) | 4 |
| `app.py` | modified (import, enqueue call, 2 new routes, scheduler init) | 4 |
| `provisional_location_core.py` | modified (CONSENT_VERSION bump + comment) | 4 |
| `templates/register.html` | modified (overpass checkbox copy) | 4 |
| `family_core.py` | modified (grandparent backfill) | 5 |
| `tests/test_family_tree_cascade.py` | modified (+21 checks) | 5 |
| `docs/dpg_evidence/12_family_tree_evidence.md` | modified (Option B status update) | 5 |
| `docs/MASTER_STATUS.md` | new (this file) | 1, updated throughout |

**All of the above remain unstaged and uncommitted**, confirmed via `git diff --cached --stat`
returning empty at the end of Phase 6. Every pre-existing unrelated file (Navi Mumbai/Tri
Nagar/Haryana scripts, `folder_export/Earth/`, `Poems/`, `docs/family_tree/`,
`docs/identity_cards/`, the four `.before_regen_*.json` backups, `scripts/dedupe_bawana_tehsil.py`,
`static/data/pilot/`) remains exactly as it was at the start of this task.

## Phase 6 verification summary

- Full regression: 28 files, 1,163 checks, 0 failures (see table above).
- `origin/main` re-fetched and confirmed equal to local `HEAD` (`1d91e63`) — only the two
  authorized Phase 1/2 commits exist on `main`; no Phase 3/4/5 commit was made.
- `git diff --cached --stat` is empty — nothing staged.
- `static/data/subcontinent_districts.json`, `static/data/india_districts_tehsils.json`, and
  `~/Desktop/0_Earth/Qumanity_Master.json` all have the identical SHA-256 hashes they had at the
  start of this task — no deduplication, renumbering, or survivor merge occurred anywhere.
- `~/Desktop/0_Earth_Archive/` holds the four approved backup files, each byte-verified against
  its original SHA-256 before the original was removed; `~/Desktop/0_Earth/.DS_Store` was removed
  (the only deletion); `O.json`, `Qumanity_Master.json`, and `Continents/` are confirmed untouched
  (unchanged size/mtime).
- No production database was written outside a `mode=ro` connection at any point in this task;
  every migration/schema change was exercised only against disposable tempfile databases inside
  the test suite.

## Revision log

- 2026-11-02: initial version, written at the start of this task's Phase 1, before any commit,
  push, or implementation in this task.
- 2026-11-02: updated after Phase 2 (push confirmed), Phase 3 (safe-edit tool, crosswalk schema,
  authoring-workflow correction, 0_Earth archiving), Phase 4 (OSM coordinate linking), Phase 5
  (grandparent backfill, Dashboard investigation), and Phase 6 (full regression, final
  verification).
- 2026-11-02 (separate, later task): updated after the Universal Multi-Religion Marquee
  infrastructure commit (`a0bd6ca`, pushed and verified against `origin/main`) -- rewrote the
  Marquee subsystem entry, added the "Marquee — Pending Rights (Content Only)" section (5 blocked
  content areas plus the pre-existing Gita Press finding), and re-baselined the full regression
  table (`test_poems_marquee.py` 79 -> 193, suite total 1,163 -> 1,277, re-run fresh this session).
  No other subsystem entry in this document was touched.
- 2026-11-02 (separate, later-still task): deeper rights research for all five pending Marquee
  content areas (named translators, direct contact routes, license-file checks) -- updated each
  item's findings and next steps, flagged the Biblica Hindi Bible candidate as now having both
  verified terms and verified text (still not imported, pending owner review). Added the new
  `/copyright/religious-texts` public notice page entry and `tests/test_copyright_pages.py` (34
  checks, new) to the regression table. Added a DPG evidence audit entry covering corrections to
  `docs/dpg_evidence/12_family_tree_evidence.md` (stale line numbers, a stale "uncommitted" claim
  for Option B that was actually already committed) and `13_referral_engine_evidence.md` (a stale
  test count, stale line numbers), plus the new `docs/dpg_evidence/14_marquee_evidence.md` and
  matching `ARCHITECTURE.md` updates in both locations. Suite total re-baselined again to 1,311
  across 29 files, re-run fresh this session. No application code, tests outside the two new test
  files, migrations, or user data were changed.
- 2026-11-02 (separate, later-still task, owner-authorized content import): the Biblica Open Hindi
  Contemporary Version (8 Psalm verses, CC BY-SA 4.0) was imported as a second language on the
  existing `christian_psalms_kjv` collection -- the Marquee's first content collection to move
  from `pending_rights_review` to actually live. `religious_text_core.py`'s `_seed_collection()`
  helper was extended to idempotently add a new language to an already-seeded collection (verified
  against a simulated pre-existing database, not just a fresh one). Updated the Marquee entry, the
  Pending Rights section (now 4 items, not 5 -- Hindi Bible moved to its own "now live" note), the
  code-complete/content-complete table, and the regression baseline (`test_poems_marquee.py` 193 ->
  226, suite total 1,311 -> 1,347, re-run fresh). The other four blocked collections and Gita Press
  were re-confirmed unaffected and still blocked.
