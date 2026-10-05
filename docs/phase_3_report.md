# Lunar-cycle archival system — Phase 3 report: pipeline engine

Built 2026-10-05. Phases 1 (`lunar_calendar.py`) and 2 (`cycle_middleware.py`, `cycle_id` on 28
tables) are prerequisites, both unmodified by this phase. See `docs/lunar_cycle_system.md` /
`docs/phase_build_plan.md` for the overall design.

## Design question answered before coding: top contributors join

Confirmed option (a) — join `karma_entries.user_id` to `users` — is both correct and the only
sensible choice: `users.name` is `NOT NULL` for every row (schema-enforced), so the join can never
silently drop a contributor. No alternative needed.

## A correctness gap found and resolved before coding (not asked as open-ended — resolved with a
concrete recommendation, confirmed by you)

The spec's pipeline assumes every activity row starts at `pipeline_level='village'` and climbs a
fixed 8-hop ladder. But `board_core.chain_of()` already documents that not every location has
every tier (registration only strictly requires country + state), and `direct_villages`
(`register.js`/`app.py:1837`) means some districts in the other 9 Sub-continent countries have
villages with **no tehsil tier** at all. Checked against the real data: **100% of the 501 real
users are India-based with the full 5-tier chain today.** Per your decision, Phase 3 is scoped to
that case; a row whose chain doesn't resolve this way is excluded from any holding and counted as
`excluded_no_chain` in every transfer's result, rather than guessed at or silently misplaced. This
is 0 in every real run so far and will stay 0 until a non-full-chain user actually registers —
revisit then, not before.

## Deviations from the literal prompt (with reasons)

1. **`country_sentiment`/`zone_sentiment` default `pipeline_level` to `'country'`/`'zone'`, not
   `'village'`.** Per Decision 3, a sentiment vote is cast directly about a country or zone and
   was never "at village" — defaulting it to `'village'` would have been a silent correctness bug
   baked into every later aggregate (these rows would need to climb back DOWN before correctly
   climbing up, which `_ancestor_id` doesn't support by design). SQLite's `ALTER TABLE ADD COLUMN
   ... DEFAULT` backfills existing rows with the column's own default at ALTER time, so this is a
   one-line fix in migration 007, not a separate backfill pass.
2. **Parent ids are derived from the data, not a static hierarchy walk.** `get_child_level_ids()`
   is built exactly as specified (useful for admin display / Phase 4), but `transfer_level()`'s
   own aggregation does NOT call it to decide which parents to aggregate — it derives every
   ancestor id directly from the rows that actually exist this cycle (`_ancestor_counts()`). This
   means a holding is only ever created where real data exists, and (combined with India's
   dot-encoded location ids) collapses the "per-table location resolution" problem into one
   generic ancestor-id helper instead of 28 separate hierarchy walks.
3. **Every function takes `conn` as its first parameter**, matching every other `*_core.py`
   module's established convention (the prompt's sketch omitted it).
4. **`holdings_created` counts holdings upserted, not strictly new.** Decision 7 requires upserts
   (`ON CONFLICT` key `(level, level_id, cycle_id)`), so re-running an already-completed transfer
   re-upserts the same holding with unchanged data and still reports it in this count — the
   number to watch for idempotency is `records_moved` (0 on a genuine no-op re-run), not this one.

## What was built

- **`migrations/007_add_pipeline_level.sql`** — `pipeline_level VARCHAR(20)` + 2 indexes on all 28
  Phase-2 tables (default `'village'`, except `country_sentiment`→`'country'`,
  `zone_sentiment`→`'zone'`, per deviation 1 above).
- **`migrations/008_add_level_holdings.sql`**, **`009_add_transfer_log.sql`**,
  **`010_add_pipeline_state.sql`** — exactly the schemas given in the prompt.
- **`pipeline_core.py`** — `get_child_level_ids`, `aggregate_level`, `transfer_level`, the 7 named
  wrappers (`transfer_village_to_tehsil` … `transfer_continent_to_earth`),
  `transfer_earth_to_archive` (Phase 4 stub), `run_full_pipeline`,
  `get_eligible_cycles_for_pipeline`, the N/N-1 safety check, and the location-resolution layer
  (`_ancestor_id`, per-table resolvers for all 28 tables — direct columns where a table already
  has one, e.g. `board_posts.group_id`/`collective_karma_log.location_id`; a `users` join
  extracting `present_location_json` otherwise).
- **5 admin endpoints** in `app.py`, all `@login_required` + the same `_is_admin()` gate as every
  other admin route (`QM_ADMIN_PRIVATE_IDS` — confirmed no `role` column exists, matching the
  Phase 2.5 finding): `POST /api/admin/pipeline/transfer`, `POST /api/admin/pipeline/run-all`,
  `GET /api/admin/pipeline/status`, `GET /api/admin/pipeline/holdings/<level>/<level_id>`,
  `GET /api/admin/pipeline/eligible-cycles`.
- **`tools/verify_pipeline.py`** — builds its own isolated, synthetic DB in a temp directory
  (reusing `seed_admin_only._apply_schema()` so it's built exactly the way a real DB would be).
  This was necessary, not optional: the real local DB's entire Phase 2 backfill landed every row
  in the SAME current cycle (`Bhadrapada_2026`), so there is no real N-2-or-older cycle to test
  against yet. Seeds 3 synthetic cycles (oldest eligible, one N-1, one active N), 3 synthetic
  users in the real pilot village, and a handful of activity rows, then walks the full chain.

## A pre-existing test-script bug caught and fixed during verification (not a bug in the app)

An early draft of the manual API-testing script imported `seed_admin_only` (which transitively
imports `db.py` via `run_migrations`) **before** setting `QM_DB_PATH` in the environment —
`db.DB_PATH` is a module-level constant resolved once at first import, so every later
`get_db()` call silently operated against the real local DB instead of the intended test file.
Fixed by setting all env vars before any import that touches `db.py`. `tools/verify_pipeline.py`
itself was never affected — it uses a raw `sqlite3.connect()`, never `db.get_db()`, so it is fully
isolated by construction.

## Verification — local run, 2026-10-05

```
$ python3 tools/run_migrations.py
Applying 007_add_pipeline_level.sql... done.
Applying 008_add_level_holdings.sql... done.
Applying 009_add_transfer_log.sql... done.
Applying 010_add_pipeline_state.sql... done.
Applied 4 migration(s).

$ python3 tools/verify_pipeline.py
cycle_state: N=Jyeshtha_2026, N-1=Vaishakha_2026
Eligible cycles (N-2 and older): ['Chaitra_2026']

Hop                          Records Moved   Holdings Created   Excluded
---------------------------------------------------------------------------
village -> tehsil            9               1                  0
tehsil -> district           9               1                  0
district -> state            9               1                  0
state -> zone                9               1                  0
zone -> country              9               1                  0
country -> continent         9               1                  0
continent -> earth           9               1                  0

Total rows for Chaitra_2026: seeded 9, still present 9
Re-run continent -> earth: records_moved=0 (expect 0)

PASS: cycle_state identifies N/N-1 correctly
PASS: Chaitra_2026 is eligible, N/N-1 are not
PASS: Safety rule rejects N and N-1
PASS: Full chain village -> earth moves every row, none deleted
PASS: Total row count unchanged end to end (no deletes)
PASS: level_holdings has the expected tehsil row
PASS: Aggregate karma_entries count matches manual SQL count
PASS: Re-running continent->earth is idempotent (0 rows moved second time)
OVERALL: ALL CHECKS PASSED

$ python3 tools/verify_lunar_calendar.py   # Phase 1 -- still passes
OVERALL: ALL CHECKS PASSED

$ python3 tools/verify_cycle_stamping.py   # Phase 2 -- still passes
OVERALL: ALL CHECKS PASSED
```

**API endpoint samples** (against a separate throwaway synthetic DB, exercised via Flask's test
client, never the real DB):

```
GET /api/admin/pipeline/eligible-cycles  -> {"eligible_cycles": ["Chaitra_2026"]}

POST /api/admin/pipeline/transfer {"from_level":"village","cycle_id":"Chaitra_2026"}
  -> {"from_level":"village","to_level":"tehsil","cycle_id":"Chaitra_2026",
      "records_moved":1,"holdings_created":1,"excluded_no_chain":0}

POST /api/admin/pipeline/run-all {"cycle_id":"Chaitra_2026"}
  -> {"cycle_id":"Chaitra_2026","transfers":[... 7 hops, each completed ...]}

GET /api/admin/pipeline/status
  -> {"pipeline_state": {"last_transfer_level":"earth","last_transfer_cycle_id":"Chaitra_2026",...},
      "recent_transfers": [... last 20 transfer_log rows ...]}

GET /api/admin/pipeline/holdings/tehsil/CS.DL.3.4
  -> {"level":"tehsil","level_id":"CS.DL.3.4","holdings":[{"summary":{"counts":{"karma_entries":1,...},
      "totals":{...},"top_contributors":[...],"by_element":{...}}, "source_ids":["CS.DL.3.4.1A"], ...}]}

POST /api/admin/pipeline/transfer {"from_level":"village","cycle_id":"<active N>"}
  -> 400 {"error": "Cycle Jyeshtha_2026 is the ACTIVE cycle (N) -- never pipeline-eligible."}

GET /api/admin/pipeline/eligible-cycles  (non-admin session)
  -> 403 {"error": "Admin access required"}
```

## Verification checklist (from the prompt)

- [x] `pipeline_level` column added to the 28 activity tables
- [x] `level_holdings` + `transfer_log` + `pipeline_state` created
- [x] `transfer_village_to_tehsil` moves rows correctly
- [x] Full chain works village → continent (→ earth)
- [x] Raw records NOT deleted (only `pipeline_level` updated — row count unchanged end to end)
- [x] Safety rule enforced: N and N-1 untouched (rejected with `PermissionError` / HTTP 400)
- [x] Idempotency verified (0 rows moved on re-run)
- [x] Aggregates match manual SQL counts (`karma_entries` count cross-checked)
- [x] Phase 1 and Phase 2 verification suites still pass

## Known limitations — what Phase 4 will need to address

- **India-only scope** (see above) — a non-full-chain user's activity is excluded from holdings
  today (`excluded_no_chain`, currently always 0). Revisit once such a user actually registers.
- **`qoins_circulating`** is a current-balance snapshot (wallets have no `cycle_id`), not a
  per-cycle delta — documented in `pipeline_core._qoins_circulating`'s own docstring.
- **No real eligible cycle exists yet** in the live local/production DB (every row's Phase-2
  backfilled `cycle_id` landed in the current cycle) — the first REAL transfer won't have data to
  move until a cycle genuinely closes and ages past N-1, which won't happen until Phase 5's cron
  (or a manual `cycle_middleware.transition_to()`) actually advances `cycle_state` more than once.
- **Phase 4** needs to implement `transfer_earth_to_archive` for real (currently a stub) and
  decide how `level_holdings` rows at `earth` level map onto the `0_Earth` archive folder
  structure described in `docs/lunar_cycle_system.md`.

## Deployment to Railway (after your confirmation — not run)

```bash
railway volume files download /data/qumanity_prototype.db ./backup_pre_phase3.db
# push this code
railway run python3 tools/run_migrations.py
railway run python3 tools/verify_pipeline.py   # self-contained; safe to run against production too
```
