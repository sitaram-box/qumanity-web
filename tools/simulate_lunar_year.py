"""Phase 5 accelerated simulation: compresses ~9 lunar cycles (roughly 9 months of real time)
into a fast, isolated run by calling daily_pipeline_tick() once per simulated day, with
simulate_date advancing instead of real sleep. Builds its own isolated DB + fake 0_Earth scaffold
under /tmp -- never touches the real local DB or the real 0_Earth tree (Safety Rule 3).

Run with:
    python3 tools/simulate_lunar_year.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tmp_ctx = tempfile.TemporaryDirectory()
TMP = Path(_tmp_ctx.name)
DB_PATH = TMP / "simulate_lunar_year.db"
EARTH_ROOT = TMP / "0_Earth_sim"

os.environ["QM_DB_PATH"] = str(DB_PATH)
os.environ["QM_EARTH_ROOT"] = str(EARTH_ROOT)
os.environ["QM_DISABLE_SCHEDULER"] = "1"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sqlite3

import archive_writer
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
N_CYCLES = 9
ROWS_PER_CYCLE_TARGET = 50  # ~17 per user x 3 users, recommended and proceeded with (see report)


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
    conn.commit()
    return conn


def _seed_users(conn) -> dict[int, int]:
    """Returns {user_id: wallet_id} -- one wallet per user, created once and reused across every
    cycle's activity (matching wallet_core.ensure_wallet's own get-or-create convention; wallets
    has UNIQUE(owner_type, owner_id), so a fresh INSERT per cycle would violate it)."""
    loc_json = json.dumps(LOCATION)
    wallets: dict[int, int] = {}
    for i, element in enumerate(["Fire", "Water", "Earth"]):
        cur = conn.execute(
            "INSERT INTO users (name,gender,dob,tob,birth_location_json,present_location_json,private_id,account_id) VALUES (?,?,?,?,?,?,?,?)",
            (f"Sim User {i}", "male" if i % 2 == 0 else "female", "1990-01-01", "08:00", loc_json, loc_json, f"SIMPRIV-{i}", f"SIMACC-{i}"),
        )
        uid = cur.lastrowid
        conn.execute("INSERT INTO user_zodiac (user_id, sun_sign, sun_element) VALUES (?, 'Aries', ?)", (uid, element))
        wcur = conn.execute("INSERT INTO wallets (owner_type,owner_id,balance_qoins) VALUES ('user', ?, 0)", (str(uid),))
        wallets[uid] = wcur.lastrowid
    conn.commit()
    return wallets


_search_code_counter = [0]  # module-level, monotonic -- guarantees unique account_ids.search_code
                            # across every (user, cycle) pair seeded in one run


def _seed_cycle_activity(conn, uids: list[int], wallets: dict[int, int], cycle_id: str, target_rows: int) -> int:
    """~target_rows spread across karma_entries, board_posts/votes/comments, wallet_transactions,
    account_ids and app_reviews -- all at pipeline_level='village'."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    n = 0
    per_user_karma = max(1, target_rows // 2 // len(uids))
    for uid in uids:
        for _ in range(per_user_karma):
            conn.execute("INSERT INTO karma_entries (user_id,kind,points,reason,created_at,cycle_id,pipeline_level) VALUES (?, 'noncommercial', 5, 's', ?, ?, 'village')", (uid, now, cycle_id))
            n += 1

    chain = json.dumps([{"level": "village", "id": VILLAGE_ID, "name": "Rohini Sector 24"}])
    for i in range(3):
        cur = conn.execute(
            "INSERT INTO board_posts (author_id,level,group_id,group_name,content,status,score,voting_start,voting_end,chain_json,created_at,cycle_id,pipeline_level) "
            "VALUES (?, 'village', ?, 'Rohini Sector 24', ?, 'frozen', 3, ?, ?, ?, ?, ?, 'village')",
            (uids[i % len(uids)], VILLAGE_ID, f"Sim post {i} for {cycle_id}", now, now, chain, now, cycle_id),
        )
        n += 1
        post_id = cur.lastrowid
        for uid in uids:
            conn.execute("INSERT INTO board_votes (post_id,user_id,value,cycle_id,pipeline_level) VALUES (?,?,1,?,'village')", (post_id, uid, cycle_id))
            n += 1
        conn.execute("INSERT INTO board_comments (post_id,user_id,text,created_at,cycle_id,pipeline_level) VALUES (?,?, 'nice', ?, ?, 'village')", (post_id, uids[0], now, cycle_id))
        n += 1

    for uid in uids:
        conn.execute("INSERT INTO wallet_transactions (wallet_id,amount_qoins,reason,cycle_id,pipeline_level) VALUES (?, 10, 's', ?, 'village')", (wallets[uid], cycle_id))
        n += 1
        _search_code_counter[0] += 1
        conn.execute("INSERT INTO account_ids (user_id,account_id,search_code,present_location_json,is_current,created_at,cycle_id,pipeline_level) VALUES (?, ?, ?, ?, 0, ?, ?, 'village')",
                     (uid, f"SIMACC-{uid}-{cycle_id}", f"{900000000000 + _search_code_counter[0]:012d}", json.dumps(LOCATION), now, cycle_id))
        n += 1

    # app_reviews.user_id is UNIQUE (one review per member, ever -- review_core.py's own rule),
    # so only ONE of the 9 cycles can seed a review per user; use a different user each cycle.
    review_user = uids[_search_code_counter[0] % len(uids)]
    if not conn.execute("SELECT 1 FROM app_reviews WHERE user_id = ?", (review_user,)).fetchone():
        conn.execute("INSERT INTO app_reviews (user_id,rating,text,allow_public,source,created_at,cycle_id,pipeline_level) VALUES (?, 5, ?, 0, 'app', ?, ?, 'village')",
                     (review_user, f"Review for {cycle_id}", now, cycle_id))
        n += 1

    conn.commit()
    return n


def _total_remaining_rows(conn, cycle_id: str) -> int:
    return sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE cycle_id=?", (cycle_id,)).fetchone()[0] for t in cycle_middleware.STAMPED_TABLES)


def _archived_record_count(conn, cycle_id: str) -> int:
    status = archive_writer.archive_status(conn, cycle_id)
    return status["records_deleted"] if status["archived"] else 0


def main() -> None:
    print("=" * 70)
    print(f"Isolated test DB: {DB_PATH}")
    print(f"Isolated 0_Earth: {EARTH_ROOT}")
    print(f"Simulating {N_CYCLES} lunar cycles, ~{ROWS_PER_CYCLE_TARGET} rows/cycle, 3 users")
    print("=" * 70)

    _scaffold_earth_tree()
    conn = _build_db()
    wallets = _seed_users(conn)
    uids = list(wallets)

    # Pick N_CYCLES real, consecutive cycles starting from "today" (whatever the real current
    # cycle is). Tracks each window's (start, mid, end) DIRECTLY via the same private helper
    # get_current_cycle_id() uses internally (lunar_calendar._amavasya_window), never by
    # round-tripping through get_cycle_dates(name) -- that round-trip is lossy whenever a Vedic
    # month's own Purnima lands in the same Gregorian year twice (the adhik-maas-adjacent
    # collision documented in pipeline_scheduler._window_for_moment / docs/phase_5_report.md) and
    # would silently resolve to the WRONG occurrence. A real such collision is exactly what this
    # script's own first draft hit while under development.
    def _window(moment):
        a_jd, mid_jd, end_jd = lunar_calendar._amavasya_window(moment)
        to_ist = lambda jd: lunar_calendar._jd_to_utc(jd).astimezone(lunar_calendar.IST)
        return to_ist(a_jd), to_ist(mid_jd), to_ist(end_jd)

    cursor = dt.datetime.now(lunar_calendar.IST)
    cycle_ids, windows = [], []
    seen_labels = set()
    while len(cycle_ids) < N_CYCLES:
        start, mid, end = _window(cursor)
        label = lunar_calendar.get_current_cycle_id(cursor)
        if label in seen_labels:
            raise RuntimeError(
                f"Cycle label collision: {label} appeared twice in this {N_CYCLES}-cycle window "
                f"(a real adhik-maas-adjacent naming ambiguity in lunar_calendar.py -- see "
                f"docs/phase_5_report.md). Re-run from a different starting date to avoid it."
            )
        seen_labels.add(label)
        cycle_ids.append(label)
        windows.append((start, mid, end))
        cursor = end + dt.timedelta(days=1)
    print(f"\nCycles (oldest to newest): {cycle_ids}")

    total_seeded = 0
    for cid in cycle_ids:
        n = _seed_cycle_activity(conn, uids, wallets, cid, ROWS_PER_CYCLE_TARGET)
        total_seeded += n
        print(f"  seeded {n} rows for {cid}")

    # Bootstrap: activate essentially immediately (year_2_start = the first cycle's own start),
    # so this simulation exercises the PIPELINE, not the Year-1 wait -- that's already verified
    # separately in tools/verify_scheduler.py.
    sim_start = windows[0][0]
    sim_end = windows[-1][2] + dt.timedelta(days=2)
    conn.execute("DELETE FROM pipeline_bootstrap")
    conn.execute(
        "INSERT INTO pipeline_bootstrap (year_1_start_amavasya, year_2_start_amavasya, pipeline_active) VALUES (?, ?, 0)",
        (sim_start.isoformat(), sim_start.isoformat()),
    )
    conn.commit()

    # Walk the clock forward one simulated day at a time across the whole span.
    now = sim_start
    tick_count = 0
    activity_log = []
    while now <= sim_end:
        r = pipeline_scheduler.daily_pipeline_tick(conn, simulate_date=now.isoformat())
        tick_count += 1
        if r["actions"]:
            for a in r["actions"]:
                activity_log.append((now.date().isoformat(), a["cycle_id"], a["from_level"], a.get("to_level"), a.get("result", {}).get("status", a.get("result"))))
        now += dt.timedelta(days=1)

    print(f"\nRan {tick_count} daily ticks covering {(sim_end - sim_start).days} days.")
    print(f"\n{'Date':<12} {'Cycle':<16} {'Hop':<20} {'Result'}")
    print("-" * 70)
    for date, cid, frm, to, status in activity_log:
        print(f"{date:<12} {cid:<16} {frm + '->' + str(to):<20} {status}")

    # --- Verification ---
    print()
    print("=" * 70)
    print("Final state per cycle")
    print("=" * 70)
    results = []
    final_states = {}
    for cid in cycle_ids:
        remaining = _total_remaining_rows(conn, cid)
        status = archive_writer.archive_status(conn, cid)
        if status["archived"]:
            state = "archived (0_Earth)"
        elif remaining > 0:
            levels = {r[0] for t in cycle_middleware.STAMPED_TABLES for r in conn.execute(f"SELECT DISTINCT pipeline_level FROM {t} WHERE cycle_id=?", (cid,))}
            state = f"in DB at level(s): {sorted(levels)}"
        else:
            state = "no data (never seeded or already gone)"
        final_states[cid] = state
        print(f"  {cid}: {state}")

    oldest, second = cycle_ids[0], cycle_ids[1]
    results.append((f"Cycle 1 ({oldest}) reached 0_Earth archive", "archived" in final_states[oldest]))
    results.append((f"Cycle 2 ({second}) progressed beyond village (not stuck)", "village" not in final_states[second] or "archived" in final_states[second]))

    # No data lost: every row ever seeded is either still in the DB (at some pipeline_level) or
    # accounted for in an archive's own recorded records_deleted count.
    total_accounted = 0
    for cid in cycle_ids:
        remaining = _total_remaining_rows(conn, cid)
        archived_count = _archived_record_count(conn, cid)
        total_accounted += remaining + archived_count
    print(f"\nTotal rows seeded: {total_seeded}; total rows accounted for (DB + archived): {total_accounted}")
    results.append(("No data lost (seeded == DB-remaining + archived)", total_seeded == total_accounted))

    conn.close()

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
