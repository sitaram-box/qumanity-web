"""Hybrid database <-> folder sync: mirrors location_elements stats and
lunar events out to a plain folder tree (Part 9 of the brief), so they can
be browsed/read without a DB client, and so other tools (static site
generators, backups) can consume them directly.

The DB (qumanity_prototype.db) stays the source of truth; this is a
read-only export, safe to delete and regenerate at any time via
sync_database_to_folders().

Per-user folders are written live, at registration time, into the real
QM_EARTH_ROOT tree (see folder_connector.py) by folder_connector.py -- this
module used to also batch-export a per-user JSON here (into a separate,
project-local folder_export/Earth/ tree, keyed by slugified location
*names*), but that became a second, conflicting copy of the same data once
folder_connector.py started writing the real thing, so it was removed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EXPORT_ROOT = BASE_DIR / "folder_export" / "Earth"


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "Unknown"


def update_location_stats_export(conn) -> int:
    """Write Earth/<location>/Space/stats.json (village/state/country/
    continent/earth-level elemental totals) from location_elements."""
    rows = conn.execute("SELECT * FROM location_elements").fetchall()
    count = 0
    for row in rows:
        folder = EXPORT_ROOT if row["location_type"] == "earth" else EXPORT_ROOT / _slug(row["location_id"])
        space_folder = folder / "Space"
        space_folder.mkdir(parents=True, exist_ok=True)
        stats = {
            "location_id": row["location_id"],
            "location_type": row["location_type"],
            "total_users": row["total_users"],
            "fire_count": row["fire_count"],
            "earth_count": row["earth_count"],
            "air_count": row["air_count"],
            "water_count": row["water_count"],
            "space_count": row["space_count"],
            "updated_at": row["updated_at"],
        }
        with open(space_folder / "stats.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        count += 1
    return count


def refresh_lunar_events_table(conn) -> int:
    """Recompute upcoming lunar events (real ephemeris, see lunar_core.py)
    and replace the lunar_events table's contents with them."""
    import lunar_core

    events = lunar_core.get_upcoming_lunar_events()
    conn.execute("DELETE FROM lunar_events")
    for e in events:
        conn.execute(
            """INSERT INTO lunar_events
               (event_type, date, time, zodiac_sign, nakshatra, description, is_visible_in_india)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (e["event_type"], e["date"], e["time"], e["zodiac_sign"], e["nakshatra"],
             e["description"], e["is_visible_in_india"]),
        )
    conn.commit()
    return len(events)


def export_lunar_data(conn) -> int:
    refresh_lunar_events_table(conn)
    rows = conn.execute("SELECT * FROM lunar_events ORDER BY date, time").fetchall()
    folder = EXPORT_ROOT / "Space" / "lunar_events"
    folder.mkdir(parents=True, exist_ok=True)
    events = [dict(r) for r in rows]
    with open(folder / "events.json", "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False, default=str)
    return len(events)


def sync_database_to_folders(conn) -> dict:
    """Run the full export. Safe to call repeatedly (idempotent overwrite),
    and safe to schedule (see app.py's daily APScheduler job)."""
    locations = update_location_stats_export(conn)
    lunar = export_lunar_data(conn)
    return {"locations_exported": locations, "lunar_events_exported": lunar}
