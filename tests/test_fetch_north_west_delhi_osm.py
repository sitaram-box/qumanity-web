#!/usr/bin/env python3
"""Tests for scripts/fetch_north_west_delhi_osm.py -- response parsing, dedup, category
classification, node/way/relation geometry conversion, malformed-response handling, 429/server-
error retry behavior, timeout handling, no-overwrite-on-failure, and valid-FeatureCollection
output. None of these depend on live Overpass availability -- every HTTP call is mocked via the
script's injectable `opener`/`sleep` parameters.

Standalone script (project convention, not pytest): run directly.
    python3 tests/test_fetch_north_west_delhi_osm.py
"""
import io
import json
import sys
import tempfile
import urllib.error
from email.message import Message
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_north_west_delhi_osm as osm  # noqa: E402

FAILS = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}")
    if not cond:
        FAILS.append(label)


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body


def fake_opener(responses):
    """Returns an `opener(req, timeout)` that yields `responses` in order. Each entry is either
    bytes (a successful body) or an Exception instance to raise."""
    it = iter(responses)

    def _opener(req, timeout):
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)

    return _opener


def http_error(code, retry_after=None, body=b"server error"):
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://overpass-api.de/api/interpreter", code, "err", hdrs, io.BytesIO(body))


def recording_sleep():
    calls = []

    def _sleep(seconds):
        calls.append(seconds)

    return _sleep, calls


# -- classify_categories -----------------------------------------------------------------------

check("highway tag classifies as road", osm.classify_categories({"highway": "residential"}) == ["road"])
check("building tag classifies as building", osm.classify_categories({"building": "yes"}) == ["building"])
check("amenity=hospital classifies as hospital", osm.classify_categories({"amenity": "hospital"}) == ["hospital"])
check("a feature may belong to multiple categories",
      osm.classify_categories({"building": "yes", "amenity": "hospital"}) == ["building", "hospital"])
check("unrelated tags classify as nothing", osm.classify_categories({"shop": "bakery"}) == [])

# -- element_to_feature: node -------------------------------------------------------------------

node = {"type": "node", "id": 1, "lat": 28.7, "lon": 77.1, "tags": {"amenity": "hospital", "name": "Test"}}
feat, limitation = osm.element_to_feature(node)
check("node converts to Point", feat["geometry"] == {"type": "Point", "coordinates": [77.1, 28.7]})
check("node has no limitation", limitation is None)
check("node categories include hospital", "hospital" in feat["properties"]["categories"])

# -- element_to_feature: way (building, closed) -----------------------------------------------

closed_way = {
    "type": "way", "id": 2, "tags": {"building": "yes"},
    "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}, {"lat": 1, "lon": 1}, {"lat": 0, "lon": 0}],
}
feat, limitation = osm.element_to_feature(closed_way)
check("closed building way converts to Polygon", feat["geometry"]["type"] == "Polygon")
check("closed building way ring is closed", feat["geometry"]["coordinates"][0][0] == feat["geometry"]["coordinates"][0][-1])
check("closed building way has no limitation", limitation is None)

# -- element_to_feature: way (building, open) ---------------------------------------------------

open_way = {
    "type": "way", "id": 3, "tags": {"building": "yes"},
    "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}, {"lat": 1, "lon": 1}],
}
feat, limitation = osm.element_to_feature(open_way)
check("open building way has null geometry", feat["geometry"] is None)
check("open building way reports a limitation, not silently dropped", limitation is not None)
check("open building way status flagged", feat["properties"]["geometry_conversion_status"] == "open_building_way_unsupported")

# -- element_to_feature: way (highway) -----------------------------------------------------------

road_way = {
    "type": "way", "id": 4, "tags": {"highway": "residential"},
    "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}],
}
feat, limitation = osm.element_to_feature(road_way)
check("road way converts to LineString", feat["geometry"]["type"] == "LineString")
check("road way has no limitation", limitation is None)

# -- element_to_feature: way with missing geometry ----------------------------------------------

no_geom_way = {"type": "way", "id": 5, "tags": {"highway": "track"}, "geometry": []}
feat, limitation = osm.element_to_feature(no_geom_way)
check("way with missing geometry has null geometry", feat["geometry"] is None)
check("way with missing geometry reports a limitation", limitation is not None)

# -- element_to_feature: relation (valid multipolygon) -------------------------------------------

valid_relation = {
    "type": "relation", "id": 6, "tags": {"amenity": "hospital", "type": "multipolygon"},
    "members": [
        {"type": "way", "role": "outer",
         "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}, {"lat": 1, "lon": 1}, {"lat": 0, "lon": 0}]},
    ],
}
feat, limitation = osm.element_to_feature(valid_relation)
check("valid multipolygon relation converts to Polygon", feat["geometry"]["type"] == "Polygon")
check("valid multipolygon relation has no limitation", limitation is None)

# -- element_to_feature: relation (unsupported structure) -----------------------------------------

bad_relation = {
    "type": "relation", "id": 7, "tags": {"amenity": "hospital", "type": "multipolygon"},
    "members": [
        {"type": "way", "role": "outer", "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}]},  # open, unusable
    ],
}
feat, limitation = osm.element_to_feature(bad_relation)
check("unsupported relation has null geometry (never silently dropped)", feat["geometry"] is None)
check("unsupported relation reports a limitation", limitation is not None)
check("unsupported relation status flagged", feat["properties"]["geometry_conversion_status"] == "unsupported_relation_structure")

# -- build_geojson: dedup + counts ----------------------------------------------------------------

study_area = {"method": "official_boundary_relation", "provenance": {"relation_id": 21181214}}
elements = [
    {"type": "way", "id": 100, "tags": {"highway": "residential"},
     "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}]},
    {"type": "way", "id": 100, "tags": {"highway": "residential"},  # exact duplicate (same type+id)
     "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}]},
    {"type": "way", "id": 101, "tags": {"building": "yes", "amenity": "hospital"},
     "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}, {"lat": 1, "lon": 1}, {"lat": 0, "lon": 0}]},
    {"type": "node", "id": 102, "lat": 1.0, "lon": 1.0, "tags": {"amenity": "hospital"}},
]
fc, stats = osm.build_geojson(elements, study_area, "2026-11-01T00:00:00Z")
check("build_geojson removes the exact duplicate", stats["duplicates_removed"] == 1)
check("build_geojson total unique elements is 3", stats["total_unique_elements"] == 3)
check("build_geojson roads_found counts only the road", stats["roads_found"] == 1)
check("build_geojson buildings_found counts the building+hospital way once", stats["buildings_found"] == 1)
check("build_geojson hospitals_found counts both hospital-tagged elements", stats["hospitals_found"] == 2)
check("build_geojson output is a FeatureCollection", fc["type"] == "FeatureCollection")
check("build_geojson includes ODbL attribution", "ODbL" in fc["metadata"]["license"])
check("build_geojson carries the OSM data timestamp", fc["metadata"]["osm_data_timestamp"] == "2026-11-01T00:00:00Z")

# -- write_atomic: valid write + no-overwrite-on-failure -----------------------------------------

with tempfile.TemporaryDirectory() as tmpdir:
    target = Path(tmpdir) / "pilot" / "out.geojson"
    good_fc = {"type": "FeatureCollection", "metadata": {}, "features": [{"type": "Feature", "geometry": None, "properties": {}}]}
    osm.write_atomic(good_fc, target)
    check("write_atomic creates the file", target.exists())
    reparsed = json.loads(target.read_text())
    check("write_atomic output round-trips as valid JSON", reparsed["type"] == "FeatureCollection")

    original_bytes = target.read_bytes()
    threw = False
    try:
        osm.write_atomic({"type": "NotAFeatureCollection"}, target)
    except ValueError:
        threw = True
    check("write_atomic rejects an invalid result", threw)
    check("write_atomic never overwrites existing good output with an invalid one",
          target.read_bytes() == original_bytes)

# -- post_overpass: malformed response then success ----------------------------------------------

sleep_fn, sleep_calls = recording_sleep()
good_body = json.dumps({"elements": [], "osm3s": {"timestamp_osm_base": "2026-11-01T00:00:00Z"}}).encode()
opener = fake_opener([b"not json at all", good_body])
result = osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
check("post_overpass recovers from one malformed response then succeeds", result["elements"] == [])
check("post_overpass backed off 30s on the first malformed-response retry", sleep_calls == [30])

# -- post_overpass: 429 with Retry-After, then success --------------------------------------------

sleep_fn, sleep_calls = recording_sleep()
opener = fake_opener([http_error(429, retry_after=45), good_body])
result = osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
check("post_overpass recovers from one 429 then succeeds", result["elements"] == [])
check("post_overpass respects a Retry-After longer than the scheduled backoff", sleep_calls == [45])

# -- post_overpass: 503 without Retry-After uses the scheduled backoff ----------------------------

sleep_fn, sleep_calls = recording_sleep()
opener = fake_opener([http_error(503), good_body])
result = osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
check("post_overpass uses the scheduled 30s backoff on a 503 with no Retry-After", sleep_calls == [30])

# -- post_overpass: timeout/network error retried then recovers -----------------------------------

sleep_fn, sleep_calls = recording_sleep()
opener = fake_opener([TimeoutError("read timed out"), good_body])
result = osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
check("post_overpass recovers from one timeout then succeeds", result["elements"] == [])

# -- post_overpass: exhausts retries and raises honestly --------------------------------------------

sleep_fn, sleep_calls = recording_sleep()
opener = fake_opener([http_error(502), http_error(502), http_error(502), http_error(502)])
threw = False
try:
    osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
except osm.OverpassError:
    threw = True
check("post_overpass raises OverpassError after exhausting all retries", threw)
check("post_overpass made exactly 3 bounded backoff waits before giving up", sleep_calls == [30, 60, 120])

# -- post_overpass: a non-retryable 4xx is not retried at all --------------------------------------

sleep_fn, sleep_calls = recording_sleep()
opener = fake_opener([http_error(400)])
threw = False
try:
    osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
except osm.OverpassError:
    threw = True
check("post_overpass does not retry a non-retryable HTTP 400", threw)
check("post_overpass never sleeps for a non-retryable error", sleep_calls == [])

# -- post_overpass: a 200 OK with no 'elements' key is reported, not silently accepted ---------------

sleep_fn, sleep_calls = recording_sleep()
bad_shape = json.dumps({"remark": "runtime error: upstream timeout"}).encode()
opener = fake_opener([bad_shape])
threw = False
try:
    osm.post_overpass("fake query", opener=opener, sleep=sleep_fn)
except osm.OverpassError:
    threw = True
check("post_overpass reports a 200 OK response missing 'elements' instead of crashing or guessing", threw)

# -- resolve_study_area: a mismatched relation is reported, never silently substituted ---------------

sleep_fn, sleep_calls = recording_sleep()
wrong_tags_body = json.dumps({
    "osm3s": {"timestamp_osm_base": "2026-11-01T00:00:00Z"},
    "elements": [{"type": "relation", "id": osm.BOUNDARY_RELATION_ID,
                  "tags": {"name": "Somewhere Else", "boundary": "administrative"}, "bounds": {}}],
}).encode()
opener = fake_opener([wrong_tags_body])
threw = False
try:
    osm.resolve_study_area(opener=opener, sleep=sleep_fn)
except osm.OverpassError:
    threw = True
check("resolve_study_area refuses a relation whose tags no longer match North West Delhi", threw)

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
