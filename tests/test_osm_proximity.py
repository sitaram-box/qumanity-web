"""Covers OSM Coordinate Linking for the Q-Map foundation (2026-11, Phase 4): the
user_osm_proximity/osm_feature_cache/osm_proximity_jobs schema, consent-gated job enqueueing
(including the "never retroactively query an older consent version" rule), the 200m proximity
worker, withdrawal, and the /api/qmap/user-nearby/<id> route's authorization.

No live Overpass call is made anywhere in this file -- every HTTP interaction is mocked via
osm_http_core.post_overpass's own injectable `opener`/`sleep` parameters, same pattern as
tests/test_fetch_north_west_delhi_osm.py.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, same conventions as every other test file in this project.

Run with: python3 tests/test_osm_proximity.py (not -I)
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import urllib.error
from email.message import Message

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import provisional_location_core as plc  # noqa: E402
import osm_proximity_core as opc  # noqa: E402
import osm_http_core  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

STATE_ID, DISTRICT_ID, TEHSIL_ID = "CS.DL", "CS.DL.3", "CS.DL.3.4"
VILLAGE_LOC = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": STATE_ID, "name": "Delhi"},
    "district": {"id": DISTRICT_ID, "name": "North West Delhi"}, "tehsil": {"id": TEHSIL_ID, "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def register_and_login():
    _n[0] += 1
    payload = {
        "name": f"OSM Tester {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_LOC, "present_location": VILLAGE_LOC, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:300]}")
    body = res.get_json()
    private_code = body["private_code"]
    user_id = body["user_id"]
    login_res = client.post("/login", json={"private_id": private_code, "pin": "12345"})
    if login_res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {login_res.status_code} {login_res.get_data(as_text=True)[:300]}")
    return user_id


def logout():
    client.get("/logout")


def raw(sql, params=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def raw_all(sql, params=()):
    conn = dbmod.get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def fake_opener(responses):
    it = iter(responses)

    class FakeResponse:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

    def _opener(req, timeout):
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    return _opener


def http_error(code, retry_after=None):
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://overpass-api.de/api/interpreter", code, "err", hdrs, io.BytesIO(b"err"))


# -- 1. Migration/table integrity ------------------------------------------------------------------

conn = dbmod.get_db()
opc.ensure_tables(conn)
tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
conn.close()
check("osm_proximity_jobs table exists", "osm_proximity_jobs" in tables)
check("osm_feature_cache table exists", "osm_feature_cache" in tables)
check("user_osm_proximity table exists", "user_osm_proximity" in tables)

# -- 2. _classify() categorization -------------------------------------------------------------------

check("classifies highway as road", opc._classify({"highway": "residential"}) == "road")
check("classifies building as building", opc._classify({"building": "yes"}) == "building")
check("classifies hospital amenity as poi", opc._classify({"amenity": "hospital"}) == "poi")
check("classifies unrelated tags as None", opc._classify({"shop": "bakery"}) is None)

# -- 3. _nearest_distance_meters: node vs way ----------------------------------------------------

node_el = {"type": "node", "lat": 28.7041, "lon": 77.1025}
dist_node = opc._nearest_distance_meters(28.7041, 77.1025, node_el)
check("node distance to itself is ~0", dist_node is not None and dist_node < 1)

way_el = {"type": "way", "geometry": [{"lat": 28.7041, "lon": 77.1025}, {"lat": 28.7100, "lon": 77.1100}]}
dist_way = opc._nearest_distance_meters(28.7041, 77.1025, way_el)
check("way distance uses the nearest vertex, not the far one", dist_way is not None and dist_way < 1)

way_no_geom = {"type": "way", "geometry": []}
check("way with no geometry returns None, never a false distance", opc._nearest_distance_meters(0, 0, way_no_geom) is None)

# -- 4. Registration/login, then consent-gated enqueue ---------------------------------------------

user_id = register_and_login()

# No consent at all -> stored, but never enqueued.
no_consent = client.post("/api/location/observation", json={
    "latitude": 28.7041, "longitude": 77.1025, "accuracy_meters": 10,
    "consent_internal_storage": False, "consent_centroid_aggregation": False, "consent_external_overpass_lookup": False,
})
check("observation with no consent is accepted by the route", no_consent.status_code == 201)
jobs_after_no_consent = raw("SELECT COUNT(*) AS c FROM osm_proximity_jobs WHERE user_id = ?", (user_id,))["c"]
check("no job is enqueued without external-lookup consent", jobs_after_no_consent == 0)

# Full consent, current version -> enqueued.
full_consent = client.post("/api/location/observation", json={
    "latitude": 28.7041, "longitude": 77.1025, "accuracy_meters": 10,
    "consent_internal_storage": True, "consent_centroid_aggregation": False, "consent_external_overpass_lookup": True,
})
check("observation with full external-lookup consent is accepted", full_consent.status_code == 201)
jobs_after_full_consent = raw_all("SELECT * FROM osm_proximity_jobs WHERE user_id = ? ORDER BY id DESC", (user_id,))
check("exactly one job is enqueued with full consent", len(jobs_after_full_consent) == 1)
check("the enqueued job is pending", jobs_after_full_consent[0]["status"] == "pending")

# -- 5. Fresh-consent rule: an observation under an OLDER consent_version is never enqueued ---------

conn = dbmod.get_db()
cur = conn.execute(
    """INSERT INTO user_location_observations
       (user_id, latitude, longitude, accuracy_meters, captured_at, consent_internal_storage,
        consent_centroid_aggregation, consent_external_overpass_lookup, consent_version, status, created_at)
       VALUES (?, 1.0, 1.0, 5, '2026-01-01T00:00:00', 1, 0, 1, 'OLD-VERSION', 'accepted', '2026-01-01T00:00:00')""",
    (user_id,),
)
old_obs_id = cur.lastrowid
conn.commit()
conn.close()
enqueue_result = opc.enqueue_job_if_eligible(dbmod.get_db(), user_id, old_obs_id)
check("an observation under an old consent_version is refused, never enqueued", not enqueue_result["enqueued"])
check("the refusal reason names the version mismatch", "consent_version" in enqueue_result["reason"])

# Re-running enqueue for the SAME current-version observation is a safe no-op (idempotent).
conn = dbmod.get_db()
repeat = opc.enqueue_job_if_eligible(conn, user_id, jobs_after_full_consent[0]["observation_id"])
conn.close()
check("re-enqueueing the same observation is refused (already queued), not duplicated", not repeat["enqueued"])
jobs_count_after_repeat = raw("SELECT COUNT(*) AS c FROM osm_proximity_jobs WHERE user_id = ?", (user_id,))["c"]
check("no duplicate job was created by the repeat enqueue attempt", jobs_count_after_repeat == 1)

# -- 6. claim_pending_jobs: claims exactly the pending job, marks it claimed -------------------------

conn = dbmod.get_db()
claimed = opc.claim_pending_jobs(conn, worker_id="test-worker")
conn.close()
check("claim_pending_jobs claims exactly one job", len(claimed) == 1)
check("the claimed job is now status='claimed'", raw("SELECT status FROM osm_proximity_jobs WHERE id = ?", (claimed[0]["id"],))["status"] == "claimed")

second_claim = opc.claim_pending_jobs(dbmod.get_db(), worker_id="other-worker")
check("a second worker claims nothing more (no pending jobs left)", len(second_claim) == 0)

# -- 7. process_job: mocked Overpass, 200m filtering, node+way classification, caching ---------------

good_body = json.dumps({
    "osm3s": {"timestamp_osm_base": "2026-11-02T00:00:00Z"},
    "elements": [
        {"type": "node", "id": 111, "lat": 28.7041, "lon": 77.1025, "tags": {"amenity": "hospital", "name": "Near Hospital"}},
        {"type": "way", "id": 222, "tags": {"building": "yes"},
         "geometry": [{"lat": 28.7041, "lon": 77.1025}, {"lat": 28.7042, "lon": 77.1026}]},
        {"type": "way", "id": 333, "tags": {"highway": "residential"},
         "geometry": [{"lat": 29.0, "lon": 78.0}]},  # far away -- must be filtered out by the 200m check
    ],
}).encode()
opener = fake_opener([good_body])

conn = dbmod.get_db()
result = opc.process_job(conn, claimed[0], post_overpass=lambda q, purpose, sleep=None: osm_http_core.post_overpass(q, purpose, opener=opener, sleep=lambda s: None))
conn.close()
check("process_job marks the job done", result["status"] == "done")
check("process_job links the 2 nearby features, filtering out the far one", result["features_linked"] == 2)

linked_rows = raw_all("SELECT * FROM user_osm_proximity WHERE user_id = ?", (user_id,))
check("exactly 2 proximity rows were stored (far feature excluded)", len(linked_rows) == 2)
categories = {r["category"] for r in linked_rows}
check("stored categories include poi and building", categories == {"poi", "building"})
check("no stored row references the far-away road", 333 not in {r["osm_id"] for r in linked_rows})

cached = raw_all("SELECT * FROM osm_feature_cache")
check("osm_feature_cache has 2 entries (the far feature was never cached either)", len(cached) == 2)

# -- 8. No raw coordinates anywhere in the public-facing result ---------------------------------------

nearby = opc.get_user_nearby(dbmod.get_db(), user_id)
check("get_user_nearby returns the 2 linked features", len(nearby) == 2)
for f in nearby:
    check(f"feature {f['osm_id']} result has no 'lat'/'lon'/'latitude'/'longitude' keys",
          not any(k in f for k in ("lat", "lon", "latitude", "longitude")))
check("every feature result carries OSM attribution", all(f["attribution"] == "© OpenStreetMap contributors" for f in nearby))
check("distance is reported in meters, rounded", all(isinstance(f["distance_meters"], float) for f in nearby))

# -- 9. Duplicate processing is idempotent (re-processing the same done job doesn't double rows) ------

done_job = raw("SELECT * FROM osm_proximity_jobs WHERE id = ?", (claimed[0]["id"],))
opener2 = fake_opener([good_body])
conn = dbmod.get_db()
opc.process_job(conn, dict(done_job), post_overpass=lambda q, purpose, sleep=None: osm_http_core.post_overpass(q, purpose, opener=opener2, sleep=lambda s: None))
conn.close()
linked_rows_after_rerun = raw_all("SELECT * FROM user_osm_proximity WHERE user_id = ?", (user_id,))
check("re-processing the same job does not create duplicate proximity rows", len(linked_rows_after_rerun) == 2)

# -- 10. Withdrawal: cancels pending jobs, marks associations withdrawn, excluded from get_user_nearby -

user_id2 = register_and_login()
client.post("/api/location/observation", json={
    "latitude": 28.7041, "longitude": 77.1025, "accuracy_meters": 10,
    "consent_internal_storage": True, "consent_centroid_aggregation": False, "consent_external_overpass_lookup": True,
})
conn = dbmod.get_db()
withdraw_result = opc.withdraw_overpass_consent(conn, user_id2)
conn.close()
check("withdrawal cancels the pending job", withdraw_result["jobs_cancelled"] == 1)
pending_after_withdraw = raw("SELECT COUNT(*) AS c FROM osm_proximity_jobs WHERE user_id = ? AND status = 'pending'", (user_id2,))["c"]
check("no pending job remains for the user after withdrawal", pending_after_withdraw == 0)

# Withdraw via the real route too, and confirm existing 'active' associations become unavailable.
# (user_id2 is the one currently logged in on `client` at this point in the test.)
conn = dbmod.get_db()
conn.execute(
    "INSERT INTO user_osm_proximity (user_id, observation_id, osm_type, osm_id, category, distance_meters, created_at) "
    "VALUES (?, 0, 'node', 999, 'poi', 10.0, '2026-11-02T00:00:00')", (user_id2,),
)
conn.commit()
conn.close()
withdraw_route = client.post("/api/location/observation/withdraw-overpass")
check("withdraw-overpass route responds 200", withdraw_route.status_code == 200)
nearby_after_route_withdraw = opc.get_user_nearby(dbmod.get_db(), user_id2)
check("get_user_nearby returns nothing once all associations are withdrawn", len(nearby_after_route_withdraw) == 0)

logout()

# -- 11. Q-Map route authorization: only the user themselves may read their own data ------------------

user_a = register_and_login()
unauth = client.get(f"/api/qmap/user-nearby/{user_a}")
check("a user can read their own Q-Map data", unauth.status_code == 200)
other_attempt = client.get(f"/api/qmap/user-nearby/{user_a + 10000}")
check("a user cannot read another user's Q-Map data (403)", other_attempt.status_code == 403)
logout()

no_session = client.get(f"/api/qmap/user-nearby/{user_a}")
check("an unauthenticated request is rejected", no_session.status_code in (302, 401, 403))

# -- 12. Overpass 429/backoff is honored by the shared HTTP layer (reused, not reimplemented) ---------

sleep_calls = []
opener3 = fake_opener([http_error(429, retry_after=45), good_body])
result3 = osm_http_core.post_overpass("fake query", purpose="test", opener=opener3, sleep=lambda s: sleep_calls.append(s))
check("post_overpass recovers from one 429 then succeeds", result3["elements"] is not None)
check("post_overpass respected the Retry-After header", sleep_calls == [45])

# -- 13. Worker restart/idempotence: a second run_worker_once with no pending jobs processes zero -----

conn = dbmod.get_db()
result_empty = opc.run_worker_once(conn, worker_id="idle-worker", sleep=lambda s: None)
conn.close()
check("run_worker_once with no pending jobs processes zero jobs", result_empty["jobs_processed"] == 0)

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
