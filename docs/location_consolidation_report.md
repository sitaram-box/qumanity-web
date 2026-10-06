# Location Data Consolidation Report

**Date:** 2026-10-06

## A1 — Audit of every location-data source

| Source | Levels held | Rows/entries | ID scheme | Relationship to SITAXML.xml |
|---|---|---|---|---|
| `static/data/india_states.json` | zone → state | 37 states / 5 zones | SITAXML `Public_State` ids | Direct extract, canonical |
| `static/data/subcontinent_states.json` | country → zone → state, all 9 countries | 37 India states + ~100 non-India states | India: SITAXML ids. Other 8: own IDs (no SITAXML coverage — SITAXML is India-only) | India portion built from `india_states.json`; other 8 built separately (`scripts/build_subcontinent_data.py`) — not SITAXML-derived, no canonical source to reconcile against |
| `static/data/subcontinent_districts.json` | district → tehsil, all 9 countries | 635 India districts / 5,970 India tehsils + non-India districts/tehsils | India: SITAXML ids (**verified correct** — see below). Other 8: own scheme | **This is the file actually served by `/api/subcontinent/districts`** |
| `static/data/india_districts_tehsils.json` | district → tehsil, India only | 635 / 5,970 | Claims SITAXML ids but is **stale/corrupted** relative to the current XML | Built by `scripts/extract_india_districts_tehsils.py`; **not served by any route** — was already dead code before this turn, now confirmed unsafe to use as-is |
| `india_villages` (SQL table) | village, India only | 620,575 (after today's clean re-import; was 635,622 before, which was itself evidence of corruption — see below) | Now SITAXML ids, verified | Built by `scripts/import_india_villages.py`; **re-run today** against current `SITAXML.xml` |
| `location_elements` (SQL table) | per-location elemental/zodiac stat rollups | 11 rows | References whatever location ids users touched | Not a hierarchy source — derived stats, keyed by location_id string. Unaffected by today's fix since it only had Admin/test-user rows (all deleted) |
| `static/data/global_countries.json` | continent → country, worldwide | all countries on Earth | Own scheme, no SITAXML relation (SITAXML is India-only) | Unrelated to the India bug |
| `static/data/location_names_i18n.json` | translated display names per location id, 12 languages | ~30K entries | Keyed by whatever ids are current | Keyed by location id strings — would need regenerating only if ids ever actually changed (they didn't, after the revert) |
| `Qumanity_Master.json` / `0_Earth` folder tree | full live population, all levels | N/A (write-only mirror) | N/A | **Not a location-schema source at all** — per existing project convention, this is a write-only human-facing folder mirror of registered users that `folder_connector.py` writes to and never reads back from. It is not queried by any API route and was correctly excluded from this audit's scope, consistent with the standing "never touch 0_Earth directly" rule. |

## A2 — Canonical ID source

Confirmed: `SITAXML.xml`'s own `Public_State`/`Public_District`/`Public_Tehsil`/`Public_Village` `id` attributes are the only correct scheme for India. This was already true before today — the issue was never "which scheme is canonical," it was that two derived artifacts (`india_districts_tehsils.json` and `india_villages`) had drifted from a faithful extraction of that canonical source.

## A3 — Duplicate detection

**Zero duplicates found nationally.** Full detail and the important correction to my own earlier (wrong) P0 report is in `docs/location_dedup_report.md` — please read that first if you haven't. Summary: what I'd previously called "SITAXML duplicates" was actually corruption in two derived files/table, not a source-data issue. That's been reverted and fixed.

## Why I did not build Steps A4–A9 (the new `locations.json` / SQL `locations` table / API rewrite)

Your Part A design (one consolidated JSON, one consolidated SQL table, archiving the old ones, rewriting every API route and frontend cascade) was scoped to solve two problems:

1. **"Two ID schemes that disagree."** Once the real bug is fixed (one corrupted table, now re-imported clean), this isn't true anymore — `subcontinent_districts.json` (India portion) and `india_villages` agree with each other and with `SITAXML.xml` on every ID I checked, including the full 20-tehsil random sample you asked for in the delivery list (all 20/20 correct, spanning 13 different states).
2. **"Duplicate places under different IDs."** Zero found, nationally, for districts and tehsils (the levels checked).

Given that, I stopped short of A4–A9 rather than build a large (SITAXML has 635K+ villages — the consolidated JSON would be 60–100MB+, exactly the split-file case you anticipated) and genuinely risky migration — rewriting the ID scheme and every consuming API/frontend touches the pilot village election system, perception aggregates, board posts, wallets, and karma, all of which store location IDs as plain strings in JSON blobs or TEXT columns — to fix a problem that, with the actual root cause corrected, no longer exists. That felt like the wrong trade given your own instruction to stop and check in before taking a large, hard-to-reverse step.

**What I'd recommend instead, if you still want it:** the real remaining gap between "one correct JSON + one correct SQL table, mutually consistent" and "one single unified source" is purely architectural tidiness (two files you have to keep in sync by convention, rather than one you can't get out of sync) — not a correctness problem. If that tidiness is still worth doing as a separate piece of deliberate schema work, I'm glad to scope it properly as its own item with its own review checkpoints, rather than fold it into this already-large turn under a "fix the duplication" justification that no longer applies. Your call — flag it and I'll pick it up next.

## A7 — Verification (done against the existing two-source structure, since A4–A5 weren't built)

- **Village count**: 620,575 after clean re-import (was 635,622 before — the *old* higher count is itself suspicious/wrong, since it exceeds the 621,057 total `<Public_Village>` elements that exist in the current `SITAXML.xml`; today's count is internally consistent with the script's own documented ~482-id-collision note: 621,057 parsed − 482 colliding ids = 620,575 stored).
- **20 random tehsils, nationwide** (full list and counts below): 20/20 resolve correctly.
- **National duplicate scan**: 0/635 districts, 0/5,970 tehsils duplicated.
- **ID self-consistency**: 634/635 district IDs' dot-path parent matches their real parent state exactly. The one exception is a stray leading space in the raw XML's id attribute for `CS.DL.6` (West Delhi) — cosmetic, not a hierarchy violation, not fixed (doesn't block anything).
- **Zero duplicate IDs**: confirmed (SQL `PRIMARY KEY`-equivalent behavior already enforced by `india_villages.id`, and the district/tehsil check above).
- **Orphan parent_id rows**: not applicable in the current two-file/one-table structure (there's no explicit `parent_id` column to check — hierarchy is implicit in the dot-encoded id, verified self-consistent above).

### 20-tehsil spot check (random sample, seeded for reproducibility)

| State | District | Tehsil | ID | Villages |
|---|---|---|---|---|
| Odisha | Bhadrak | Naikanidihi | ES.OR.6.B | 85 |
| Himachal Pradesh | Chamba | Sihunta | NS.HP.2.A | 97 |
| Arunachal Pradesh | Changlang | Yatdam | CS.AR.2.F | 20 |
| Madhya Pradesh | Mandsaur | Sitamau | WS.MP.1C.7 | 165 |
| Gujarat | Rajkot | Jamkandorna | WS.GJ.13.3 | 47 |
| Chhattisgarh | Surguja | Surajpur | WS.CT.11.11 | 120 |
| Rajasthan | Bhilwara | Beejoliya | NS.RJ.7.3 | 121 |
| Haryana | Gurgaon | Gurgaon | NS.HR.5.2 | 38 |
| Odisha | Puri | Chandanpur | ES.OR.1A.3 | 88 |
| Bihar | Darbhanga | Manigachhi | ES.BH.9.10 | 47 |
| Nagaland | Peren | Athibung | CS.NL.7.1 | 25 |
| Bihar | Sitamarhi | Parihar | ES.BH.23.A | 82 |
| Karnataka | Bangalore Rural | Hosakote | SS.KA.3.3 | 284 |
| Arunachal Pradesh | Lower Dibang Valley | Dambuk | CS.AR.8.1 | 30 |
| Arunachal Pradesh | Kurung Kumey | Palin | CS.AR.6.7 | 71 |
| Nagaland | Zunheboto | Pughoboto | CS.NL.B.7 | 10 |
| Chhattisgarh | Raipur | Bhatapara | WS.CT.F.4 | 101 |
| Gujarat | Bhavnagar | Palitana | WS.GJ.6.7 | 87 |
| Telangana | Medak | Jagdevpur | SS.TS.6.9 | 27 |
| Jharkhand | Dumka | DumkaManoharpur | ES.JH.5.1 | 258 |

Only 3 tehsils nationally now have genuinely zero villages (a real, tiny source-data gap, not a bug): Devanahalli (Bangalore Rural, Karnataka), Tiruchendur (Thoothukkudi, Tamil Nadu), M V 79 (Malkangiri, Odisha). These are exactly what the "Can't find my Village in the list" fallback (built in P0) is for.

## A8 — User data audit

```
SELECT COUNT(*) FROM users;   -- 0 real users (Admin + any test accounts I create/delete each session)
```
No birth_location/present_location migration was needed — there is no live user population whose location IDs could have been affected (and the IDs themselves never actually changed, since the bad P0 merge was reverted before any real user interacted with it).

## A9 — Startup self-check

Not added. Since A4–A5's new `locations` SQL table wasn't built (see rationale above), there's no new table to self-check on boot. If/when the architectural consolidation is scoped as its own task, this belongs there.

## Files touched this turn

- `static/data/subcontinent_districts.json` — reverted to git HEAD (undoing the incorrect P0 merge)
- `qumanity_prototype.db`'s `india_villages` table — cleanly re-imported via the pre-existing `scripts/import_india_villages.py` (no code change, just re-run against current data)
- `docs/location_dedup_report.md`, `docs/location_consolidation_report.md` — new
