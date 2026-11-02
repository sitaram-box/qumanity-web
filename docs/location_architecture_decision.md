# India Location Data: Canonical Source Architecture Decision

**Status: RECOMMENDATION FOR OWNER REVIEW. Nothing in this document has been implemented.**

2026-11-01. Written as part of the India-wide location integrity audit, after `scripts/
audit_all_india_duplicates.py` established the real measured scale of the duplicate problem (see
`docs/india_location_integrity_report.md` for the consolidated findings). This document answers
one question only: **should `Qumanity_Master.json` remain canonical, or should SQLite become
canonical, with the other becoming a generated artifact?**

## Recommendation

**Keep `Qumanity_Master.json` as the canonical source, but build the missing guardrails around
it: a deduplication/validation step that runs as part of every regeneration, and a durable
ID-crosswalk table in SQLite for any future merge.** Do not make SQLite canonical. The reasons
are below, organized around the three axes the audit asked for.

This is not "both have pros and cons" — it is a specific choice, made because the alternative
(SQLite-canonical) would require solving a harder problem (collapsing a 34 MB hand-authored/
hand-edited nested JSON tree into a relational schema without losing the `0_Earth` folder-tree
correspondence the Master JSON was built to mirror) to fix a narrower one (the JSON has no
built-in duplicate check and no transactional multi-file write).

## 1. Query performance

**Measured, not assumed, this pass:**

- Real data volume: 37 States/UTs, 5 Zones, 559 Districts, 7,301 Tehsils, 635,693 Villages for
  India alone (from `scripts/audit_all_india_duplicates.py`'s own run, re-verified by re-parsing
  its CSV output independently). `india_villages` (SQLite) holds 721,237 rows — the 635,693 above
  plus the other 9 Sub-continent countries' villages, which this same table also stores despite
  its India-specific name (confirmed: `scripts/regenerate_location_data.py`'s own Step 2/2 inserts
  non-India villages into it via `build_subcontinent_data.build_districts_and_villages()`).
- `static/data/subcontinent_districts.json` is 543 KB; `static/data/india_districts_tehsils.json`
  is 309 KB (current sizes, post-Bawana-fix).
- **No in-memory caching for the two files most of the app actually reads.** `app.py`'s own
  `_load_json()` (`app.py:90-92`) is a bare `open()` + `json.load()` — every call to
  `GET /api/india/districts-tehsils` (`app.py:3803`) or `GET /api/subcontinent/districts`
  (`app.py:3839`) re-reads and re-parses the whole file from disk, on every request, with no
  cache. `provisional_location_core.py`'s own loader (`_load_subcontinent_districts()`,
  `provisional_location_core.py:182-188`), built later for the Crowdsourced Location MVP, *does*
  cache the parsed dict at module level — the same underlying file is handled two different ways
  by two different modules today, which is itself a real, citable architectural inconsistency,
  independent of JSON vs. SQLite.
- Village lookup (the one genuinely large dataset) is already NOT JSON-based — `GET /api/
  india-villages/<tehsil_id>` queries SQLite directly (`SELECT id, name FROM india_villages WHERE
  tehsil_id = ?`), which is indexed and fast at this row count regardless of which side is
  "canonical."

**What this means for the decision:** the real performance-sensitive path (villages, 635K+ rows)
is *already* SQLite-backed and already performs acceptably — this is not a reason to move the
State/District/Tehsil tree (559 + 7,301 + 37 + 5 records, a few thousand total) into SQLite too.
At this scale, even the current uncached `_load_json()` pattern is a sub-millisecond file read on
modern hardware; the measured problem here is not JSON being too slow, it is JSON having no
duplicate-prevention and (as the Avatar/`_load_json` inconsistency shows) no single, disciplined
access pattern enforced across the codebase. Both are process problems, fixable without a storage
migration.

## 2. Transactional safety and operational reliability

**The real incident this pass is built on, cited directly:** the Bawana correction (commit
`211480c`) needed a hand-written backup + SHA-256 verification + atomic temp-file-then-replace
step (`scripts/dedupe_bawana_tehsil.py`) *specifically because* JSON has no transaction spanning
`subcontinent_districts.json` and `india_districts_tehsils.json` together — a crash between
writing the first and the second would have left them disagreeing, exactly the kind of drift the
app's own boot-time check (`app.py:5925-5954`, `_validate_india_district_data`-style function) was
built to catch after the fact, not prevent.

The same investigation also showed *why* the obvious "just use the existing generator"
(`scripts/regenerate_location_data.py`) was unsafe for a narrow fix: it rebuilds **both** JSON
files from Master in one pass and performs an unconditional `DELETE FROM india_villages` followed
by a full reimport — the correct tool for a full refresh, but it would have silently discarded a
narrow, already-audited correction and triggered a blast-radius far beyond the one record being
fixed. This is a real operational-reliability gap: there is currently no "edit just this one
record, safely" tool for the Master JSON itself, only a from-scratch regenerate-everything path
and now one single-purpose, Bawana-specific script.

**SQLite would genuinely help here** — a real `BEGIN`/`COMMIT` around a multi-table edit, foreign
keys, and a constraint that could reject a same-name-same-parent insert outright. But adopting
SQLite as canonical to get this would mean re-platforming the *authoring* workflow (however the
Master JSON is actually edited today — see §4's "unknown" callout below) onto a relational schema,
a materially larger undertaking than building the same safety properties as a disciplined *script
convention* on top of the JSON, which is what this pass's own `scripts/dedupe_bawana_tehsil.py`
already demonstrates is possible (backup, hash-verify, atomic replace, idempotent, narrow).
**Recommendation: formalize that script's pattern into a small shared helper
(`location_edit_core.py` or similar) that any future narrow correction reuses**, rather than
moving canonicality to SQLite to get transactions this project doesn't currently need at this
data volume.

## 3. Stable identity and migration safety

Dotted IDs like `CS.DL.3.4` are load-bearing — they appear in every registered user's
`present_location_json`/`birth_location_json`, in `india_villages.tehsil_id`, and now in
`provisional_location_core.py`'s `PROV-<n>` scheme's own parent-reference columns.

- **Today, under the JSON-canonical model, IDs are stable by convention, not by mechanism.**
  Nothing in `scripts/build_subcontinent_data.py`/`scripts/import_india_villages.py` enforces that
  re-running the generator preserves an existing ID for an existing place — it works today because
  the generators are idempotent in practice (same source order in → same IDs out), not because
  anything would stop a future source reordering from silently renumbering everything.
- **A SQLite-canonical model would not automatically fix this either** — a `AUTOINCREMENT` primary
  key is stable *within* SQLite, but the moment data is re-imported from a new Master-JSON-like
  source (which would still be needed for any future bulk correction from an external geography
  source), the same renumbering risk reappears unless a crosswalk is built — which is exactly the
  piece missing today regardless of which side is canonical.
- **What would actually break without a controlled migration and crosswalk, either way:** every
  registered user's `present_location_json`/`birth_location_json` for the renumbered node; every
  `india_villages.tehsil_id` under it; any `provisional_location_core.py` row whose
  `parent_verified_tehsil_id`/`parent_verified_state_id` pointed at it; any Q-Punch/council/election
  record keyed by location (see `docs/india_dedup_migration_plan.md` §3.2 for the full, schema-
  verified list).

**Recommendation: build the crosswalk as a new SQLite table (`location_id_history` or similar: old
id, new id, retired_at, reason) regardless of which source stays canonical.** This is the one
piece of infrastructure this audit found to be genuinely missing on both sides, and it is required
before any future duplicate is actually merged (see the migration plan).

## 4. Actual current readers and writers

Enumerated by inspecting the real code this pass, not inferred:

| Path | Reads | Writes |
|---|---|---|
| `Qumanity_Master.json` (`~/Desktop/0_Earth/...`, resolved via `scripts/import_india_villages.resolve_master_json_path()`) | `scripts/import_india_villages.py`, `scripts/build_subcontinent_data.py`, `scripts/regenerate_location_data.py`, `scripts/audit_all_india_duplicates.py` (this pass), `app.py:5925-5954`'s boot-time validation | **Unknown by repository evidence alone.** No script in this repository writes to it — it is edited by some process outside this codebase (a manual editor, a separate authoring tool, or hand edits against the `0_Earth` tree). This is flagged as unknown, not invented, per this task's own instruction. |
| `static/data/subcontinent_districts.json` | `app.py` (`_load_json`, several routes), `provisional_location_core.py` (cached), `scripts/dedupe_bawana_tehsil.py`, this audit's own cross-reference | `scripts/build_subcontinent_data.py` (via `regenerate_location_data.py`'s orchestration), `scripts/dedupe_bawana_tehsil.py` (the one narrow, already-committed exception) |
| `static/data/india_districts_tehsils.json` | `app.py`, `elemental_core.py`-driven routes, this audit | `scripts/extract_india_districts_tehsils.py`'s logic as reimplemented inside `scripts/regenerate_location_data.py`'s `build_india_districts_tehsils()`, `scripts/dedupe_bawana_tehsil.py` |
| `india_villages` (SQLite) | `app.py` (`GET /api/india-villages/<tehsil_id>`), `app.py:5957-5989`'s boot check | `scripts/import_india_villages.py` (full `DELETE`+reimport), `scripts/regenerate_location_data.py` (orchestrates the same) |

No scheduled/background job (the four `BackgroundScheduler` instances this project runs) touches
any of these paths — all writes are developer-invoked scripts, never automatic.

## Consequences of this recommendation

- **What changes:** add `location_id_history` (SQLite) for future crosswalks; extract
  `scripts/dedupe_bawana_tehsil.py`'s safety pattern into a reusable helper for any future narrow
  correction; add a same-name-same-parent duplicate check to `scripts/regenerate_location_data.py`
  itself, so a future full regeneration from a corrected Master JSON fails loudly instead of
  silently reproducing a duplicate.
- **What stays generated:** `static/data/subcontinent_districts.json`,
  `static/data/india_districts_tehsils.json`, `india_villages` — unchanged, still rebuilt from
  Master JSON by the existing generator for a full refresh.
- **How location data would be authored and reviewed going forward:** unchanged by this
  recommendation, since the authoring process outside this repository is not something this pass
  can observe or redesign — **this is itself an open question for the owner** (where/how is
  `Qumanity_Master.json` actually edited today?), not resolved here.
- **How tests would prevent future duplicates:** `scripts/audit_all_india_duplicates.py` (this
  pass's own deliverable) can be added to the test suite as a one-off CI-style check: a non-zero
  duplicate-group count would fail the check, giving the project its first automated regression
  guard against this exact class of problem.
- **Staging without breaking registration:** none of the above requires a cutover — every change
  is additive (a new crosswalk table, a new check in an existing script) and can be built and
  tested independently of a live deployment.
- **Decisions requiring owner approval before any of this is built:** (1) confirming where/how
  `Qumanity_Master.json` is actually authored today, since that determines whether a duplicate
  check can be enforced *before* a bad edit ever reaches this repository, or only after; (2)
  approving the `location_id_history` schema; (3) approving which script gets the extracted safety
  helper first.
