# Railway boot-crash fix — DB initialization & Admin-only seed (2026-10-05)

## The crash

```
sqlite3.OperationalError: no such table: users
  File "app.py", line 2948, in <module>
    _ensure_user_columns()
  File "app.py", line 87, in _ensure_user_columns
    conn.execute("ALTER TABLE users ADD COLUMN daily_language TEXT")
```

The Railway Volume at `/data` has no DB file yet, so the very first thing module-level startup
code did — `_ensure_user_columns()` — tried to `ALTER` a `users` table that was never created.
`db/schema.sql` (which defines `users`) is normally applied once, by hand, via `db/init_db.py` —
nothing ever ran that on the Volume.

## What was verified before writing anything

- Confirmed the crash's exact line numbers against the real, current `app.py` — they matched,
  confirming this is a real, current crash, not stale.
- Confirmed Phase 2 (`25a23a4`) really is committed and pushed — `git log` matches the prompt's
  claim.
- Confirmed `app.py` has no `logger` object anywhere (the prompt's sketch code assumed one) —
  the codebase's own convention for startup logging is plain `print()` (see
  `_run_scheduled_sync`, `_validate_india_location_data`), so the fix matches that instead of
  introducing a new logging setup.
- Confirmed there is **no `role` column anywhere** in `users` — admin-ness is controlled purely by
  the `QM_ADMIN_PRIVATE_IDS` env var matching `private_id_9digit` (`_is_admin()`'s own docstring
  says so explicitly). The seed script does **not** set `role = 'founder'` as the original prompt
  sketched — that column doesn't exist and shouldn't be invented for this fix.
- Confirmed the Admin's real `private_id` in the local DB is
  `PD5-RM-GMA2-ZFL-CS.DL.7.14.12` — **not** `FIM-RM-GMA2-ZFL-CS.DL.1.A.12` as stated in the
  prompt's context. Rather than hand-typing a (wrong) private_id into a new seed row, the seed
  script copies the Admin's real, already-correct row instead — see "Design change" below.

## Design change from the original prompt: copy, don't regenerate, the Admin row

The prompt's sketch for `tools/seed_admin_only.py` was to re-run the full registration pipeline
(zodiac calculation, kundali generation, `id_generator`) to construct a new Admin row from
scratch. That's riskier than it needs to be: `id_generator` and the zodiac/kundali computation are
not guaranteed to reproduce the exact same `private_id_9digit` (`014918240`) a second time, and
there is already a real, fully-correct Admin row sitting in the local DB (user id 24, "Rohit
Mudgal") with real `user_zodiac` / `user_elemental_profile` / `account_ids` / `wallets` rows
already attached.

So `tools/seed_admin_only.py` instead **copies** that real row (and its four dependent rows) out
of an existing source DB into a freshly-schema'd target DB. This guarantees byte-for-byte fidelity
with the real account — same `private_id_9digit`, same `pin_hash` (no PIN re-entry or re-hashing
needed at all), same zodiac/kundali data, same wallet balance — with zero risk of drift.
`wallet_transactions` (the Admin's history) is deliberately **not** copied, to keep the seed
minimal; the wallet's current balance (copied) is enough for the app to function correctly.

## Fix 1 — `ensure_database_ready()` (app.py)

Applies the **full** schema unconditionally, before anything else touches the DB:
`db/schema.sql` → zodiac reference-data seed → `founder_core`/`visibility_core`/`recovery_core`'s
own tables → every other `*_core` module's tables + the Phase 2 lunar-cycle migrations (via
`tools/run_migrations.py`, reused as-is) → the `social_core` data-normalization passes →
`election_core.ensure_history_table`. Every one of these is already idempotent
("CREATE TABLE IF NOT EXISTS" / a tracked migration), so running this unconditionally is exactly
as safe against the long-lived local/production DB as against an empty file — there is no
"is this DB fresh?" branch to get wrong. Called first, before `_ensure_user_columns()`.

**A second, genuinely pre-existing latent bug was found while testing this against a truly empty
DB** (not something Phase 2 introduced): `board_core.ensure_tables()` checks `subgroups`'s columns,
but `subgroups` is only created by the separate `ensure_sub_tables()` — this only ever "worked"
because every real DB already had `subgroups` from months of prior use. Fixed by having
`ensure_tables()` call `ensure_sub_tables()` first, so it's self-sufficient regardless of call
order or how old the DB is.

## Fix 2 — defensive `_ensure_user_columns()` (app.py)

Checks `users` exists before touching it; if `ensure_database_ready()` somehow didn't run first,
this logs and returns instead of crashing. Defense in depth, not the actual fix (Fix 1 is).

## Fix 3 — `tools/seed_admin_only.py`

```
python3 tools/seed_admin_only.py --db-path ./admin_only.db
```
Builds the full schema into a fresh file (reusing the exact same functions `ensure_database_ready()`
uses, so it can never drift out of sync with the real schema), then copies the real Admin row
(`private_id_9digit=014918240` by default, `--private-id` to override) and its `user_zodiac` /
`user_elemental_profile` / `account_ids` / `wallets` rows from `--source-db` (default: the local
dev DB). Refuses to overwrite an existing `--db-path` unless `--force` is passed.

## Fix 4 — `GET /healthz` (app.py)

Unauthenticated (matches the purpose — a platform healthcheck and a way to see live DB state
without shell access to the Volume). Reports `status`, `db_path`, `db_exists`, `has_users_table`,
and `user_count` — no other user data.

## Verification — all run locally, 2026-10-05

**The exact crash scenario, reproduced and fixed** (brand-new, nonexistent DB file):
```
$ rm -rf /tmp/fresh_boot_test && mkdir -p /tmp/fresh_boot_test
$ QM_DB_PATH=/tmp/fresh_boot_test/qumanity_prototype.db QM_SECRET_KEY='test-key' python3 -c "import app"
Applying 001_add_cycle_state.sql... done.
Applying 002_add_cycle_id_to_activity_tables.sql... done.
Applying 003_backfill_cycle_ids.py... Backfill complete -- 0 row(s) across 28 table(s). done.
Applied 3 migration(s).
[boot] database ready at /tmp/fresh_boot_test/qumanity_prototype.db
IMPORT SUCCEEDED, no crash
healthz: 200 {'db_exists': True, 'has_users_table': True, 'status': 'ok', 'user_count': 0}
```

**The other named crash case** (a DB file that exists but is empty — `touch`'d, zero tables):
same result, `status: ok`, `user_count: 0`.

**Backward compatibility** (the real, 501-user local DB, months of history):
```
$ python3 -c "import app"
No pending migrations.
[boot] database ready at <local default: qumanity_prototype.db>
OK, existing local DB still boots clean
```

**The seed script:**
```
$ python3 tools/seed_admin_only.py --db-path /tmp/admin_only_test.db
Seeded 1 user ('Rohit Mudgal', private_id_9digit=014918240), 1 zodiac row, 1 elemental profile row,
1 account_id row, 1 wallet row, 39 zodiac/nakshatra reference rows -- no demo users.
Admin-only DB ready at /tmp/admin_only_test.db

$ sqlite3 /tmp/admin_only_test.db "SELECT private_id_9digit, name FROM users;"
014918240|Rohit Mudgal
```
(No `role` column exists in this schema — see "What was verified" above — so this differs from the
originally-expected `014918240|founder` output; admin access on Railway is, and remains, controlled
by `QM_ADMIN_PRIVATE_IDS`, not a stored role.)

**Booting the real app against that Admin-only DB:**
```
$ QM_DB_PATH=/tmp/admin_only_boot_test.db QM_SECRET_KEY='test-key' python3 -c "import app; ..."
No pending migrations.
[boot] database ready at /tmp/admin_only_boot_test.db
healthz: 200 {'db_exists': True, 'has_users_table': True, 'status': 'ok', 'user_count': 1}
```
A join across `users`/`user_zodiac`/`user_elemental_profile`/`account_ids`/`wallets` for that row
confirmed every dependent field came through intact (sun_sign, moon_sign, dominant_element,
account_id/search_code, wallet balance) — the dashboard has what it needs to render without
crashing on missing related data.

**Existing suites re-run clean after these changes**: `tools/verify_cycle_stamping.py` (Phase 2)
and `tools/verify_lunar_calendar.py` (Phase 1) both still report `ALL CHECKS PASSED`.

## Constraints honored

No existing table's schema changed (additive only); the local DB was never touched directly by
testing (all crash-scenario tests ran against throwaway files in `/tmp`); `lunar_calendar.py` and
`cycle_middleware.py` are unmodified; the one logic change outside app.py/tools (the
`board_core.ensure_tables()` ordering fix) is additive/ordering-only, not a schema change.
