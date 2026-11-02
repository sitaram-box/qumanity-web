"""Covers the Q-Map page itself (2026-11-02): the /qmap route's rendering, the North West Delhi
pilot dataset's static delivery, privacy/authorization boundaries around a signed-in member's own
GPS center, and that no new data API route was introduced -- the existing, already-tested
GET /api/qmap/user-nearby/<user_id> (see tests/test_osm_proximity.py) remains the only one.

This file does not exercise static/js/qmap.js's own runtime behavior (fetch/render/toggle/
cross-reference) -- that is only meaningfully testable in a real browser and was verified
separately. It tests everything the Flask route itself controls: what HTML/JS-global values are
server-rendered, for whom, and under what authorization/consent conditions.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, same conventions as every other test file in this project
(see tests/test_osm_proximity.py for the closest sibling).

Run with: python3 tests/test_qmap.py (not -I)
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402

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
        "name": f"QMap Tester {_n[0]}", "gender": "female", "dob": "1992-03-10", "tob": "09:00",
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


def insert_observation(user_id, lat, lon, status="accepted"):
    conn = dbmod.get_db()
    conn.execute(
        """INSERT INTO user_location_observations
           (user_id, latitude, longitude, accuracy_meters, captured_at, consent_internal_storage,
            consent_centroid_aggregation, consent_external_overpass_lookup, consent_version, status, created_at)
           VALUES (?, ?, ?, 10, '2026-11-02T00:00:00', 1, 0, 0, 'v1', ?, '2026-11-02T00:00:00')""",
        (user_id, lat, lon, status),
    )
    conn.commit()
    conn.close()


# -- 1. Route map: exactly one page route and the one pre-existing data route, nothing new ----------

qmap_rules = [r for r in appmod.app.url_map.iter_rules() if "qmap" in r.rule.lower()]
rule_strings = sorted(r.rule for r in qmap_rules)
check("exactly the page route and the existing user-nearby data route exist, no new data route",
      rule_strings == ["/api/qmap/user-nearby/<int:user_id>", "/qmap"])

# -- 2. Anonymous visitor: page loads, public pilot layers only, no personal data, no CacheControl --

anon_resp = client.get("/qmap")
check("anonymous visitor gets 200", anon_resp.status_code == 200)
anon_html = anon_resp.get_data(as_text=True)
check("map container present", 'id="qmap-map"' in anon_html)
check("layer-control-bearing script (qmap.js) is referenced", "js/qmap.js" in anon_html)
check("Leaflet 1.9.4 is loaded (the established version)", "leaflet@1.9.4" in anon_html)
check("no second Leaflet version is loaded", anon_html.count("unpkg.com/leaflet@") == 2)  # css + js, same version
check("ODbL attribution text is present and visible", "OpenStreetMap contributors" in anon_html)
check("attribution links to the real OSM copyright page", "https://www.openstreetmap.org/copyright" in anon_html)
check("ODbL license itself is named", "Open Database License" in anon_html or "ODbL" in anon_html)
check("anonymous visitor's QM_USER_ID is null, never a real id", "var QM_USER_ID = null;" in anon_html)
check("anonymous visitor's QM_GPS_CENTER is null, never 0,0", "var QM_GPS_CENTER = null;" in anon_html)
check("anonymous visitor is invited to sign in rather than shown a GPS layer", "Sign in" in anon_html)
check("the pilot GeoJSON's static URL is embedded for client-side loading",
      "data/pilot/north_west_delhi_osm.geojson" in anon_html)
check("no raw coordinate pair appears anywhere in the anonymous page", "28.70" not in anon_html and "77.10" not in anon_html)
check("anonymous response is not marked private/no-store (nothing personal to protect)",
      anon_resp.headers.get("Cache-Control") != "private, no-store")

# -- 3. The pilot GeoJSON itself is actually served as a static file (not just referenced) ----------

geojson_resp = client.get("/static/data/pilot/north_west_delhi_osm.geojson")
check("the pilot GeoJSON file is reachable at the embedded static URL", geojson_resp.status_code == 200)
check("the pilot GeoJSON is non-trivially sized (the real ~21MB pilot dump, not a stub)",
      int(geojson_resp.headers.get("Content-Length", 0)) > 1_000_000)

# -- 4. Home page carries a visible Q-Map nav link, without touching the Dashboard/Stats Modal ------

home_html = client.get("/").get_data(as_text=True)
check("home page links to the Q-Map page", 'href="/qmap"' in home_html)

# -- 5. Authenticated member, no GPS observation at all: no center override, no fabricated 0,0 ------

user_no_gps = register_and_login()
resp_no_gps = client.get("/qmap")
html_no_gps = resp_no_gps.get_data(as_text=True)
check("authenticated member without GPS still gets 200", resp_no_gps.status_code == 200)
check("their own QM_USER_ID is embedded", f"var QM_USER_ID = {user_no_gps};" in html_no_gps)
check("no GPS observation means QM_GPS_CENTER stays null (never 0,0)", "var QM_GPS_CENTER = null;" in html_no_gps)
check("a signed-in response carries Cache-Control: private, no-store",
      resp_no_gps.headers.get("Cache-Control") == "private, no-store")
logout()

# -- 6. Authenticated member with a pending (not yet accepted) observation: still no center ---------

user_pending = register_and_login()
insert_observation(user_pending, 28.70, 77.10, status="pending")
resp_pending = client.get("/qmap")
html_pending = resp_pending.get_data(as_text=True)
check("a 'pending' observation never supplies a GPS center", "var QM_GPS_CENTER = null;" in html_pending)
logout()

# -- 7. Authenticated member with an accepted observation: center is exactly that coordinate --------

user_with_gps = register_and_login()
insert_observation(user_with_gps, 28.7041, 77.1025, status="accepted")
resp_with_gps = client.get("/qmap")
html_with_gps = resp_with_gps.get_data(as_text=True)
check("an 'accepted' observation supplies a real GPS center",
      '"lat": 28.7041' in html_with_gps and '"lon": 77.1025' in html_with_gps)
check("the authenticated member's own id is embedded, matching their own session",
      f"var QM_USER_ID = {user_with_gps};" in html_with_gps)
check("the embedded QM_USER_ID is never a different user's id",
      f"var QM_USER_ID = {user_with_gps + 999};" not in html_with_gps)

# -- 8. Only the MOST RECENT accepted observation is used, never an older one -----------------------

insert_observation(user_with_gps, 29.0000, 78.0000, status="accepted")  # newer row, same user
resp_latest = client.get("/qmap")
html_latest = resp_latest.get_data(as_text=True)
check("the latest accepted observation wins over an earlier accepted one",
      '"lat": 29.0' in html_latest)
check("the stale earlier coordinate is no longer the one shown", '"lat": 28.7041' not in html_latest)
logout()

# -- 9. Cross-user isolation: one member's GPS is never served from another member's page render ----

other_user = register_and_login()
resp_other = client.get("/qmap")
html_other = resp_other.get_data(as_text=True)
check("a different signed-in member never sees the first member's GPS center", "29.0" not in html_other)
check("a different signed-in member gets their own (absent) center instead", "var QM_GPS_CENTER = null;" in html_other)
logout()

# -- 10. The existing user-nearby endpoint's own authorization is untouched and still enforced ------

user_final = register_and_login()
own_nearby = client.get(f"/api/qmap/user-nearby/{user_final}")
check("a member can still read their own Q-Map proximity data", own_nearby.status_code == 200)
other_nearby = client.get(f"/api/qmap/user-nearby/{user_final + 12345}")
check("a member still cannot read another user's Q-Map proximity data (403)", other_nearby.status_code == 403)
logout()

no_session_nearby = client.get(f"/api/qmap/user-nearby/{user_final}")
check("an unauthenticated request to user-nearby is still rejected", no_session_nearby.status_code in (302, 401, 403))

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
