"""Phase 3 of the lunar-cycle archival system: the aggregation + transfer engine. Raw activity
rows physically move up the pipeline one level per lunar cycle (`pipeline_level`, added by
migration 007 to the same 28 tables Phase 2 stamped with `cycle_id`); an aggregate snapshot is
computed and stored in `level_holdings` at each hop. See docs/lunar_cycle_system.md and
docs/phase_3_report.md for the full design and the deviations from the original spec explained
there (country/zone sentiment's own native level; India-only scope; how parent ids are derived).

This module does NOT run on a schedule, does NOT write to 0_Earth, and never fires automatically
-- every transfer is triggered manually, via the admin endpoints in app.py. It also never touches
`lunar_calendar.py` or `cycle_middleware.py` -- it only READS cycle_state through
cycle_middleware.history() to enforce the N/N-1 safety rule.

**India-only scope (confirmed, 2026-10-05)**: every registered user today is India-based with the
full village/tehsil/district/state/zone chain (checked against the real DB before building this).
Aggregation and parent-id derivation below assume that chain; a row whose acting user lacks it
(not possible today) is simply excluded from any holding, counted separately as
"excluded_no_chain", rather than guessed at -- a known limitation, not a silent bug, see
docs/phase_3_report.md.
"""
from __future__ import annotations

import datetime as dt
import json as _json
from pathlib import Path

import cycle_middleware

PIPELINE_LEVELS = ["village", "tehsil", "district", "state", "zone", "country", "continent", "earth"]
INDIA_COUNTRY_ID = "O_AS_IND"
INDIA_CONTINENT_ID = "O_AS"
EARTH_ID = "EARTH"

_STATIC_DIR = Path(__file__).resolve().parent / "static" / "data"
_SEGMENTS = {"state": 2, "district": 3, "tehsil": 4, "village": 5}  # dot-segment count in an India location id

SCHEMA = """
CREATE TABLE IF NOT EXISTS level_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level VARCHAR(20) NOT NULL,
    level_id VARCHAR(50) NOT NULL,
    cycle_id VARCHAR(50) NOT NULL,
    summary_json TEXT NOT NULL,
    source_ids TEXT,
    record_counts TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(level, level_id, cycle_id)
);
CREATE INDEX IF NOT EXISTS idx_holding_level_cycle ON level_holdings(level, cycle_id);
CREATE INDEX IF NOT EXISTS idx_holding_level_id ON level_holdings(level_id);

CREATE TABLE IF NOT EXISTS transfer_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_level VARCHAR(20) NOT NULL,
    to_level VARCHAR(20) NOT NULL,
    cycle_id VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    records_moved INTEGER DEFAULT 0,
    holdings_created INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'in_progress',
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_transfer_log_cycle ON transfer_log(cycle_id);
CREATE INDEX IF NOT EXISTS idx_transfer_log_status ON transfer_log(status);

CREATE TABLE IF NOT EXISTS pipeline_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_transfer_level VARCHAR(20),
    last_transfer_cycle_id VARCHAR(50),
    last_transfer_completed_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO pipeline_state (id) VALUES (1)")
    conn.commit()


# ---- India hierarchy helpers -----------------------------------------------------------------
# Village/tehsil/district/state ids are dot-encoded (e.g. "CS.DL.3.4.1A" = state.district.tehsil.
# village), so an ancestor id is just a prefix truncation; zone needs one small reverse index
# (zone ids, e.g. "IND/CS", aren't a prefix of their states' ids). Country/continent/earth are
# fixed constants under the India-only scope.

_state_to_zone_cache: dict[str, str] | None = None


def _india_states_data() -> dict:
    return _json.loads((_STATIC_DIR / "india_states.json").read_text(encoding="utf-8"))


def _india_districts_data() -> dict:
    return _json.loads((_STATIC_DIR / "india_districts_tehsils.json").read_text(encoding="utf-8"))


def _state_to_zone(state_id: str | None) -> str | None:
    global _state_to_zone_cache
    if not state_id:
        return None
    if _state_to_zone_cache is None:
        data = _india_states_data()
        _state_to_zone_cache = {s["id"]: z["id"] for z in data["zones"] for s in z["states"]}
    return _state_to_zone_cache.get(state_id)


def _truncate_id(location_id: str, from_level: str, to_level: str) -> str | None:
    if from_level not in _SEGMENTS or to_level not in _SEGMENTS:
        return None
    if _SEGMENTS[to_level] > _SEGMENTS[from_level]:
        return None
    parts = location_id.split(".")
    if len(parts) < _SEGMENTS[to_level]:
        return None
    return ".".join(parts[: _SEGMENTS[to_level]])


def _ancestor_id(native_id: str | None, native_level: str, target_level: str) -> str | None:
    """The id of `native_id`'s ancestor at `target_level`, India-only scope. None if not
    derivable (target is finer than native, or the id doesn't parse)."""
    if not native_id or native_level not in PIPELINE_LEVELS or target_level not in PIPELINE_LEVELS:
        return None
    if native_level == target_level:
        return native_id
    if target_level == "earth":
        return EARTH_ID
    if target_level == "continent":
        return INDIA_CONTINENT_ID
    if target_level == "country":
        return INDIA_COUNTRY_ID
    if native_level in ("earth", "continent", "country"):
        return None  # can't derive a finer level from a coarser one
    if target_level == "zone":
        state_id = native_id if native_level == "state" else _truncate_id(native_id, native_level, "state")
        return _state_to_zone(state_id)
    if native_level == "zone":
        return None
    return _truncate_id(native_id, native_level, target_level)


def get_child_level_ids(conn, level: str, level_id: str) -> list[str]:
    """Children of `level_id` one tier down -- for admin display / Phase 4 reference. NOT used by
    transfer_level()'s own aggregation, which derives parent ids directly from which rows actually
    have data this cycle (see _ancestor_counts) rather than walking the static hierarchy first --
    that way a holding is only ever created where real data exists."""
    if level == "village":
        return [level_id]
    if level == "tehsil":
        return [r[0] for r in conn.execute("SELECT id FROM india_villages WHERE tehsil_id = ?", (level_id,))]
    if level == "district":
        state_id = _truncate_id(level_id, "district", "state")
        for d in _india_districts_data()["states"].get(state_id, {}).get("districts", []):
            if d["id"] == level_id:
                return [t["id"] for t in d.get("tehsils", [])]
        return []
    if level == "state":
        return [d["id"] for d in _india_districts_data()["states"].get(level_id, {}).get("districts", [])]
    if level == "zone":
        for z in _india_states_data()["zones"]:
            if z["id"] == level_id:
                return [s["id"] for s in z["states"]]
        return []
    if level == "country":
        return [z["id"] for z in _india_states_data()["zones"]] if level_id == INDIA_COUNTRY_ID else []
    if level == "continent":
        return [INDIA_COUNTRY_ID] if level_id == INDIA_CONTINENT_ID else []
    if level == "earth":
        return [INDIA_CONTINENT_ID]
    return []


# ---- Per-table location resolution ------------------------------------------------------------
# Every table's rows are reduced to (native_level, native_location_id) pairs. Most tables have a
# single fixed native level ("village" for most activity, "country"/"zone" for sentiment votes,
# which were never "at village" -- see Decision 3 / docs/phase_3_report.md); a handful carry their
# OWN varying level per row already (board_posts/votes/comments via the post's own group_id+level,
# collective_karma_log's own location_id+location_level, wallet_transactions via the wallet's own
# owner_type/owner_id when it's a location wallet rather than a user's).

_FIXED_LEVEL_SQL = {
    "election_candidates": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM election_candidates t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "election_votes": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM election_votes t JOIN users u ON u.id=t.voter_user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "karma_entries": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM karma_entries t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "business_ratings": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM business_ratings t JOIN users u ON u.id=t.provider_user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "board_messages": ("village", "SELECT sg.village_id FROM board_messages t JOIN subgroups sg ON sg.id=t.subgroup_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "personal_messages": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM personal_messages t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "private_messages": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM private_messages t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "account_ids": ("village", "SELECT json_extract(present_location_json,'$.village.id') FROM account_ids WHERE cycle_id=? AND pipeline_level=?"),
    "people_requests": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM people_requests t JOIN users u ON u.id=t.from_user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "account_id_requests": ("village", "SELECT json_extract(present_location_json,'$.village.id') FROM account_id_requests WHERE cycle_id=? AND pipeline_level=?"),
    "payment_orders": ("village", "SELECT json_extract(present_location_json,'$.village.id') FROM payment_orders WHERE cycle_id=? AND pipeline_level=?"),
    "country_sentiment": ("country", "SELECT country_id FROM country_sentiment WHERE cycle_id=? AND pipeline_level=?"),
    "zone_sentiment": ("zone", "SELECT zone_id FROM zone_sentiment WHERE cycle_id=? AND pipeline_level=?"),
    "app_reviews": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM app_reviews t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "profile_change_requests": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM profile_change_requests t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "volunteers": ("village", "SELECT group_id FROM volunteers WHERE cycle_id=? AND pipeline_level=?"),
    "referrer_applications": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM referrer_applications t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "subgroups": ("village", "SELECT village_id FROM subgroups WHERE cycle_id=? AND pipeline_level=?"),
    "personal_groups": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM personal_groups t JOIN users u ON u.id=t.owner_user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "private_chats": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM private_chats t JOIN users u ON u.id=t.user_lo WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "subgroup_members": ("village", "SELECT sg.village_id FROM subgroup_members t JOIN subgroups sg ON sg.id=t.subgroup_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "personal_group_members": ("village", "SELECT json_extract(u.present_location_json,'$.village.id') FROM personal_group_members t JOIN personal_groups g ON g.id=t.group_id JOIN users u ON u.id=g.owner_user_id WHERE t.cycle_id=? AND t.pipeline_level=?"),
    "message_reactions": ("village", """
        SELECT CASE WHEN t.scope='subgroup' THEN sg.village_id ELSE json_extract(u2.present_location_json,'$.village.id') END
        FROM message_reactions t
        LEFT JOIN board_messages bm ON t.scope='subgroup' AND bm.id=t.message_id
        LEFT JOIN subgroups sg ON sg.id=bm.subgroup_id
        LEFT JOIN personal_messages pm ON t.scope='personal' AND pm.id=t.message_id
        LEFT JOIN personal_groups pg ON pg.id=pm.group_id
        LEFT JOIN users u2 ON u2.id=pg.owner_user_id
        WHERE t.cycle_id=? AND t.pipeline_level=?"""),
}

_VARYING_LEVEL_SQL = {
    "collective_karma_log": "SELECT location_id AS loc_id, location_level AS loc_level FROM collective_karma_log WHERE cycle_id=? AND pipeline_level=?",
    "board_posts": "SELECT group_id AS loc_id, level AS loc_level FROM board_posts WHERE cycle_id=? AND pipeline_level=?",
    "board_votes": "SELECT p.group_id AS loc_id, p.level AS loc_level FROM board_votes t JOIN board_posts p ON p.id=t.post_id WHERE t.cycle_id=? AND t.pipeline_level=?",
    "board_comments": "SELECT p.group_id AS loc_id, p.level AS loc_level FROM board_comments t JOIN board_posts p ON p.id=t.post_id WHERE t.cycle_id=? AND t.pipeline_level=?",
    "wallet_transactions": """
        SELECT CASE WHEN w.owner_type='user' THEN json_extract(u.present_location_json,'$.village.id') ELSE w.owner_id END AS loc_id,
               CASE WHEN w.owner_type='user' THEN 'village' ELSE w.owner_type END AS loc_level
        FROM wallet_transactions t JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN users u ON w.owner_type='user' AND u.id = CAST(w.owner_id AS INTEGER)
        WHERE t.cycle_id=? AND t.pipeline_level=?""",
}

assert set(_FIXED_LEVEL_SQL) | set(_VARYING_LEVEL_SQL) == set(cycle_middleware.STAMPED_TABLES), \
    "pipeline_core's table resolvers must cover exactly the 28 Phase-2-stamped tables"


def _resolve_all(conn, cycle_id: str, pipeline_level: str) -> dict[str, list[tuple[str, str]]]:
    """{table: [(native_level, native_location_id), ...]} for every row of every table currently
    sitting at `pipeline_level` for `cycle_id`. One query per table (28 total), not per location --
    avoids any N+1 pattern regardless of how many villages/tehsils end up involved."""
    out: dict[str, list[tuple[str, str]]] = {}
    for table, (native_level, sql) in _FIXED_LEVEL_SQL.items():
        rows = conn.execute(sql, (cycle_id, pipeline_level)).fetchall()
        out[table] = [(native_level, r[0]) for r in rows if r[0] is not None]
    for table, sql in _VARYING_LEVEL_SQL.items():
        rows = conn.execute(sql, (cycle_id, pipeline_level)).fetchall()
        out[table] = [(r["loc_level"], r["loc_id"]) for r in rows if r["loc_id"] is not None and r["loc_level"] is not None]
    return out


def _ancestor_counts(resolved: dict[str, list[tuple[str, str]]], target_level: str) -> dict[str, dict[str, int]]:
    """{ancestor_id: {table: count}} across every table, plus how many rows couldn't be resolved
    (excluded_no_chain) -- derives WHICH locations have holdings directly from the data, rather
    than walking the static hierarchy and checking each one."""
    out: dict[str, dict[str, int]] = {}
    for table, entries in resolved.items():
        for native_level, native_id in entries:
            anc = _ancestor_id(native_id, native_level, target_level)
            if anc is None:
                out.setdefault("__excluded_no_chain__", {}).setdefault(table, 0)
                out["__excluded_no_chain__"][table] += 1
                continue
            out.setdefault(anc, {}).setdefault(table, 0)
            out[anc][table] += 1
    return out


def _source_ids_for(resolved: dict[str, list[tuple[str, str]]], to_level: str, level_id: str) -> list[str]:
    idx = PIPELINE_LEVELS.index(to_level)
    from_level = PIPELINE_LEVELS[idx - 1] if idx > 0 else None
    ids: set[str] = set()
    if from_level:
        for entries in resolved.values():
            for native_level, native_id in entries:
                if _ancestor_id(native_id, native_level, to_level) == level_id:
                    child = _ancestor_id(native_id, native_level, from_level)
                    if child:
                        ids.add(child)
    return sorted(ids)


_FRIENDLY_ALIASES = {
    "posts": "board_posts", "votes": "board_votes", "comments": "board_comments",
    "wallet_transactions": "wallet_transactions", "karma_entries": "karma_entries",
    "payment_orders": "payment_orders", "reviews": "app_reviews",
}
_CHAT_MESSAGE_TABLES = ("board_messages", "personal_messages", "private_messages")
_GROUP_JOIN_TABLES = ("subgroup_members", "personal_group_members")
_GROUP_CREATE_TABLES = ("subgroups", "personal_groups")


def _friendly_counts(table_counts: dict[str, int]) -> dict[str, int]:
    out = {name: table_counts.get(table, 0) for name, table in _FRIENDLY_ALIASES.items()}
    out["chat_messages"] = sum(table_counts.get(t, 0) for t in _CHAT_MESSAGE_TABLES)
    out["group_joins"] = sum(table_counts.get(t, 0) for t in _GROUP_JOIN_TABLES)
    out["group_creates"] = sum(table_counts.get(t, 0) for t in _GROUP_CREATE_TABLES)
    used = set(_FRIENDLY_ALIASES.values()) | set(_CHAT_MESSAGE_TABLES) | set(_GROUP_JOIN_TABLES) | set(_GROUP_CREATE_TABLES)
    for table in cycle_middleware.STAMPED_TABLES:
        if table not in used:
            out[table] = table_counts.get(table, 0)
    return out


def _karma_detail(conn, cycle_id: str, pipeline_level: str) -> list[dict]:
    """karma_entries joined to users/user_zodiac once per aggregate call -- top_contributors,
    by_element and karma_total_value all derive from this single result set (no N+1 queries)."""
    sql = """SELECT k.user_id AS user_id, u.name AS name, k.points AS points,
                    json_extract(u.present_location_json,'$.village.id') AS village_id,
                    z.sun_element AS element
             FROM karma_entries k JOIN users u ON u.id = k.user_id
             LEFT JOIN user_zodiac z ON z.user_id = u.id
             WHERE k.cycle_id = ? AND k.pipeline_level = ?"""
    return [dict(r) for r in conn.execute(sql, (cycle_id, pipeline_level)).fetchall()]


def _qoins_circulating(conn, level: str, level_id: str) -> int:
    """Current total Qoins balance of every user whose present village rolls up to `level_id` --
    a point-in-time snapshot of the CURRENT balance, not a per-cycle delta (wallets don't carry a
    cycle_id; wallet_transactions does, but a balance is cumulative by nature)."""
    rows = conn.execute(
        """SELECT w.balance_qoins AS bal, json_extract(u.present_location_json,'$.village.id') AS village_id
           FROM wallets w JOIN users u ON u.id = CAST(w.owner_id AS INTEGER)
           WHERE w.owner_type = 'user'"""
    ).fetchall()
    return sum(r["bal"] or 0 for r in rows if _ancestor_id(r["village_id"], "village", level) == level_id)


def _build_summary(conn, level: str, level_id: str, cycle_id: str, table_counts: dict[str, int]) -> dict:
    karma_rows = _karma_detail(conn, cycle_id, level)
    matching = [r for r in karma_rows if _ancestor_id(r["village_id"], "village", level) == level_id]

    by_user: dict[int, dict] = {}
    by_element = {"fire": 0, "earth": 0, "air": 0, "water": 0}
    for r in matching:
        u = by_user.setdefault(r["user_id"], {"user_id": r["user_id"], "name": r["name"], "karma": 0})
        u["karma"] += r["points"]
        el = (r["element"] or "").lower()
        if el in by_element:
            by_element[el] += r["points"]
    top_contributors = sorted(by_user.values(), key=lambda u: u["karma"], reverse=True)[:10]

    return {
        "cycle_id": cycle_id,
        "level": level,
        "level_id": level_id,
        "counts": _friendly_counts(table_counts),
        "totals": {
            "qoins_circulating": _qoins_circulating(conn, level, level_id),
            "karma_total_value": sum(r["points"] for r in matching),
        },
        "top_contributors": top_contributors,
        "by_element": by_element,
        "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def aggregate_level(conn, level: str, level_id: str, cycle_id: str) -> dict:
    resolved = _resolve_all(conn, cycle_id, level)
    table_counts = _ancestor_counts(resolved, level).get(level_id, {})
    summary = _build_summary(conn, level, level_id, cycle_id, table_counts)
    summary["source_ids"] = _source_ids_for(resolved, level, level_id)
    return summary


# ---- Safety rule: only cycle N-2 and older ---------------------------------------------------

def _n_and_n_minus_1(conn) -> tuple[str | None, str | None]:
    """N = cycle_state's current active cycle; N-1 = the most recently closed one, if any has
    ever been recorded (Year 1 bootstrap means there may be none yet -- cycle_state has only ever
    had ITS OWN self-seeded active row since Phase 2, with no real transitions). If N-1 has never
    existed, there is nothing to protect besides N itself."""
    hist = cycle_middleware.history(conn, limit=20)
    active = next((h for h in hist if h["status"] == "active"), None)
    n = active["cycle_id"] if active else None
    closed = [h for h in hist if h["status"] == "closed"]
    n_minus_1 = closed[0]["cycle_id"] if closed else None
    return n, n_minus_1


def _check_safety(conn, cycle_id: str) -> None:
    n, n_minus_1 = _n_and_n_minus_1(conn)
    if cycle_id == n:
        raise PermissionError(f"Cycle {cycle_id} is the ACTIVE cycle (N) -- never pipeline-eligible.")
    if n_minus_1 and cycle_id == n_minus_1:
        raise PermissionError(f"Cycle {cycle_id} is the previous cycle (N-1) -- kept live for continuity, never pipeline-eligible.")


def get_eligible_cycles_for_pipeline(conn) -> list[str]:
    """Every cycle_id with real activity data, excluding N and (if it has ever existed) N-1."""
    n, n_minus_1 = _n_and_n_minus_1(conn)
    exclude = {c for c in (n, n_minus_1) if c}
    found: set[str] = set()
    for table in cycle_middleware.STAMPED_TABLES:
        for r in conn.execute(f"SELECT DISTINCT cycle_id FROM {table} WHERE cycle_id IS NOT NULL"):
            found.add(r[0])
    return sorted(found - exclude)


# ---- Transfer log / pipeline_state bookkeeping ------------------------------------------------

def _log_start(conn, from_level: str, to_level: str, cycle_id: str) -> int:
    cur = conn.execute(
        "INSERT INTO transfer_log (from_level, to_level, cycle_id, status) VALUES (?, ?, ?, 'in_progress')",
        (from_level, to_level, cycle_id),
    )
    conn.commit()
    return cur.lastrowid


def _log_complete(conn, log_id: int, records_moved: int, holdings_created: int) -> None:
    conn.execute(
        "UPDATE transfer_log SET status='completed', completed_at=CURRENT_TIMESTAMP, records_moved=?, holdings_created=? WHERE id=?",
        (records_moved, holdings_created, log_id),
    )
    conn.commit()


def _log_error(conn, log_id: int, message: str) -> None:
    conn.execute(
        "UPDATE transfer_log SET status='failed', completed_at=CURRENT_TIMESTAMP, error_message=? WHERE id=?",
        (message, log_id),
    )
    conn.commit()


def _update_pipeline_state(conn, to_level: str, cycle_id: str) -> None:
    conn.execute(
        "UPDATE pipeline_state SET last_transfer_level=?, last_transfer_cycle_id=?, "
        "last_transfer_completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=1",
        (to_level, cycle_id),
    )
    conn.commit()


def _upsert_holding(conn, level: str, level_id: str, cycle_id: str, summary: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO level_holdings (level, level_id, cycle_id, summary_json, source_ids, record_counts, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(level, level_id, cycle_id) DO UPDATE SET
               summary_json=excluded.summary_json, source_ids=excluded.source_ids,
               record_counts=excluded.record_counts, updated_at=excluded.updated_at""",
        (level, level_id, cycle_id, _json.dumps(summary), _json.dumps(summary.get("source_ids")),
         _json.dumps(summary.get("counts")), now, now),
    )


# ---- Transfer execution -----------------------------------------------------------------------

def transfer_level(conn, from_level: str, to_level: str, cycle_id: str) -> dict:
    """Executes one hop. Idempotent: re-running after rows are already at `to_level` moves 0 rows
    (the UPDATE's WHERE no longer matches anything) and re-upserts the same holdings (no
    duplicates, ON CONFLICT handles it) -- see Decision 7 / docs/phase_3_report.md."""
    if from_level not in PIPELINE_LEVELS or to_level not in PIPELINE_LEVELS:
        raise ValueError(f"Unknown pipeline level: {from_level} -> {to_level}")
    if PIPELINE_LEVELS.index(to_level) != PIPELINE_LEVELS.index(from_level) + 1:
        raise ValueError(f"{from_level} -> {to_level} is not an adjacent hop")
    _check_safety(conn, cycle_id)
    ensure_tables(conn)
    log_id = _log_start(conn, from_level, to_level, cycle_id)
    try:
        records_moved = 0
        for table in cycle_middleware.STAMPED_TABLES:
            cur = conn.execute(
                f"UPDATE {table} SET pipeline_level = ? WHERE cycle_id = ? AND pipeline_level = ?",
                (to_level, cycle_id, from_level),
            )
            records_moved += cur.rowcount
        conn.commit()

        resolved = _resolve_all(conn, cycle_id, to_level)
        counts_by_parent = _ancestor_counts(resolved, to_level)
        holdings_created = 0
        for level_id, table_counts in counts_by_parent.items():
            if level_id == "__excluded_no_chain__":
                continue
            summary = _build_summary(conn, to_level, level_id, cycle_id, table_counts)
            summary["source_ids"] = _source_ids_for(resolved, to_level, level_id)
            _upsert_holding(conn, to_level, level_id, cycle_id, summary)
            holdings_created += 1
        conn.commit()

        _log_complete(conn, log_id, records_moved, holdings_created)
        _update_pipeline_state(conn, to_level, cycle_id)
        excluded = sum(counts_by_parent.get("__excluded_no_chain__", {}).values())
        print(f"[pipeline] {from_level} -> {to_level} for {cycle_id}: {records_moved} records moved, "
              f"{holdings_created} holdings upserted, {excluded} rows excluded (no full India chain)")
        return {"from_level": from_level, "to_level": to_level, "cycle_id": cycle_id,
                "records_moved": records_moved, "holdings_created": holdings_created, "excluded_no_chain": excluded}
    except Exception as e:
        _log_error(conn, log_id, str(e))
        raise


def transfer_village_to_tehsil(conn, cycle_id: str) -> dict: return transfer_level(conn, "village", "tehsil", cycle_id)
def transfer_tehsil_to_district(conn, cycle_id: str) -> dict: return transfer_level(conn, "tehsil", "district", cycle_id)
def transfer_district_to_state(conn, cycle_id: str) -> dict: return transfer_level(conn, "district", "state", cycle_id)
def transfer_state_to_zone(conn, cycle_id: str) -> dict: return transfer_level(conn, "state", "zone", cycle_id)
def transfer_zone_to_country(conn, cycle_id: str) -> dict: return transfer_level(conn, "zone", "country", cycle_id)
def transfer_country_to_continent(conn, cycle_id: str) -> dict: return transfer_level(conn, "country", "continent", cycle_id)
def transfer_continent_to_earth(conn, cycle_id: str) -> dict: return transfer_level(conn, "continent", "earth", cycle_id)


def transfer_earth_to_archive(conn, cycle_id: str, dry_run: bool = False) -> dict:
    """Phase 4: writes the cycle's earth-level data to 0_Earth, then deletes the raw rows (unless
    dry_run). See archive_writer.py / docs/phase_4_report.md."""
    from archive_writer import archive_cycle
    return archive_cycle(conn, cycle_id, dry_run=dry_run)


def run_full_pipeline(conn, cycle_id: str) -> list[dict]:
    """Runs all 7 real transfers (village->...->earth) in sequence. Skips earth->archive (Phase 4).
    Safety-checked up front so a failure partway through still means nothing illegal started."""
    _check_safety(conn, cycle_id)
    results = []
    for from_level, to_level in zip(PIPELINE_LEVELS[:-1], PIPELINE_LEVELS[1:]):
        results.append(transfer_level(conn, from_level, to_level, cycle_id))
    return results
