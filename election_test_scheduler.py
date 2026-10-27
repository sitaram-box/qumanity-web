"""Q-Punch council election automation for the pilot village (2026-10-27): the missing piece
between `election_core.auto_nominate()`/`auto_vote()` (already correct, already idempotent) and
the calendar -- without this, nothing has ever called either except the one-off
`scripts/seed_election_demo.py --vote` and two unwired admin routes.

Modeled on pipeline_scheduler.py's daily-tick shape, NOT test_cycle_scheduler.py's calendar cron
(day=1 / day_of_week="mon"): a zodiac sign's nomination/voting window does not land on the 1st of
a month or on Mondays (e.g. Aries runs roughly Mar 21 - Apr 19), so a daily tick that just
re-derives today's real status from election_core.current_cycle_for_village() -- exactly what
every other reader of the election already does -- is the only way to not miss a window's actual
start. Runs on its OWN BackgroundScheduler instance, entirely separate from pipeline_scheduler's
and test_cycle_scheduler's.

Never modifies election_core.py -- only calls its existing, unmodified public functions
(current_cycle_for_village, auto_nominate, auto_vote), the same functions the two existing admin
routes and scripts/seed_election_demo.py already go through. daily_tick(conn, now=None,
simulate_date=None) always takes an explicit conn, exactly like pipeline_scheduler's
daily_pipeline_tick(conn, simulate_date=None) -- the cron wrapper inside init_scheduler() is the
only thing that opens/closes a connection on its own; every test or tool calls daily_tick()
directly against an isolated DB, passing an explicit simulate_date instead of relying on the real
clock (same Safety Rule pipeline_scheduler.py's own docstring states)."""
from __future__ import annotations

import datetime as dt
import os

import election_core

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def daily_tick(conn, now: dt.datetime | None = None, simulate_date: str | None = None) -> dict:
    """The cron's own job function -- also called directly, with simulate_date, by every test and
    tool here (never a real tick against the main DB without one).

    Re-derives today's real cycle status (current_cycle_for_village() does the zodiac-sign-window
    math, not this function) and does the one thing that status calls for:
      nomination -> auto_nominate() (idempotent: tops up to 3/gender, never over-picks)
      voting     -> auto_vote(turnout=1.0) (idempotent: cast_vote() rejects a repeat voter, counted
                    as skipped, never an error)
      closed     -> nothing -- current_cycle_for_village() itself already tallied village_council
                    the first time this cycle was ever seen as closed, by anyone's read."""
    if simulate_date:
        now = dt.datetime.fromisoformat(simulate_date)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
    else:
        now = now or dt.datetime.now(IST)
    today = now.date()

    cycle = election_core.current_cycle_for_village(conn, election_core.PILOT_VILLAGE_ID, today)
    result = {"date": now.isoformat(), "sign": cycle["zodiac_sign"], "status": cycle["status"],
              "picked": None, "cast": None}

    if cycle["status"] == "nomination":
        try:
            result["picked"] = election_core.auto_nominate(conn, election_core.PILOT_VILLAGE_ID, today=today)
            picked_n = sum(len(v) for v in result["picked"].values())
            print(f"[election_test] INFO: daily_tick -- {cycle['zodiac_sign']} nomination, picked {picked_n} new candidate(s)")
        except ValueError as e:
            print(f"[election_test] WARNING: daily_tick -- auto_nominate skipped: {e}")
    elif cycle["status"] == "voting":
        try:
            result["cast"] = election_core.auto_vote(conn, election_core.PILOT_VILLAGE_ID, today=today, turnout=1.0)
            print(f"[election_test] INFO: daily_tick -- {cycle['zodiac_sign']} voting, "
                  f"cast {result['cast']['male'] + result['cast']['female']} new vote(s), "
                  f"{result['cast']['skipped']} skipped")
        except ValueError as e:
            print(f"[election_test] WARNING: daily_tick -- auto_vote skipped: {e}")
    else:
        print(f"[election_test] INFO: daily_tick -- {cycle['zodiac_sign']} closed, nothing to do")

    return result


# ---- Cron wiring ------------------------------------------------------------------------------

def init_scheduler(app) -> None:
    """Registers the daily tick, offset an hour from pipeline_scheduler's 00:00 IST and
    test_cycle_scheduler's 02:00 IST ticks (not a correctness requirement -- all three run on
    separate scheduler instances with no shared state -- just avoids every cron's log lines
    landing at the same timestamp). Skipped entirely when QM_DISABLE_SCHEDULER is set, same env
    var the other two schedulers already use for the same purpose (tests/tools)."""
    if os.environ.get("QM_DISABLE_SCHEDULER"):
        print("[election_test] QM_DISABLE_SCHEDULER set -- election-test cron not registered")
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from db import get_db

        def _tick():
            conn = get_db()
            try:
                daily_tick(conn)
            finally:
                conn.close()

        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(_tick, CronTrigger(hour=3, minute=0))
        scheduler.start()
        print("[election_test] daily election tick registered for 03:00 Asia/Kolkata")
