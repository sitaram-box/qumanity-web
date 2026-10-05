# Lunar-cycle archival system — phase build plan

See `docs/lunar_cycle_system.md` for the full design these phases implement. **All 5 phases are
built as of 2026-10-05 — the lunar-cycle archival system is complete**, pending your review and
Railway deployment.

## Phase 1 (built, 2026-10-05): Lunar cycle detection + Vedic naming

- `lunar_calendar.py` using `pyswisseph` — compute Purnima/Amavasya for any date, detect the
  Chandra Maas, generate cycle IDs.
- `translations/lunar_months.json` — 12 months × 13 languages, plus "Purnima"/"Amavasya" suffix
  translations.
- `tools/verify_lunar_calendar.py` — a verification script (table of Purnima/Amavasya dates,
  cross-checks, translation-loading tests).
- Two unwired admin-only endpoint stubs in `app.py` (`/admin/lunar/current-cycle`,
  `/admin/lunar/upcoming`) for manual verification only — not called from anywhere else yet.
- **No DB schema changes. No pipeline. No production wiring.**

### Reconciling the two naming stubs

The original spec describes month-naming two ways: `get_current_cycle_id` "determine Vedic Chandra
Maas based on that [cycle's] Amavasya," while `get_vedic_month_name` is "based on Sun's sidereal
position at the Purnima." These are reconciled as one consistent rule: a "cycle" is the
Amavasya-to-Amavasya window; it is named using the Sun's sidereal rashi (Lahiri ayanamsa, matching
`zodiac_core.py`'s existing convention) **at that window's own Purnima** — i.e.
`get_current_cycle_id(dt)` locates the Amavasya-to-Amavasya window containing `dt`, then calls
`get_vedic_month_name()` on that window's Purnima. Both stubs describe the same single rule from
two different angles, not two different rules.

## Phase 2 (built, 2026-10-05): Cycle ID stamping

- `cycle_id` column (+ index) added to 28 tables classified as "ongoing activity" — see
  `docs/phase_2_report.md` for the full table list and the include/exclude rationale behind it.
- `cycle_middleware.py` — every real insert site across `wallet_core.py`, `karma_core.py`,
  `board_core.py`, `social_core.py`, `perception_core.py`, `review_core.py`, `payment_core.py`,
  `election_core.py`, `reactions_core.py`, and `app.py` now stamps `cycle_id` on write.
- `cycle_state` table tracks the currently-active cycle (a history of rows, not a single mutable
  one — see `docs/phase_2_report.md` §2).
- Three admin endpoints to inspect/manually trigger a cycle transition (needed because Year 1 is
  bootstrap-only — nothing auto-activates the pipeline yet): `GET /api/admin/lunar/cycle-state`,
  `POST /api/admin/lunar/cycle-state/transition`, `GET /api/admin/lunar/cycle-state/status`.
- `migrations/001_add_cycle_state.sql`, `migrations/002_add_cycle_id_to_activity_tables.sql`,
  `migrations/003_backfill_cycle_ids.py`, run via the idempotent `tools/run_migrations.py`.
- `tools/verify_cycle_stamping.py` — all 4 checks passing locally as of 2026-10-05.
- **No pipeline wiring. No cron. `lunar_calendar.py` unmodified. No `0_Earth` file touched.**

## Phase 3 (built, 2026-10-05): Pipeline engine

- `pipeline_core.py` — aggregation + the 7 real transfer functions (village→tehsil→…→earth),
  `transfer_earth_to_archive` (Phase 4 stub), `run_full_pipeline`, `get_eligible_cycles_for_pipeline`.
- `level_holdings` (the aggregate per level/level_id/cycle_id), `transfer_log` (audit trail),
  `pipeline_state` (last-transfer pointer) — `migrations/008-010`.
- `pipeline_level` column (+ indexes) on the same 28 Phase-2 tables — `migrations/007`.
- 5 admin endpoints (manual trigger only — see `docs/phase_3_report.md`).
- `tools/verify_pipeline.py` — builds its own isolated synthetic DB (the real DB has no
  N-2-or-older cycle to test against yet); all checks passing as of 2026-10-05.
- **Scoped to India's full 5-tier location chain for now** (confirmed 100% of real users fit this;
  see `docs/phase_3_report.md`'s "correctness gap" section) — a row that doesn't is excluded from
  aggregation, not guessed at. No pipeline is wired to a schedule. `lunar_calendar.py` and
  `cycle_middleware.py` unmodified. No `0_Earth` file touched.

## Phase 4 (built, 2026-10-05): Archive writer

- `archive_writer.py` — `archive_cycle()`, `write_location_archive()` (village AND
  country/zone, for sentiment data — see `docs/phase_4_report.md`), `write_user_archive()`
  (BORN_HERE + LIVING_HERE, via `folder_connector`'s own real path-resolution functions),
  `build_cycle_metadata()`, `verify_archive()`, `delete_cycle_raw_records()`,
  `archive_status()`.
- Writes to the real `0_Earth` tree via `folder_connector.resolve_location_dir()` (the same
  function every registration already uses) — `.../archives/<archive-folder-name>/`.
- `cycle_metadata.json` with all 13 language display names (reuses Phase 1's
  `translated_cycle_display_name()` unmodified) + a `dry_run` flag (see report, deviation 4).
- Both location-level (16 files, covering all 28 Phase-2 tables) and user-level
  (`my_*.json` + `cycle_summary.json`) archive files, each checksummed.
- Hard-deletes raw records after a verified, durable write — only ever for `pipeline_level='earth'`
  rows, with a pre-delete SQL backup (`0_Earth/.backups/pre_archive_<cycle_id>.sql`).
- `pipeline_core.transfer_earth_to_archive`'s stub replaced with a one-line call into this module
  — no other line in `pipeline_core.py`/`cycle_middleware.py`/`lunar_calendar.py` changed.
- 2 admin endpoints, `tools/verify_archive_writer.py` (isolated DB + isolated fake 0_Earth
  scaffold) — all checks passing as of 2026-10-05, including a real collision bug this phase's
  own testing caught and fixed (see report).
- No cron wiring (Phase 5). Tested only against `/tmp` — no Railway command run, nothing
  committed or pushed.

## Phase 5 (built, 2026-10-05): Cron scheduler + bootstrap — final phase

- `pipeline_scheduler.py` — `daily_pipeline_tick()` (the cron's own job function, also callable
  directly with `simulate_date` for testing/emergency use), `init_bootstrap()`, `init_scheduler()`,
  `health()`, a minimal `admin_notifications` log (no general-purpose notification/email system
  existed to reuse — see `docs/phase_5_report.md`).
- `pipeline_bootstrap` table (`migrations/011`) — Year 1 (no transfers) vs. Year 2 (pipeline
  active) tracked via the first Amavasya after boot and the next Chaitra Navratri.
- A daily APScheduler cron at 00:00 Asia/Kolkata, registered in `app.py` after
  `ensure_database_ready()` -- skippable via `QM_DISABLE_SCHEDULER` (tests/tools always set it).
- 4 admin endpoints (manual override / emergency use): bootstrap activate/reset (confirm-token
  gated), manual tick, health.
- `tools/simulate_lunar_year.py` (9 real cycles compressed into ~4 seconds) and
  `tools/verify_scheduler.py` — both passing, plus all of Phases 1-4's own verification suites
  re-confirmed passing after this phase's changes.
- **Two genuine bugs in the new Phase 5 code were found by its own tests and fixed** (not
  pre-existing Phase 1-4 bugs): `cycle_state` never advancing on its own over time, and a
  latent cycle-naming-collision landmine in how the scheduler read Purnima/Amavasya dates —
  both detailed in `docs/phase_5_report.md`, which also flags the underlying naming ambiguity in
  `lunar_calendar.py` itself (unmodified, per Safety Rule 4) for a future, separate pass.
- Tested only against `/tmp` DBs + a fake 0_Earth scaffold. No Railway command run; nothing
  committed or pushed.

## Explicit non-goals, every phase until stated otherwise

- Never touch the live Qoins wallet, Karma, or election systems — this archival system is
  orthogonal to all of them (council records are explicitly on their own separate archival track,
  not this lunar pipeline, per `docs/lunar_cycle_system.md`).
- Never run unattended in production before Phase 5's cron is explicitly turned on — every
  transfer/archive action stays manually triggered through Phase 4.
