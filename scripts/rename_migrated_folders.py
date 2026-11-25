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

Also importable as a library (2026-11-26): app.py's api_admin_rename_migrated_folders() imports
run_rename()/pending_rename_count()/_ensure_folder_renames_table() directly to back the Admin
Panel's "Rename Migrated Folders" button -- added after the Railway Console turned out to have no
python3 on this deployment. Same reasoning as migrate_to_dob_ids.py's own refactor: everything
CLI-ONLY (the --confirm gate and `import app`, which would be circular when the importer IS
app.py) lives inside main() below, never at module level.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import folder_connector  # no dependency on app.py -- safe to import unconditionally


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


def pending_rename_count(conn) -> int:
    """How many id_migrations rows are currently in the one ACTIONABLE state (old folder exists,
    new one doesn't) -- the idempotency check for the Admin Panel button: if this is 0, there is
    nothing for run_rename() to do (everything is already renamed, conflicted, or unresolvable),
    so the button's route refuses outright rather than re-running for no effect."""
    rows = conn.execute(
        "SELECT user_id, old_private_id_9digit, new_private_id_9digit FROM id_migrations"
    ).fetchall()
    pending = 0
    for row in rows:
        paths = _resolve_born_here_paths(conn, row["user_id"], row["old_private_id_9digit"], row["new_private_id_9digit"])
        if paths is None:
            continue
        old_path, new_path = paths
        if old_path.exists() and not new_path.exists():
            pending += 1
    return pending


def run_rename(conn) -> dict:
    """The core rename loop, shared by this script's own main() below and the Admin Panel's
    "Rename Migrated Folders" button (app.py's api_admin_rename_migrated_folders()) -- extracted
    (2026-11-26) so the panel can never drift from the one already proven safe from the CLI.
    Expects _ensure_folder_renames_table(conn) to have already been called by the caller."""
    rows = conn.execute(
        "SELECT user_id, old_private_id_9digit, new_private_id_9digit FROM id_migrations ORDER BY user_id"
    ).fetchall()

    renamed = already_done = skipped_conflict = skipped_missing = 0
    outcomes = []
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
            outcomes.append({"user_id": user_id, "outcome": "skipped_unresolvable"})
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
        outcomes.append({"user_id": user_id, "outcome": outcome})

    return {
        "renamed": renamed,
        "already_done": already_done,
        "skipped_conflict": skipped_conflict,
        "skipped_missing": skipped_missing,
        "outcomes": outcomes,
    }


def main() -> None:
    if "--confirm" not in sys.argv:
        print(__doc__)
        print("Refusing to run without --confirm.", file=sys.stderr)
        sys.exit(1)

    import app  # noqa: F401  (runs ensure_database_ready() at import time)
    from db import get_db

    conn = get_db()
    _ensure_folder_renames_table(conn)
    result = run_rename(conn)
    conn.close()
    print(
        f"Renamed {result['renamed']} folder(s). Already done: {result['already_done']}. "
        f"Skipped (conflict): {result['skipped_conflict']}. "
        f"Skipped (missing/unresolvable): {result['skipped_missing']}."
    )


if __name__ == "__main__":
    main()
