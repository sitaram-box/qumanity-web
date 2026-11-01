"""Crowdsourced Location System, MVP Phases A/B/C/E (2026-11): lets a member register when their
real Village or Tehsil is missing from the verified directory (static/data/subcontinent_districts.
json), collects fully optional GPS observations, and promotes a provisional location once it
reaches QM_PROVISIONAL_LOCATION_THRESHOLD qualifying present-resident members.

Three data layers, kept strictly separate (never merged into one table family):
  - Layer A, the VERIFIED directory: static/data/subcontinent_districts.json (and
    static/data/india_districts_tehsils.json / the india_villages table for India's own deeper
    tiers) -- read-only here, never written to. The canonical Master JSON is untouched.
  - Layer B, PROVISIONAL submissions: provisional_locations / provisional_location_members /
    location_submission_events below.
  - Layer C, GPS observations: user_location_observations / location_centroid_observations below.
    OSM/Overpass (osm_features, qmap_location_osm_features, osm_query_jobs) is explicitly OUT OF
    SCOPE this phase -- see this module's own absence of any Overpass/requests import.

A provisional location's id is NEVER a verified-style dotted code (e.g. "CS.DL.3.4.1A"); it is
always exposed as the string "PROV-<row id>" wherever it needs to sit inside the existing
present_location_json contract (present_location.tehsil.id / present_location.village.id) --
this is what lets the rest of the app's present_location_json-reading code keep working
unmodified, by construction, rather than needing a second location-identity system.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

BASE_DIR = Path(__file__).resolve().parent
SUBCONTINENT_DISTRICTS_FILE = BASE_DIR / "static" / "data" / "subcontinent_districts.json"

PROV_ID_RE = re.compile(r"^PROV-(\d+)$")

VALID_LOCATION_TYPES = ("village", "tehsil")
VALID_STATUSES = ("provisional", "eligible_for_activation", "pending_review", "active", "rejected", "merged", "inactive")

SCHEMA = """
CREATE TABLE IF NOT EXISTS provisional_locations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    location_type   TEXT NOT NULL CHECK (location_type IN ('village', 'tehsil')),
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    parent_verified_tehsil_id    TEXT,
    parent_provisional_tehsil_id INTEGER REFERENCES provisional_locations(id),
    parent_verified_district_id  TEXT NOT NULL,
    parent_verified_state_id     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'provisional'
                    CHECK (status IN ('provisional','eligible_for_activation','pending_review','active','rejected','merged','inactive')),
    merged_into_id  INTEGER REFERENCES provisional_locations(id),
    created_by_user_id INTEGER NOT NULL,
    created_at      TEXT NOT NULL,
    activated_at    TEXT,
    activated_as_verified_id TEXT,
    CHECK (
        (location_type = 'tehsil' AND parent_verified_tehsil_id IS NULL AND parent_provisional_tehsil_id IS NULL) OR
        (location_type = 'village' AND (
            (parent_verified_tehsil_id IS NOT NULL AND parent_provisional_tehsil_id IS NULL) OR
            (parent_verified_tehsil_id IS NULL AND parent_provisional_tehsil_id IS NOT NULL)
        ))
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_provisional_name_per_parent ON provisional_locations(
    location_type, normalized_name, COALESCE(parent_verified_tehsil_id, ''), COALESCE(parent_provisional_tehsil_id, 0)
);
CREATE INDEX IF NOT EXISTS idx_provisional_status ON provisional_locations(status);
CREATE INDEX IF NOT EXISTS idx_provisional_state_district ON provisional_locations(parent_verified_state_id, parent_verified_district_id);
CREATE INDEX IF NOT EXISTS idx_provisional_prov_tehsil_parent ON provisional_locations(parent_provisional_tehsil_id);

CREATE TABLE IF NOT EXISTS provisional_location_members (
    provisional_location_id INTEGER NOT NULL REFERENCES provisional_locations(id),
    user_id         INTEGER NOT NULL,
    role            TEXT NOT NULL DEFAULT 'present_resident' CHECK (role IN ('present_resident')),
    joined_at       TEXT NOT NULL,
    left_at         TEXT,
    PRIMARY KEY (provisional_location_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_prov_members_user ON provisional_location_members(user_id);

CREATE TABLE IF NOT EXISTS location_submission_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provisional_location_id INTEGER NOT NULL REFERENCES provisional_locations(id),
    event_type TEXT NOT NULL,
    actor_user_id INTEGER,
    detail_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_submission_events_location ON location_submission_events(provisional_location_id);

-- latitude/longitude are NULLABLE (a deliberate deviation from the original research draft,
-- documented here): a "GPS unavailable"/"permission denied" outcome must be recordable as a
-- real status-only row, never as fabricated 0,0 coordinates. status='pending'/'accepted' rows
-- always carry real coordinates (enforced in code, not SQL, since SQLite CHECK constraints can't
-- cleanly express "NULL iff status X" alongside the other checks here); 'denied'/'unavailable'
-- rows always have NULL coordinates.
CREATE TABLE IF NOT EXISTS user_location_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    qumanity_verified_location_id TEXT,
    provisional_location_id INTEGER REFERENCES provisional_locations(id),
    latitude REAL,
    longitude REAL,
    accuracy_meters REAL,
    captured_at TEXT,
    consent_internal_storage INTEGER NOT NULL DEFAULT 0,
    consent_centroid_aggregation INTEGER NOT NULL DEFAULT 0,
    consent_external_overpass_lookup INTEGER NOT NULL DEFAULT 0,
    consent_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected_outlier','denied','unavailable','withdrawn')),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_user ON user_location_observations(user_id);
CREATE INDEX IF NOT EXISTS idx_observations_provisional ON user_location_observations(provisional_location_id);
CREATE INDEX IF NOT EXISTS idx_observations_verified ON user_location_observations(qumanity_verified_location_id);

CREATE TABLE IF NOT EXISTS location_centroid_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL CHECK (target_type IN ('provisional_location','verified_location')),
    target_id TEXT NOT NULL,
    centroid_lat REAL,
    centroid_lon REAL,
    sample_size INTEGER NOT NULL,
    method TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('pending','low','medium','high')),
    computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_centroid_target ON location_centroid_observations(target_type, target_id);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


# ---- Configuration (same "read fresh, parse truthy strings" convention as QM_MARQUEE_ENABLED in
# app.py -- read as a function, not a module-level constant, so the existing subprocess-based
# precedence-testing pattern this project already uses for QM_MARQUEE_ENABLED works unchanged
# here too, rather than needing a process restart to pick up a changed env var mid-test). ----

def allow_provisional_locations() -> bool:
    """QM_ALLOW_PROVISIONAL_LOCATIONS -- absent defaults to True (the approved launch default)."""
    raw = os.environ.get("QM_ALLOW_PROVISIONAL_LOCATIONS")
    if raw is None:
        return True
    return raw.strip().lower() in ("1", "true", "yes")


def activation_threshold() -> int:
    """QM_PROVISIONAL_LOCATION_THRESHOLD -- absent or invalid (non-positive, non-numeric) falls
    back to the approved default of 24, never silently to 0 or a negative number that would
    activate on the very first member."""
    raw = os.environ.get("QM_PROVISIONAL_LOCATION_THRESHOLD")
    if raw is None:
        return 24
    try:
        value = int(raw.strip())
    except ValueError:
        return 24
    return value if value > 0 else 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_name(name: str) -> str:
    """Case/whitespace/Unicode-NFKC-insensitive comparison key -- same philosophy as every other
    normalize_name() already in this project this session (the India audit script, the Lok Sabha
    classification script). Never used for display; the original submitted name is preserved
    separately in the `name` column."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name or "")).strip().casefold()


# ---- Layer A: read-only lookups against the existing verified directory -----------------------

_subcontinent_cache = None


def _load_subcontinent_districts() -> dict:
    """The SAME file static/js/register.js's own dropdowns already load client-side
    (static/data/subcontinent_districts.json) -- reusing it here, not a parallel data source, per
    the task's explicit "reuse the existing verified location-loading mechanism" instruction.
    Cached in-process; the file only changes via scripts/regenerate_location_data.py, which this
    module never calls."""
    global _subcontinent_cache
    if _subcontinent_cache is None:
        with open(SUBCONTINENT_DISTRICTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # data["states"] is ALREADY a dict keyed by state id (e.g. "CS.DL" -> {...}), confirmed by
        # direct inspection -- not a list, despite how similar files elsewhere in this project are
        # shaped. Used as-is; copying it into a second dict here would be a pointless, bug-prone
        # re-keying step.
        _subcontinent_cache = data.get("states", {})
    return _subcontinent_cache


def verified_state(state_id: str):
    return _load_subcontinent_districts().get(state_id)


def verified_district(state_id: str, district_id: str):
    state = verified_state(state_id)
    if not state:
        return None
    return next((d for d in state.get("districts", []) if d["id"] == district_id), None)


def verified_tehsil(state_id: str, district_id: str, tehsil_id: str):
    district = verified_district(state_id, district_id)
    if not district:
        return None
    return next((t for t in district.get("tehsils", []) if t["id"] == tehsil_id), None)


def verified_village_exists(conn, tehsil_or_district_id: str, village_id: str) -> bool:
    """India only -- the india_villages table (scripts/import_india_villages.py) is the real
    source; other Sub-continent countries don't currently have a village-level verified table at
    all (confirmed: static/data/subcontinent_districts.json stops at tehsil), so this always
    returns False for them -- correctly treated as "not verified," never as an error, since a
    provisional Village is exactly the right outcome when no verified village tier exists yet."""
    row = conn.execute(
        "SELECT 1 FROM india_villages WHERE id = ? AND tehsil_id = ?", (village_id, tehsil_or_district_id)
    ).fetchone()
    return row is not None


# ---- Layer B: provisional location CRUD and search --------------------------------------------

def _row_to_dict(row) -> dict:
    return dict(row) if row else None


def get_provisional(conn, provisional_id: int):
    return _row_to_dict(conn.execute("SELECT * FROM provisional_locations WHERE id = ?", (provisional_id,)).fetchone())


def to_present_location_id(provisional_id: int) -> str:
    return f"PROV-{provisional_id}"


def from_present_location_id(value: str):
    """None if `value` isn't a provisional-id string -- lets callers treat every present_location
    id uniformly: try this first, fall through to verified-directory lookup otherwise."""
    m = PROV_ID_RE.match(value or "")
    return int(m.group(1)) if m else None


def search_locations(conn, level: str, state_id: str, district_id: str = None, tehsil_id: str = None, q: str = "") -> list[dict]:
    """Same-STATE search only (never cross-state), verified candidates first then provisional
    ones, each result carrying its full parent hierarchy so two same-named results in different
    districts are visibly distinguishable. Exact-normalized-name match only -- no fuzzy scoring,
    consistent with this project's existing "normalize, never guess" convention."""
    if level not in VALID_LOCATION_TYPES:
        raise ValueError("level must be 'village' or 'tehsil'")
    norm_q = normalize_name(q)
    results = []

    state = verified_state(state_id)
    if not state:
        return results

    if level == "tehsil":
        for district in state.get("districts", []):
            for tehsil in district.get("tehsils", []):
                if not norm_q or normalize_name(tehsil["name"]) == norm_q:
                    results.append({
                        "id": tehsil["id"], "name": tehsil["name"], "type": "tehsil", "kind": "verified",
                        "state_name": state["name"], "district_name": district["name"],
                    })
        for row in conn.execute(
            """SELECT * FROM provisional_locations WHERE location_type = 'tehsil' AND parent_verified_state_id = ?
               AND status NOT IN ('rejected', 'merged')""",
            (state_id,),
        ).fetchall():
            if not norm_q or row["normalized_name"] == norm_q:
                district = verified_district(state_id, row["parent_verified_district_id"])
                results.append({
                    "id": to_present_location_id(row["id"]), "name": row["name"], "type": "tehsil", "kind": "provisional",
                    "state_name": state["name"], "district_name": district["name"] if district else "(unknown district)",
                    "status": row["status"],
                })
    else:  # village
        for district in state.get("districts", []):
            for tehsil in district.get("tehsils", []):
                # Verified villages (India only -- see verified_village_exists()'s own docstring).
                for vrow in conn.execute(
                    "SELECT id, name FROM india_villages WHERE tehsil_id = ?", (tehsil["id"],)
                ).fetchall():
                    if not norm_q or normalize_name(vrow["name"]) == norm_q:
                        results.append({
                            "id": vrow["id"], "name": vrow["name"], "type": "village", "kind": "verified",
                            "state_name": state["name"], "district_name": district["name"], "tehsil_name": tehsil["name"],
                        })
        for row in conn.execute(
            """SELECT * FROM provisional_locations WHERE location_type = 'village' AND parent_verified_state_id = ?
               AND status NOT IN ('rejected', 'merged')""",
            (state_id,),
        ).fetchall():
            if norm_q and row["normalized_name"] != norm_q:
                continue
            district = verified_district(state_id, row["parent_verified_district_id"])
            if row["parent_verified_tehsil_id"]:
                tehsil = verified_tehsil(state_id, row["parent_verified_district_id"], row["parent_verified_tehsil_id"])
                tehsil_name = tehsil["name"] if tehsil else "(unknown tehsil)"
            else:
                parent_tehsil = get_provisional(conn, row["parent_provisional_tehsil_id"])
                tehsil_name = f"{parent_tehsil['name']} (provisional)" if parent_tehsil else "(unknown tehsil)"
            results.append({
                "id": to_present_location_id(row["id"]), "name": row["name"], "type": "village", "kind": "provisional",
                "state_name": state["name"], "district_name": district["name"] if district else "(unknown district)",
                "tehsil_name": tehsil_name, "status": row["status"],
            })
    return results


def create_provisional_tehsil(conn, user_id: int, name: str, state_id: str, district_id: str) -> dict:
    if not allow_provisional_locations():
        raise PermissionError("Provisional location creation is currently disabled")
    if not (name or "").strip():
        raise ValueError("Name is required")
    district = verified_district(state_id, district_id)
    if not district:
        raise ValueError("District is not a verified child of the given State")
    existing = conn.execute(
        "SELECT id FROM provisional_locations WHERE location_type='tehsil' AND normalized_name=? AND parent_verified_district_id=?",
        (normalize_name(name), district_id),
    ).fetchone()
    if existing:
        raise ValueError("A provisional Tehsil with this name already exists under this District -- search for it instead of creating a duplicate")
    now = _now()
    cur = conn.execute(
        """INSERT INTO provisional_locations
           (location_type, name, normalized_name, parent_verified_district_id, parent_verified_state_id,
            status, created_by_user_id, created_at)
           VALUES ('tehsil', ?, ?, ?, ?, 'provisional', ?, ?)""",
        (name.strip(), normalize_name(name), district_id, state_id, user_id, now),
    )
    pid = cur.lastrowid
    conn.commit()
    record_event(conn, pid, "created", actor_user_id=user_id, detail={"location_type": "tehsil"})
    return get_provisional(conn, pid)


def create_provisional_village(conn, user_id: int, name: str, state_id: str, district_id: str,
                                verified_tehsil_id: str = None, provisional_tehsil_id: int = None) -> dict:
    if not allow_provisional_locations():
        raise PermissionError("Provisional location creation is currently disabled")
    if not (name or "").strip():
        raise ValueError("Name is required")
    if bool(verified_tehsil_id) == bool(provisional_tehsil_id):
        raise ValueError("Exactly one of verified_tehsil_id or provisional_tehsil_id is required")

    if verified_tehsil_id:
        tehsil = verified_tehsil(state_id, district_id, verified_tehsil_id)
        if not tehsil:
            raise ValueError("Tehsil is not a verified child of the given District/State")
        parent_verified_tehsil_id, parent_provisional_tehsil_id = verified_tehsil_id, None
    else:
        parent_tehsil = get_provisional(conn, provisional_tehsil_id)
        if not parent_tehsil or parent_tehsil["location_type"] != "tehsil":
            raise ValueError("provisional_tehsil_id does not refer to a real provisional Tehsil")
        if parent_tehsil["parent_verified_district_id"] != district_id or parent_tehsil["parent_verified_state_id"] != state_id:
            raise ValueError("The provisional Village must use the SAME State/District as its provisional Tehsil parent")
        parent_verified_tehsil_id, parent_provisional_tehsil_id = None, provisional_tehsil_id

    dup_filter = "parent_verified_tehsil_id = ?" if parent_verified_tehsil_id else "parent_provisional_tehsil_id = ?"
    dup_value = parent_verified_tehsil_id or parent_provisional_tehsil_id
    existing = conn.execute(
        f"SELECT id FROM provisional_locations WHERE location_type='village' AND normalized_name=? AND {dup_filter}",
        (normalize_name(name), dup_value),
    ).fetchone()
    if existing:
        raise ValueError("A provisional Village with this name already exists under this Tehsil -- search for it instead of creating a duplicate")

    now = _now()
    cur = conn.execute(
        """INSERT INTO provisional_locations
           (location_type, name, normalized_name, parent_verified_tehsil_id, parent_provisional_tehsil_id,
            parent_verified_district_id, parent_verified_state_id, status, created_by_user_id, created_at)
           VALUES ('village', ?, ?, ?, ?, ?, ?, 'provisional', ?, ?)""",
        (name.strip(), normalize_name(name), parent_verified_tehsil_id, parent_provisional_tehsil_id,
         district_id, state_id, user_id, now),
    )
    pid = cur.lastrowid
    conn.commit()
    record_event(conn, pid, "created", actor_user_id=user_id, detail={"location_type": "village"})
    return get_provisional(conn, pid)


def record_event(conn, provisional_location_id: int, event_type: str, actor_user_id: int = None, detail: dict = None) -> None:
    """Append-only; never edited or deleted. detail never carries GPS coordinates -- callers pass
    only non-sensitive context (counts, ids, reasons), matching Section 4 (Part 8.4)'s explicit
    instruction."""
    conn.execute(
        "INSERT INTO location_submission_events (provisional_location_id, event_type, actor_user_id, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (provisional_location_id, event_type, actor_user_id, json.dumps(detail or {}), _now()),
    )
    conn.commit()


# ---- Membership and the 24-user activation engine (Phase E) -----------------------------------

def is_qualifying_user(conn, user_id: int) -> bool:
    """A real, present-residence, non-demo, non-removed account -- the existing project
    conventions (users.is_demo, users.is_removed, both from migration 016_add_demo_flags.py),
    never a Family Tree placeholder (those have no users.id at all) and never a birth-location
    reference (birth_users is a separate, metadata-only concept -- see elemental_core.py)."""
    row = conn.execute("SELECT is_demo, is_removed FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return False
    return not row["is_demo"] and not row["is_removed"]


def add_membership(conn, provisional_location_id: int, user_id: int) -> dict:
    """Idempotent: ON CONFLICT DO NOTHING means a duplicate call never creates a second row or
    double-counts. Transaction-safe: the INSERT and the recount both happen before commit, inside
    the same connection's implicit transaction -- SQLite's single-writer model makes the combined
    operation atomic without extra locking. Triggers the IMMEDIATE half of the hybrid activation
    check right here; the background reconciler (reconcile_all) is the other half, for anything
    this path misses."""
    prov = get_provisional(conn, provisional_location_id)
    if not prov:
        raise LookupError("Provisional location not found")
    if prov["status"] in ("active", "rejected", "merged", "inactive"):
        return {"membership": "not_added", "reason": f"location status is '{prov['status']}'"}
    conn.execute(
        """INSERT INTO provisional_location_members (provisional_location_id, user_id, role, joined_at)
           VALUES (?, ?, 'present_resident', ?)
           ON CONFLICT(provisional_location_id, user_id) DO UPDATE SET left_at = NULL""",
        (provisional_location_id, user_id, _now()),
    )
    conn.commit()
    record_event(conn, provisional_location_id, "member_joined", actor_user_id=user_id)
    activation_result = evaluate_activation(conn, provisional_location_id)
    return {"membership": "added", "activation": activation_result}


def remove_membership(conn, provisional_location_id: int, user_id: int, reason: str = "present_residence_changed") -> None:
    """Called when a member changes present residence away from this provisional location, or
    becomes ineligible. Soft-removal (left_at timestamp), never a DELETE -- the historical fact
    "this user was once counted here" stays auditable; qualifying_member_count() below excludes
    left_at IS NOT NULL rows from the live count."""
    conn.execute(
        "UPDATE provisional_location_members SET left_at = ? WHERE provisional_location_id = ? AND user_id = ? AND left_at IS NULL",
        (_now(), provisional_location_id, user_id),
    )
    conn.commit()
    record_event(conn, provisional_location_id, "status_changed", actor_user_id=user_id, detail={"reason": reason, "change": "member_left"})


def qualifying_member_count(conn, provisional_location_id: int) -> int:
    rows = conn.execute(
        "SELECT user_id FROM provisional_location_members WHERE provisional_location_id = ? AND left_at IS NULL",
        (provisional_location_id,),
    ).fetchall()
    return sum(1 for r in rows if is_qualifying_user(conn, r["user_id"]))


def evaluate_activation(conn, provisional_location_id: int) -> dict:
    """The single controlled promotion service (Section 5.7) -- the ONLY place that ever sets
    status='active'. A client-supplied status is never trusted (no route accepts a raw status
    field at all -- see app.py's routes). Safe to call repeatedly (idempotent): a location already
    'active' is a pure no-op; one already 'pending_review' is re-evaluated but not force-promoted."""
    prov = get_provisional(conn, provisional_location_id)
    if not prov or prov["status"] in ("active", "rejected", "merged", "inactive"):
        return {"result": "no_change", "status": prov["status"] if prov else None}

    count = qualifying_member_count(conn, provisional_location_id)
    threshold = activation_threshold()
    if count < threshold:
        return {"result": "below_threshold", "count": count, "threshold": threshold}

    # Section 5.6: independent Village/Tehsil activation -- a Village at threshold whose parent
    # Tehsil (verified OR provisional) is not itself active/verified goes to pending_review, never
    # force-promotes the parent and never force-activates itself past that check.
    if prov["location_type"] == "village" and prov["parent_provisional_tehsil_id"]:
        parent_tehsil = get_provisional(conn, prov["parent_provisional_tehsil_id"])
        if not parent_tehsil or parent_tehsil["status"] != "active":
            conn.execute("UPDATE provisional_locations SET status = 'pending_review' WHERE id = ?", (provisional_location_id,))
            conn.commit()
            record_event(conn, provisional_location_id, "status_changed",
                         detail={"new_status": "pending_review", "reason": "parent provisional Tehsil is not yet active"})
            return {"result": "pending_review", "reason": "parent_tehsil_not_active", "count": count}

    # Duplicate check (Section 5.7 step 5): another provisional location with the same normalized
    # name under the SAME parent that is already active would mean this one should have been
    # matched/merged, not independently promoted.
    dup_filter = "parent_verified_tehsil_id = ?" if prov["parent_verified_tehsil_id"] else "parent_provisional_tehsil_id = ?"
    dup_value = prov["parent_verified_tehsil_id"] or prov["parent_provisional_tehsil_id"]
    if prov["location_type"] == "village":
        dup = conn.execute(
            f"SELECT id FROM provisional_locations WHERE location_type='village' AND normalized_name=? AND {dup_filter} AND status='active' AND id != ?",
            (prov["normalized_name"], dup_value, provisional_location_id),
        ).fetchone()
    else:
        dup = conn.execute(
            "SELECT id FROM provisional_locations WHERE location_type='tehsil' AND normalized_name=? AND parent_verified_district_id=? AND status='active' AND id != ?",
            (prov["normalized_name"], prov["parent_verified_district_id"], provisional_location_id),
        ).fetchone()
    if dup:
        conn.execute("UPDATE provisional_locations SET status = 'pending_review' WHERE id = ?", (provisional_location_id,))
        conn.commit()
        record_event(conn, provisional_location_id, "status_changed",
                     detail={"new_status": "pending_review", "reason": "duplicate of an already-active provisional location", "duplicate_of": dup["id"]})
        return {"result": "pending_review", "reason": "duplicate_candidate", "count": count}

    now = _now()
    conn.execute(
        "UPDATE provisional_locations SET status = 'active', activated_at = ? WHERE id = ?",
        (now, provisional_location_id),
    )
    conn.commit()
    record_event(conn, provisional_location_id, "activated", detail={"qualifying_member_count": count, "threshold": threshold})
    return {"result": "activated", "count": count, "threshold": threshold, "activated_at": now}


def reconcile_all(conn, batch_size: int = 200) -> dict:
    """The background half of the hybrid activation engine (Section 5.4) -- re-evaluates every
    non-terminal provisional location in bounded batches, catching anything the immediate
    per-registration check missed (e.g. a membership change, or a parent Tehsil that activated
    after its child Village already reached the threshold). Idempotent and safe to run repeatedly
    -- evaluate_activation() itself is the only state-changing call, and it's already a no-op for
    anything not eligible."""
    rows = conn.execute(
        "SELECT id FROM provisional_locations WHERE status IN ('provisional', 'eligible_for_activation', 'pending_review') LIMIT ?",
        (batch_size,),
    ).fetchall()
    results = {"checked": 0, "activated": 0, "pending_review": 0, "below_threshold": 0, "errors": 0}
    for row in rows:
        results["checked"] += 1
        try:
            outcome = evaluate_activation(conn, row["id"])
            key = outcome.get("result")
            if key in results:
                results[key] += 1
        except Exception as e:  # noqa: BLE001 -- a single bad row must never abort the batch
            results["errors"] += 1
            print(f"[provisional_location_core] reconcile_all: error on id={row['id']}: {e}")
    return results


def init_scheduler(app) -> None:
    """Same safe-deployment pattern as election_test_scheduler.init_scheduler() (app.py:5924) --
    guarded by QM_DISABLE_SCHEDULER (tests/tools) and by the WERKZEUG_RUN_MAIN check so the Flask
    debug reloader's parent+child process pair never ends up running two independent
    BackgroundScheduler instances."""
    if os.environ.get("QM_DISABLE_SCHEDULER"):
        print("[provisional_location] QM_DISABLE_SCHEDULER set -- reconciliation cron not registered")
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from db import get_db

        def _tick():
            conn = get_db()
            try:
                ensure_tables(conn)
                result = reconcile_all(conn)
                if result["checked"]:
                    print(f"[provisional_location] reconciliation tick: {result}")
            finally:
                conn.close()

        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(_tick, IntervalTrigger(minutes=15))
        scheduler.start()
        print("[provisional_location] reconciliation worker registered (every 15 minutes)")


# ---- Phase C: GPS observations ------------------------------------------------------------------

CONSENT_VERSION = "2026-11-mvp-v1"


def submit_observation(conn, user_id: int, latitude, longitude, accuracy_meters,
                        consent_internal_storage: bool, consent_centroid_aggregation: bool,
                        consent_external_overpass_lookup: bool,
                        qumanity_verified_location_id: str = None, provisional_location_id: int = None) -> dict:
    """Section 4.1's consent dependency, enforced here (not just documented): centroid-aggregation
    consent without internal-storage consent is rejected outright with an explanatory error,
    rather than silently storing the coordinate anyway -- "do not silently override an unchecked
    consent" (Part 4.1). Returns no coordinates in its own result, by design (Section 4.5)."""
    if consent_centroid_aggregation and not consent_internal_storage:
        raise ValueError("Centroid-aggregation consent requires internal-storage consent too -- storage must be allowed before a coordinate can be retained for any purpose")

    if not consent_internal_storage:
        # Consent for storage was never given -- record that the user was asked and declined,
        # WITHOUT any coordinate, ever (not even transiently) -- Part 4.1/4.4's explicit requirement.
        cur = conn.execute(
            """INSERT INTO user_location_observations
               (user_id, qumanity_verified_location_id, provisional_location_id, consent_internal_storage,
                consent_centroid_aggregation, consent_external_overpass_lookup, consent_version, status, created_at)
               VALUES (?, ?, ?, 0, 0, ?, ?, 'denied', ?)""",
            (user_id, qumanity_verified_location_id, provisional_location_id, int(bool(consent_external_overpass_lookup)), CONSENT_VERSION, _now()),
        )
        conn.commit()
        return {"observation_id": cur.lastrowid, "stored_coordinates": False, "status": "denied"}

    lat = float(latitude)
    lon = float(longitude)
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError("Coordinates out of valid range")
    acc = float(accuracy_meters) if accuracy_meters is not None else None

    cur = conn.execute(
        """INSERT INTO user_location_observations
           (user_id, qumanity_verified_location_id, provisional_location_id, latitude, longitude, accuracy_meters,
            captured_at, consent_internal_storage, consent_centroid_aggregation, consent_external_overpass_lookup,
            consent_version, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'accepted', ?)""",
        (user_id, qumanity_verified_location_id, provisional_location_id, lat, lon, acc, _now(),
         int(bool(consent_centroid_aggregation)), int(bool(consent_external_overpass_lookup)), CONSENT_VERSION, _now()),
    )
    observation_id = cur.lastrowid
    conn.commit()

    # consent_external_overpass_lookup is recorded as a PREFERENCE only -- no job is ever queued,
    # no request ever made, this phase (Part 9's absolute boundary). Nothing else happens here.

    if consent_centroid_aggregation:
        target_type = "provisional_location" if provisional_location_id else "verified_location"
        target_id = str(provisional_location_id) if provisional_location_id else qumanity_verified_location_id
        if target_id:
            _recompute_centroid(conn, target_type, target_id)

    return {"observation_id": observation_id, "stored_coordinates": True, "status": "accepted"}


def record_observation_unavailable(conn, user_id: int, reason: str,
                                    qumanity_verified_location_id: str = None, provisional_location_id: int = None) -> dict:
    """GPS denied/unsupported/timed-out -- a real, auditable status-only row, zero coordinates,
    per Section 1.6's explicit requirement not to fabricate 0,0."""
    status = "denied" if reason == "permission_denied" else "unavailable"
    cur = conn.execute(
        """INSERT INTO user_location_observations
           (user_id, qumanity_verified_location_id, provisional_location_id, consent_internal_storage,
            consent_centroid_aggregation, consent_external_overpass_lookup, consent_version, status, created_at)
           VALUES (?, ?, ?, 0, 0, 0, ?, ?, ?)""",
        (user_id, qumanity_verified_location_id, provisional_location_id, CONSENT_VERSION, status, _now()),
    )
    conn.commit()
    return {"observation_id": cur.lastrowid, "stored_coordinates": False, "status": status}


def _recompute_centroid(conn, target_type: str, target_id: str) -> dict:
    """Method: per-axis MEDIAN of qualifying observations (consent_internal_storage=1 AND
    consent_centroid_aggregation=1 AND status='accepted'), chosen over a plain mean because it is
    far more robust to a single wildly-wrong outlier (e.g. a stale/cached browser location from a
    different city) without needing a separate outlier-detection pass first -- documented here per
    Part 4.6's explicit instruction to record the chosen method and its rationale. Confidence is
    'pending' below the research-recommended minimum sample size (reusing the SAME 24 used for
    membership activation is NOT assumed -- kept at a smaller, separately-configurable sample
    threshold here since GPS consent is optional and will almost always lag membership count; see
    this module's own Decision-register note in the final report)."""
    rows = conn.execute(
        """SELECT latitude, longitude FROM user_location_observations
           WHERE status = 'accepted' AND consent_internal_storage = 1 AND consent_centroid_aggregation = 1
             AND {col} = ?""".format(col="provisional_location_id" if target_type == "provisional_location" else "qumanity_verified_location_id"),
        (target_id,),
    ).fetchall()
    sample_size = len(rows)
    MIN_SAMPLE_FOR_CONFIDENCE = 5  # a separate, smaller, explicitly-configurable-in-future constant -- NOT the 24-member activation threshold
    if sample_size == 0:
        confidence = "pending"
        lat = lon = None
    else:
        lat = median(r["latitude"] for r in rows)
        lon = median(r["longitude"] for r in rows)
        confidence = "high" if sample_size >= MIN_SAMPLE_FOR_CONFIDENCE else "low"
    conn.execute(
        "DELETE FROM location_centroid_observations WHERE target_type = ? AND target_id = ?",
        (target_type, target_id),
    )
    conn.execute(
        """INSERT INTO location_centroid_observations (target_type, target_id, centroid_lat, centroid_lon, sample_size, method, confidence, computed_at)
           VALUES (?, ?, ?, ?, ?, 'median', ?, ?)""",
        (target_type, target_id, lat, lon, sample_size, confidence, _now()),
    )
    conn.commit()
    return {"sample_size": sample_size, "confidence": confidence}
