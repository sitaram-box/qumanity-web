"""Phase 5 of the lunar-cycle archival system: the automation layer. Detects Purnima/Amavasya
transitions and runs the Phase 3/4 pipeline on the Krishna Paksha Day 1-15 schedule described in
docs/lunar_cycle_system.md, with a Year-1-bootstrap gate before any transfer ever fires. See
docs/phase_5_report.md.

Never modifies lunar_calendar.py / cycle_middleware.py / pipeline_core.py / archive_writer.py --
only reads their public functions. The cron job itself (init_scheduler) is the only thing that can
make this run unattended; every test and tool in this phase calls daily_pipeline_tick() directly
with an explicit simulate_date instead, against an isolated DB (Safety Rule 1/3).
"""
from __future__ import annotations

import datetime as dt
import os

import cycle_middleware
import lunar_calendar
import pipeline_core

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_bootstrap (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year_1_start_amavasya TIMESTAMP NOT NULL,
    year_2_start_amavasya TIMESTAMP NOT NULL,
    pipeline_active BOOLEAN DEFAULT 0,
    activated_at TIMESTAMP,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS admin_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_notifications_read ON admin_notifications(read_at);
"""

# Krishna Paksha day -> (from_level, to_level). "archive" is the Day 15 special case: it calls
# pipeline_core.transfer_earth_to_archive, not transfer_level.
_HOP_FOR_DAY: dict[int, tuple[str, str]] = {
    1: ("village", "tehsil"), 2: ("village", "tehsil"),
    3: ("tehsil", "district"), 4: ("tehsil", "district"),
    5: ("district", "state"), 6: ("district", "state"),
    7: ("state", "zone"), 8: ("state", "zone"),
    9: ("zone", "country"), 10: ("zone", "country"),
    11: ("country", "continent"), 12: ("country", "continent"),
    13: ("continent", "earth"), 14: ("continent", "earth"),
    15: ("earth", "archive"),
}


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---- Notifications ---------------------------------------------------------------------------
# No general-purpose notification/email system exists to reuse: notify_core.py is a narrow
# per-user chat/request unread-badge counter (checked before building this), and no
# QM_ADMIN_EMAIL / smtplib / any email-sending code exists anywhere in the codebase. Rather than
# inventing a new SMTP integration nobody asked for, admin "email" is a print()-logged stub here,
# matching the project's own established pattern for an unconnected provider (see
# payment_core.py's simulated Razorpay mode, OTP's QM_DEV_SHOW_OTP) -- the REAL, usable
# notification is the admin_notifications row, readable via the admin API.

def _notify(conn, event_type: str, message: str) -> None:
    ensure_tables(conn)
    conn.execute("INSERT INTO admin_notifications (event_type, message) VALUES (?, ?)", (event_type, message))
    conn.commit()
    print(f"[notify] {event_type}: {message}")
    admin_email = os.environ.get("QM_ADMIN_EMAIL")
    if admin_email:
        print(f"[notify] (email stub -- no SMTP/email provider is wired up) would email {admin_email}: {message}")


def list_notifications(conn, limit: int = 50, unread_only: bool = False) -> list[dict]:
    ensure_tables(conn)
    sql = "SELECT * FROM admin_notifications"
    if unread_only:
        sql += " WHERE read_at IS NULL"
    sql += " ORDER BY id DESC LIMIT ?"
    return [dict(r) for r in conn.execute(sql, (limit,))]


def mark_notification_read(conn, notification_id: int) -> None:
    ensure_tables(conn)
    conn.execute("UPDATE admin_notifications SET read_at = CURRENT_TIMESTAMP WHERE id = ? AND read_at IS NULL", (notification_id,))
    conn.commit()


# ---- Bootstrap (Decision 1) -------------------------------------------------------------------

def _get_bootstrap(conn) -> dict | None:
    ensure_tables(conn)
    row = conn.execute("SELECT * FROM pipeline_bootstrap ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _find_year_boundaries(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """(year_1_start, year_2_start): the first Amavasya after `now`, and the next Chaitra
    Amavasya (Chaitra Navratri -- the cycle named "Chaitra_YYYY" always starts at one) strictly
    after that. Scans upcoming_events() in growing windows until both are found -- Chaitra occurs
    once every ~12-13 cycles, so a modest scan is always enough."""
    count = 30
    while count <= 400:
        events = lunar_calendar.upcoming_events(count, from_moment=now)
        amavasyas = [e for e in events if e["phase"] == "Amavasya"]
        if amavasyas:
            year1 = amavasyas[0]
            year2 = next((e for e in amavasyas if e["vedic_month"] == "Chaitra" and e["datetime"] > year1["datetime"]), None)
            if year2:
                return dt.datetime.fromisoformat(year1["datetime"]), dt.datetime.fromisoformat(year2["datetime"])
        count *= 2
    raise RuntimeError("Could not find two Chaitra Amavasyas within a 400-event scan -- something is wrong with lunar_calendar")


def init_bootstrap(conn, now: dt.datetime | None = None) -> dict:
    """Creates the pipeline_bootstrap row on first call; a no-op every call after. NEVER
    activates the pipeline itself (Safety Rule 7) -- that is exclusively daily_pipeline_tick's
    job (or an explicit admin override), so calling this on the existing, long-lived production
    DB is always safe."""
    existing = _get_bootstrap(conn)
    if existing:
        return existing
    now = now or dt.datetime.now(IST)
    year1_start, year2_start = _find_year_boundaries(now)
    conn.execute(
        "INSERT INTO pipeline_bootstrap (year_1_start_amavasya, year_2_start_amavasya, pipeline_active, notes) VALUES (?, ?, 0, ?)",
        (year1_start.isoformat(), year2_start.isoformat(), f"Initialized at boot, {now.isoformat()}"),
    )
    conn.commit()
    print(f"[bootstrap] pipeline_bootstrap created: Year 1 starts {year1_start.date()}, Year 2 starts {year2_start.date()} (Chaitra Navratri)")
    return _get_bootstrap(conn)


def _activate_pipeline(conn, now: dt.datetime, note: str = "") -> dict:
    conn.execute(
        "UPDATE pipeline_bootstrap SET pipeline_active = 1, activated_at = ?, notes = COALESCE(notes, '') || ? "
        "WHERE id = (SELECT id FROM pipeline_bootstrap ORDER BY id DESC LIMIT 1)",
        (now.isoformat(), f" | activated {now.isoformat()}{(' - ' + note) if note else ''}"),
    )
    conn.commit()
    return _get_bootstrap(conn)


def bootstrap_reset(conn, now: dt.datetime | None = None) -> dict:
    """Deletes the existing bootstrap row and recomputes it fresh -- an emergency/testing-only
    action, gated by a confirm token at the API layer (app.py), not here."""
    now = now or dt.datetime.now(IST)
    conn.execute("DELETE FROM pipeline_bootstrap")
    conn.commit()
    return init_bootstrap(conn, now)


# ---- Krishna Paksha day detection + the tick itself (Decision 2) -------------------------------

def _cycles_at_level(conn, pipeline_level: str) -> set[str]:
    found: set[str] = set()
    for table in cycle_middleware.STAMPED_TABLES:
        for r in conn.execute(f"SELECT DISTINCT cycle_id FROM {table} WHERE pipeline_level = ? AND cycle_id IS NOT NULL", (pipeline_level,)):
            found.add(r[0])
    return found


def _already_done_today(conn, from_level: str, cycle_id: str, now: dt.datetime) -> bool:
    cutoff = now.astimezone(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=24)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        "SELECT 1 FROM transfer_log WHERE from_level = ? AND cycle_id = ? AND status = 'completed' AND completed_at >= ? LIMIT 1",
        (from_level, cycle_id, cutoff_str),
    ).fetchone()
    return row is not None


def _window_for_moment(now: dt.datetime) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    """(start_amavasya, mid_purnima, end_amavasya) of the cycle containing `now`, computed
    DIRECTLY -- never via get_cycle_dates(get_current_cycle_id(now)). That round-trip through a
    "{Month}_{Year}" string is lossy: a Vedic month's own Purnima can land in the same Gregorian
    year twice (the naming scheme has no way to tell two such occurrences apart -- related to the
    adhik maas / ~32-33-month phenomenon Phase 1's own docs already flag as rare-but-real), and
    get_cycle_dates() can then resolve the name to the WRONG one of the two. Found during Phase 5
    testing (tools/simulate_lunar_year.py hit a real "Margashirsha_2026" collision); NOT fixed in
    lunar_calendar.py itself (Safety Rule 4) -- worked around here by using the same private
    helper get_current_cycle_id()/get_vedic_month_name() already use internally, which needs no
    name and therefore cannot collide. See docs/phase_5_report.md."""
    a_jd, mid_jd, end_jd = lunar_calendar._amavasya_window(now)
    to_ist = lambda jd: lunar_calendar._jd_to_utc(jd).astimezone(IST)
    return to_ist(a_jd), to_ist(mid_jd), to_ist(end_jd)


def krishna_paksha_day(conn, now: dt.datetime) -> int | None:
    """1-15 if `now` falls in the current cycle's Krishna Paksha (Purnima -> Amavasya, the
    waning fortnight), else None. A negative/zero/>15 "days since Purnima" naturally covers both
    "still in Shukla Paksha" (before this cycle's own Purnima) and any edge case beyond day 15."""
    _, mid_purnima, _ = _window_for_moment(now)
    days_since = (now - mid_purnima).days
    if 1 <= days_since <= 15:
        return days_since
    return None


def daily_pipeline_tick(conn, simulate_date: str | None = None) -> dict:
    """The cron's own job function -- also called directly, with simulate_date, by every test and
    tool in this phase (Safety Rule 1: never a real tick against the main DB without one)."""
    if simulate_date:
        now = dt.datetime.fromisoformat(simulate_date)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
    else:
        now = dt.datetime.now(IST)

    bootstrap = init_bootstrap(conn, now)

    # Keep cycle_state's "active cycle" (N) in step with the (real or simulated) calendar. Nothing
    # else ever does this: cycle_middleware.get_active_cycle_row() only self-seeds once, using the
    # REAL wall-clock "now" (never `now` here), and nothing else calls transition_to(). Without
    # this, N/N-1 would stay frozen at whatever they were the first time anything asked, and
    # pipeline_core's N-2 safety rule would never let a new cycle through once the real calendar
    # moved past it. Passing `real_cycle` explicitly (not cycle_middleware's own default) is what
    # makes this correct under simulate_date too, not just real time.
    real_cycle = lunar_calendar.get_current_cycle_id(now)
    active_row = cycle_middleware.get_active_cycle_row(conn)
    if active_row["cycle_id"] != real_cycle:
        cycle_middleware.transition_to(conn, real_cycle, activated_by="scheduler:auto")
        print(f"[scheduler] cycle_state advanced: {active_row['cycle_id']} -> {real_cycle}")

    activated_this_tick = False
    year2_start = dt.datetime.fromisoformat(bootstrap["year_2_start_amavasya"])
    if not bootstrap["pipeline_active"] and now >= year2_start:
        bootstrap = _activate_pipeline(conn, now, note="Year 2 (Chaitra Navratri) reached")
        activated_this_tick = True
        _notify(conn, "pipeline_activated", f"Pipeline activated {now.isoformat()} -- Year 2 has begun, transfers can now run.")

    if not bootstrap["pipeline_active"]:
        print(f"[scheduler] {now.date()}: Year 1 bootstrap still active (pipeline starts {year2_start.date()}) -- no transfers")
        return {"date": now.isoformat(), "pipeline_active": False, "activated_this_tick": activated_this_tick, "kp_day": None, "actions": []}

    kp_day = krishna_paksha_day(conn, now)
    if kp_day is None:
        print(f"[scheduler] {now.date()}: not in Krishna Paksha -- no transfers")
        return {"date": now.isoformat(), "pipeline_active": True, "activated_this_tick": activated_this_tick, "kp_day": None, "actions": []}

    from_level, to_level = _HOP_FOR_DAY[min(kp_day, 15)]
    # Robustness: a synodic half-month averages ~14.77 days, so a cycle's own Krishna Paksha is
    # just as often 14 calendar days as 15 -- Day 15 (archive) would then never literally occur
    # for that cycle, silently skipping the archive step. Key the archive trigger to "the last day
    # before this cycle's own Amavasya" instead of the bare day number, so it fires on whichever
    # day that actually is. By then continent->earth has already run (day 13, or day 14 if the
    # window is short), so the cycle is already sitting at 'earth' and ready to archive.
    _, _, end_amavasya = _window_for_moment(now)
    if kp_day >= 13 and (end_amavasya - now) < dt.timedelta(days=1):
        from_level, to_level = "earth", "archive"
    eligible = set(pipeline_core.get_eligible_cycles_for_pipeline(conn))
    candidates = sorted(_cycles_at_level(conn, from_level) & eligible)

    actions = []
    for cycle_id in candidates:
        if _already_done_today(conn, from_level, cycle_id, now):
            print(f"[scheduler] {cycle_id} {from_level}->{to_level} already completed in the last 24h -- skipping")
            continue
        try:
            if to_level == "archive":
                result = pipeline_core.transfer_earth_to_archive(conn, cycle_id)
                if result.get("status") == "archived":
                    _notify(conn, "archive_complete", f"Cycle {cycle_id} archived to 0_Earth ({result.get('records_deleted', 0)} records).")
            else:
                result = pipeline_core.transfer_level(conn, from_level, to_level, cycle_id)
                if kp_day in (1, 2):
                    _notify(conn, "kp_run_started", f"Krishna Paksha Day {kp_day}: {cycle_id} moving {from_level} -> {to_level}.")
            actions.append({"cycle_id": cycle_id, "from_level": from_level, "to_level": to_level, "result": result})
        except Exception as e:
            _notify(conn, "transfer_failed", f"Transfer failed for {cycle_id} ({from_level} -> {to_level}): {e}")
            print(f"[scheduler] ERROR transferring {cycle_id} {from_level}->{to_level}: {e}")
            actions.append({"cycle_id": cycle_id, "from_level": from_level, "to_level": to_level, "error": str(e)})

    return {"date": now.isoformat(), "pipeline_active": True, "activated_this_tick": activated_this_tick,
            "kp_day": kp_day, "hop": f"{from_level}->{to_level}", "actions": actions}


# ---- Cron wiring (Decision 3) ------------------------------------------------------------------

def init_scheduler(app) -> None:
    """Registers the daily 00:00 IST tick. Skipped entirely when QM_DISABLE_SCHEDULER is set
    (tests/tools) -- this is a SEPARATE job/flag from the existing _run_scheduled_sync cron in
    app.py, which this phase does not touch."""
    if os.environ.get("QM_DISABLE_SCHEDULER"):
        print("[scheduler] QM_DISABLE_SCHEDULER set -- lunar pipeline cron not registered")
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from db import get_db

        def _tick():
            conn = get_db()
            try:
                daily_pipeline_tick(conn)
            finally:
                conn.close()

        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(_tick, CronTrigger(hour=0, minute=0))
        scheduler.start()
        print("[scheduler] lunar pipeline daily tick registered for 00:00 Asia/Kolkata")


# ---- Health (Decision 7) -----------------------------------------------------------------------

def health(conn, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(IST)
    bootstrap = _get_bootstrap(conn) or init_bootstrap(conn, now)
    kp_day = krishna_paksha_day(conn, now) if bootstrap["pipeline_active"] else None
    last_transfer = conn.execute("SELECT * FROM transfer_log ORDER BY id DESC LIMIT 1").fetchone()
    recent_errors = [dict(r) for r in conn.execute("SELECT * FROM transfer_log WHERE status = 'failed' ORDER BY id DESC LIMIT 5")]

    next_action = None
    if not bootstrap["pipeline_active"]:
        next_action = f"Pipeline activates at Year 2 start: {bootstrap['year_2_start_amavasya']}"
    else:
        upcoming = lunar_calendar.upcoming_events(2, from_moment=now)
        next_purnima = next((e for e in upcoming if e["phase"] == "Purnima"), None)
        if next_purnima:
            next_action = f"Krishna Paksha Day 1 (village->tehsil) begins the day after the next Purnima: {next_purnima['datetime']}"

    return {
        "bootstrap": bootstrap,
        "current_cycle_id": lunar_calendar.get_current_cycle_id(now),
        "kp_day": kp_day,
        "last_transfer": dict(last_transfer) if last_transfer else None,
        "next_scheduled_action": next_action,
        "recent_errors": recent_errors,
        "checked_at": now.isoformat(),
    }
