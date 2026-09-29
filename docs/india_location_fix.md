# India location ID fix (2026-09-28)

## The bug
The website's India district/tehsil/village dataset (`static/data/india_districts_tehsils.json` + the `india_villages` SQLite table) was imported separately from a SITAXML source (`scripts/import_india_villages.py`), independently of `Qumanity_Master.json`. Both systems used the same dotted-ID convention (`CS.DL.5.4`) but assigned it to **different real places** — the website called `CS.DL.5.4` "Bawana"; Master.json calls it "Kondli". Since the *physical* `0_Earth` folder tree is built from Master.json, a Bawana resident's account was actually filed in the folder Master.json calls Kondli.

**Confirmed scope:** India only. Continents, countries, zones and states already matched Master.json exactly (checked programmatically — states had only 2 harmless spelling differences, e.g. "Pondicherry" vs "Puducherry"); the other 9 Sub-continent countries' full district/tehsil/village trees already come from Master.json via `scripts/build_subcontinent_data.py`. Only India's district level and below used the separate SITAXML source. 452 district-id mismatches were found before the fix.

## The fix
`static/data/india_states.json`, `static/data/india_districts_tehsils.json` and the `india_villages` table are now generated **directly from `Qumanity_Master.json`** — the same source the physical folder tree was built from — so the website and the folders agree by construction. The SITAXML source (`scripts/import_india_villages.py`) is retired; do not re-run it.

A startup check (`app._validate_india_location_data`, in `app.py`) compares the live `india_districts_tehsils.json` against Master.json every time the server starts and prints a `[STARTUP WARNING]` if they ever drift apart again.

## What else this touched
The Founder's own account (`private_id_9digit` 014918240) was registered under the old, wrong scheme — birth "New Delhi" (should be Chandni Chowk), present "North West Delhi/Bawana" filed one place removed from the real Bawana. Corrected by hand for this one account:
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
