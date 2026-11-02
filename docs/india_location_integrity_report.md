# India Location Data Integrity: Consolidated Report

**2026-11-02. Research and read-only audit only. No location data was changed by this report or
by any script it describes, beyond the already-committed Bawana pilot correction
(commit `211480c`) that motivated this investigation.**

## 5.1 Executive summary

This investigation started from one specific correction: removing a duplicate "Bawana" tehsil
record from Delhi's North West district (`CS.DL.3.4` vs. `CS.DL.3.E`), committed as a narrow,
read-only-audited pilot fix in `211480c`. While investigating *that* pair, it became clear the
duplication was not a one-off — every one of Delhi's 7 districts showed signs of its tehsil list
being doubled. That single observation was enough to warrant stopping before committing any
broader fix, and instead measuring the real, national scale of the problem before anyone proposes
a migration.

**What was actually audited:** the entire India hierarchy inside the canonical
`Qumanity_Master.json` (37 States/UTs, 5 Zones, 559 Districts, 7,301 Tehsils, 635,693 Villages),
using an exact, narrow duplicate definition (same category, same name after only trim+lowercase
normalization, same immediate parent — no fuzzy matching). This was done with a new, read-only
script (`scripts/audit_all_india_duplicates.py`), actually run against the real data, with its
output independently re-verified by re-parsing the CSV it produced.

**The measured scale:** 74 Tehsil-level duplicate groups and 15 Village-level duplicate groups
nationally. **Zero** State-level or District-level duplicates anywhere in the country. 61 of the
74 Tehsil groups are in Delhi's 7 districts; the other 13 are scattered across Andaman & Nicobar,
Assam, Karnataka, Tamil Nadu, Mizoram, and Odisha. This is the real, measured number — it is not
extrapolated from the Delhi finding, and the Delhi finding itself turned out to be real but not
total (61 of a possible ~70, not all of them).

**What remains uncertain:** which of the 73 still-open Tehsil groups (Bawana is the one already
resolved) and 15 Village groups have a safe, evidence-supported survivor. A concrete, real,
*unresolved* example was found this pass — the "Tri Nagar" pair in Chandni Chowk
(`CS.DL.7.4`/`CS.DL.7.14`) has a real user reference on **both** sides and zero overlap between
their own children, meaning this pass cannot and does not recommend a survivor for it. Every
other open group needs the same per-case check before anyone touches it.

**Why no location cleanup or migration has been executed:** this task was explicitly scoped as
research and proposal only. Beyond that, the Tri Nagar example above is concrete proof that a
blanket "just dedupe everything the same way Bawana was done" approach would be unsafe — some of
these 88 open groups may have real, conflicting user data on multiple sides, and must be resolved
one at a time, with explicit owner sign-off per case (see `docs/india_dedup_migration_plan.md`).

## 5.2 Measured duplicate findings

| | Count |
|---|---|
| States/UTs examined | 37 |
| Zones examined | 5 |
| Districts examined | 559 |
| Tehsils examined | 7,301 |
| Villages examined | 635,693 |
| **Duplicate groups — State** | **0** |
| **Duplicate groups — District** | **0** |
| **Duplicate groups — Tehsil** | **74** (61 in Delhi, 13 elsewhere) |
| **Duplicate groups — Village** | **15** (9 in Delhi, 6 elsewhere: Gujarat, Maharashtra, Telangana, Odisha) |

**Top 10 largest duplicate groups** (by combined child count — full list in
`docs/india_duplicate_audit_2026-11-01.csv`):

1. Viluppuram, Tamil Nadu (`SS.TN.D.5`/`SS.TN.D.7`) — 180 combined villages, 0 overlap
2. Kandhamal, Odisha (`ES.OR.15.13`/`ES.OR.15.1F`) — 177 combined, 0 overlap
3. Lakhimpur, Assam (`CS.AS.5.B`/`CS.AS.5.F`) — 152 combined, 0 overlap
4. Cuddalore, Tamil Nadu (`SS.TN.1B.1`/`SS.TN.1B.8`) — 128 combined, 0 overlap
5. Andaman and Nicobar Islands (`CS.AN.1.8`/`CS.AN.1.D`) — 120 combined, 4/116 overlap
6. Darrang-Udalguri, Assam (`CS.AS.4.14`/`CS.AS.4.18`) — 103 combined, 0 overlap
7. West Delhi (`CS.DL.4.6`/`CS.DL.4.E`) — 96 combined, 2/94 overlap
8. West Delhi (`CS.DL.4.9`/`CS.DL.4.F`) — 95 combined, 2/93 overlap
9. Darrang-Udalguri, Assam (`CS.AS.4.15`/`CS.AS.4.19`) — 90 combined, 0 overlap
10. New Delhi (`CS.DL.1.6`/`CS.DL.1.D`) — 86 combined, 12/73 overlap

**Canonical Master vs. derived-file agreement:** both `static/data/subcontinent_districts.json`
and `static/data/india_districts_tehsils.json` agree with `Qumanity_Master.json` on every single
District and Tehsil ID/name — **except exactly one**, `CS.DL.3.E` (the Bawana duplicate), which
is present in Master but correctly absent from both derived files, precisely because of the
already-committed pilot fix. No other drift was found anywhere in the country. This is a strong,
reassuring result: the derived files are not independently corrupted — they faithfully reflect
Master except for the one place this project already, deliberately, corrected.

**The Delhi seven-district issue, precisely:** not "every tehsil in every district is doubled" —
61 of a possible ~70 tehsil-name pairs across the 7 districts are genuine duplicates under this
audit's own definition; the rest are singly-present. The Bawana pilot (`211480c`) corrected
exactly one of these 61 pairs, in the derived files only, leaving the Master JSON and the other
60 Delhi pairs (plus 13 outside Delhi) untouched, exactly as that task's own scope required.

**Mandatory addendum applied:** `docs/location_dedup_report.md` now has a dated 2026-11-02
addendum tracing the full history (the 2026-10-06 report's now-superseded "zero duplicates"
finding against the retired SITAXML source, commit `9672e02`'s intentional Master-JSON-based
rebuild that introduced the current duplication, and this pass's own measured findings) —
preserved alongside, not over, the original 2026-10-06 content.

## 5.3 Architecture recommendation

**Recommendation: keep `Qumanity_Master.json` canonical.** Do not move to SQLite-canonical. Full
reasoning in `docs/location_architecture_decision.md`; summarized:

- **Performance:** the measured data volume (a few thousand States/Districts/Tehsils, 635K+
  villages) is not large enough to need a storage-engine change — the one genuinely large dataset
  (villages) is *already* SQLite-backed (`india_villages`) and performs acceptably. The real,
  measured performance gap found this pass is an **inconsistency**, not a slowness: `app.py`'s own
  `_load_json()` re-reads the file from disk on every request with no cache, while
  `provisional_location_core.py` caches the same file in memory — two different access patterns
  for the same data, independent of JSON vs. SQLite.
- **Transactional safety:** the real operational gap found this pass is the *lack of a safe,
  narrow-edit tool* — the only existing generator (`scripts/regenerate_location_data.py`) rebuilds
  everything from Master and wipes/reimports `india_villages` wholesale, which is why a
  purpose-built, single-use script (`scripts/dedupe_bawana_tehsil.py`) had to be written for the
  Bawana fix instead. Recommendation: formalize that script's backup/verify/atomic-write pattern
  into a reusable helper, rather than re-platforming onto SQLite to get transactions this project
  doesn't need yet at this data volume.
- **Stable IDs:** neither architecture currently has a crosswalk for a retired ID — this is a real
  gap on *either* side, and the recommendation is to build one (a new `location_id_history` SQLite
  table) regardless of which source stays canonical.
- **Enumerated writers:** no script in this repository writes to `Qumanity_Master.json` itself —
  it is edited by a process outside this codebase, which this pass could not identify from
  repository evidence alone. This is flagged as an open question for the owner, not resolved here.

## 5.4 Migration strategy

Full detail in `docs/india_dedup_migration_plan.md` (marked AWAITING APPROVAL — DO NOT EXECUTE).
Summary:

- **Classification:** reuses this audit's own exact duplicate definition — never fuzzy-matched.
- **Survivor decision:** evidence-based per case (real user references, child-name overlap, data
  quality) — **never** reference-count alone, since a popular wrong ID is still wrong and a quiet
  correct one is still correct. Bawana (resolved) is the clean example; Tri Nagar (open) is the
  concrete counter-example where this pass explicitly refuses to guess, because real users
  reference *both* sides and their children don't overlap at all.
- **Reference audit:** a full, schema-verified inventory of every table that could hold a
  location reference — 19 distinct tables/column-pairs found this pass (several beyond the task's
  own starting list: `qpunch_addresses`, `qpunch_queue_messages`, `announcements`,
  `collective_karma`(`_log`), `election_cycles`, `location_elements`, `profile_change_requests`,
  `recognition_stars`, `reports`, `subgroups`, `village_council`, `zone_sentiment`(`_stats`),
  `admin_export_log`, plus the known `users`/`account_ids`/`india_villages`/
  `provisional_locations`). Most are currently empty in the live database; three
  (`election_cycles`, `recognition_stars`, `village_council`) all point at the same real pilot
  village, `CS.DL.3.4.1A`, which is itself a child of the already-resolved Bawana tehsil.
- **Non-overlapping children:** never auto-discarded — merge, reparent, or block, per an explicit
  decision rule (§3.5 of the migration plan), with no fuzzy-name shortcut permitted.
- **Safety mechanics:** backup + SHA-256 verify + atomic replace + idempotency check, the same
  pattern already proven by the Bawana script.
- **Unresolved, needing owner approval before any implementation:** survivor selection for all 73
  remaining Tehsil groups and 15 Village groups (Tri Nagar explicitly flagged as needing a human
  decision, not an algorithm); the crosswalk table's schema; which script gets the extracted
  safety helper first.

**No migration code has been written. No further deduplication beyond the already-committed
Bawana pilot has been performed.**

## 5.5 `0_Earth` assessment

Full detail in `docs/0_earth_cleanup_proposal.md`. `~/Desktop/0_Earth/Continents/` is a genuinely
live, ~493,000-directory, 107.8 MB scaffold containing real per-user subfolders — classified as a
single "clearly live, do not touch" unit, not enumerated path-by-path (impractical and not useful
at that scale). The seven loose files directly under `0_Earth/` were reviewed individually:
`Qumanity_Master.json` is clearly live; one `.DS_Store` file (plus 34 more found inside
`Continents/`) is clearly disposable Finder metadata; the remaining five (`O.json` and four
timestamped `Qumanity_Master.before_*_fix_*.json` backups, one of them an outlier at 115 MB vs.
the ~32.4 MB norm) are honestly classified "unclear, needs a human decision" — deciding whether a
backup is still needed requires confidence about whether its corresponding fix is final, which is
not this pass's call to make.

**No file or folder under `0_Earth` was moved, deleted, renamed, or modified.**

## 5.6 What is not decided or built

- No location records have been deleted or merged in this phase, beyond the already-committed
  Bawana pilot from the prior task.
- No user location identities have been changed.
- No database table has been modified — every database access this phase was a `SELECT` against
  a `mode=ro` connection.
- No source or derived geography JSON has been modified.
- No migration script has been written.
- No new canonical location architecture has been implemented — `location_architecture_decision.md`
  is a recommendation document only.
- No `0_Earth` file has been archived, moved, renamed, or deleted.
- No Phase 2 report or audit script has been staged or committed to git (see below — this is
  deliberate, pending the sequence this task specified).

**Approvals needed before any implementation begins:** (1) confirmation of where/how
`Qumanity_Master.json` is actually authored outside this repository; (2) the `location_id_history`
crosswalk schema; (3) a survivor decision for each of the 73 remaining Tehsil groups and 15
Village groups, case by case — not a blanket rule; (4) the partial-overlap child-handling rule in
the migration plan; (5) whether/when to act on the `0_Earth` loose-file backups once their
corresponding fixes are confirmed stable.
