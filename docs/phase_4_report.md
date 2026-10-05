# Lunar-cycle archival system — Phase 4 report: archive writer

Built 2026-10-05. Phases 1–3 are prerequisites; per Safety Rule 4, nothing in `lunar_calendar.py`,
`cycle_middleware.py`, or `pipeline_core.py` changed except the single `transfer_earth_to_archive`
stub line. See `docs/lunar_cycle_system.md` / `docs/phase_3_report.md`.

## Question answered before coding: hard delete vs. soft delete

Proceeded with your recommendation (hard `DELETE`) — no objection. It matches the "archive is now
the source of truth" model used throughout this design, and keeping duplicate rows around for 8
cycles' worth of data would directly undermine the "keep the DB small" goal the whole pipeline
exists for.

## Real folder structure used (not the prompt's simplified sketch)

The prompt's Decision 1/3 sketch (`{village}/BORN_HERE/{element}/{user_id}/archives/...`) doesn't
match the REAL 0_Earth tree, which `folder_connector.py` already builds for every registration:
`Continents/<c>/Countries/<c>/Zones/<c>:<id>/States/.../Districts/.../Tehsils/.../Villages/<c>:<id>/`,
with users keyed by **Private ID** under `BORN_HERE` and **Account ID** under `LIVING_HERE` (never
the internal numeric `user_id`), each inside a `private_account/` subfolder alongside their
existing `profile.json`/`account_ids.json`/`change_requests/`. `archive_writer.py` reuses
`folder_connector.resolve_location_dir()` / `create_user_folder()` directly — the exact functions
every real registration already goes through — rather than inventing a parallel path scheme.

## Deviations from the prompt (with reasons)

1. **The file list was extended from 13 to 16 files, covering all 28 Phase-2 tables exactly
   once.** Decision 2's list had no home for 8 tables (`election_candidates`, `election_votes`,
   `collective_karma_log`, `business_ratings`, `account_ids`, `people_requests`,
   `account_id_requests`, `message_reactions`) — silently dropping them would violate Safety Rule
   1 ("never delete a raw record before its archive is written"). Added `elections.json`,
   `collective_karma.json`, `business_ratings.json`, `account_activity.json`; folded
   `message_reactions` into `messages.json`. See the schema table below for the final mapping.
2. **`sentiment.json` is written at the Country/Zone's OWN folder, never nested inside a
   village.** Per Phase 3's own Decision 3, `country_sentiment`/`zone_sentiment` were never
   "village data" — nesting them under some village would misrepresent where they actually live.
   `write_location_archive()` was generalized to handle any of the 8 pipeline levels, not just
   village, for exactly this reason.
3. **A genuine bug found and fixed by this phase's own test**: an early version of the
   location-resolution helper hardcoded `country: INDIA_COUNTRY_ID` for every call, including
   when archiving a sentiment vote cast about a *different* country (e.g. Nepal). That silently
   resolved two distinct archives (Nepal's country-level sentiment and India's own fallback zone
   archive) onto the *same physical folder*, and the second write clobbered the first before
   verification caught the checksum mismatch. Fixed, and a standing collision guard was added to
   `archive_cycle()`: if any two distinct `(level, location_id)` pairs ever resolve to the same
   directory again (possible if the real 0_Earth scaffold is incomplete anywhere), the whole
   archive attempt is refused rather than risking silent data loss.
4. **Decision 6's "archive exists + DB rows exist → mismatch" rule was refined to not fire on the
   expected dry-run-then-real-run sequence.** Taken literally, it would refuse Step 4 of your own
   verification checklist (dry run, then immediately a real run) — a dry run legitimately writes
   the same final folder, since there's no separate "draft" location, so "archive exists" is the
   *normal* state right after a dry run, not evidence of a crash. Fixed by stamping each
   `cycle_metadata.json` with its own `"dry_run": true/false`; the mismatch check now only fires
   when a **finalized** (`dry_run: false`) archive is found sitting next to raw rows that should
   have been deleted with it — the genuine "a previous real run crashed mid-way" signal.
5. **No new DB table for idempotency tracking.** Decision 6 is implemented against the filesystem
   (`cycle_metadata.json`'s `dry_run` flag) plus `transfer_log`/`level_holdings`, which Phase 3
   already persists and never deletes — `get_archived_villages()` derives "which villages were
   archived" from `level_holdings`'s own `source_ids` at tehsil level even in a brand-new process,
   long after the raw rows are gone. The prompt's deliverables list doesn't mention a Phase 4
   migration, and this avoids adding one unasked.
6. **The checksum excludes `cycle_metadata.json` itself** (computed over every other file, stored
   inside the metadata, then recomputed the same way on verify) — storing a file's own hash inside
   itself is circular; this is the standard resolution.

## File schema (final, stable)

| File | Tables |
|---|---|
| `posts.json` | `board_posts` |
| `votes.json` | `board_votes` |
| `comments.json` | `board_comments` |
| `messages.json` | `board_messages`, `personal_messages`, `private_messages`, `message_reactions` |
| `wallet_transactions.json` | `wallet_transactions` |
| `karma_entries.json` | `karma_entries` |
| `collective_karma.json` | `collective_karma_log` |
| `reviews.json` | `app_reviews` |
| `business_ratings.json` | `business_ratings` |
| `payment_orders.json` | `payment_orders` |
| `sentiment.json` | `country_sentiment`, `zone_sentiment` (Country/Zone folders only) |
| `group_activity.json` | `subgroups`, `personal_groups`, `private_chats`, `subgroup_members`, `personal_group_members` |
| `profile_changes.json` | `profile_change_requests` |
| `volunteers.json` | `volunteers`, `referrer_applications` |
| `elections.json` | `election_candidates`, `election_votes` |
| `account_activity.json` | `account_ids`, `account_id_requests`, `people_requests` |

Each file is a JSON array of the matching table's raw rows (as stored, column names unchanged —
light normalization only, not an exhaustive foreign-key resolution pass); a file with zero
matching rows for that location/user is simply not created (no empty arrays on disk). User
archives use the same files renamed `my_*.json` for the 7 personally-scoped ones (posts, votes,
comments, wallet_transactions, karma_entries, chat_messages, reviews) plus a `cycle_summary.json`
of personal totals; the rest keep their name (already personal-scoped by being filtered to one
user). `cycle_metadata.json` matches Decision 4 exactly, plus the `dry_run` flag from deviation 4.

## Verification — local run, 2026-10-05

Both scripts build their OWN isolated DB **and** fake 0_Earth scaffold under `/tmp` (env vars set
before any import that binds them — the same footgun documented in `docs/phase_3_report.md`);
neither ever touches the real local DB or the real 0_Earth tree.

```
$ python3 tools/verify_archive_writer.py
Seeded 22 activity rows, cycle_id=Chaitra_2026
Rows at pipeline_level='earth' after climbing: 22

Dry run result: {'status': 'dry_run_complete', 'locations': 3, 'users': 3, 'bytes': 12769}

File                           Exists   Valid    Records
------------------------------------------------------------
account_activity.json          ✓        ✓        2
collective_karma.json          ✓        ✓        1
comments.json                  ✓        ✓        1
cycle_metadata.json            ✓        ✓        -
group_activity.json            ✓        ✓        5
karma_entries.json             ✓        ✓        3
payment_orders.json            ✓        ✓        1
posts.json                     ✓        ✓        1
profile_changes.json           ✓        ✓        1
reviews.json                   ✓        ✓        1
volunteers.json                ✓        ✓        2
votes.json                     ✓        ✓        1
wallet_transactions.json       ✓        ✓        1

Real run result: {'status': 'archived', 'locations': 3, 'users': 3, 'bytes': 12769, 'records_deleted': 22}
Re-run result: {'status': 'already_archived', 'cycle_id': 'Chaitra_2026'}
archive_status(): {'archived': True, 'folder_count': 1, 'total_bytes': 8370, 'records_deleted': 22, 'checksum_match': True}

PASS: All seeded rows reached earth
PASS: Dry run writes files but does not delete
PASS: Every written file exists and is valid JSON
PASS: cycle_metadata.json has all 13 language display_names
PASS: checksum_sha256 matches recomputation
PASS: Raw records ARE deleted after the real run
PASS: records_deleted matches what was seeded
PASS: Backup SQL file was written before delete
PASS: Idempotency: re-run reports already_archived, no error
PASS: archive_status reports archived=True with a checksum match
OVERALL: ALL CHECKS PASSED

$ python3 tools/verify_lunar_calendar.py   # Phase 1 -- still passes
$ python3 tools/verify_cycle_stamping.py   # Phase 2 -- still passes
$ python3 tools/verify_pipeline.py          # Phase 3 -- still passes
OVERALL: ALL CHECKS PASSED  (x3)
```

**Sample archive folder tree** (one real run, village + 1 user, `ls -R`-equivalent):
```
0_Earth_test/.backups/pre_archive_Chaitra_2026.sql
0_Earth_test/Continents/0_AS/Countries/0_AS_IND/Zones/0_AS_IND:CS/States/0_AS_IND:CS.DL/
  Districts/0_AS_IND:CS.DL.3/Tehsils/0_AS_IND:CS.DL.3.4/Villages/0_AS_IND:CS.DL.3.4.1A/
    archives/Chaitra_Purnima-to-Vaishakha_Amavasya_2026/
      cycle_metadata.json  karma_entries.json  posts.json
    BORN_HERE/Fire/PRIV-0/private_account/archives/Chaitra_Purnima-to-Vaishakha_Amavasya_2026/
      cycle_metadata.json  cycle_summary.json  my_karma_entries.json  my_posts.json
    LIVING_HERE/Fire/ACC-0/private_account/archives/Chaitra_Purnima-to-Vaishakha_Amavasya_2026/
      cycle_metadata.json  cycle_summary.json  my_karma_entries.json  my_posts.json
```

**API response samples** (synthetic throwaway DB via Flask's test client):
```
POST /api/admin/pipeline/archive {"cycle_id":"Chaitra_2026","dry_run":true}
  -> {"status":"dry_run_complete","cycle_id":"Chaitra_2026","locations":3,"users":3,"bytes":12769}

GET /api/admin/pipeline/archive-status/Chaitra_2026
  -> {"cycle_id":"Chaitra_2026","archived":true,"folder_count":1,"total_bytes":8370,
      "records_deleted":22,"checksum_match":true}
```

## Known limitations — what Phase 5 will need to address

- Foreign-key normalization is light (column names unchanged, no exhaustive id→human-readable
  resolution pass beyond what each row already carries) — acceptable for now, flagged as a choice
  rather than an oversight.
- `write_user_archive`'s BORN_HERE/LIVING_HERE writes assume both locations are already
  India-scaffolded; a user whose birth or present location doesn't resolve to a real folder is
  skipped for that half (`born_here`/`living_here: None` in the result), matching
  `folder_connector.register_user_folder`'s own existing "soft failure" convention.
- No cron wiring (Phase 5) — every archive call is still a manual admin trigger.

## Deployment to Railway (after your confirmation — not run; no Railway command was executed)

```bash
railway volume files download /data/qumanity_prototype.db ./backup_pre_phase4.db
# push this code
railway run python3 tools/run_migrations.py          # no-op: Phase 4 adds no new migration
railway run python3 tools/verify_archive_writer.py    # self-contained; safe to run against production too
```
