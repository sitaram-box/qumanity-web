"""One-off: renames each DOB-ID-migrated user's orphaned BORN_HERE folder from their OLD
private_id_9digit to their NEW one -- see the Admin Panel Q-Cards page investigation, 2026-11-26.
scripts/migrate_to_dob_ids.py only ever changed users.private_id_9digit in the database; it never
touched folder_connector.py's on-disk BORN_HERE/<Element>/<private_id>/ directories, which are
keyed by whatever Private ID was current AT REGISTRATION TIME and are never renamed on their own.
Every migrated user's actual folder on disk is therefore still named after their PRE-migration id.

Reads id_migrations for the full list of (user_id, old_private_id_9digit, new_private_id_9digit)
rows, resolves each user's BORN_HERE folder the same way folder_connector.register_user_folder()
originally built it (users.birth_location_json -> folder_connector.resolve_location_dir(), plus
user_zodiac.sun_element for the <Element> segment -- NOT a literal "Earth" in the path; Earth is
only one of the four zodiac elements, same as Fire/Water/Air), then for each user:

  - old folder exists, new one doesn't -> rename old -> new. The normal, expected case.
  - new folder already exists           -> warn and skip (ambiguous -- never overwrite/merge).
  - neither folder exists                -> warn and skip (the original folder write likely
                                             soft-failed at registration -- see
                                             folder_connector.register_user_folder()'s own
                                             docstring on that being a non-fatal failure mode, or
                                             the birth location/element couldn't be resolved at
                                             all, e.g. a missing user_zodiac row).
  - new exists, old doesn't              -> already renamed (e.g. a prior, interrupted run of
                                             this same script) -- logged as already-done, not a
                                             warning, specifically so this script stays safe to
                                             re-run without crying wolf on its own prior success.

Every attempted rename, skip, or already-done row is logged to the folder_renames table (created
here) for audit -- visible afterward in the Admin Panel's Database Viewer.

Usage:
    python3 scripts/rename_migrated_folders.py --confirm
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

if "--confirm" not in sys.argv:
    print(__doc__)
    print("Refusing to run without --confirm.", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: F401,E402  (runs ensure_database_ready() at import time)
import folder_connector  # noqa: E402
from db import get_db  # noqa: E402


def _ensure_folder_renames_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS folder_renames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        old_private_id_9digit TEXT NOT NULL,
        new_private_id_9digit TEXT NOT NULL,
        old_path TEXT,
        new_path TEXT,
        outcome TEXT NOT NULL,
        detail TEXT,
        renamed_at TEXT NOT NULL
    )""")
    conn.commit()


def _resolve_born_here_paths(conn, user_id: int, old_id: str, new_id: str) -> tuple[Path, Path] | None:
    """(old_folder, new_folder) for this user, or None if their birth location or zodiac element
    can't be resolved at all -- meaning no BORN_HERE folder could ever have been created for them
    in the first place, so there is nothing to rename."""
    row = conn.execute(
        "SELECT u.birth_location_json, z.sun_element FROM users u "
        "LEFT JOIN user_zodiac z ON z.user_id = u.id WHERE u.id = ?",
        (user_id,),
    ).fetchone()
    if not row or not row["sun_element"]:
        return None
    try:
        birth_location = json.loads(row["birth_location_json"] or "{}")
    except (TypeError, ValueError):
        return None
    location_dir = folder_connector.resolve_location_dir(birth_location)
    if location_dir is None:
        return None
    born_here = location_dir / "BORN_HERE" / row["sun_element"]
    return born_here / old_id, born_here / new_id


def main() -> None:
    conn = get_db()
    _ensure_folder_renames_table(conn)

    rows = conn.execute(
        "SELECT user_id, old_private_id_9digit, new_private_id_9digit FROM id_migrations ORDER BY user_id"
    ).fetchall()

    renamed = already_done = skipped_conflict = skipped_missing = 0
    for row in rows:
        user_id = row["user_id"]
        old_id = row["old_private_id_9digit"]
        new_id = row["new_private_id_9digit"]
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

        paths = _resolve_born_here_paths(conn, user_id, old_id, new_id)
        if paths is None:
            print(f"[warn] user {user_id}: could not resolve birth location/element -- skipped")
            conn.execute(
                "INSERT INTO folder_renames (user_id, old_private_id_9digit, new_private_id_9digit, "
                "old_path, new_path, outcome, detail, renamed_at) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, old_id, new_id, None, None, "skipped_unresolvable",
                 "birth location/element not resolvable", now),
            )
            conn.commit()
            skipped_missing += 1
            continue

        old_path, new_path = paths
        old_exists = old_path.exists()
        new_exists = new_path.exists()

        if old_exists and not new_exists:
            old_path.rename(new_path)
            print(f"[ok] user {user_id}: renamed {old_path} -> {new_path}")
            outcome, detail = "renamed", None
            renamed += 1
        elif new_exists and not old_exists:
            print(f"[info] user {user_id}: {new_path} already exists and {old_path} doesn't -- "
                  f"already renamed, skipping")
            outcome, detail = "already_done", None
            already_done += 1
        elif old_exists and new_exists:
            print(f"[warn] user {user_id}: BOTH {old_path} and {new_path} exist -- not overwriting, skipped")
            outcome, detail = "skipped_conflict", "both old and new folders exist"
            skipped_conflict += 1
        else:
            print(f"[warn] user {user_id}: neither {old_path} nor {new_path} exists -- skipped")
            outcome, detail = "skipped_missing", "neither folder exists on disk"
            skipped_missing += 1

        conn.execute(
            "INSERT INTO folder_renames (user_id, old_private_id_9digit, new_private_id_9digit, "
            "old_path, new_path, outcome, detail, renamed_at) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, old_id, new_id, str(old_path), str(new_path), outcome, detail, now),
        )
        conn.commit()

    conn.close()
    print(
        f"Renamed {renamed} folder(s). Already done: {already_done}. "
        f"Skipped (conflict): {skipped_conflict}. Skipped (missing/unresolvable): {skipped_missing}."
    )


if __name__ == "__main__":
    main()
