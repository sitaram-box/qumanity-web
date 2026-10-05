"""Phase 5 verification script. Builds its own isolated test DB + fake 0_Earth scaffold under
/tmp (env vars set before any import that binds them). Never touches the real local DB or the
real 0_Earth tree, and never calls daily_pipeline_tick() without an explicit simulate_date
(Safety Rule 1).

Run with:
    python3 tools/verify_scheduler.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tmp_ctx = tempfile.TemporaryDirectory()
TMP = Path(_tmp_ctx.name)
DB_PATH = TMP / "verify_scheduler.db"
EARTH_ROOT = TMP / "0_Earth_test"

os.environ["QM_DB_PATH"] = str(DB_PATH)
os.environ["QM_EARTH_ROOT"] = str(EARTH_ROOT)
os.environ["QM_DISABLE_SCHEDULER"] = "1"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sqlite3

import cycle_middleware
import folder_connector
import lunar_calendar
import pipeline_core
import pipeline_scheduler
import seed_admin_only

VILLAGE_ID = "CS.DL.3.4.1A"
LOCATION = {
    "continent": {"id": "O_AS"}, "country": {"id": "O_AS_IND"}, "zone": {"id": "IND/CS"},
    "state": {"id": "CS.DL"}, "district": {"id": "CS.DL.3"}, "tehsil": {"id": "CS.DL.3.4"},
    "village": {"id": VILLAGE_ID},
}
CYCLE_OLD, CYCLE_N1, CYCLE_N = "Chaitra_2026", "Vaishakha_2026", "Jyeshtha_2026"


def _scaffold_earth_tree() -> None:
    cf = folder_connector._root_char_fix("O_AS")
    countryf = folder_connector._root_char_fix("O_AS_IND")
    path = EARTH_ROOT / "Continents" / cf / "Countries" / countryf
    path.mkdir(parents=True, exist_ok=True)
    for container, name in [("Zones", f"{countryf}:CS"), ("States", f"{countryf}:CS.DL"), ("Districts", f"{countryf}:CS.DL.3"),
                             ("Tehsils", f"{countryf}:CS.DL.3.4"), ("Villages", f"{countryf}:CS.DL.3.4.1A")]:
        path = path / container / name
        path.mkdir(parents=True, exist_ok=True)


def _build_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    seed_admin_only._apply_schema(conn)
    pipeline_core.ensure_tables(conn)
    pipeline_scheduler.ensure_tables(conn)
    conn.execute("DELETE FROM cycle_state")
    conn.execute("DELETE FROM pipeline_bootstrap")
    conn.commit()
    return conn


def _seed_user(conn, suffix: str = "0") -> int:
    loc_json = json.dumps(LOCATION)
    cur = conn.execute(
        "INSERT INTO users (name,gender,dob,tob,birth_location_json,present_location_json,private_id,account_id) VALUES (?,?,?,?,?,?,?,?)",
        (f"Sched Test {suffix}", "male", "1995-01-01", "08:00", loc_json, loc_json, f"PRIV-S{suffix}", f"ACC-S{suffix}"),
    )
    uid = cur.lastrowid
    conn.execute("INSERT INTO user_zodiac (user_id, sun_sign, sun_element) VALUES (?, 'Aries', 'Fire')", (uid,))
    conn.commit()
    return uid


def _seed_village_row(conn, uid: int, cycle_id: str) -> None:
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO karma_entries (user_id,kind,points,reason,created_at,cycle_id,pipeline_level) VALUES (?, 'noncommercial', 15, 's', ?, ?, 'village')",
        (uid, now_iso, cycle_id),
    )
    conn.commit()


def main() -> None:
    results = []
    print("=" * 70)
    print(f"Isolated test DB: {DB_PATH}")
    print(f"Isolated 0_Earth: {EARTH_ROOT}")
    print("=" * 70)

    _scaffold_earth_tree()
    conn = _build_db()

    # --- 1. Bootstrap row created on first boot ---
    bootstrap = pipeline_scheduler.init_bootstrap(conn)
    results.append(("Bootstrap row created on first call", bootstrap is not None and not bootstrap["pipeline_active"]))
    again = pipeline_scheduler.init_bootstrap(conn)
    results.append(("init_bootstrap is idempotent (same row, not recreated)", again["id"] == bootstrap["id"]))
    print(f"Bootstrap: year_1_start={bootstrap['year_1_start_amavasya']}, year_2_start={bootstrap['year_2_start_amavasya']}, active={bool(bootstrap['pipeline_active'])}")

    # Override year_2_start to a date we control, so the activation tests below are deterministic
    # rather than depending on how far the REAL calendar happens to be from the next Chaitra
    # Navratri right now.
    year2_start = lunar_calendar.get_cycle_dates(CYCLE_OLD)[0]  # CYCLE_OLD's own start_amavasya
    conn.execute("UPDATE pipeline_bootstrap SET year_2_start_amavasya = ? WHERE id = ?", (year2_start.isoformat(), bootstrap["id"]))
    conn.commit()

    # --- 2. Cron registered in test mode ---
    import apscheduler.schedulers.background as bg_mod
    OrigScheduler = bg_mod.BackgroundScheduler
    created = []

    class _CapturingScheduler(OrigScheduler):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            created.append(self)

    bg_mod.BackgroundScheduler = _CapturingScheduler
    os.environ.pop("QM_DISABLE_SCHEDULER")
    os.environ["WERKZEUG_RUN_MAIN"] = "true"
    try:
        class _FakeApp:
            debug = True
        pipeline_scheduler.init_scheduler(_FakeApp())
        registered = len(created) == 1 and len(created[0].get_jobs()) == 1
        results.append(("Cron job registers in test mode (scheduler.get_jobs() == 1)", registered))
        if created:
            created[0].shutdown(wait=False)
    finally:
        bg_mod.BackgroundScheduler = OrigScheduler
        os.environ["QM_DISABLE_SCHEDULER"] = "1"
        os.environ.pop("WERKZEUG_RUN_MAIN", None)

    # Confirm it's skipped when the env var IS set (the normal case for every other test here).
    created.clear()
    bg_mod.BackgroundScheduler = _CapturingScheduler
    try:
        pipeline_scheduler.init_scheduler(_FakeApp())
        results.append(("Cron job is NOT registered when QM_DISABLE_SCHEDULER=1", len(created) == 0))
    finally:
        bg_mod.BackgroundScheduler = OrigScheduler

    # --- 3. daily_pipeline_tick scenarios ---
    # IMPORTANT: kp_day is always computed relative to whichever cycle `now` itself falls in (the
    # CURRENT cycle, N) -- the cycle a transfer actually TARGETS is a different, older, eligible
    # one (N-2). So to legitimately exercise "KP Day 1 moves an eligible cycle," `now` must be
    # inside the CURRENT cycle's own Krishna Paksha, while CYCLE_OLD (the N-2 target) must already
    # be history. daily_pipeline_tick's own cycle_state sync (see pipeline_scheduler.py) builds
    # that history naturally as `now` is walked forward cycle by cycle below -- it is NOT
    # hand-seeded directly, since the sync would just immediately overwrite a hand-seeded row the
    # moment `now` didn't match it (a real bug this test caught during development).
    before = (year2_start - dt.timedelta(days=5)).isoformat()
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=before)
    print(f"\nBefore year_2_start ({before}): {r}")
    results.append(("Before year_2_start: pipeline inactive, no actions", r["pipeline_active"] is False and r["actions"] == []))

    on_boundary = (year2_start + dt.timedelta(hours=1)).isoformat()
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=on_boundary)
    print(f"On/after year_2_start ({on_boundary}): activated_this_tick={r['activated_this_tick']}, pipeline_active={r['pipeline_active']}")
    results.append(("On year_2_start: pipeline activates", r["activated_this_tick"] is True and r["pipeline_active"] is True))
    # cycle_state's active cycle is now CYCLE_OLD (Chaitra_2026), synced from `on_boundary` itself.

    uid = _seed_user(conn)
    _seed_village_row(conn, uid, CYCLE_OLD)

    # Walk `now` forward into CYCLE_N1 (Vaishakha_2026): sync closes Chaitra_2026, activates
    # Vaishakha_2026. Pick a Shukla Paksha moment (just after its own start_amavasya) so this tick
    # does no transfer work of its own.
    vaishakha_start = lunar_calendar.get_cycle_dates(CYCLE_N1)[0]
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=(vaishakha_start + dt.timedelta(hours=6)).isoformat())
    print(f"Advance into {CYCLE_N1}: kp_day={r['kp_day']}")

    # Walk `now` forward into CYCLE_N (Jyeshtha_2026): sync closes Vaishakha_2026 (now N-1),
    # activates Jyeshtha_2026 (N) -- Chaitra_2026 is now properly N-2 and eligible.
    jyeshtha_start, jyeshtha_mid, jyeshtha_end = lunar_calendar.get_cycle_dates(CYCLE_N)
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=(jyeshtha_start + dt.timedelta(hours=6)).isoformat())
    print(f"Advance into {CYCLE_N}: kp_day={r['kp_day']}")
    eligible_now = pipeline_core.get_eligible_cycles_for_pipeline(conn)
    results.append((f"After advancing to {CYCLE_N}, {CYCLE_OLD} is eligible (N-2)", eligible_now == [CYCLE_OLD]))

    waxing_date = (jyeshtha_mid - dt.timedelta(days=2)).isoformat()
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=waxing_date)
    print(f"\nWaxing phase, before {CYCLE_N}'s own Purnima ({waxing_date}): kp_day={r['kp_day']}, actions={r['actions']}")
    results.append(("Waxing phase (before Purnima): kp_day is None, no actions", r["kp_day"] is None and r["actions"] == []))

    day1_date = (jyeshtha_mid + dt.timedelta(days=1)).isoformat()
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=day1_date)
    print(f"\nKP Day 1 ({day1_date}): kp_day={r['kp_day']}, hop={r.get('hop')}, actions={len(r['actions'])}")
    moved_to_tehsil = any(a.get("cycle_id") == CYCLE_OLD and a.get("to_level") == "tehsil" for a in r["actions"])
    results.append(("KP Day 1: village -> tehsil fires for the eligible (N-2) cycle", r["kp_day"] == 1 and moved_to_tehsil))

    # Idempotency: re-run the exact same simulate_date -- transfer_log's 24h check should mean no
    # second transfer (the row is also no longer at 'village' by now, which alone would prevent
    # a re-move, but the explicit 24h check is exercised here too).
    r2 = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=day1_date)
    results.append(("Idempotency: re-running the same tick moves nothing new", r2["actions"] == []))

    # Walk the remaining 6 hops manually (Phase 3, already verified elsewhere) so we have a cycle
    # sitting at 'earth' to exercise the Day 15 archive hop.
    for from_level, to_level in [("tehsil", "district"), ("district", "state"), ("state", "zone"),
                                  ("zone", "country"), ("country", "continent"), ("continent", "earth")]:
        pipeline_core.transfer_level(conn, from_level, to_level, CYCLE_OLD)

    day15_date = min(jyeshtha_mid + dt.timedelta(days=15), jyeshtha_end - dt.timedelta(hours=1)).isoformat()
    r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=day15_date)
    print(f"\nKP Day 15 ({day15_date}): kp_day={r['kp_day']}, hop={r.get('hop')}, actions={r['actions']}")
    archived = any(a.get("cycle_id") == CYCLE_OLD and a.get("result", {}).get("status") == "archived" for a in r["actions"])
    # kp_day may legitimately be 14, not 15, if this cycle's own Krishna Paksha is a day short
    # (see pipeline_scheduler.daily_pipeline_tick's own "last day before Amavasya" fallback) --
    # what matters is that the archive hop fired and completed, not the exact day number.
    results.append(("KP Day ~15 (last day of Krishna Paksha): earth -> archive fires and completes", r["kp_day"] >= 13 and r.get("hop") == "earth->archive" and archived))

    # --- 5. Notifications queued ---
    notifications = pipeline_scheduler.list_notifications(conn, limit=20)
    print(f"\nNotifications queued ({len(notifications)}):")
    for n in notifications:
        print(f"  [{n['event_type']}] {n['message']}")
    event_types = {n["event_type"] for n in notifications}
    results.append(("Notifications queued for activation, KP start, and archive-complete",
                     {"pipeline_activated", "kp_run_started", "archive_complete"} <= event_types))

    conn.close()

    # --- 6. Phase 1-4 verifications still pass ---
    print()
    print("=" * 70)
    print("Phase 1-4 verification suites")
    print("=" * 70)
    clean_env = {k: v for k, v in os.environ.items() if k not in ("QM_DB_PATH", "QM_EARTH_ROOT")}
    for script in ("verify_lunar_calendar.py", "verify_cycle_stamping.py", "verify_pipeline.py", "verify_archive_writer.py"):
        # Each of these scripts sets its own QM_DB_PATH/QM_EARTH_ROOT (to its own /tmp dir) before
        # any import -- but pass a clean env anyway rather than relying on that overwrite.
        proc = subprocess.run([sys.executable, str(ROOT / "tools" / script)], cwd=str(ROOT),
                               capture_output=True, text=True, env=clean_env)
        ok = proc.returncode == 0
        results.append((f"{script} still passes", ok))
        print(("PASS" if ok else "FAIL") + f": {script}")
        if not ok:
            print(proc.stdout[-2000:], proc.stderr[-2000:])

    print()
    print("=" * 70)
    print("Consistency checks")
    print("=" * 70)
    all_pass = True
    for label, ok in results:
        print(("PASS" if ok else "FAIL") + f": {label}")
        all_pass = all_pass and ok

    print()
    print("=" * 70)
    print("OVERALL:", "ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED")
    print("=" * 70)
    _tmp_ctx.cleanup()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
