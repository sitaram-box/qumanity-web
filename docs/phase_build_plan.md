# Lunar-cycle archival system — phase build plan

See `docs/lunar_cycle_system.md` for the full design these phases implement. **Phases 1 and 2 are
built as of 2026-10-05** — Phases 3-5 are documented here for context and sequencing, not started.

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

## Phase 3: Pipeline engine

- `pipeline_core.py`.
- A `level_holdings` table.
- Aggregation functions (the public-facing summary a level displays).
- Transfer functions (level L → L+1, raw + aggregate, per the safety rule — only N-2 and older).
- Day-1-to-15 scheduler mapping, manual trigger only (not yet on a cron).

## Phase 4: Archive writer

- Writes to `/0_Earth/.../archives/<archive-folder-name>/`.
- `cycle_metadata.json` with all 13 language display names.
- Both location-level and user-level archive files.
- DB cleanup after a successful archive write (only for data that's reached level Earth → archive,
  per the safety rule).

## Phase 5: Cron scheduler + bootstrap

- A daily cron at 00:00 IST.
- Detects Purnima/Amavasya transitions automatically.
- Schedules the Day 1-15 actions from Phase 3 automatically.
- Implements the Year 1 bootstrap (no transfers) and the steady state from Year 2 onward.

## Explicit non-goals, every phase until stated otherwise

- Never touch the live Qoins wallet, Karma, or election systems — this archival system is
  orthogonal to all of them (council records are explicitly on their own separate archival track,
  not this lunar pipeline, per `docs/lunar_cycle_system.md`).
- Never run unattended in production before Phase 5's cron is explicitly turned on — every
  transfer/archive action stays manually triggered through Phase 4.
