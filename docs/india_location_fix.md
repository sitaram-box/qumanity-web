# India location ID fix (2026-09-28)

## Incident: 2026-10-11 Production DB Never Seeded

**Summary**: Separately from the scheme-mismatch incident below, production (qumanity.in) was
found running on an essentially empty database (2 users, 0 villages, 0 posts) -- the Railway
volume at `/data` never received `Qumanity_Master.json`, and `scripts/import_india_villages.py`
had a hardcoded Mac-only path to it, so the village import could never have succeeded inside the
container even if it had been run.

**Fix**: `scripts/import_india_villages.py` now resolves both the Master.json path and the DB
path from env vars (`MASTER_JSON_PATH`, `QM_DB_PATH`) with environment-appropriate fallbacks, so
the same script runs unmodified on Mac dev or inside the Railway container. Added `--dry-run`
(count only, no writes), `--verify` (post-import sanity check against
`subcontinent_districts.json`, PASS/FAIL), and progress logging every 100,000 villages. Added
`scripts/deploy_data_to_railway.sh`, a one-command operator helper that uploads Master.json to
the volume and runs the import+verify inside the container -- idempotent, safe to re-run.
`GET /healthz` now also reports `village_count`/`posts_count`/`master_json_present`/`boot_time`
and returns `"status": "degraded"` (still HTTP 200) whenever `user_count` or `village_count` is
zero, so an unseeded production DB is visible before a real user hits it.

## Incident: 2026-10-11 Village Dropdown Empty (P0)

**Summary**: A prior session re-ran the retired SITAXML-based import script, silently
reintroducing a scheme mismatch that had been fixed on 2026-09-28. Registration was blocked --
the Village dropdown showed zero options for most tehsils (and wrong villages for others), because
`india_villages` had been repopulated with SITAXML's own district/tehsil numbering, which assigns
the same dotted IDs (e.g. `CS.DL.3.4`) to different real places than `Qumanity_Master.json` does.
A second, independent instance of the same class of bug was found while re-verifying through the
real registration UI (not just the database): `static/data/subcontinent_districts.json` --  a
separate file the registration page's own dropdowns actually fetch via `/api/subcontinent/districts`
-- had never been updated when `india_districts_tehsils.json` got fixed on 2026-09-28, so its India
portion was still 100% SITAXML-numbered.

**Fix**:
- (a) `scripts/import_india_villages.py` rewritten to source from `Qumanity_Master.json` directly
  (635,622 villages re-imported; tehsil-id overlap with the website's own district data went from
  ~50% to 100%).
- (b) `static/data/subcontinent_districts.json`'s India portion (all 37 states) replaced with the
  already-correct data from `india_districts_tehsils.json`.
- (c) The retired SITAXML-based script moved to `scripts/_retired/import_india_villages_SITAXML.py`,
  with a warning header and a `--i-know-this-is-retired` guard flag it refuses to run without.
- (d) `app.py`'s `_validate_india_villages_loaded()` (startup check) now also compares every
  `tehsil_id` in `india_villages` against `subcontinent_districts.json` and logs a `[boot] WARNING`
  if any are missing -- the scheme-mismatch failure mode is now loud in the logs instead of silent.
- (e) The "Can't find my Village in the list" fallback (added as a workaround for the empty-list
  symptom) was removed entirely, including its `PENDING`/`pending_assignment` location-JSON path --
  zero existing users had a `PENDING` village, so no data migration was needed.

**Rule for future sessions: ALWAYS source India location data from `Qumanity_Master.json`. NEVER
from `SITAXML.xml`.** If `india_villages` or any India district/tehsil dataset ever needs
re-importing, use `scripts/import_india_villages.py` (the Master.json version) -- never the
retired script in `scripts/_retired/`, and never re-derive from `SITAXML.xml` directly.

## The bug
The website's India district/tehsil/village dataset (`static/data/india_districts_tehsils.json` + the `india_villages` SQLite table) was imported separately from a SITAXML source (`scripts/import_india_villages.py`), independently of `Qumanity_Master.json`. Both systems used the same dotted-ID convention (`CS.DL.5.4`) but assigned it to **different real places** — the website called `CS.DL.5.4` "Bawana"; Master.json calls it "Kondli". Since the *physical* `0_Earth` folder tree is built from Master.json, a Bawana resident's account was actually filed in the folder Master.json calls Kondli.

**Confirmed scope:** India only. Continents, countries, zones and states already matched Master.json exactly (checked programmatically — states had only 2 harmless spelling differences, e.g. "Pondicherry" vs "Puducherry"); the other 9 Sub-continent countries' full district/tehsil/village trees already come from Master.json via `scripts/build_subcontinent_data.py`. Only India's district level and below used the separate SITAXML source. 452 district-id mismatches were found before the fix.

## The fix
`static/data/india_states.json`, `static/data/india_districts_tehsils.json` and the `india_villages` table are now generated **directly from `Qumanity_Master.json`** — the same source the physical folder tree was built from — so the website and the folders agree by construction. The SITAXML source (`scripts/import_india_villages.py`) is retired; do not re-run it.

A startup check (`app._validate_india_location_data`, in `app.py`) compares the live `india_districts_tehsils.json` against Master.json every time the server starts and prints a `[STARTUP WARNING]` if they ever drift apart again.

## What else this touched
The Founder's own account (`private_id_9digit` ADMIN_ID_PLACEHOLDER) was registered under the old, wrong scheme — birth "New Delhi" (should be Chandni Chowk), present "North West Delhi/Bawana" filed one place removed from the real Bawana. Corrected by hand for this one account:
- `users.birth_location_json` / `present_location_json` updated to the real district/tehsil/village (Chandni Chowk → Tri Nagar → Ganesh Pura, Tri Nagar; North West Delhi → Bawana → Rohini Sector 24).
- Readable `private_id`/`account_id` regenerated to match (the 9-digit login code and PIN are unchanged).
- `location_elements` counts moved from the old ids to the new ones.
- The `BORN_HERE`/`LIVING_HERE` folders were moved on disk to the folders Master.json actually assigns those ids to (old, wrongly-filed folders removed after copying their contents across).
- `election_core.PILOT_VILLAGE_ID` (and its copy in `templates/dashboard.html`) updated from `CS.DL.5.4.1E` to the real Rohini Sector 24, `CS.DL.3.4.1A`; the stray election-cycle test rows created under the old id were cleared.

**The other 187 (demo) accounts were left untouched** — their location data may now be stale in the same way, but they're demo data slated for removal in the separate Master.json v2 / Cloudflare D1 rebuild (see `qoins_wallet_system.md`'s sibling doc, to be written when that project starts), not fixed individually here.

## A data-quality note for that future rebuild
While tracing this, `Qumanity_Master.json`'s own India tree was found to contain **duplicate tehsil entries** in places (e.g. district CS.DL.7 "Chandni Chowk" lists "Tri Nagar" twice, as both CS.DL.7.4 and CS.DL.7.14, each a full copy with its own villages) — and the physical `0_Earth` folder tree, built from an earlier version of Master.json, doesn't have folders for all of today's Master.json village entries (e.g. no `CS.DL.7.14` folder exists on disk yet, only `CS.DL.7.4`). `resolve_location_dir()` already handles this gracefully — it stops at the deepest level that actually exists on disk rather than inventing folders — so nothing is broken, but a full rebuild should de-duplicate tehsils by name+parent and re-sync the disk tree to whatever Master.json version is authoritative at that time.

## Not touched
- The ~500,000 already-existing `0_Earth` folders for every other place (they were already correctly keyed to Master.json's ids; nothing needed to move except the Founder's own two folders above).
- The 187 demo user accounts.
- Zones/states/continents/countries (already correct).
- The other 9 countries (already correct).
