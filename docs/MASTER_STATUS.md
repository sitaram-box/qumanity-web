# Qumanity Master Status Tracker

**Updated 2026-11-02**, from live inspection this session — `git log`, `git status`, real file
contents, and a fresh full test run. This is a concise, navigable status tracker, not a full
technical reference. For implementation detail, see **`docs/HANDOVER.md`**. For a high-level,
partner-facing overview of the project, see **`docs/QUMANITY_WHITEPAPER.md`**.

**Repository**: `qumanity-web`, branch `main`. Local `HEAD` = `origin/main` = **`6b8e5b5`**
("feat: add Q-Map Leaflet rendering with OSM pilot data"), confirmed identical by fetch this
session.

**Full regression, fresh this session: 1,380 checks across 30 test files, 0 failures.** Full
per-file table: `docs/HANDOVER.md` §11. (Supersedes the previously reported 1,378 — a recount of
`tests/test_qmap.py` found 33 checks, not 31.)

---

## Subsystem status

| Subsystem | Status | Notes |
|---|---|---|
| Q-Map (public map UI) | ✅ **Implemented & Committed**, `6b8e5b5` | See **Q-Map** section below |
| OSM Proximity (backend) | ✅ Implemented & Committed | `osm_proximity_core.py`, `osm_http_core.py`, `osm_proximity_worker.py`, migration 035. 200m radius, consent-gated, no raw coordinates ever returned |
| Provisional Locations | ✅ Implemented & Committed | `provisional_location_core.py`, migration 034. 24-qualifying-member auto-activation **within the provisional system only** — never an automatic write to canonical `Qumanity_Master.json` |
| OSM Pilot script (North West Delhi fetch) | ✅ Implemented & Committed | `scripts/fetch_north_west_delhi_osm.py`; its GeoJSON output is now also committed (via the Q-Map commit, for production deployment) |
| Multi-religion Marquee (infrastructure) | ✅ Implemented & Committed | 4-table architecture; Religion/Language Selector; rights-gating. See **Marquee** section below for content status |
| Family Tree (core model + cascade + grandparent backfill + Profile Card UI) | ✅ Implemented & Committed | Confirmed fully clean in `git status` this session — no longer split between committed backend / uncommitted frontend |
| Location edit tool + crosswalk schema | ✅ Implemented & Committed | `scripts/edit_master_location.py`, `docs/location_id_crosswalk_schema.md` (schema only, not populated) |
| India location deduplication (execution) | 🔵 Researched & Waiting — **not authorized** | 74 Tehsil + 15 Village duplicate groups nationally; only one pair (Bawana) resolved, in derived JSON only, not `Qumanity_Master.json`. `docs/india_dedup_migration_plan.md` is marked AWAITING APPROVAL — DO NOT EXECUTE |
| DPG Documentation / evidence pack | ✅ Implemented & Committed & Pushed; 🟡 **known drift, uncorrected** | See **DPG evidence** section below |
| Dashboard (multi-view, Stats Modal) | ✅ Implemented & Committed | Not touched this session |
| Wallet / Qoins | ✅ Implemented & Committed | `wallet_core.py`, `qoin_core.py` |
| Elections (zodiac council) | 🟡 Piloted, one village only | Rohini Sector 24; above-village councils don't exist yet |
| QMail | ✅ Implemented & Committed | Retention/delete-on-request still pending |
| Admin Panel | ✅ Implemented & Committed | Council-scoped queue |
| Referral Engine (registration attribution + bonus) | ✅ Implemented & Committed | A separate, unfinished board-level referrer-code system has no redemption path or tests — do not conflate the two; see `docs/dpg_evidence/13_referral_engine_evidence.md` |
| Copyright/religious-text notice pages | ✅ Implemented & Committed | `/copyright/gita-press`, `/copyright/religious-texts` |

---

## Q-Map

**✅ Implemented & Committed** — `6b8e5b5`, "feat: add Q-Map Leaflet rendering with OSM pilot data".

- Public `GET /qmap` page — **login is not required to view the base pilot map.**
- North West Delhi local OSM GeoJSON pilot dataset (25,365 features, ~22.3 MB), loaded from a
  committed local static file — **no live Overpass queries from the Q-Map page.**
- Independent Roads / Buildings / Hospitals layers via Leaflet's own layer control; Roads and
  Hospitals visible by default, Buildings togglable on.
- Visible, clickable OpenStreetMap/ODbL attribution.
- Responsive desktop and mobile layout (verified live at 375px).
- A signed-in member's own GPS location and OSM-proximity layer is available **only to that
  member's own authenticated session** — fetched via the existing, independently-authorized `GET
  /api/qmap/user-nearby/<user_id>` (403 for any other user's id, re-verified this session). No
  raw coordinate text is ever shown, even to the member themselves.

**The privacy distinction that matters**: **the base pilot map is public. A member's GPS location
and personal proximity information are private**, restricted to that one authenticated session.
Public map *visibility* must never be confused with public access to personal *location data* —
they are deliberately kept on opposite sides of the login wall.

Full detail: `docs/HANDOVER.md` §7.

---

## Marquee — content rights status

Infrastructure is complete and committed (4 tables, Religion Selector, Language Selector,
rights-gating). **Live content**: Hindu (original Qumanity poetry), Christian (English KJV Psalms +
Hindi Biblica, 8 selected verses), Muslim (Quran Al-Fatiha, Arabic), Buddhist (Dhammapada ch.1
vv.1-5, Pali + English). **Still pending rights review — code-complete, content blocked, not
available in the live Marquee**: Urdu Quran, Sikh Gurbani, Hindi Dhammapada, Jain texts. Gita
Press/Vinaya Patrika is separately `not_permitted`. Full research trail and next steps:
`docs/marquee_religious_text_sources.md`, `docs/marquee_rights_roadmap.md`. A religion is never
marked content-complete merely because the database infrastructure can support it.

---

## DPG evidence

The evidence pack (`docs/dpg_evidence/`) is internal evidence-preparation/self-assessment work —
every document in it marks itself "not a DPGA resubmission." **No document claims formal DPG
certification or registry acceptance.** Application-form-answers: 40 of 45 fields "Ready"
(verified fresh this session).

**Known, uncorrected drift** (found in an untracked research document,
`docs/audit_dpg_unfinished_features_2026_11.md`, not yet actioned): `dpg_evidence/ARCHITECTURE.md`
has fallen 16 lines behind the main `docs/ARCHITECTURE.md`; Family Tree and the Referral Engine are
absent from every `dpg_evidence/` document; two factual claims in the pack (an "automated election
testing cycle is planned, not built" claim, and an SMTP email-delivery claim) are now false against
the current code. **Not corrected by this pass** — re-syncing the pack is recommended as its own,
separately authorized task. Full detail: `docs/HANDOVER.md` §10.

---

## Website phase → phone app transition

The website feature-development phase is complete as of `6b8e5b5` plus this documentation
consolidation. The next phase is the phone application (`qumanity-app`), which must integrate with
the existing backend's `/api` routes and **must not** independently redefine location IDs,
consent rules, geography, or user identity. Full handover instructions: `docs/HANDOVER.md` §15.

---

## Standing constraints (do not re-decide these without explicit authorization)

- Geography IDs are stable, load-bearing identifiers — no renumbering/reparenting/deduplication
  without an approved migration and crosswalk.
- India location deduplication remains proposal-only; the Bawana correction was a narrow pilot, not
  a nationwide fix.
- `~/Desktop/0_Earth/` and its archive have established preservation constraints — no filesystem
  changes without being asked.
- Q-Punch reachability remains **village-only** (`QPUNCH_REACHABLE_LEVELS = {"village"}`,
  `qmail_core.py:45`) — council addresses above village exist as rows but cannot receive messages.
- User GPS data is sensitive and must remain protected; OSM attribution obligations are mandatory
  wherever OSM-derived data is shown.
- Qumanity Lok LLP is still in registration; copyright assignment, trademark filing, and domain
  transfer are gated on that completing.

---

## Revision log

- 2026-11-02: full rewrite as part of the final documentation consolidation for the current website
  phase — added the Q-Map entry and its public/private data distinction, re-verified every
  subsystem's git status fresh (Family Tree is now fully committed, not split; OSM Proximity and
  Provisional Locations are fully committed), re-baselined the regression count to 1,380/30 (fresh
  run, corrected from the previously reported 1,378), added the DPG evidence drift summary, and
  condensed the prior version's long phase-by-phase build log (preserved in git history) into this
  concise tracker. Cross-references to `docs/HANDOVER.md` and the new `docs/QUMANITY_WHITEPAPER.md`
  added throughout.
- Earlier history (Phases 1–6 of the prior consolidation task, the Marquee infrastructure build,
  the Biblica Hindi Bible import, the OSM proximity/Q-Map backend build, the grandparent backfill):
  preserved in full in this file's git history (commits up to and including `6b8e5b5`'s
  predecessors) and summarized in `docs/HANDOVER.md`.
