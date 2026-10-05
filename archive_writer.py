"""Phase 4 of the lunar-cycle archival system: writes a cycle's Earth-level data to disk under
0_Earth, then deletes the raw DB rows -- only after the write is durable and verified. See
docs/lunar_cycle_system.md, docs/phase_3_report.md, docs/phase_4_report.md.

Reuses folder_connector.resolve_location_dir() -- the SAME function every real user registration
already writes through -- rather than inventing a parallel path scheme, and lunar_calendar's own
archive_folder_name()/translated_cycle_display_name()/get_cycle_dates() from Phase 1, unmodified.

Never runs automatically (Phase 5), never touches lunar_calendar.py / cycle_middleware.py /
pipeline_core.py (only pipeline_core.transfer_earth_to_archive's single stub line changes), and is
always tested with QM_EARTH_ROOT pointed at an isolated /tmp directory -- never the real tree.

**Extension beyond the literal spec's file list (documented, not silent)**: the spec's
posts/votes/.../volunteers.json list has no home for 8 of the 28 Phase-2 tables
(election_candidates, election_votes, collective_karma_log, business_ratings, account_ids,
people_requests, account_id_requests, message_reactions), and country_sentiment/zone_sentiment are
Country/Zone-anchored data (Phase 3 Decision 3), not village data -- nesting them under a village
folder would be wrong. _ARCHIVE_FILES below covers every one of the 28 tables exactly once, and
sentiment is written at its own Country/Zone location folder, never inside a village's.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
from pathlib import Path

import cycle_middleware
import folder_connector
import lunar_calendar
import pipeline_core

EARTH_ROOT = Path(os.environ.get("QM_EARTH_ROOT", "/Users/macmudgal/Desktop/0_Earth"))
BACKUPS_DIR = EARTH_ROOT / ".backups"

# file name -> list of tables whose earth-level rows (for whichever location/user they belong to)
# land in that file. Covers exactly the 28 Phase-2 tables, once each.
_ARCHIVE_FILES = {
    "posts.json": ["board_posts"],
    "votes.json": ["board_votes"],
    "comments.json": ["board_comments"],
    "messages.json": ["board_messages", "personal_messages", "private_messages", "message_reactions"],
    "wallet_transactions.json": ["wallet_transactions"],
    "karma_entries.json": ["karma_entries"],
    "collective_karma.json": ["collective_karma_log"],
    "reviews.json": ["app_reviews"],
    "business_ratings.json": ["business_ratings"],
    "payment_orders.json": ["payment_orders"],
    "sentiment.json": ["country_sentiment", "zone_sentiment"],
    "group_activity.json": ["subgroups", "personal_groups", "private_chats", "subgroup_members", "personal_group_members"],
    "profile_changes.json": ["profile_change_requests"],
    "volunteers.json": ["volunteers", "referrer_applications"],
    "elections.json": ["election_candidates", "election_votes"],
    "account_activity.json": ["account_ids", "account_id_requests", "people_requests"],
}
_FILE_FOR_TABLE = {t: f for f, tables in _ARCHIVE_FILES.items() for t in tables}

# Per-table: (native_level_kind, sql, user_column_or_None). Deliberately duplicated from
# pipeline_core's own resolver dicts, with t.rowid + the row's full columns + a user column added
# -- Safety Rule 4 forbids modifying pipeline_core.py except the stub, so this can't just import
# and extend those dicts in place. kind is "village"/"country"/"zone" (fixed) or "varies" (the
# query's own _loc_level column decides, per row).
_ROWS_SQL = {
    "wallet_transactions": ("varies", """
        SELECT t.*, t.rowid AS _rowid,
               CASE WHEN w.owner_type='user' THEN json_extract(u.present_location_json,'$.village.id') ELSE w.owner_id END AS _loc_id,
               CASE WHEN w.owner_type='user' THEN 'village' ELSE w.owner_type END AS _loc_level,
               COALESCE(t.related_user_id, CASE WHEN w.owner_type='user' THEN CAST(w.owner_id AS INTEGER) END) AS _uid
        FROM wallet_transactions t JOIN wallets w ON w.id=t.wallet_id
        LEFT JOIN users u ON w.owner_type='user' AND u.id = CAST(w.owner_id AS INTEGER)
        WHERE t.cycle_id=? AND t.pipeline_level='earth'""", None),
    "election_candidates": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM election_candidates t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "election_votes": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.voter_user_id AS _uid FROM election_votes t JOIN users u ON u.id=t.voter_user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "karma_entries": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM karma_entries t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "collective_karma_log": ("varies", "SELECT t.*, t.rowid AS _rowid, t.location_id AS _loc_id, t.location_level AS _loc_level, NULL AS _uid FROM collective_karma_log t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "business_ratings": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.provider_user_id AS _uid FROM business_ratings t JOIN users u ON u.id=t.provider_user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "board_posts": ("varies", "SELECT t.*, t.rowid AS _rowid, t.group_id AS _loc_id, t.level AS _loc_level, t.author_id AS _uid FROM board_posts t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "board_votes": ("varies", "SELECT t.*, t.rowid AS _rowid, p.group_id AS _loc_id, p.level AS _loc_level, t.user_id AS _uid FROM board_votes t JOIN board_posts p ON p.id=t.post_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "board_comments": ("varies", "SELECT t.*, t.rowid AS _rowid, p.group_id AS _loc_id, p.level AS _loc_level, t.user_id AS _uid FROM board_comments t JOIN board_posts p ON p.id=t.post_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "board_messages": ("village", "SELECT t.*, t.rowid AS _rowid, sg.village_id AS _loc_id, t.user_id AS _uid FROM board_messages t JOIN subgroups sg ON sg.id=t.subgroup_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "personal_messages": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM personal_messages t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "private_messages": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM private_messages t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "account_ids": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(t.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM account_ids t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "people_requests": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.from_user_id AS _uid FROM people_requests t JOIN users u ON u.id=t.from_user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "account_id_requests": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(t.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM account_id_requests t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "payment_orders": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(t.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM payment_orders t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "country_sentiment": ("country", "SELECT t.*, t.rowid AS _rowid, t.country_id AS _loc_id, t.user_id AS _uid FROM country_sentiment t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "zone_sentiment": ("zone", "SELECT t.*, t.rowid AS _rowid, t.zone_id AS _loc_id, t.user_id AS _uid FROM zone_sentiment t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "app_reviews": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM app_reviews t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "profile_change_requests": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM profile_change_requests t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "volunteers": ("village", "SELECT t.*, t.rowid AS _rowid, t.group_id AS _loc_id, t.user_id AS _uid FROM volunteers t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "message_reactions": ("village", """
        SELECT t.*, t.rowid AS _rowid,
               CASE WHEN t.scope='subgroup' THEN sg.village_id ELSE json_extract(u2.present_location_json,'$.village.id') END AS _loc_id,
               t.user_id AS _uid
        FROM message_reactions t
        LEFT JOIN board_messages bm ON t.scope='subgroup' AND bm.id=t.message_id
        LEFT JOIN subgroups sg ON sg.id=bm.subgroup_id
        LEFT JOIN personal_messages pm ON t.scope='personal' AND pm.id=t.message_id
        LEFT JOIN personal_groups pg ON pg.id=pm.group_id
        LEFT JOIN users u2 ON u2.id=pg.owner_user_id
        WHERE t.cycle_id=? AND t.pipeline_level='earth'""", None),
    "referrer_applications": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM referrer_applications t JOIN users u ON u.id=t.user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "subgroups": ("village", "SELECT t.*, t.rowid AS _rowid, t.village_id AS _loc_id, t.created_by AS _uid FROM subgroups t WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "personal_groups": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.owner_user_id AS _uid FROM personal_groups t JOIN users u ON u.id=t.owner_user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "private_chats": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_lo AS _uid, t.user_hi AS _uid2 FROM private_chats t JOIN users u ON u.id=t.user_lo WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "subgroup_members": ("village", "SELECT t.*, t.rowid AS _rowid, sg.village_id AS _loc_id, t.user_id AS _uid FROM subgroup_members t JOIN subgroups sg ON sg.id=t.subgroup_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
    "personal_group_members": ("village", "SELECT t.*, t.rowid AS _rowid, json_extract(u.present_location_json,'$.village.id') AS _loc_id, t.user_id AS _uid FROM personal_group_members t JOIN personal_groups g ON g.id=t.group_id JOIN users u ON u.id=g.owner_user_id WHERE t.cycle_id=? AND t.pipeline_level='earth'", None),
}

assert set(_ROWS_SQL) == set(cycle_middleware.STAMPED_TABLES), "archive_writer must cover exactly the 28 Phase-2 tables"
assert set(_FILE_FOR_TABLE) == set(cycle_middleware.STAMPED_TABLES), "every table must map to exactly one archive file"

_INTERNAL_COLS = ("_rowid", "_loc_id", "_loc_level", "_uid", "_uid2")


def _row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys() if k not in _INTERNAL_COLS}


def _fetch(conn, table: str, cycle_id: str) -> list:
    kind, sql, _ = _ROWS_SQL[table]
    rows = conn.execute(sql, (cycle_id,)).fetchall()
    out = []
    for r in rows:
        loc_level = kind if kind != "varies" else r["_loc_level"]
        out.append({
            "table": table, "rowid": r["_rowid"], "loc_level": loc_level, "loc_id": r["_loc_id"],
            "uid": r["_uid"], "uid2": r["_uid2"] if "_uid2" in r.keys() else None,
            "data": _row_to_dict(r),
        })
    return out


def _all_earth_rows(conn, cycle_id: str) -> list:
    out = []
    for table in cycle_middleware.STAMPED_TABLES:
        out.extend(_fetch(conn, table, cycle_id))
    return out


def location_groups(conn, cycle_id: str) -> dict[tuple[str, str], list]:
    """{(level, location_id): [row_entry, ...]} -- every row that resolved to a real location.
    A row whose loc_id is None (shouldn't happen given Phase 3's India-only scope, but defensive)
    is skipped, not guessed at."""
    groups: dict[tuple[str, str], list] = {}
    for entry in _all_earth_rows(conn, cycle_id):
        if not entry["loc_id"] or not entry["loc_level"]:
            continue
        groups.setdefault((entry["loc_level"], entry["loc_id"]), []).append(entry)
    return groups


def get_villages_with_activity(conn, cycle_id: str) -> list[str]:
    return sorted({loc_id for (level, loc_id) in location_groups(conn, cycle_id) if level == "village"})


def user_groups(conn, cycle_id: str) -> dict[int, list]:
    """{user_id: [row_entry, ...]} across every table with a resolvable acting user. private_chats
    contributes to BOTH participants (uid and uid2)."""
    groups: dict[int, list] = {}
    for entry in _all_earth_rows(conn, cycle_id):
        for uid in (entry["uid"], entry["uid2"]):
            if uid:
                groups.setdefault(uid, []).append(entry)
    return groups


def get_users_with_activity(conn, cycle_id: str, village_id: str | None = None) -> list[int]:
    groups = user_groups(conn, cycle_id)
    if village_id is None:
        return sorted(groups)
    return sorted(uid for uid, entries in groups.items() if any(e["loc_id"] == village_id for e in entries))


# ---- Writing ------------------------------------------------------------------------------

def _write_json_files(target_dir: Path, entries: list, file_names: list[str] | None = None) -> dict[str, int]:
    """Groups `entries` by their archive file and writes each as a JSON array. Returns
    {filename: record_count} for every file actually written (files with zero matching rows for
    this location/user are not created, so a village with no board posts has no empty posts.json)."""
    by_file: dict[str, list] = {}
    for e in entries:
        fname = _FILE_FOR_TABLE[e["table"]]
        if file_names is not None and fname not in file_names:
            continue
        by_file.setdefault(fname, []).append(e["data"])
    counts = {}
    for fname, rows in by_file.items():
        with open(target_dir / fname, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False, default=str)
        counts[fname] = len(rows)
    return counts


def _sha256_of_dir(path: Path, exclude: set[str] = frozenset({"cycle_metadata.json"})) -> str:
    """Checksum of every OTHER file's content in `path`, order-independent (sorted by filename).
    Excludes cycle_metadata.json itself -- it's where this checksum gets stored, so hashing it
    too would be self-referential (its own content changes the moment the checksum is written
    into it). Verification recomputes the exact same way and compares against the stored value."""
    h = hashlib.sha256()
    for f in sorted(path.iterdir()):
        if f.is_file() and f.name not in exclude:
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def build_cycle_metadata(cycle_id: str, record_counts: dict, archive_level: str, extra: dict | None = None, dry_run: bool = False) -> dict:
    start, mid, end = lunar_calendar.get_cycle_dates(cycle_id)
    end_month = lunar_calendar.get_vedic_month_name(end + dt.timedelta(days=1))
    start_month, year = cycle_id.rsplit("_", 1)
    meta = {
        "cycle_id": cycle_id,
        "display_names": lunar_calendar.translated_cycle_display_name(cycle_id),
        "start_date": start.isoformat(), "start_phase": "Amavasya", "start_vedic_name": f"{start_month}_Amavasya",
        "mid_date": mid.isoformat(), "mid_phase": "Purnima", "mid_vedic_name": f"{start_month}_Purnima",
        "end_date": end.isoformat(), "end_phase": "Amavasya", "end_vedic_name": f"{end_month}_Amavasya",
        "archived_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "archive_level": archive_level,
        "records_archived": record_counts,
        # True while this folder was written by a dry run and the matching raw rows are still in
        # the DB -- lets a later real run tell "a dry run already wrote this" (fine, proceed) apart
        # from "a previous REAL run wrote this and then failed before deleting" (Decision 6's
        # mismatch case, refuse). A real run always rewrites this to False as its own last step.
        "dry_run": dry_run,
    }
    if extra:
        meta.update(extra)
    return meta


def _write_archive_folder(target_parent: Path, cycle_folder: str, entries: list, archive_level: str,
                           cycle_id: str, extra_metadata: dict | None = None, file_names: list[str] | None = None,
                           dry_run: bool = False) -> dict:
    """Transactional write: build everything in a .tmp_ sibling dir, then atomically rename it
    into place. Never touches an already-written, differently-named folder."""
    target_parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_parent / f".tmp_{cycle_folder}"
    final_dir = target_parent / cycle_folder
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    record_counts = _write_json_files(tmp_dir, entries, file_names)
    # Checksum covers every data file written above (never cycle_metadata.json itself -- see
    # _sha256_of_dir), computed BEFORE cycle_metadata.json is written at all, so there is exactly
    # one write of that file and no self-reference to resolve.
    checksum = _sha256_of_dir(tmp_dir)
    data_bytes = sum(p.stat().st_size for p in tmp_dir.iterdir() if p.is_file())
    meta = build_cycle_metadata(cycle_id, record_counts, archive_level, extra_metadata, dry_run=dry_run)
    meta["checksum_sha256"] = checksum
    meta["filesize_bytes"] = data_bytes  # the data files only; cycle_metadata.json's own size isn't knowable before it's written
    with open(tmp_dir / "cycle_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    final_checksum = checksum  # verify_archive recomputes the same exclude-metadata hash and compares to this

    if final_dir.exists():
        shutil.rmtree(final_dir)
    tmp_dir.rename(final_dir)

    total_bytes = sum(p.stat().st_size for p in final_dir.iterdir() if p.is_file())
    print(f"Writing {archive_level} {meta.get('level_id', '')} archive ({sum(record_counts.values())} records, {total_bytes} bytes)...")
    return {"path": str(final_dir), "record_counts": record_counts, "bytes": total_bytes,
            "checksum_sha256": final_checksum, "files": list(record_counts) + ["cycle_metadata.json"]}


def _location_dict_for(level: str, location_id: str) -> dict:
    """A minimal {level: {"id": ...}} chain for folder_connector.resolve_location_dir() -- it
    only ever reads each level's "id", never the name, so ancestor ids alone are enough.

    `level == "country"` is special: country_sentiment can be cast about ANY of the 10
    Sub-continent countries, not just India -- `location_id` IS the real target country, and must
    be used as-is, not replaced with the hardcoded India default below (an earlier version of this
    function did exactly that, which silently resolved two different countries' sentiment archives
    onto the same physical folder -- caught by tools/verify_archive_writer.py). Every OTHER level
    here (zone/state/district/tehsil/village) is India-only by construction (Phase 3 scope;
    zone_sentiment's zone_id is always an India zone), so hardcoding India's own country/continent
    as their ancestor is correct for those."""
    if level == "country":
        return {"continent": {"id": pipeline_core.INDIA_CONTINENT_ID}, "country": {"id": location_id}}
    chain = {"continent": {"id": pipeline_core.INDIA_CONTINENT_ID}, "country": {"id": pipeline_core.INDIA_COUNTRY_ID}}
    for lvl in ("zone", "state", "district", "tehsil", "village"):
        anc = pipeline_core._ancestor_id(location_id, level, lvl)
        if anc:
            chain[lvl] = {"id": anc}
    return chain


def write_location_archive(conn, level: str, location_id: str, cycle_id: str, entries: list, dry_run: bool = False) -> dict:
    """Writes one location's archive folder: {resolved_dir}/archives/{cycle_folder}/."""
    if level in ("country", "zone", "state", "district", "tehsil", "village"):
        location_dir = folder_connector.resolve_location_dir(_location_dict_for(level, location_id))
    elif level == "continent":
        location_dir = folder_connector.CONTINENTS_ROOT / folder_connector._root_char_fix(pipeline_core.INDIA_CONTINENT_ID)
    else:  # earth
        location_dir = folder_connector.CONTINENTS_ROOT.parent
    if location_dir is None or not location_dir.exists():
        raise RuntimeError(f"Could not resolve a real folder for {level} {location_id} under {folder_connector.EARTH_ROOT} -- refusing to archive into a fabricated path")

    cycle_folder = lunar_calendar.archive_folder_name(cycle_id)
    result = _write_archive_folder(location_dir / "archives", cycle_folder, entries, level.capitalize(), cycle_id,
                                    extra_metadata={"level_id": location_id}, dry_run=dry_run)
    result["level"], result["level_id"] = level, location_id
    return result


def write_user_archive(conn, user_id: int, cycle_id: str, entries: list, dry_run: bool = False) -> dict:
    """Writes the user's archive under BOTH their BORN_HERE and LIVING_HERE folders (if those
    locations resolve to real folders), with filenames prefixed "my_" per Decision 3, plus a
    cycle_summary.json of personal totals."""
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise RuntimeError(f"User {user_id} not found -- cannot archive their activity")
    import json as _j
    birth_loc = _j.loads(user["birth_location_json"])
    present_loc = _j.loads(user["present_location_json"])
    element_row = conn.execute("SELECT sun_element FROM user_zodiac WHERE user_id = ?", (user_id,)).fetchone()
    element = (element_row["sun_element"] if element_row else "Fire").capitalize()

    cycle_folder = lunar_calendar.archive_folder_name(cycle_id)
    summary = {
        "user_id": user_id, "private_id": user["private_id"], "account_id": user["account_id"],
        "cycle_id": cycle_id, "record_counts": {}, "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    written: dict[str, dict] = {}
    for category, loc in (("born_here", birth_loc), ("living_here", present_loc)):
        loc_dir = folder_connector.resolve_location_dir(loc)
        if loc_dir is None:
            written[category] = None
            continue
        key = user["private_id"] if category == "born_here" else user["account_id"]
        user_dir = folder_connector.create_user_folder(loc_dir, "BORN_HERE" if category == "born_here" else "LIVING_HERE", element, key)
        target = user_dir / "private_account" / "archives"
        file_map = {
            "my_posts.json": "posts.json", "my_votes.json": "votes.json", "my_comments.json": "comments.json",
            "my_wallet_transactions.json": "wallet_transactions.json", "my_karma_entries.json": "karma_entries.json",
            "my_chat_messages.json": "messages.json", "my_reviews.json": "reviews.json",
        }
        result = _write_archive_folder(target, cycle_folder, entries, "User", cycle_id,
                                        extra_metadata={"user_id": user_id, "private_id": user["private_id"]}, dry_run=dry_run)
        # rename the generic file names to the "my_"-prefixed ones Decision 3 asks for
        final_dir = Path(result["path"])
        for generic, my_name in [("posts.json", "my_posts.json"), ("votes.json", "my_votes.json"),
                                  ("comments.json", "my_comments.json"), ("wallet_transactions.json", "my_wallet_transactions.json"),
                                  ("karma_entries.json", "my_karma_entries.json"), ("messages.json", "my_chat_messages.json"),
                                  ("reviews.json", "my_reviews.json")]:
            p = final_dir / generic
            if p.exists():
                p.rename(final_dir / my_name)
        # everything else (elections, group_activity, profile_changes, volunteers, sentiment,
        # business_ratings, collective_karma, account_activity, payment_orders) keeps its name --
        # already personal-scoped by virtue of being filtered to this one user's rows.
        with open(final_dir / "cycle_summary.json", "w", encoding="utf-8") as f:
            json.dump({**summary, "record_counts": result["record_counts"]}, f, indent=2, ensure_ascii=False)
        written[category] = result
    return {"user_id": user_id, "born_here": written["born_here"], "living_here": written["living_here"]}


def verify_archive(level: str, location_id: str, cycle_id: str, expected: dict) -> bool:
    """Re-reads the written files and confirms every one is valid JSON and the checksum matches
    what was recorded at write time."""
    path = Path(expected["path"])
    if not path.exists():
        print(f"[archive] FAIL verify: {path} does not exist")
        return False
    for fname in expected["files"]:
        fpath = path / fname
        if not fpath.exists():
            print(f"[archive] FAIL verify: missing {fpath}")
            return False
        try:
            json.loads(fpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[archive] FAIL verify: {fpath} is not valid JSON ({e})")
            return False
    recomputed = _sha256_of_dir(path)
    if recomputed != expected["checksum_sha256"]:
        print(f"[archive] FAIL verify: checksum mismatch for {path}")
        return False
    return True


# ---- Delete phase --------------------------------------------------------------------------

def _backup_before_delete(conn, cycle_id: str) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUPS_DIR / f"pre_archive_{cycle_id}.sql"
    lines = [f"-- Backup of cycle {cycle_id}'s earth-level rows before Phase 4 delete, "
             f"{dt.datetime.now(dt.timezone.utc).isoformat()}\n"]
    for table in cycle_middleware.STAMPED_TABLES:
        rows = conn.execute(f"SELECT * FROM {table} WHERE cycle_id = ? AND pipeline_level = 'earth'", (cycle_id,)).fetchall()
        for row in rows:
            cols = row.keys()
            values = ", ".join(_sql_literal(row[c]) for c in cols)
            lines.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({values});\n")
    backup_path.write_text("".join(lines), encoding="utf-8")
    print(f"Backed up {sum(1 for l in lines if l.startswith('INSERT')) } row(s) to {backup_path}")
    return backup_path


def _sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def delete_cycle_raw_records(conn, cycle_id: str) -> int:
    print(f"Deleting rows from DB for cycle {cycle_id}...")
    total = 0
    for table in cycle_middleware.STAMPED_TABLES:
        cur = conn.execute(f"DELETE FROM {table} WHERE cycle_id = ? AND pipeline_level = 'earth'", (cycle_id,))
        total += cur.rowcount
    conn.commit()
    return total


# ---- Idempotency + orchestration -----------------------------------------------------------

def _count_earth_rows(conn, cycle_id: str) -> int:
    return sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE cycle_id=? AND pipeline_level='earth'", (cycle_id,)).fetchone()[0]
               for t in cycle_middleware.STAMPED_TABLES)


def _has_completed_earth_transfer(conn, cycle_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM transfer_log WHERE cycle_id=? AND to_level='earth' AND status='completed' LIMIT 1", (cycle_id,)
    ).fetchone()
    return row is not None


def get_archived_villages(conn, cycle_id: str) -> list[str]:
    """Village ids that contributed to this cycle, derived from level_holdings' own source_ids
    at tehsil level (one level above village -- see pipeline_core._source_ids_for). level_holdings
    is never touched by Phase 4's delete, so this works for a status check in a brand-new process,
    at any time after archiving, not just immediately after archive_cycle() returns in the same
    call. (Requires the cycle to have actually climbed to tehsil+ -- true for anything archived.)"""
    rows = conn.execute("SELECT source_ids FROM level_holdings WHERE level='tehsil' AND cycle_id=?", (cycle_id,)).fetchall()
    villages: set[str] = set()
    for r in rows:
        if r["source_ids"]:
            villages.update(json.loads(r["source_ids"]))
    return sorted(villages)


def archive_status(conn, cycle_id: str) -> dict:
    """{archived, folder_count, total_bytes, records_deleted, checksum_match} -- works whether or
    not this is the same process that ran archive_cycle()."""
    remaining = _count_earth_rows(conn, cycle_id)
    completed_transfer = _has_completed_earth_transfer(conn, cycle_id)
    archived = remaining == 0 and completed_transfer

    cycle_folder = lunar_calendar.archive_folder_name(cycle_id)
    folder_count = total_bytes = checksum_ok = 0
    for village_id in get_archived_villages(conn, cycle_id):
        village_dir = folder_connector.resolve_location_dir(_location_dict_for("village", village_id))
        if not village_dir:
            continue
        archive_dir = village_dir / "archives" / cycle_folder
        meta_path = archive_dir / "cycle_metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        folder_count += 1
        total_bytes += sum(p.stat().st_size for p in archive_dir.iterdir() if p.is_file())
        if _sha256_of_dir(archive_dir) == meta.get("checksum_sha256"):
            checksum_ok += 1

    records_deleted = 0
    if archived:
        holding = conn.execute("SELECT summary_json FROM level_holdings WHERE level='earth' AND cycle_id=?", (cycle_id,)).fetchone()
        if holding:
            records_deleted = sum(json.loads(holding["summary_json"]).get("counts", {}).values())

    return {
        "cycle_id": cycle_id, "archived": archived, "folder_count": folder_count,
        "total_bytes": total_bytes, "records_deleted": records_deleted,
        "checksum_match": folder_count > 0 and checksum_ok == folder_count,
    }


def archive_cycle(conn, cycle_id: str, dry_run: bool = False) -> dict:
    """Full Phase 4 flow. See docs/phase_4_report.md for the idempotency rules (Decision 6) this
    implements against the filesystem + transfer_log, without a new DB table."""
    pipeline_core.ensure_tables(conn)
    pipeline_core._check_safety(conn, cycle_id)

    remaining = _count_earth_rows(conn, cycle_id)
    if remaining == 0:
        if _has_completed_earth_transfer(conn, cycle_id):
            print(f"[archive] {cycle_id} already archived (no raw rows remain at earth level) -- skipping")
            return {"status": "already_archived", "cycle_id": cycle_id}
        print(f"[archive] {cycle_id} has no earth-level data to archive")
        return {"status": "nothing_to_archive", "cycle_id": cycle_id}

    locations = location_groups(conn, cycle_id)
    users = user_groups(conn, cycle_id)

    # Collision guard: two DISTINCT (level, loc_id) keys must never resolve to the same physical
    # folder (possible if the real 0_Earth scaffold is incomplete somewhere -- resolve_location_dir
    # degrades to the deepest EXISTING ancestor, so an under-scaffolded country/zone could in
    # principle land on the same folder as another). Writing both would let the second overwrite
    # the first's archive before its rows are deleted -- caught once already during this phase's
    # own testing; refuse outright rather than risk silent data loss.
    resolved_paths: dict[Path, tuple] = {}
    for (level, loc_id) in locations:
        if level not in ("village", "country", "zone"):
            continue
        d = folder_connector.resolve_location_dir(_location_dict_for(level, loc_id))
        if d is None:
            continue
        if d in resolved_paths and resolved_paths[d] != (level, loc_id):
            raise RuntimeError(
                f"Both {resolved_paths[d]} and {(level, loc_id)} resolve to the same folder ({d}) -- "
                f"the 0_Earth scaffold is incomplete somewhere. Refusing to archive either until this is fixed."
            )
        resolved_paths[d] = (level, loc_id)

    # Pre-write existence probe: if a village's expected folder already has a FINALIZED (non-dry-
    # run) cycle_metadata.json for this cycle, treat it as a mismatch needing investigation rather
    # than silently overwriting -- Decision 6 asks for this to be refused up front. A dry run
    # legitimately writes this same final folder (there's no separate "draft" location), so an
    # existing archive whose own metadata says dry_run=true is the EXPECTED state right before a
    # real run, not a failure signal -- only a prior dry_run=false (or old-format, pre-dry-run-flag)
    # archive sitting next to still-present raw rows indicates a previous real run failed midway.
    cycle_folder = lunar_calendar.archive_folder_name(cycle_id)
    existing = []
    for (level, loc_id) in locations:
        probe_dir = None
        if level == "village":
            probe_dir = folder_connector.resolve_location_dir(_location_dict_for(level, loc_id))
        if not probe_dir:
            continue
        meta_path = probe_dir / "archives" / cycle_folder / "cycle_metadata.json"
        if not meta_path.exists():
            continue
        try:
            prior_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing.append((level, loc_id))
            continue
        if prior_meta.get("dry_run") is not True:  # missing key (old format) -> treat conservatively as finalized
            existing.append((level, loc_id))
    if existing:
        print(f"[archive] WARNING: {len(existing)} location(s) already have a FINALIZED '{cycle_folder}' archive on "
              f"disk, but {remaining} raw row(s) still exist in the DB for {cycle_id} -- a previous real run likely "
              f"failed between write and delete. Refusing to proceed automatically; investigate before retrying.")
        return {"status": "mismatch", "cycle_id": cycle_id, "remaining_rows": remaining, "conflicting_locations": existing}

    loc_results = []
    for (level, loc_id), entries in locations.items():
        loc_results.append(write_location_archive(conn, level, loc_id, cycle_id, entries, dry_run=dry_run))
    user_results = []
    for uid, entries in users.items():
        user_results.append(write_user_archive(conn, uid, cycle_id, entries, dry_run=dry_run))

    all_ok = all(verify_archive(r["level"], r["level_id"], cycle_id, r) for r in loc_results)
    if not all_ok:
        raise RuntimeError(f"Archive verification failed for {cycle_id} -- raw records left untouched")

    total_bytes = sum(r["bytes"] for r in loc_results)
    print(f"Wrote {len(loc_results)} locations, {len(user_results)} users, {total_bytes} bytes total")

    if dry_run:
        print(f"[archive] dry_run=True -- raw records left untouched for {cycle_id}")
        return {"status": "dry_run_complete", "cycle_id": cycle_id, "locations": len(loc_results),
                "users": len(user_results), "bytes": total_bytes}

    _backup_before_delete(conn, cycle_id)
    deleted = delete_cycle_raw_records(conn, cycle_id)
    print(f"Archive complete for {cycle_id}")
    return {"status": "archived", "cycle_id": cycle_id, "locations": len(loc_results), "users": len(user_results),
            "bytes": total_bytes, "records_deleted": deleted}
