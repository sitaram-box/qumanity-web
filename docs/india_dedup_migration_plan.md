# India Location Duplicate Deduplication: Migration Plan

**AWAITING APPROVAL — DO NOT EXECUTE.**

This is a future migration plan, not executable code. Nothing in this document has been run
against `Qumanity_Master.json`, the derived JSON files, or the live database beyond the read-only
queries shown, which were actually executed (read-only, against `qumanity_prototype.db?mode=ro`)
to ground this plan in real evidence rather than hypothetical examples.

Source: `scripts/audit_all_india_duplicates.py`'s real run, 2026-11-01/02 (74 Tehsil-level duplicate
groups, 15 Village-level, 0 State/District-level, nationally — see
`docs/india_duplicate_audit_2026-11-01.csv` and `docs/india_location_integrity_report.md`).

## 3.1 Evidence-based survivor selection

Two real, representative cases from the actual audit — one already resolved, one genuinely open —
rather than fabricated examples.

### Case A (resolved): Bawana, North West Delhi (`CS.DL.3.4` vs `CS.DL.3.E`)

Already corrected in commit `211480c` (`CS.DL.3.E` removed from the two derived JSON files only;
`Qumanity_Master.json` still has both, since that file was explicitly off-limits for that task).
Re-confirmed this pass with a fresh read-only query:

- `CS.DL.3.4`: referenced by 500 demo users + 16 real, eligible users (via
  `present_location_json`/`birth_location_json`).
- `CS.DL.3.E`: referenced by **zero** users, demo or real.
- Children: `CS.DL.3.4` has 33 villages with clean names; `CS.DL.3.E` has 40, mostly
  differently-formatted duplicates of the same real places (see the earlier Bawana report for the
  detailed village-name comparison).

**Evidence is sufficient here**: `CS.DL.3.4` is clearly the survivor (real, heavy, zero-conflict
usage); `CS.DL.3.E` is clearly the retired duplicate (zero usage anywhere). This case needed no
further decision — it is included here only to show what a *clean* case looks like, contrasted
with Case B.

### Case B (open, NOT resolved): "Tri Nagar," Chandni Chowk (`CS.DL.7.4` vs `CS.DL.7.14`)

A **genuinely unresolved** case, found by this pass's national audit:

- `CS.DL.7.4` ("Tri Nagar," 12 villages) — referenced by user id 765 (`is_demo=0`,
  `is_removed=0`) as their **present** location.
- `CS.DL.7.14` ("Tri Nagar," 23 villages) — referenced by user id 24 (`is_demo=0`,
  `is_removed=0`) as their **birth** location. (User 24 is the account on file as the
  repository's own git committer identity for this project — reported here only as a factual
  database fact relevant to the audit, not as personal commentary.)
- Child overlap: **0 of 35** combined village names match between the two (12 vs. 23, completely
  disjoint) — unlike Bawana's near-duplicate villages, these two "Tri Nagar" records' own
  children don't even look like the same underlying data twice.

**Evidence is NOT sufficient to select a survivor here, and this plan does not select one.** Both
sides have a real, current, eligible user reference; their child sets are completely disjoint
(so this doesn't even look like Bawana's "same place imported twice" pattern — it could equally be
two genuinely different real localities that happen to share a name, which is exactly the
scenario this whole audit's own duplicate *definition* is designed to protect against merging).
**This is reported as an open question for the owner, not resolved by guessing.** The same caution
applies to the other 72 Tehsil-level and 15 Village-level groups this pass did not individually
re-audit for user references — see §3.3's query, which must be run per-group before any of them
is touched.

### The general rule this plan follows (not just for these two cases)

1. Query every table in §3.2 for references to every ID in the group.
2. If exactly one member has real (demo-excluded) references and the others have none, and the
   evidence otherwise doesn't contradict it (as Bawana's village-quality comparison didn't), that
   member is the candidate survivor.
3. If **more than one** member has real references, or **zero** members have children that
   overlap in a way that suggests "same place, reimported" — **stop. Do not select a survivor.**
   Report the ambiguity for a human decision. Existing user references are evidence of *identity
   usage*, never proof of *administrative correctness* — a popular wrong ID is still wrong, and a
   quiet correct one is still correct; this plan does not let reference-count alone override that
   distinction.

## 3.2 Complete live database schema inventory (read-only, re-verified this pass)

Queried directly against `qumanity_prototype.db` via `sqlite3.connect(..., mode=ro)` and
`PRAGMA table_info()` across all 86 real application tables (not assumed from the task's own
starting list — every column name below was found by scanning every table, not by checking only
the columns the starting list named):

| Table.Column | Type | Current rows (non-null) | Shape | Application use |
|---|---|---|---|---|
| `users.present_location_json` | TEXT | many (536 users total) | nested JSON (`.state`/`.district`/`.tehsil`/`.village`, each `{id, name}`) | The member's own declared residence; read by every location-aware feature |
| `users.birth_location_json` | TEXT | many | same nested JSON shape | Birth location for Kundali/zodiac; also location-tier Qoin credit at registration |
| `account_ids.present_location_json` | TEXT | mirrors `users` (denormalized copy per Account ID history row) | same shape | Historical snapshot per past Account ID — confirmed this pass (Bawana investigation) to sometimes carry a **denormalized full `district.tehsils[]` list** as cached metadata, which a naive substring search over-matches; any future reference audit must check the structured `.tehsil.id`/`.village.id` fields specifically, never a raw substring search |
| `account_id_requests.present_location_json` | TEXT | 0 | same shape | Pending Account ID change/recovery requests — currently empty in this database |
| `qpunch_addresses.location_id` | TEXT | 0 | plain dotted ID string | Q-Punch council address, one per location once it qualifies |
| `qpunch_queue_messages.location_id` | TEXT | 0 | plain dotted ID string | Messages sent to a Q-Punch address |
| `announcements.location_id` / `.location_level` | TEXT | 0 | id + an explicit level string (`village`\|`tehsil`\|...\|`earth`) | Council announcement scope |
| `collective_karma.location_id` / `.location_level` | TEXT | 0 | id + level | Collective karma score per location |
| `collective_karma_log.location_id` / `.location_level` | TEXT | 0 | id + level | Karma change log |
| `election_cycles.village_id` | TEXT | 2 (both `CS.DL.3.4.1A`) | plain dotted ID | The Rohini Sector 24 pilot village's election cycle rows |
| `location_elements.location_id` / `.location_type` | TEXT | 17 | id + level, multiple levels present (`AS`, `CS.DL`, `CS.DL.3`, ...) | Elemental/zodiac demographic aggregates per location |
| `profile_change_requests.location_id` / `.location_level` | TEXT | 3 rows, 0 non-null `location_id` | id + level | Pending profile-change requests — none currently reference a location |
| `recognition_stars.location_id` | TEXT | 1 (`CS.DL.3.4.1A`) | plain dotted ID | A recognition star awarded at the pilot village |
| `reports.location_id` / `.location_level` | TEXT | 0 | id + level | Citizen Reports |
| `subgroups.village_id` | TEXT | 0 | plain dotted ID | Collective Board village sub-groups |
| `village_council.village_id` | TEXT | 1 (`CS.DL.3.4.1A`) | plain dotted ID | The pilot village's council row |
| `zone_sentiment.zone_id` / `zone_sentiment_stats.zone_id` | TEXT | 0 | plain ID | Perception voting, zone-level |
| `india_villages.tehsil_id` | TEXT | 721,237 rows (635,693 India + others) | plain dotted ID | Village lookup table for the registration dropdown |
| `admin_export_log.location_id` | TEXT | 0 | plain dotted ID | Admin Panel export audit log |
| `provisional_location_core` tables (`provisional_locations.parent_verified_tehsil_id`/`parent_verified_state_id`, etc.) | TEXT | (not yet in production use — MVP not yet live-tested with real traffic) | plain dotted ID, or never a verified ID at all for a fully-provisional parent | New since the Crowdsourced Location MVP (commit `211480c`); any merge must also check these, since a provisional location can be anchored to a verified parent ID that might later be retired |

**Malformed/unparseable JSON**: re-confirmed this pass (same check as the Bawana audit): **zero**
malformed `present_location_json`/`birth_location_json` rows across all 536 users.

**Tables found NOT to currently hold any non-null location reference** (confirmed empty this
pass, but structurally capable, so still listed for any future re-check): `qpunch_addresses`,
`qpunch_queue_messages`, `announcements`, `collective_karma`, `collective_karma_log`,
`profile_change_requests`, `reports`, `subgroups`, `zone_sentiment`, `admin_export_log`. Being
empty *today* is a database-state fact, not a schema guarantee — any future migration must still
re-run the check in §3.3 against the live data at the time it runs, not rely on this snapshot.

## 3.3 Exact read-only audit queries for every reference

Run once per candidate duplicate-group member ID, before any merge of that group:

```sql
-- users / account_ids (structured check, NOT a substring search -- see the denormalization
-- caveat above; this must be done in Python after json.loads(), checking only the top-level
-- .state/.district/.tehsil/.village keys' own .id field, exactly as
-- scripts/dedupe_bawana_tehsil.py's audit_real_user_references() already does)
SELECT id, present_location_json, birth_location_json, is_demo, is_removed FROM users;
SELECT user_id, present_location_json FROM account_ids;

-- plain dotted-ID columns (safe to query directly -- no JSON parsing needed)
SELECT COUNT(*) FROM qpunch_addresses WHERE location_id = ?;
SELECT COUNT(*) FROM qpunch_queue_messages WHERE location_id = ?;
SELECT COUNT(*) FROM announcements WHERE location_id = ?;
SELECT COUNT(*) FROM collective_karma WHERE location_id = ?;
SELECT COUNT(*) FROM collective_karma_log WHERE location_id = ?;
SELECT COUNT(*) FROM election_cycles WHERE village_id = ?;
SELECT COUNT(*) FROM location_elements WHERE location_id = ?;
SELECT COUNT(*) FROM profile_change_requests WHERE location_id = ?;
SELECT COUNT(*) FROM recognition_stars WHERE location_id = ?;
SELECT COUNT(*) FROM reports WHERE location_id = ?;
SELECT COUNT(*) FROM subgroups WHERE village_id = ?;
SELECT COUNT(*) FROM village_council WHERE village_id = ?;
SELECT COUNT(*) FROM zone_sentiment WHERE zone_id = ?;
SELECT COUNT(*) FROM zone_sentiment_stats WHERE zone_id = ?;
SELECT COUNT(*) FROM admin_export_log WHERE location_id = ?;
SELECT COUNT(*) FROM india_villages WHERE tehsil_id = ?;  -- Tehsil-level groups only
SELECT COUNT(*) FROM provisional_locations WHERE parent_verified_tehsil_id = ? OR parent_verified_state_id = ?;
```

Every query above is a `SELECT` only. For the eligible/ineligible split (`users`/`account_ids`),
filter by `is_demo = 0 AND is_removed = 0` for "eligible," everything else "ineligible" — the same
split the Bawana audit used, re-verified this pass against the actual `users` schema (both columns
still exist, same meaning).

## 3.4 Exact future migration sequence (described, not written)

Conceptually, reusing `scripts/dedupe_bawana_tehsil.py`'s already-proven safety pattern:

1. Read-only preflight audit (§3.3) of all references and children for the group.
2. Verify the proposed survivor against §3.1's rule — refuse if ambiguous.
3. Safety gate: block if any eligible reference exists on the non-survivor side(s), exactly as
   Bawana's own gate did (zero tolerance, not a threshold).
4. Byte-for-byte backup of every file/artifact about to change, SHA-256-verified.
5. Build the full crosswalk (retired id → surviving id) for this group — this is new relative to
   the Bawana script, which had no children needing reassignment; see §3.5 for why it matters here.
6. Reconcile children: for each child of the retired record, decide (per §3.5) whether it merges
   into the survivor, is held as a flagged orphan, or blocks the migration.
7. Update every table in §3.2 that has a real reference, rewriting the retired id to the
   survivor's id — never deleting a user's own location identity, only repointing it.
8. Remove the retired parent record itself, only after steps 6-7 are complete and verified empty
   of references.
9. Validate: re-run §3.3's queries and confirm zero remaining references to the retired id
   anywhere; re-run `scripts/audit_all_india_duplicates.py` and confirm the group no longer
   appears.
10. Commit the SQLite changes transactionally (`BEGIN`/`COMMIT`); write the JSON changes via
    temp-file-then-atomic-replace, exactly as the Bawana script already does.
11. Verify idempotency: running the whole script again against the now-migrated data is a no-op.
12. Keep an auditable migration log (which ids, which tables, how many rows touched, timestamp) —
    not an ad hoc print statement, a real log file this can be reviewed from afterward.

Order matters: children and references are reconciled (steps 6-7) **before** the retired parent
is removed (step 8) — reversing this would orphan references mid-migration.

## 3.5 Decision rule for partially overlapping child sets

Bawana's own 33-vs-40-village split (4 overlaps by exact name, several more by near-identical
spelling) is the original open question; Tri Nagar's 0-of-35 split is a second, starker instance
of the same general problem. Proposed rule, never fully automatic:

- **Exact normalized name match, same expected locality context** → safe to treat as the same
  real place; the retired record's child is dropped (its own id retired too, via the same
  crosswalk), the survivor's matching child is kept.
- **Same name, materially different metadata** (e.g. different recorded village-level
  demographic/election data, if any exists for it) → do not silently merge; flag for manual
  review, hold both ids in the crosswalk pointing at a single human-reviewed decision.
- **Different but plausibly-the-same name** (a spelling/suffix/transliteration variant, e.g.
  Bawana's "Auchandi" vs. "Auchandi Village") → **never auto-merged** under this audit's own
  duplicate definition (no fuzzy matching permitted) — held as a separately-flagged, lower-
  confidence pairing for human review, never collapsed automatically no matter how obvious it
  looks to a reader.
- **A child unique to the retired record, with no plausible match on the survivor's side** (most
  of Bawana's 40 and essentially all of Tri Nagar's 23) → **not discarded.** Reparented onto the
  survivor as a *new, distinct* child (keeping its own identity, just moving its parent pointer),
  unless it has its own real user/operational reference, in which case it blocks the migration
  until a human confirms the reparent is correct.
- **A child unique to the retired record WITH its own real user/operational reference** → this
  alone blocks removing the parent record at all, regardless of the parent-level survivor
  decision, until that specific child's own fate is separately resolved.

This rule deliberately never deletes a child outright — every child of a retired record either
merges, reparents, or blocks; none simply disappear.

## 3.6 Explicit approval gates

Before any of this is implemented, the owner must approve:

- The architecture decision in `docs/location_architecture_decision.md` (Master JSON stays
  canonical; a crosswalk table and a shared safety-script helper get built).
- The duplicate definition itself (unchanged from this audit: exact name after trim+lowercase
  only, same immediate parent, applied per category level) — and confirmation that fuzzy/
  transliteration matching is never introduced later without a separate, explicit decision.
- Survivor selection for each of the 74 Tehsil-level and 15 Village-level groups — Case A
  (Bawana) is done; **Case B (Tri Nagar) and every other group need an explicit per-case decision**,
  not a blanket rule, given the real evidence that user references can exist on more than one
  side.
- The partial-overlap child-handling rule in §3.5.
- The crosswalk table's schema (`location_id_history` or similar, per the architecture decision).
- Backup/rollback and idempotency requirements (already proven out by
  `scripts/dedupe_bawana_tehsil.py`; the future script must meet the same bar).
- A testing and rollout plan before touching anything beyond the already-corrected Bawana pair.

**AWAITING APPROVAL — DO NOT EXECUTE.**
