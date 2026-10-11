# Lunar-cycle archival system — Phase 5 report: cron scheduler + bootstrap logic

Built 2026-10-05. This is the final phase. Phases 1-4 are prerequisites; per Safety Rule 4, none
of `lunar_calendar.py` / `cycle_middleware.py` / `pipeline_core.py` / `archive_writer.py` changed.

## Questions answered before coding

1. **Notification system**: `notify_core.py` is a narrow per-user unread-chat/request badge
   counter, not a general event log — not reusable. Built the minimal `admin_notifications` table
   as suggested.
2. **`QM_ADMIN_EMAIL` convention**: none exists, and no email-sending capability (`smtplib`,
   `sendgrid`, any SMTP) exists anywhere in this codebase. Rather than inventing a new email
   integration nobody asked for, "admin email" is a `print()`-logged stub — matching the
   project's own established pattern for an unconnected provider (OTP's
   `QM_DEV_SHOW_OTP`). The real, usable notification is the `admin_notifications` row.
3. **Simulation scale**: proceeded with your recommendation — 3 users, 9 cycles, ~50 rows/cycle.

## Two genuine bugs found by this phase's own testing (not pre-existing Phase 1-4 bugs introduced
## here — both are in NEW Phase 5 code, fixed within this phase; nothing in Phase 1-4 was touched)

**1. `cycle_state` never advanced on its own.** Nothing in Decision 2/3's design calls
`cycle_middleware.transition_to()` as time passes — without it, `pipeline_core`'s N/N-1 safety
rule would stay frozen at whatever cycle_state happened to be the first time anything asked,
forever, and the pipeline would never process a new cycle once the real calendar moved past it.
Fixed: `daily_pipeline_tick()` now syncs `cycle_state` to the real (or simulated) calendar on
every tick, before anything else — passing the explicit current cycle id, never relying on
`cycle_middleware`'s own self-seed (which always uses the real wall-clock time, not
`simulate_date`).

**2. A latent landmine in the `{Month}_{Year}` cycle-naming scheme, surfaced via
`tools/simulate_lunar_year.py`.** A Vedic month's own Purnima can land in the same Gregorian year
twice (related to the adhik-maas-adjacent ~32-33-month phenomenon Phase 1's own docs already flag
as rare-but-real) — when that happens, `get_cycle_dates("SomeMonth_2026")` is genuinely
ambiguous between two different real occurrences, and can resolve to the wrong one.
`daily_pipeline_tick()` itself was calling exactly this vulnerable round-trip
(`get_cycle_dates(get_current_cycle_id(now))`) to find the current cycle's Purnima/Amavasya —
meaning this wasn't just a simulation-tooling artifact, it was a latent bug in the real
scheduling logic too, for whatever rare dates happen to collide. **Not fixed in
`lunar_calendar.py`** (Safety Rule 4) — worked around in `pipeline_scheduler.py` by computing the
window directly via the same private helper (`lunar_calendar._amavasya_window`)
`get_current_cycle_id`/`get_vedic_month_name` already use internally, which needs no name string
and therefore cannot collide. **Flagging this for a future, separate pass**: the underlying
ambiguity in `lunar_calendar.py`'s naming scheme itself is unresolved — anything that still reads
a `cycle_id` string and calls `get_cycle_dates()` on it (not through `pipeline_scheduler.py`)
remains exposed to it.

## Other deviations from the prompt (with reasons)

3. **Day 15's archive trigger is keyed to "the last day before this cycle's own Amavasya," not
   the literal number 15.** A synodic half-month averages ~14.77 days, so a cycle's own Krishna
   Paksha is just as often 14 calendar days as 15 — a hardcoded `kp_day == 15` check would then
   never fire for that specific cycle, silently skipping its archive step forever. Days 1-14 keep
   the literal mapping (far enough from the boundary to never have this problem); only the
   archive trigger uses the boundary-relative check.
4. **`tools/simulate_lunar_year.py`'s cycle traversal tracks each window's real
   (start, mid, end) directly**, for the same reason as bug 2 above — never by round-tripping
   through `get_cycle_dates(name)` — with a defensive uniqueness check that raises clearly if two
   of the 9 picked cycles would ever collide.
5. All 9 of the simulation's seeded cycles ended up archived by the end of the run, not "cycle 1
   archived, cycle 2 at Earth" as the prompt's illustrative example suggested. On reflection this
   is correct, not a bug: at the very first tick after activation, `cycle_state` has no N-1
   history yet (Year 1's backlog accumulated without any transitions happening), so every
   backlogged cycle except the brand-new N is immediately eligible and drains in one wave — new
   cycles arriving afterward then settle into the normal one-at-a-time staggered pace (visible
   later in the simulation's own activity log).

## What was built

- **`migrations/011_add_pipeline_bootstrap.sql`** — `pipeline_bootstrap` + `admin_notifications`.
- **`pipeline_scheduler.py`** — `init_bootstrap`, `_activate_pipeline`, `bootstrap_reset`,
  `krishna_paksha_day`, `daily_pipeline_tick`, `init_scheduler`, `health`, `_notify`/
  `list_notifications`/`mark_notification_read`.
- **`app.py`**: `init_bootstrap()` + `init_scheduler(app)` wired in after `ensure_database_ready()`
  (never activates the pipeline itself — Safety Rule 7); 4 admin endpoints
  (`bootstrap/activate`, `bootstrap/reset` with a `"RESET-BOOTSTRAP"` confirm token, `tick`,
  `health`).
- **`tools/simulate_lunar_year.py`**, **`tools/verify_scheduler.py`** — both build their own
  isolated DB + fake 0_Earth scaffold under `/tmp`.

## Verification — local runs, 2026-10-05

```
$ python3 tools/run_migrations.py
Applying 011_add_pipeline_bootstrap.sql... done.

$ QM_DISABLE_SCHEDULER=1 python3 -c "import app"   # real local DB, backward-compat check
No pending migrations.
[boot] database ready at <local default: qumanity_prototype.db>
[bootstrap] pipeline_bootstrap created: Year 1 starts 2026-10-10, Year 2 starts 2027-04-07 (Chaitra Navratri)
[scheduler] QM_DISABLE_SCHEDULER set -- lunar pipeline cron not registered
# Re-running: "No pending migrations." + no new bootstrap row (idempotent) -- confirmed via
# `SELECT COUNT(*) FROM pipeline_bootstrap` == 1, pipeline_active == 0 (Safety Rule 7).
# Year 2 start (2027-04-07) independently matches Phase 1's own real-world cross-check
# ("Chaitra Navratri ~April 6-7, 2027") -- a nice internal consistency confirmation.

$ python3 tools/verify_scheduler.py
PASS: Bootstrap row created on first call
PASS: init_bootstrap is idempotent (same row, not recreated)
PASS: Cron job registers in test mode (scheduler.get_jobs() == 1)
PASS: Cron job is NOT registered when QM_DISABLE_SCHEDULER=1
PASS: Before year_2_start: pipeline inactive, no actions
PASS: On year_2_start: pipeline activates
PASS: After advancing to Jyeshtha_2026, Chaitra_2026 is eligible (N-2)
PASS: Waxing phase (before Purnima): kp_day is None, no actions
PASS: KP Day 1: village -> tehsil fires for the eligible (N-2) cycle
PASS: Idempotency: re-running the same tick moves nothing new
PASS: KP Day ~15 (last day of Krishna Paksha): earth -> archive fires and completes
PASS: Notifications queued for activation, KP start, and archive-complete
PASS: verify_lunar_calendar.py / verify_cycle_stamping.py / verify_pipeline.py / verify_archive_writer.py still pass
OVERALL: ALL CHECKS PASSED
```

**Accelerated simulation** (9 real consecutive cycles, ~45 rows each, 3 users — 268 simulated
days compressed into 269 `daily_pipeline_tick` calls):

```
$ python3 tools/simulate_lunar_year.py
Cycles (oldest to newest): ['Bhadrapada_2026', 'Ashwin_2026', 'Kartik_2026', 'Margashirsha_2026',
  'Pausha_2027', 'Magha_2027', 'Phalguna_2027', 'Chaitra_2027', 'Vaishakha_2027']
Ran 269 daily ticks covering 268 days.

Final state per cycle
  Bhadrapada_2026: archived (0_Earth)      Ashwin_2026: archived (0_Earth)
  Kartik_2026: archived (0_Earth)          Margashirsha_2026: archived (0_Earth)
  Pausha_2027: archived (0_Earth)          Magha_2027: archived (0_Earth)
  Phalguna_2027: archived (0_Earth)        Chaitra_2027: archived (0_Earth)
  Vaishakha_2027: archived (0_Earth)

Total rows seeded: 406; total rows accounted for (DB + archived): 406

PASS: Cycle 1 (Bhadrapada_2026) reached 0_Earth archive
PASS: Cycle 2 (Ashwin_2026) progressed beyond village (not stuck)
PASS: No data lost (seeded == DB-remaining + archived)
OVERALL: ALL CHECKS PASSED
```
Real elapsed time: **~4 seconds** for 268 simulated days — comfortably "minutes," as asked.

**Sample `/api/admin/pipeline/health`** (fresh bootstrap, before activation):
```json
{
  "bootstrap": {"pipeline_active": 0, "year_1_start_amavasya": "2026-10-10T21:20:07+05:30",
                "year_2_start_amavasya": "2027-04-07T05:21:09+05:30", "activated_at": null},
  "current_cycle_id": "Bhadrapada_2026", "kp_day": null, "last_transfer": null,
  "next_scheduled_action": "Pipeline activates at Year 2 start: 2027-04-07T05:21:09+05:30",
  "recent_errors": []
}
```

**Notification samples** (from a real run — `admin_notifications` rows):
```
[pipeline_activated] Pipeline activated 2026-04-17T18:21:49+05:30 -- Year 2 has begun, transfers can now run.
[kp_run_started] Krishna Paksha Day 1: Chaitra_2026 moving village -> tehsil.
[archive_complete] Cycle Chaitra_2026 archived to 0_Earth (1 records).
```
Each also printed the email-stub line (no `QM_ADMIN_EMAIL` was set in these test runs, so that
line never fired — confirmed separately that setting it prints `"(email stub...) would email
<address>: ..."` rather than silently doing nothing).

## Known limitations

- **The cron needs the server process running continuously** — a gunicorn worker that restarts or
  a Railway redeploy loses the in-memory APScheduler job until the next boot re-registers it
  (`init_scheduler()` runs on every `import app`, so a redeploy self-heals; a long outage spanning
  a Krishna Paksha window does not — the missed day's transfer simply happens on the next tick
  after restart, since `_cycles_at_level` always re-checks current DB state, not a missed-trigger
  queue). For guaranteed delivery independent of server uptime, **migrate to Railway Cron Jobs**
  (a separate scheduled command hitting `POST /api/admin/pipeline/tick`, or running
  `python3 -c "..."` directly) instead of the in-process APScheduler — noted here for whoever
  picks this up next, not built in this phase (out of scope; Decision 3 explicitly asked for
  APScheduler).
- **The naming-collision landmine (bug 2 above) is only worked around in `pipeline_scheduler.py`**,
  not fixed at the source. Anything else that calls `lunar_calendar.get_cycle_dates(cycle_id)`
  with a name string (rather than a moment) remains exposed for the rare dates where it applies.
- **Manual tick command**: `python3 -c "from db import get_db; import pipeline_scheduler; c=get_db(); print(pipeline_scheduler.daily_pipeline_tick(c, simulate_date='2027-04-15')); c.close()"`
  (or via the admin endpoint). **Accelerated simulation**: `python3 tools/simulate_lunar_year.py`.

## Deployment to Railway (after your confirmation — not run; no Railway command executed)

```bash
railway volume files download /data/qumanity_prototype.db ./backup_pre_phase5.db
# push this code
railway run python3 tools/run_migrations.py
railway run python3 tools/verify_scheduler.py       # self-contained; safe to run against production too
# Then monitor via: curl https://<your-app>/api/admin/pipeline/health (as an admin session)
```
