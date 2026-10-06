# Location De-duplication Report

**Date:** 2026-10-06
**Scope:** All India states/districts/tehsils in SITAXML.xml (635 districts, 5,970 tehsils), checked for same-name-within-same-parent duplicates.

## Result: zero real duplicates found

A full streaming parse of the canonical source (`SITAXML.xml`, 50MB, all `Public_District`/`Public_Tehsil` elements) found:

- **Duplicate districts (same name, same state): 0**
- **Duplicate tehsils (same name, same district): 0**

This is well under the 20-duplicate threshold, so no stop-and-list was triggered.

## Important correction to the P0 report

The P0 fix (previous turn) reported "every tehsil in North West Delhi appears twice (e.g. Bawana as `CS.DL.3.4` and `CS.DL.3.E`)" as a SITAXML source issue. **That was wrong, and I need to correct it here.**

What actually happened: `static/data/india_districts_tehsils.json` (built Sep 28 by `scripts/extract_india_districts_tehsils.py`) and the `india_villages` SQL table (built by `scripts/import_india_villages.py`) both had **corrupted district-id-to-name mappings** relative to the real `SITAXML.xml` on disk today — e.g. both files/table said `CS.DL.3` = "North West Delhi" / Bawana, while the actual raw XML says `CS.DL.3` = "New Delhi" (Patel Nagar, Karol Bagh, etc.) and the real Bawana is `CS.DL.5.4`. I was not able to determine *why* those two scripts' outputs diverge from a fresh run of the same scripts against the same XML file — possibly the source XML was replaced at some point without re-running the exact scripts whose outputs are currently on disk. I did not chase that further since it's moot once the data is regenerated fresh (below).

The P0 fix merged the *wrong* (`india_districts_tehsils.json`) district/tehsil data into the live site, which both (a) swapped real district names (New Delhi ↔ North West Delhi, and surely others) and (b) is what produced the apparent "duplicate Bawana" — it wasn't a SITAXML duplication, it was two corrupted derived artifacts agreeing with each other while disagreeing with the source.

**This has been reverted.** `static/data/subcontinent_districts.json` is back to its original, git-tracked state, which — verified directly against today's `SITAXML.xml` — is correct: `CS.DL.3` = New Delhi, `CS.DL.5` = North West Delhi/Bawana, no duplicate districts or tehsils anywhere in Delhi or nationally.

## The real root cause (both of P0's original symptom and the above)

`india_villages` (635,622 rows, pre-existing) had villages filed under the same corrupted tehsil IDs as the stale `india_districts_tehsils.json` — e.g. Bawana's 40 real villages were stored under `tehsil_id='CS.DL.3.4'` instead of the correct `CS.DL.5.4'`. The original, always-correct `subcontinent_districts.json` asks for `CS.DL.5.4` when a user picks Bawana — which is why the dropdown came back empty before any of my changes: the correct ID simply had no matching rows in the corrupted table.

**Fix:** re-ran the existing, already-correct `scripts/import_india_villages.py` against the current `SITAXML.xml`. This is a clean `DELETE FROM india_villages` + full re-import, no code changes needed — the import script itself was fine, only its prior output was stale/wrong.

## Verification after the fix

- `CS.DL.5.4` (true Bawana): now 40 villages, all genuine Bawana-area names (Auchandi, Bajitpur Thakaran, Punjab Khor, Mungeshpur, ...).
- `CS.DL.3.4` (true New Delhi/Patel Nagar): now 14 villages, all genuine Patel Nagar-area names (Baljeet Nagar, Nehru Nagar, East Patel Nagar, ...).
- Re-ran the national district/tehsil duplicate scan against the restored file: **0 duplicates**, as reported above.
- One minor, unrelated data-quality note: a single district ID in the raw XML, `" CS.DL.6"` (West Delhi), has a stray leading space in its `id` attribute. Affects 1 of 635 districts. Not a duplication issue; flagging for awareness, not fixed (cosmetic, doesn't block anything — the frontend's searchable-select already works fine here since it's keyed by exact string match either way).

## Bottom line for Part A

There is no real duplicate-ID problem to resolve. The "single source of truth" requirement is already satisfied in substance: one correct JSON file (`subcontinent_districts.json`) and one correct SQL table (`india_villages`), both derived from and verified against `SITAXML.xml`, mutually consistent. See `docs/location_consolidation_report.md` for the fuller picture and a recommendation on whether the larger unified-schema work (Steps A4–A9 of the original ask) is still worth doing given this.
