# Lunar-cycle archival system — Phase 2 report: cycle ID stamping & active cycle tracking

Built 2026-10-05. Phase 1 (`lunar_calendar.py`, unmodified) is a prerequisite — see
`docs/lunar_cycle_system.md` / `docs/phase_build_plan.md`. This phase adds no pipeline, no
transfers, no archive writes, and touches no `0_Earth` file — it only records *which lunar cycle*
every new "ongoing activity" row happened in, so Phase 3+ has that data to work with later.

## 1. Which tables got `cycle_id`, and why

A read-only schema-mapping pass (52 tables total) classified every table into (a) ongoing
activity, (b) permanent identity/config, or (c) aggregate/frozen stats, then the Founder resolved
every genuinely ambiguous case explicitly before any migration was written. Final list — **28
tables**:

**From the Founder's own named examples** (`wallet_transactions`, `karma_entries`,
`collective_karma_log`, `business_ratings`, `board_posts`, `board_votes`, `board_comments`,
`board_messages`, `personal_messages`, `private_messages`, `account_ids`, `people_requests`,
`account_id_requests`, `payment_orders`, `country_sentiment`, `zone_sentiment`, `app_reviews`,
`profile_change_requests` ("change_requests"), `election_candidates`/`election_votes`
("council_candidates"/"council_votes")) — 19 tables.

**Resolved by the Founder's own explicit exclusions**, not asked about: `election_cycles`,
`referrers` ("user_roles"), `village_council` ("council_members") are all excluded.

**Asked, then confirmed on review** (3 `AskUserQuestion` rounds):
- Upsert-pattern "latest state" tables (`volunteers`, `message_reactions`,
  `referrer_applications`) — **included**, matching the already-decided `board_votes` precedent.
- Security/account-infra tables (`otp_requests`, `id_recovery_requests`, `id_recovery_reveals`,
  `user_onboarding`, `chat_read_state`, `election_history_entries`, `referrers`) — **excluded**:
  auth/recovery/role/profile-flag records, not civic-social-financial activity.
- Group/container tables (`subgroups`, `personal_groups`, `private_chats`, `subgroup_members`,
  `personal_group_members`) — **included** (changed from the initial recommendation to exclude,
  on the Founder's explicit instruction mid-review).

Full table → owning module → insert-site map is in the schema-mapping research this phase started
from; every confirmed insert site is listed in section 3 below.

## 2. Design decisions locked in

- **What value goes into `cycle_id`**: always the result of `cycle_middleware.get_active_cycle_id()`
  at the moment of the write — never computed from the row's own timestamp at write time (that
  computation only happens once, during the Phase 2 backfill, for rows that pre-date this change).
- **`cycle_state`**: a small history table, not a single mutable row — every past "active" cycle
  stays as a `status='closed'` row with its own `activated_at`/`closed_at`. Exactly one row is
  `status='active'` at any time. This is a richer design than a bare "current cycle" singleton
  because Phase 3's pipeline will eventually need to know N-1/N-2 relative to *when* each cycle was
  active, not just what's active right now.
- **Bootstrapping**: `cycle_middleware.get_active_cycle_row()` self-seeds `cycle_state` from
  `lunar_calendar.get_current_cycle_id()` the very first time anything asks — no separate manual
  "activate the first cycle" step was needed. Year-1-bootstrap counting and automatic cycle
  transitions are explicitly **not** this phase's job (per the Founder's own phasing — Phase 5's
  cron is what will eventually call `cycle_middleware.transition_to()` automatically; for now it's
  manual-only, via the new admin endpoint).
- **Backfill rule for pre-existing rows**: compute `cycle_id` from the row's own write timestamp
  via `lunar_calendar.get_current_cycle_id(that_timestamp)`. For the one table with no timestamp
  column at all (`board_votes`), or any row whose timestamp doesn't parse, fall back to whatever
  cycle is active at the moment the backfill runs.
- **Timestamp format inconsistency**, discovered during the schema mapping and handled in the
  backfill: `wallet_transactions.created_at` / `election_candidates.created_at` /
  `election_votes.voted_at` are SQLite's own `DEFAULT CURRENT_TIMESTAMP` (`"YYYY-MM-DD HH:MM:SS"`,
  naive UTC); every other table's `created_at`/`voted_at`-equivalent is this app's own
  `_now()`-style `isoformat()` (`"YYYY-MM-DDTHH:MM:SS+00:00"`, timezone-aware). The backfill
  parses both.
- **The N-2 safety rule (only cycle N-2 and older are ever pipeline-eligible) is explicitly not
  enforced anywhere in this phase** — there is no pipeline yet to enforce it against. This phase
  only records which cycle a row belongs to; Phase 3 is what will read that column.

## 3. What was built

- **`migrations/001_add_cycle_state.sql`** — the `cycle_state` table + 2 indexes
  (`idx_cycle_state_status`, `idx_cycle_state_activated_at`).
- **`migrations/002_add_cycle_id_to_activity_tables.sql`** — `ALTER TABLE ... ADD COLUMN cycle_id
  VARCHAR(50)` + one index per table, for all 28 tables above.
- **`migrations/003_backfill_cycle_ids.py`** — fills `cycle_id` on every pre-existing row per the
  backfill rule above. Additive only; no row is deleted, no other column changes.
- **`tools/run_migrations.py`** — idempotent runner, tracks applied migrations in its own
  `migrations` table. Pre-creates any lazily-created source table first (via each module's own
  `ensure_tables()`/`ensure_sub_tables()`/etc, matching the codebase's existing convention) so
  migration 002's `ALTER TABLE` statements always find a real table underneath. A half-applied
  `.sql` file is re-runnable: "duplicate column name" / "already exists" errors are treated as
  already-applied and skipped statement-by-statement, not fatal.
- **`cycle_middleware.py`** — `ensure_tables()`, `get_active_cycle_id()` /
  `get_active_cycle_row()` (self-seeding), `transition_to()` (manual cycle advance, closes the old
  active row, activates the new one), `history()`, and the `STAMPED_TABLES` map (table → timestamp
  column, or `None`) that the backfill reads.
- **Every real insert site now stamps `cycle_id`**, across `wallet_core.py`, `karma_core.py`,
  `board_core.py` (6 sites — `board_posts`, `board_votes`, `board_comments`, `board_messages`,
  `subgroups`, `subgroup_members`, `volunteers`, `referrer_applications`), `social_core.py` (10
  sites — `account_ids` ×2, `personal_groups`, `personal_messages`, `people_requests` ×3,
  `private_chats`, `private_messages` ×2, `personal_group_members`, `account_id_requests`),
  `perception_core.py`, `review_core.py`, `payment_core.py`, `election_core.py` (3 sites —
  `nominate`, `auto_nominate`, `cast_vote`), `reactions_core.py`, and `app.py`
  (`api_dashboard_edit_request`). Two existing sites in `board_core.py`
  (`subgroup_members`/`volunteers`) used a bare, column-less `INSERT ... VALUES (?,?,?,?)` that
  positionally assumed the table's exact old column count — adding `cycle_id` would have silently
  broken both without converting them to named columns first, which this pass did.
- **Three new admin endpoints** in `app.py`, same `_is_admin()` gating as every existing admin
  route: `GET /api/admin/lunar/cycle-state` (current active row, self-seeding), `POST
  /api/admin/lunar/cycle-state/transition` (manual advance — body `{}` advances to whatever
  `lunar_calendar` says is live right now, or `{"cycle_id": "..."}` for a specific one), `GET
  /api/admin/lunar/cycle-state/status` (full history + whether `cycle_state` has drifted behind
  the live calendar — expected during bootstrap, since nothing transitions it automatically yet).
- **`tools/verify_cycle_stamping.py`** — 4 checks: `cycle_state` has exactly one active row
  matching `lunar_calendar`'s live computation; all 28 tables have the column; zero pre-existing
  rows are missing `cycle_id`; a live round-trip through the real `karma_core`/`wallet_core`
  functions, run against a disposable temp copy of the DB (never the real one), confirms new rows
  come out stamped.

## 4. Verification — local run, 2026-10-05

```
$ python3 tools/run_migrations.py
Applying 001_add_cycle_state.sql... done.
Applying 002_add_cycle_id_to_activity_tables.sql... done.
Applying 003_backfill_cycle_ids.py...
  wallet_transactions: backfilled 408 row(s)
  election_candidates: backfilled 6 row(s)
  board_posts: backfilled 3 row(s)
  board_votes: backfilled 3 row(s)
  personal_messages: backfilled 1 row(s)
  account_ids: backfilled 502 row(s)
  app_reviews: backfilled 1 row(s)
  personal_groups: backfilled 4 row(s)
  (every other table: 0 rows — none had existing data)
Backfill complete -- 928 row(s) across 28 table(s).
  done.
Applied 1 migration(s).

$ python3 tools/run_migrations.py        # re-run: idempotency check
No pending migrations.

$ python3 tools/verify_cycle_stamping.py
PASS: cycle_state has exactly one active row (Bhadrapada_2026), matching lunar_calendar's live cycle (Bhadrapada_2026)
PASS: all 28 tables have a cycle_id column
PASS: no pre-existing rows missing cycle_id (found 0)
PASS: live writes through karma_core/wallet_core stamp cycle_id='Bhadrapada_2026' (temp copy, never the real DB)
OVERALL: ALL CHECKS PASSED
```

The three new admin endpoints were also exercised directly via Flask's test client (temporary
admin grant, reverted after): `GET /api/admin/lunar/cycle-state` → 200 with the active row; `GET
/api/admin/lunar/cycle-state/status` → 200 with `"in_sync": true`; `POST
.../transition` with an empty body → 200, same cycle, no duplicate row created; a non-admin
session → 403 on all three. A separate manual test (on a throwaway temp copy of the DB, not
touching the real one) confirmed `transition_to()` correctly closes the old active row and
activates a new one, and that transitioning back reopens the original row rather than creating a
third one.

The real local DB (`qumanity_prototype.db`) was backed up to `/tmp/qumanity_prototype_pre_phase2_backup.db`
before any migration ran.

## 5. Deploying to Railway

```bash
# 1. Back up the production DB first (safety rule #6 from the Phase 2 prompt) --
#    run from a machine with the Railway CLI linked to this project:
railway volume files download /data/qumanity_prototype.db ./backup_pre_phase2.db

# 2. Push this code (migrations/, cycle_middleware.py, and the updated *_core.py / app.py files)
#    the normal way -- git push to the branch Railway deploys from.

# 3. Run the migrations against the production DB. QM_DB_PATH on Railway already points at the
#    Volume path, so this needs no extra flag -- run it as a one-off Railway command against the
#    deployed environment:
railway run python3 tools/run_migrations.py

# 4. Verify:
railway run python3 tools/verify_cycle_stamping.py
```

No code change in this phase touches `app.secret_key`, `QM_DB_PATH`, the scheduler, or any other
go-live setting from the earlier hardening pass — this is purely additive schema + middleware.

## 6. Explicitly not done in this phase (per the Founder's own rules)

No pipeline, no transfers between location levels, no archive writes, no `0_Earth` file touched,
`lunar_calendar.py` unmodified, no cron — all Phase 3/4/5, not started.
