# Qumanity Master Status Tracker

**Updated 2026-11-09**, from live inspection this session — `git log`, a live `git ls-remote`,
`git status`, real file contents, and a fresh full test run. This is a concise, navigable status
tracker, not a full technical reference. For implementation detail, see **`docs/HANDOVER.md`**
(§9.3, §14, §15 for the Global Account/C1 release and the phone-app handover). For a high-level,
partner-facing overview of the project, see **`docs/QUMANITY_WHITEPAPER.md`**.

**Repository**: `qumanity-web`, branch `main`. Local `HEAD` = `origin/main` =
**`a157d7af01e1e5791de6e2449cde2945652c8659`** ("Add Global Account registration and dashboard
UI"), confirmed by a live `git ls-remote origin refs/heads/main` this session — the website
feature-development phase (Global Account, Q-Punch/election hardening, and the C1 security
correction below) is now **committed and pushed**; only pre-existing, unrelated work remains
uncommitted (9 modified + 25 untracked files — see `docs/HANDOVER.md` §14 for the exact list).

**Full regression, fresh this session: 1,370 checks across 33 test files, 0 failures.** The
mobile app's cross-repo checker: 156 passed, 1 pre-existing, unrelated failure (`"board shows the
post, score and vote state"`, tracked separately, not fixed). Production: the live site's
`/register` page and `register.js` were confirmed, by direct read-only inspection, to be serving
this release's code; Railway's own deployment metadata was not independently verified (CLI
authentication was expired) — that remains an owner action.

---

## Subsystem status

| Subsystem | Status | Notes |
|---|---|---|
| Q-Map (public map UI) | ✅ **Implemented & Committed**, `6b8e5b5` | See **Q-Map** section below |
| OSM Proximity (backend) | ✅ Implemented & Committed | `osm_proximity_core.py`, `osm_http_core.py`, `osm_proximity_worker.py`, migration 035. 200m radius, consent-gated, no raw coordinates ever returned |
| Provisional Locations | ✅ Implemented & Committed | `provisional_location_core.py`, migration 034. 24-qualifying-member auto-activation **within the provisional system only** — never an automatic write to canonical `Qumanity_Master.json` |
| OSM Pilot script (North West Delhi fetch) | ✅ Implemented & Committed | `scripts/fetch_north_west_delhi_osm.py`; its GeoJSON output is now also committed (via the Q-Map commit, for production deployment) |
| Multi-religion Marquee | 🔴 **Discontinued 2026-11-08** (owner legal decision) | Entirely removed — see **Marquee** section below |
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
| Global Account (registration outside the 10 Public Account countries) | ✅ **Implemented, tested, Committed & Pushed** (`a7d43a7`/`a157d7a`) | See **Global Account** section below |

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

## Marquee — discontinued

**Removed entirely, 2026-11-08, owner legal decision.** Gita Press denied permission for the Hindi
Vinaya Patrika translation; the owner chose to discontinue the whole Marquee rather than remove
only that one collection — this supersedes every earlier entry in this document describing the
Marquee as live or partially live. No religious text and no religion-based public identity symbol
is displayed anywhere on the site today.

Deleted: `templates/_poems_marquee.html`, `static/js/poems.js`, `static/css/poems.css`, the
`Poems/` directory's content, four backend routes, the `QM_MARQUEE_ENABLED` flag, and
`tests/test_poems_marquee.py`. Preserved: `users.religion_belief` and the Private Account religion
selector (private, never public); `religious_text_core.py` and its four tables (dormant, not
dropped); both public rights-notice pages (`/copyright/gita-press`,
`/copyright/religious-texts`), updated in place to describe the Marquee in the past tense without
erasing the underlying rights research; `docs/marquee_religious_text_sources.md` and
`docs/marquee_rights_roadmap.md` as the historical audit trail. Full detail:
`docs/HANDOVER.md` §9.1.

---

## Global Account

**✅ Implemented, security-hardened, tested, committed and pushed to `origin/main` — 2026-11-09**
— a user whose Present
Location's country is outside the 10 Public Account Activation countries
(`SUBCONTINENT_COUNTRY_IDS`, now in its own `account_core.py` module: India, Nepal, Bhutan,
Bangladesh, Myanmar, Sri Lanka, Pakistan, Balochistan, Afghanistan, Maldives — Mauritius and every
other country, e.g. Japan/Kenya, are Global) registers with a location that stops at Continent +
Country, gets the Global/Personal/Private Dashboard tabs (no Public tab), is denied the local
Public timeline and Q-Punch's Village Council election — and **can** vote on posts that reached
Country/Continent/Earth level, scoped to whoever shares that same geography (Earth level is the
only universal tier). Full detail: `docs/HANDOVER.md` §9.3.

**Hardening pass (2026-11-08)**: a real security gap was found and closed — the self-service
profile-change-request pathway accepted a `present_location` edit with no validation at all, the
realistic route by which an internally inconsistent location (Global country + a Subcontinent
village id) could reach a real row and satisfy the old, ungated village-residency check.
`election_core._present_village_id()` now independently re-checks `account_access_type()`; the
profile-change-request pathway is now validated at both submission and approval, and a
Global↔Public account-boundary crossing is refused in either direction (no transition workflow
exists in this product yet — building one was out of scope here). Also fixed: a 4px mobile
Dashboard header overflow (`static/css/dashboard.css`), unrelated to Global Accounts but found
during this feature's browser verification.

**Independent adversarial review (same date)**: confirmed the hardening above, then found and
closed one further real gap — the profile-change-request validator checked state-belongs-to-
country but not the rest of the ancestry chain, so a Public Account could submit a real but
mismatched Village id (e.g. claiming a village from a different Tehsil/District) and still pass.
Closed using existing data only (`subcontinent_states.json`/`subcontinent_districts.json` for
Zone/District/Tehsil, `india_villages.tehsil_id` for Village — no new hierarchy, no migration).
Also verified the admin-only `auto_nominate()`/`auto_vote()` simulation endpoints cannot bypass
the same eligibility gate (they re-check it internally even though their own candidate/voter pool
query doesn't). One pre-existing, unrelated finding noted but not touched per instruction:
`perception_core.py` carries its own independent copy of the 10-country list (currently in sync,
but with no shared source with `account_core.py`).

**Phase 1 (2026-11-08)**: an owner-approval audit found one further confirmed bypass — the
Tehsil-belongs-to-District check only ran when a District was *also* submitted, so omitting
District entirely skipped it. Fixed: District is now mandatory whenever a real Tehsil is
submitted, enforced identically at **both** registration and the profile-change path (registration
had never validated ancestry beyond state-belongs-to-country before this). The Village-level
`india_villages` check also tightened from soft-fail-on-not-found to hard-reject — "unverifiable"
is no longer treated as "confirmed valid." A separate robustness fix closes an unhandled-crash
path for malformed (wrong-type) location fields. See `docs/HANDOVER.md` §9.3 for full detail.

**Also fixed in Phase 1 (unrelated to Global Account, but found via the same mobile-migration
work)**: a real Q-Punch winner-tally bug — `election_core._ensure_tallied()` tallied a cycle's
winners once ever per village/sign/year, permanently freezing a null tally if the cycle was first
seen as closed before all its votes existed. Confirmed live against a copy of the real database
(`qumanity_prototype.db` itself had exactly this stale state for Libra 2026 / Rohini Sector 24).
Fixed by always recomputing from current votes; new test file `tests/test_election_winner_tally.py`
(25 checks).

**Corrective follow-up (2026-11-08)**: registration's own Village check had been left weaker than
profile-change's — it never queried `india_villages` at all, so a non-provisional, fabricated
Village id was silently accepted. Closed by reusing the existing
`provisional_location_core.verified_village_exists()` helper inside registration's own
provisional-check loop; no new lookup mechanism, no change to the provisional-location system's
own activation rules. Confirmed, by direct test, that a genuine database-query failure during
verification raises rather than silently returning a valid result. Closing this at registration
meant 19 existing test files (each registering through the real route with a real Village) needed a
short `india_villages` seed added — none of their own test logic was touched. The two newly added
files `tests/test_global_account.py` and `tests/test_election_winner_tally.py` independently
include the same seed setup, bringing the total number of test files containing this seed setup
to 21.

**Independent adversarial pre-merge audit (2026-11-08), C1 fix (same date)**: the audit found that
every check above was wired into `app.py`'s profile-change-request flow only ("Path B"). A second,
entirely separate route to the same `users.present_location_json` write —
`social_core.request_new_account()`/`decide_account_request()` ("Path A", the dedicated "request a
new Account ID" flow, `POST /api/people/account-ids/request` and
`POST /api/admin/account-ids/<id>/decide`) — called none of it, so a Global Account could submit a
fabricated India village location through it and, once approved, cross the Global/Public boundary
and acquire the real pilot village's Q-Punch residency. Fixed by moving
`_validate_present_location_change()` and its helpers into `account_core.py` (so `social_core.py`
can call it without a circular import) and calling it at both submission and approval in Path A,
exactly mirroring Path B. New test file `tests/test_account_id_request_security.py` (31 checks),
including the exact exploit reproduced and rejected through the real HTTP routes. See
`docs/HANDOVER.md` §9.3 for full detail.

**Mobile UI exploitation surface (found during the independent post-fix audit, same date)**: the
mobile app's own "Account IDs → request a new one" screen
(`Qumanity_App/mobile/src/app/account-ids.tsx`) calls these exact two routes, and its entry point
in `private.tsx` is not gated on account type — so a Global Account could reach this normal,
un-fabricated screen and, before this fix, queue a request that an admin's approval could turn
into an illegitimate Global-to-Public crossing. The mobile screen itself was never the security
boundary and no mobile code change was made or is needed: the backend now validates the proposed
present-location at submission and independently revalidates it against the user's current
account state at approval, and the screen's existing generic error handling already surfaces a
rejection correctly. Backend authorization and validation remain the sole, authoritative gate.

**Committed and pushed to `origin/main`** (`a7d43a7` then `a157d7a`) — `tests/test_global_account.py`:
**136 checks**, all pass; plus `tests/test_election_winner_tally.py` (25 checks) and
`tests/test_account_id_request_security.py` (31 checks); full regression is 33 files /
**1,370 checks** / 0 failures. The mobile app's own cross-repo checker
(`Qumanity_App/tools/website-check/check_app_api.py`) shows only one remaining, pre-existing,
unrelated failure ("board shows the post, score and vote state" — tracked separately, not a
Global Account or election issue, and not fixed by this release). Production serving of this
release's registration UI was confirmed by direct, read-only inspection of the live site; Railway's
own deployment metadata was not independently verified (CLI authentication expired) — that remains
an owner action.

---

## DPG evidence

The evidence pack (`docs/dpg_evidence/`) is internal evidence-preparation/self-assessment work —
5 of its 17 documents (the ones touched by the 2026-11-01 correction pass) mark themselves "not a
DPGA resubmission"; the other 12 carry no such banner but likewise make no certification claim.
**No document in the pack claims formal DPG certification or registry acceptance** (re-confirmed
by grep this session). Application-form-answers: 40 of 45 fields "Ready"
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

The website feature-development phase is complete as of `a157d7af01e1e5791de6e2449cde2945652c8659`
(pushed to `origin/main` 2026-11-09 — Global Account registration/authorization, Q-Punch
winner-tally correction, and the C1 account-ID-request security correction; see `docs/HANDOVER.md`
§9.3/§14). The next phase is the phone application (`qumanity-app` / `Qumanity_App`), which already
has substantial prior work against this backend and must integrate with the existing `/api` routes
and **must not** independently redefine location IDs, consent rules, geography, or user identity.
Full, comprehensive handover instructions (API contracts to reuse, permission rules, known
limitations, where to start): `docs/HANDOVER.md` §15.

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

- 2026-11-09: documentation reconciliation following the Global Account / C1 release
  (`a7d43a7`/`a157d7a`, pushed to `origin/main`). Corrected every remaining "uncommitted"/stale-SHA
  reference to Global Account across this file and `docs/HANDOVER.md`; added the final regression
  totals (33 files/1,370 checks; cross-repo checker 156 passed/1 pre-existing unrelated failure);
  recorded that production was confirmed, by direct read-only inspection, to be serving this
  release's code, while Railway's own deployment metadata remains unverified (expired CLI
  authentication, an owner action); verified and updated the status of the two previously flagged
  phone-app API discrepancies (the missing `donation` object was never a backend defect — a stale
  checker assertion; the winner-tally display bug was real and is fixed, Task 1B); rewrote
  `docs/HANDOVER.md` §15 into a comprehensive, standalone website-to-phone-app handover; added the
  missing `account_core.py` row to `docs/ARCHITECTURE.md`'s module map; added a Global Account
  section to `docs/phone_app_api.md` (the `Qumanity_App` copy of that file was not touched —
  out of scope for this repository-scoped task).
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
