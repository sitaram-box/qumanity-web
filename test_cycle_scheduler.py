"""Post Testing cycle scheduler (2026-10-17, docs/test_cycle_design.md): the automation layer
for the year-long demo-vote test of the Board's post -> vote -> reward -> freeze/elevate path.

Mirrors pipeline_scheduler.py's structure: its own SCHEMA/ensure_tables() for testing_windows
(also created by migrations/017_test_cycle.py -- the same belt-and-suspenders pattern
pipeline_scheduler.py itself uses for pipeline_bootstrap/admin_notifications, so this module
stays self-sufficient even if invoked standalone, e.g. by a test harness that hasn't run the
full migration pipeline); its own guarded init_scheduler(app); the same WERKZEUG_RUN_MAIN /
app.debug guard; and the same plain print()-based logging convention (pipeline_scheduler.py does
not use Python's logging module anywhere -- every message there is print(f"[scheduler] ...")).

Runs on its OWN BackgroundScheduler instance, entirely separate from pipeline_scheduler's and
app.py's own _start_scheduler() -- this whole feature is meant to be independently removable once
the test year is over. Single-worker dependency: safe only because this deploy runs one gunicorn
worker (Procfile: `--workers 1`); more workers would register each cron job once per worker, the
same caveat already noted for the existing schedulers.

monthly_post_job(conn, now=None) and weekly_vote_job(conn, now=None) always take an explicit
conn, exactly like pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=None) -- the cron
wrapper inside init_scheduler() is the only thing that opens/closes a connection on its own;
every test or tool calls these directly against an isolated DB, passing conn and (optionally) an
explicit `now` instead of relying on the real clock.

Never modifies board_core.py / wallet_core.py / karma_core.py -- only calls their existing,
unmodified public functions (create_post, cast_vote), the same functions a real user's own
actions already go through and that are already covered by the reward-path test suite
(Scenarios A-G, H1-H9)."""
from __future__ import annotations

import datetime as dt
import json
import os
import random

FEATURE = "post_testing"

SCHEMA = """
CREATE TABLE IF NOT EXISTS testing_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    demo_user_count INTEGER NOT NULL,
    vote_distribution TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_testing_windows_feature_status ON testing_windows(feature, status);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---- The shared window check (used by both jobs) -----------------------------------------------

def active_window(conn, now: dt.datetime | None = None) -> dict | None:
    """The active post_testing window, or None if there isn't one. Flips a past-due window to
    'expired' itself -- the only place that transition happens, so neither job repeats this
    logic."""
    ensure_tables(conn)
    now = now or dt.datetime.now(dt.timezone.utc)
    row = conn.execute(
        "SELECT * FROM testing_windows WHERE feature = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
        (FEATURE,),
    ).fetchone()
    if not row:
        return None
    window = dict(row)
    end = dt.datetime.fromisoformat(window["end_date"])
    if end.tzinfo is None:
        end = end.replace(tzinfo=dt.timezone.utc)
    if now >= end:
        conn.execute("UPDATE testing_windows SET status = 'expired' WHERE id = ?", (window["id"],))
        conn.commit()
        print(f"[test_cycle] WARNING: post_testing window {window['id']} expired at {window['end_date']} -- no longer active")
        return None
    return window


def _demo_voters(conn) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM users WHERE is_demo = 1 AND is_removed = 0")]


def _random_vote(vote_distribution: dict) -> int:
    """vote_distribution is the JSON-decoded {"+1": 0.5, "0": 0.3, "-1": 0.2} stored on the
    active window. int() correctly parses a leading '+' (int("+1") == 1), so the dict's own keys
    are used directly as the candidate values -- no separate mapping table needed."""
    values = [int(k) for k in vote_distribution]
    weights = [vote_distribution[k] for k in vote_distribution]
    return random.choices(values, weights=weights, k=1)[0]


# ---- Window CRUD (called by app.py's admin routes -- this module owns testing_windows, the same
# way every other *_core.py module owns its own table; app.py's routes stay thin wrappers) --------

def start_window(conn, demo_user_count: int, vote_distribution: dict, now: dt.datetime | None = None) -> dict:
    """Creates a new active post_testing window. THIS is Layer 2 of the two-layer defence: it
    re-checks, independently of whatever the admin panel's own UI believed (Layer 1), that no
    post_testing window is already active -- raises and creates nothing if one is."""
    ensure_tables(conn)
    now = now or dt.datetime.now(dt.timezone.utc)
    if conn.execute("SELECT 1 FROM testing_windows WHERE feature = ? AND status = 'active'", (FEATURE,)).fetchone():
        raise ValueError("A post_testing window is already active -- stop it before starting a new one.")
    end = now + dt.timedelta(days=365)
    conn.execute(
        """INSERT INTO testing_windows (feature, start_date, end_date, status, demo_user_count, vote_distribution, created_at)
           VALUES (?, ?, ?, 'active', ?, ?, ?)""",
        (FEATURE, now.isoformat(), end.isoformat(), demo_user_count, json.dumps(vote_distribution), now.isoformat()),
    )
    conn.commit()
    print(f"[test_cycle] INFO: post_testing window started, {now.date()} -> {end.date()}")
    return active_window(conn, now)


def renew_window(conn, now: dt.datetime | None = None) -> dict:
    """Extends the active window's end_date by 365 days in place. Only works on a row that is
    still 'active' -- 'expired'/'stopped' windows have no renew path (Decision 3: the only way
    forward from a terminal state is start_window(), a fresh row)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    window = active_window(conn, now)
    if window is None:
        raise ValueError("No active post_testing window to renew.")
    new_end = dt.datetime.fromisoformat(window["end_date"]) + dt.timedelta(days=365)
    conn.execute("UPDATE testing_windows SET end_date = ? WHERE id = ?", (new_end.isoformat(), window["id"]))
    conn.commit()
    print(f"[test_cycle] INFO: post_testing window {window['id']} renewed, new end_date {new_end.date()}")
    window["end_date"] = new_end.isoformat()
    return window


def stop_window(conn, now: dt.datetime | None = None) -> dict:
    """Sets status='stopped' on the active window. Never touches users.is_removed -- stopping a
    window and retiring demo voters are independent actions (design doc Section 10)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    window = active_window(conn, now)
    if window is None:
        raise ValueError("No active post_testing window to stop.")
    conn.execute("UPDATE testing_windows SET status = 'stopped' WHERE id = ?", (window["id"],))
    conn.commit()
    print(f"[test_cycle] INFO: post_testing window {window['id']} stopped by admin")
    window["status"] = "stopped"
    return window


def panel_data(conn, now: dt.datetime | None = None) -> dict:
    """Everything the admin panel (design doc Section 8) needs to render, computed fresh on each
    call -- no separate counters stored anywhere. {"window": None} when no post_testing window
    has ever been created (Layer 1 of the two-layer defence reads window["status"] from this to
    decide which buttons to show; Layer 2, in start_window()/stop_window()/renew_window() above,
    is what actually enforces it)."""
    ensure_tables(conn)
    now = now or dt.datetime.now(dt.timezone.utc)
    row = conn.execute(
        "SELECT * FROM testing_windows WHERE feature = ? ORDER BY id DESC LIMIT 1", (FEATURE,)
    ).fetchone()
    if not row:
        return {"window": None, "posts_this_month": 0, "votes_this_month": 0}
    window = dict(row)
    if window["status"] == "active":
        end = dt.datetime.fromisoformat(window["end_date"])
        if end.tzinfo is None:
            end = end.replace(tzinfo=dt.timezone.utc)
        if now >= end:
            conn.execute("UPDATE testing_windows SET status = 'expired' WHERE id = ?", (window["id"],))
            conn.commit()
            window["status"] = "expired"

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    posts_this_month = conn.execute(
        "SELECT COUNT(*) FROM board_posts WHERE is_demo_post = 1 AND created_at >= ?", (month_start,)
    ).fetchone()[0]
    demo_ids = _demo_voters(conn)
    votes_this_month = 0
    if demo_ids:
        qmarks = ",".join("?" * len(demo_ids))
        votes_this_month = conn.execute(
            f"SELECT COUNT(*) FROM board_votes WHERE user_id IN ({qmarks}) AND voted_at >= ?",
            (*demo_ids, month_start),
        ).fetchone()[0]
    return {"window": window, "posts_this_month": posts_this_month, "votes_this_month": votes_this_month}


# ---- monthly_post_job -----------------------------------------------------------------------

def monthly_post_job(conn, now: dt.datetime | None = None) -> dict:
    """1st-of-the-month job: one test post per demo user, skipping anyone who already has an
    is_demo_post=1 post created this calendar month. Idempotent per (demo_user, calendar_month) --
    re-running after everyone's already posted this month creates nothing."""
    import board_core

    now = now or dt.datetime.now(dt.timezone.utc)
    window = active_window(conn, now)
    if window is None:
        print("[test_cycle] WARNING: monthly_post_job -- no active post_testing window, exiting")
        return {"ran": False, "reason": "no active window", "created": 0, "skipped": 0, "errors": []}

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    created, skipped, errors = 0, 0, []
    for user_id in _demo_voters(conn):
        already = conn.execute(
            "SELECT 1 FROM board_posts WHERE author_id = ? AND is_demo_post = 1 AND created_at >= ? LIMIT 1",
            (user_id, month_start),
        ).fetchone()
        if already:
            skipped += 1
            continue
        try:
            row = conn.execute("SELECT present_location_json, name FROM users WHERE id = ?", (user_id,)).fetchone()
            present_location = json.loads(row["present_location_json"])
            content = f"Test post created by {row['name']} for the monthly test cycle - {now.strftime('%B %Y')}."
            board_core.create_post(conn, user_id, present_location, content, level="village", now=now,
                                    post_kind="test", is_demo_post=True)
            created += 1
        except Exception as e:
            print(f"[test_cycle] ERROR: monthly_post_job -- post creation failed for demo user {user_id}: {e}")
            errors.append({"user_id": user_id, "error": str(e)})
            continue

    print(f"[test_cycle] INFO: monthly_post_job -- created {created} post(s), skipped {skipped} "
          f"(already posted this month), {len(errors)} error(s)")
    return {"ran": True, "created": created, "skipped": skipped, "errors": errors}


# ---- weekly_vote_job -------------------------------------------------------------------------

def weekly_vote_job(conn, now: dt.datetime | None = None) -> dict:
    """Every-Monday job: every is_test=1, status='active' post gets one vote from every demo
    voter who hasn't already voted on it (the top-up rule -- a demo voter votes on a given post
    exactly once, ever). Idempotent per (demo_user, post) -- re-running after everyone eligible
    has already voted a post changes nothing for that post.

    Calls board_core.settle() once, explicitly, up front -- cast_vote() already calls settle()
    internally on every single call, but relying on that as the ONLY trigger would mean a fully-
    voted test post sits in 'active' status, hidden from real members, until something else
    happens to read or vote on it again. Settling explicitly here means a closed voting window
    is processed on this job's own schedule, not as an accidental side effect of vote casting."""
    import board_core

    now = now or dt.datetime.now(dt.timezone.utc)
    window = active_window(conn, now)
    if window is None:
        print("[test_cycle] WARNING: weekly_vote_job -- no active post_testing window, exiting")
        return {"ran": False, "reason": "no active window", "cast": 0, "skipped": 0, "errors": []}

    board_core.settle(conn, now)
    vote_distribution = json.loads(window["vote_distribution"])
    voters = _demo_voters(conn)
    posts = conn.execute("SELECT id FROM board_posts WHERE is_test = 1 AND status = 'active'").fetchall()

    cast, skipped, errors = 0, 0, []
    for post in posts:
        for user_id in voters:
            already = conn.execute(
                "SELECT 1 FROM board_votes WHERE post_id = ? AND user_id = ? LIMIT 1", (post["id"], user_id)
            ).fetchone()
            if already:
                skipped += 1
                continue
            try:
                row = conn.execute("SELECT present_location_json FROM users WHERE id = ?", (user_id,)).fetchone()
                present_location = json.loads(row["present_location_json"])
                value = _random_vote(vote_distribution)
                board_core.cast_vote(conn, user_id, present_location, post["id"], value, now=now)
                cast += 1
            except Exception as e:
                print(f"[test_cycle] ERROR: weekly_vote_job -- vote failed for demo user {user_id} on post {post['id']}: {e}")
                errors.append({"user_id": user_id, "post_id": post["id"], "error": str(e)})
                continue

    print(f"[test_cycle] INFO: weekly_vote_job -- cast {cast} vote(s), skipped {skipped} "
          f"(already voted), {len(errors)} error(s)")
    return {"ran": True, "cast": cast, "skipped": skipped, "errors": errors}


# ---- Cron wiring -----------------------------------------------------------------------------

def init_scheduler(app) -> None:
    """Registers the monthly post job (1st of the month) and the weekly vote job (every Monday)
    on their OWN BackgroundScheduler instance, 2 hours offset from pipeline_scheduler's 00:00
    IST tick (not a correctness requirement -- the two run on separate scheduler instances with
    no shared state -- just avoids both ticks' log lines landing at the same timestamp). Skipped
    entirely when QM_DISABLE_SCHEDULER is set, same env var pipeline_scheduler.py already uses
    for the same purpose (tests/tools)."""
    if os.environ.get("QM_DISABLE_SCHEDULER"):
        print("[test_cycle] QM_DISABLE_SCHEDULER set -- test-cycle cron not registered")
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from db import get_db

        def _monthly():
            conn = get_db()
            try:
                monthly_post_job(conn)
            finally:
                conn.close()

        def _weekly():
            conn = get_db()
            try:
                weekly_vote_job(conn)
            finally:
                conn.close()

        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(_monthly, CronTrigger(day=1, hour=2, minute=0))
        scheduler.add_job(_weekly, CronTrigger(day_of_week="mon", hour=2, minute=0))
        scheduler.start()
        print("[test_cycle] monthly post job registered for day 1, 02:00 Asia/Kolkata; "
              "weekly vote job registered for Monday 02:00 Asia/Kolkata")
