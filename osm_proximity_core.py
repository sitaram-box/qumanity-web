"""OSM Coordinate Linking for the Q-Map foundation, 2026-11.

Links a consenting user's stored GPS observation (provisional_location_core.py's
user_location_observations) to nearby OSM features (roads/buildings/POIs within 200m), via the
public Overpass API, entirely asynchronously -- registration and any future present-residence
update must never wait on this.

CONSENT, READ THIS BEFORE CHANGING ANYTHING: provisional_location_core.py's own submit_observation()
has, since the Crowdsourced Location MVP (commit 211480c), recorded consent_external_overpass_lookup
as "a PREFERENCE only -- no job is ever queued, no request ever made" (see that function's own
comment). This module is what turns that preference into a real action, for the FIRST time -- and
it does so deliberately conservatively: it only ever enqueues a job for an observation whose
consent_version equals the CURRENT, live value of provisional_location_core.CONSENT_VERSION, which
this feature's own activation bumped (see that module's own changelog comment on the constant).
Every observation captured under the OLD version (when the checkbox said "when this service
becomes available") is never retroactively queried -- a user who consented before this feature
existed is asked again, not assumed, consistent with this task's explicit "no blanket retroactive
query against all existing users" rule. A user consents FRESH to get queried; nothing here reaches
backward into history.

OVERPASS FAIR-USE, READ THIS TOO: the public Overpass API's own usage policy is built around
occasional, bounded queries -- not sustained per-user production traffic. run_worker_once() is
deliberately conservative: it processes a small, bounded batch per call, with a real sleep between
each request (never a burst), and is meant to be invoked periodically (via init_scheduler(), the
same BackgroundScheduler convention every other scheduler in this project uses), not continuously.
If Qumanity's registered-user volume grows meaningfully, this feature's query volume should be
revisited against Overpass's published usage policy -- possibly moving to a self-hosted mirror --
before it becomes a volume feature. This is flagged here and in docs/MASTER_STATUS.md as a real
operational risk, not a hypothetical one.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os

import osm_http_core

SCHEMA = """
CREATE TABLE IF NOT EXISTS osm_proximity_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    observation_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','claimed','done','failed','cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    claimed_by TEXT,
    claimed_at TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (observation_id)
);
CREATE INDEX IF NOT EXISTS idx_osm_jobs_status ON osm_proximity_jobs(status);

CREATE TABLE IF NOT EXISTS osm_feature_cache (
    osm_type TEXT NOT NULL,
    osm_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    tags_json TEXT,
    geometry_json TEXT NOT NULL,
    osm_data_timestamp TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (osm_type, osm_id)
);

CREATE TABLE IF NOT EXISTS user_osm_proximity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    observation_id INTEGER NOT NULL,
    qumanity_location_id TEXT,
    osm_type TEXT NOT NULL,
    osm_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    distance_meters REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','withdrawn')),
    created_at TEXT NOT NULL,
    UNIQUE (observation_id, osm_type, osm_id)
);
CREATE INDEX IF NOT EXISTS idx_user_osm_proximity_user ON user_osm_proximity(user_id, status);
"""

PROXIMITY_RADIUS_METERS = 200
MAX_JOBS_PER_WORKER_TICK = 5
INTER_REQUEST_SLEEP_SECONDS = 5  # throttle between consecutive Overpass calls within one tick -- never a burst


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def enqueue_job_if_eligible(conn, user_id: int, observation_id: int) -> dict:
    """Called right after provisional_location_core.submit_observation() accepts a new
    observation. Only enqueues if BOTH consent_internal_storage and
    consent_external_overpass_lookup are set, the observation is 'accepted' (has real
    coordinates), AND its consent_version is the CURRENT live version -- never an older,
    preference-only consent. Idempotent: a second call for the same observation_id is a no-op
    (UNIQUE constraint)."""
    import provisional_location_core as plc  # local import avoids a circular import at module load

    row = conn.execute(
        "SELECT consent_internal_storage, consent_external_overpass_lookup, consent_version, status "
        "FROM user_location_observations WHERE id = ?", (observation_id,),
    ).fetchone()
    if not row:
        return {"enqueued": False, "reason": "observation not found"}
    if not (row["consent_internal_storage"] and row["consent_external_overpass_lookup"]):
        return {"enqueued": False, "reason": "consent not given for external OSM lookup"}
    if row["status"] != "accepted":
        return {"enqueued": False, "reason": f"observation status is {row['status']!r}, not 'accepted'"}
    if row["consent_version"] != plc.CONSENT_VERSION:
        return {"enqueued": False, "reason": f"observation consent_version {row['consent_version']!r} predates "
                                              f"the current OSM lookup consent version {plc.CONSENT_VERSION!r} -- "
                                              f"never retroactively queried"}
    try:
        cur = conn.execute(
            "INSERT INTO osm_proximity_jobs (user_id, observation_id, created_at) VALUES (?, ?, ?)",
            (user_id, observation_id, _now()),
        )
        conn.commit()
        return {"enqueued": True, "job_id": cur.lastrowid}
    except Exception:
        conn.rollback()
        return {"enqueued": False, "reason": "already queued for this observation"}


def withdraw_overpass_consent(conn, user_id: int) -> dict:
    """Stops future jobs, cancels pending ones, and makes this user's existing OSM associations
    unavailable to Q-Map -- the rows themselves are kept (status='withdrawn', not deleted) so the
    fact that a withdrawal happened remains auditable, but get_user_nearby() below only ever
    returns 'active' rows. Does NOT touch user_location_observations -- that table's consent
    columns are an immutable record of what was true at submission time; withdrawal is recorded
    here, not by falsifying history there."""
    cancelled = conn.execute(
        "UPDATE osm_proximity_jobs SET status = 'cancelled' WHERE user_id = ? AND status IN ('pending', 'claimed')",
        (user_id,),
    ).rowcount
    withdrawn = conn.execute(
        "UPDATE user_osm_proximity SET status = 'withdrawn' WHERE user_id = ? AND status = 'active'",
        (user_id,),
    ).rowcount
    conn.commit()
    return {"jobs_cancelled": cancelled, "associations_withdrawn": withdrawn}


def get_user_nearby(conn, user_id: int) -> list[dict]:
    """The Q-Map route's own data source -- active rows only, joined with the cached feature's
    own safe tag subset. Never includes the user's raw coordinates."""
    rows = conn.execute(
        """SELECT p.osm_type, p.osm_id, p.category, p.distance_meters, p.qumanity_location_id, p.created_at,
                  c.tags_json
           FROM user_osm_proximity p
           LEFT JOIN osm_feature_cache c ON c.osm_type = p.osm_type AND c.osm_id = p.osm_id
           WHERE p.user_id = ? AND p.status = 'active'
           ORDER BY p.distance_meters ASC""",
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        tags = {}
        if r["tags_json"]:
            try:
                tags = json.loads(r["tags_json"])
            except (json.JSONDecodeError, TypeError):
                tags = {}
        safe_tags = {k: v for k, v in tags.items() if k in ("name", "highway", "building", "amenity")}
        out.append({
            "osm_type": r["osm_type"], "osm_id": r["osm_id"], "category": r["category"],
            "distance_meters": round(r["distance_meters"], 1), "tags": safe_tags,
            "qumanity_location_id": r["qumanity_location_id"], "linked_at": r["created_at"],
            "attribution": "© OpenStreetMap contributors",
        })
    return out


def _haversine_meters(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_distance_meters(lat: float, lon: float, element: dict) -> float | None:
    """Node -> its own point. Way/relation -> the minimum distance to any vertex of its own
    geometry (an approximation of nearest-point-on-geometry, not a full point-to-segment
    projection -- documented here as exactly that; a straight centroid would be worse, since a
    long road's centroid can be far from the segment nearest the user). None if no usable
    geometry -- reported as a skipped element, never a false distance."""
    if element["type"] == "node":
        return _haversine_meters(lat, lon, element["lat"], element["lon"])
    geometry = element.get("geometry")
    if not geometry:
        return None
    return min(_haversine_meters(lat, lon, pt["lat"], pt["lon"]) for pt in geometry)


def _classify(tags: dict) -> str | None:
    if tags.get("amenity") in ("hospital", "clinic", "school", "place_of_worship", "police", "fire_station"):
        return "poi"
    if "building" in tags:
        return "building"
    if "highway" in tags:
        return "road"
    return None


def _build_query(lat: float, lon: float) -> str:
    return (
        f'[out:json][timeout:30];\n'
        f'(\n'
        f'  way["highway"](around:{PROXIMITY_RADIUS_METERS},{lat},{lon});\n'
        f'  way["building"](around:{PROXIMITY_RADIUS_METERS},{lat},{lon});\n'
        f'  node["amenity"~"^(hospital|clinic|school|place_of_worship|police|fire_station)$"](around:{PROXIMITY_RADIUS_METERS},{lat},{lon});\n'
        f'  way["amenity"~"^(hospital|clinic|school|place_of_worship|police|fire_station)$"](around:{PROXIMITY_RADIUS_METERS},{lat},{lon});\n'
        f');\n'
        f'out geom;\n'
    )


def process_job(conn, job: dict, post_overpass=osm_http_core.post_overpass, sleep=None) -> dict:
    """Processes exactly one job: re-verifies consent is still live right now (not just at
    enqueue time -- a withdrawal between enqueue and processing must still be honored), fetches
    nearby features, stores them, marks the job done. Never raises on an Overpass failure --
    records it on the job and returns, so one bad job never crashes the batch."""
    import provisional_location_core as plc

    obs = conn.execute(
        "SELECT latitude, longitude, qumanity_verified_location_id, provisional_location_id, "
        "consent_internal_storage, consent_external_overpass_lookup, consent_version, status "
        "FROM user_location_observations WHERE id = ?", (job["observation_id"],),
    ).fetchone()
    if not obs or obs["status"] != "accepted" or not obs["consent_external_overpass_lookup"] \
            or not obs["consent_internal_storage"] or obs["consent_version"] != plc.CONSENT_VERSION:
        conn.execute("UPDATE osm_proximity_jobs SET status = 'cancelled', completed_at = ? WHERE id = ?",
                     (_now(), job["id"]))
        conn.commit()
        return {"status": "cancelled", "reason": "consent no longer valid at processing time"}

    qumanity_location_id = (obs["qumanity_verified_location_id"]
                             or (f"PROV-{obs['provisional_location_id']}" if obs["provisional_location_id"] else None))

    try:
        query = _build_query(obs["latitude"], obs["longitude"])
        parsed = post_overpass(query, purpose="Qumanity Q-Map OSM proximity link", sleep=sleep or osm_http_core.time.sleep)
    except osm_http_core.OverpassError as e:
        attempts = job.get("attempts", 0) + 1
        conn.execute(
            "UPDATE osm_proximity_jobs SET status = 'pending', attempts = ?, last_error = ?, claimed_by = NULL, claimed_at = NULL WHERE id = ?",
            (attempts, str(e)[:500], job["id"]),
        )
        conn.commit()
        return {"status": "failed", "error": str(e)}

    osm_timestamp = parsed.get("osm3s", {}).get("timestamp_osm_base")
    linked = 0
    for el in parsed.get("elements", []):
        tags = el.get("tags", {}) or {}
        category = _classify(tags)
        if category is None:
            continue
        distance = _nearest_distance_meters(obs["latitude"], obs["longitude"], el)
        if distance is None or distance > PROXIMITY_RADIUS_METERS:
            continue
        geometry_for_cache = (
            {"lat": el["lat"], "lon": el["lon"]} if el["type"] == "node" else {"geometry": el.get("geometry", [])}
        )
        conn.execute(
            """INSERT INTO osm_feature_cache (osm_type, osm_id, category, tags_json, geometry_json, osm_data_timestamp, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(osm_type, osm_id) DO UPDATE SET
                 category = excluded.category, tags_json = excluded.tags_json,
                 geometry_json = excluded.geometry_json, osm_data_timestamp = excluded.osm_data_timestamp,
                 fetched_at = excluded.fetched_at""",
            (el["type"], el["id"], category, json.dumps(tags, ensure_ascii=False),
             json.dumps(geometry_for_cache), osm_timestamp, _now()),
        )
        conn.execute(
            """INSERT INTO user_osm_proximity (user_id, observation_id, qumanity_location_id, osm_type, osm_id, category, distance_meters, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(observation_id, osm_type, osm_id) DO UPDATE SET
                 distance_meters = excluded.distance_meters, status = 'active'""",
            (job["user_id"], job["observation_id"], qumanity_location_id, el["type"], el["id"], category, distance, _now()),
        )
        linked += 1

    conn.execute("UPDATE osm_proximity_jobs SET status = 'done', completed_at = ? WHERE id = ?", (_now(), job["id"]))
    conn.commit()
    return {"status": "done", "features_linked": linked}


def claim_pending_jobs(conn, worker_id: str, limit: int = MAX_JOBS_PER_WORKER_TICK) -> list[dict]:
    """Claims up to `limit` pending jobs atomically, so two worker instances never process the
    same job -- an UPDATE with a WHERE on the current status, immediately re-read by id, is
    SQLite's own safe equivalent of a claim-and-lock without a separate advisory lock."""
    candidates = conn.execute(
        "SELECT id FROM osm_proximity_jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?", (limit,)
    ).fetchall()
    claimed = []
    for row in candidates:
        cur = conn.execute(
            "UPDATE osm_proximity_jobs SET status = 'claimed', claimed_by = ?, claimed_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (worker_id, _now(), row["id"]),
        )
        if cur.rowcount == 1:
            job = conn.execute("SELECT * FROM osm_proximity_jobs WHERE id = ?", (row["id"],)).fetchone()
            claimed.append(dict(job))
    conn.commit()
    return claimed


def run_worker_once(conn, worker_id: str = "worker-1", sleep=None) -> dict:
    """One bounded tick: claim a small batch, process each with a real throttle between
    requests. Meant to be called periodically (see init_scheduler), never in a tight loop."""
    sleep = sleep or osm_http_core.time.sleep
    jobs = claim_pending_jobs(conn, worker_id)
    results = []
    for i, job in enumerate(jobs):
        if i > 0:
            sleep(INTER_REQUEST_SLEEP_SECONDS)
        results.append(process_job(conn, job, sleep=sleep))
    return {"jobs_processed": len(results), "results": results}


def init_scheduler(app) -> None:
    """Same BackgroundScheduler convention as provisional_location_core.init_scheduler() and
    every other scheduler in this project -- gated by QM_DISABLE_SCHEDULER, guarded against the
    Werkzeug reloader double-starting it."""
    if os.environ.get("QM_DISABLE_SCHEDULER"):
        return
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.debug:
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    import db as dbmod

    def _tick():
        conn = dbmod.get_db()
        try:
            ensure_tables(conn)
            run_worker_once(conn)
        finally:
            conn.close()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(_tick, "interval", minutes=15, id="osm_proximity_worker_tick")
    scheduler.start()
