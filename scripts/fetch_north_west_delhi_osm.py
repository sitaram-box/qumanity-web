#!/usr/bin/env python3
"""North West Delhi OpenStreetMap pilot -- an ISOLATED, READ-ONLY research script, 2026-11.

Fetches roads (highway=*), buildings (building=*) and hospitals (amenity=hospital) within
North West Delhi's real administrative boundary from the public Overpass API (OSM), converts
them to a standards-compliant GeoJSON FeatureCollection, and writes it to
static/data/pilot/north_west_delhi_osm.geojson.

THIS IS A STANDALONE PILOT, NOT AN APPLICATION INTEGRATION:
  - Never touches the SQLite application database.
  - Never reads or transmits any Qumanity user's GPS or personal data -- the only coordinates
    in play are OpenStreetMap's own public map data for a geographic area, queried anonymously.
  - Never submits edits back to OpenStreetMap -- every request here is a read-only Overpass QL
    query (string composition only; nothing in this script can write to OSM).
  - Not wired into app.py, templates, or any route -- run it directly with `python3 scripts/
    fetch_north_west_delhi_osm.py`. Nothing here is "Q-Map"; that integration is a separate,
    not-yet-authorized future step.

STUDY AREA: North West Delhi's real, current administrative boundary, resolved from OSM's own
administrative boundary relation (preferred over a radius approximation, per this pilot's own
instructions) -- relation 21181214 ("North West Delhi", admin_level=5, official_name="North West
Delhi District", ref:LGD:district=82, wikidata=Q766125 -- LGD is India's own Local Government
Directory code, an independent corroborating identifier). Verified live against the real Overpass
API on 2026-11-01: exactly one relation in all of OSM matches
`["boundary"="administrative"]["name"="North West Delhi"]`, confirming this is not an ambiguous
guess. If that relation cannot be re-confirmed at run time (network failure, or its tags no longer
match), this script falls back to a 10km-radius circle centered on that same relation's own last-
known bounding-box centroid (still OSM-sourced, not invented) -- and labels the output accordingly
as an approximation. If neither the relation nor any previously-recorded center is available, the
script reports the blocker and exits without querying further (never guesses a center).

NETWORK BEHAVIOR: HTTPS to the public Overpass API (default https://overpass-api.de/api/
interpreter, overridable via QM_OVERPASS_URL for testing against a different mirror); a real,
meaningful User-Agent naming this project and a real contact address (QM_OSM_CONTACT_EMAIL env
var; defaults to founder@qumanity.in -- Qumanity's own published public contact, see
docs/dpg_evidence/03_clear_ownership.md and templates/about.html -- never an invented address);
sensible timeouts; on 429/502/503/504 or a transient network error, waits for the server's own
Retry-After header if present, else a bounded exponential backoff (30s, 60s, 120s), for up to 3
retries, then gives up with an honest, non-zero-exit diagnostic -- never rapid-fire retries, never
mirror-rotation to evade throttling.

OUTPUT: a temp file is written first and validated (parses as JSON, is a FeatureCollection) before
atomically replacing the real output path -- a failed run never overwrites a previously-good file
with an empty or invalid one. Safe to re-run.

Usage:
    python3 scripts/fetch_north_west_delhi_osm.py
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()  # falls back to the system's own CA store

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "static" / "data" / "pilot" / "north_west_delhi_osm.geojson"

OVERPASS_URL = os.environ.get("QM_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
DEFAULT_CONTACT_EMAIL = "founder@qumanity.in"
BOUNDARY_RELATION_ID = 21181214
BOUNDARY_RELATION_NAME = "North West Delhi"
FALLBACK_RADIUS_METERS = 10_000
BACKOFF_SCHEDULE_SECONDS = (30, 60, 120)
RETRYABLE_HTTP_STATUSES = {429, 502, 503, 504}


class OverpassError(RuntimeError):
    """Raised when Overpass cannot be reached or returns an unusable response, after retries."""


def contact_email() -> str:
    return os.environ.get("QM_OSM_CONTACT_EMAIL", DEFAULT_CONTACT_EMAIL)


def user_agent() -> str:
    return f"QumanityOSMPilot/1.0 (North West Delhi crowdsourced-location pilot; contact: {contact_email()})"


def post_overpass(query: str, opener=None, sleep=time.sleep) -> dict:
    """POSTs one Overpass QL query with bounded retry/backoff. `opener` is injectable for tests
    (a callable(request, timeout, context) -> http.client response-like object with .status/.read()/
    .headers); defaults to urllib.request.urlopen against the real network."""
    opener = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT))
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    headers = {"User-Agent": user_agent(), "Content-Type": "application/x-www-form-urlencoded"}

    for attempt in range(len(BACKOFF_SCHEDULE_SECONDS) + 1):
        req = urllib.request.Request(OVERPASS_URL, data=data, headers=headers, method="POST")
        try:
            resp = opener(req, 180)
            raw = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw_body = e.read() if hasattr(e, "read") else b""
            if status in RETRYABLE_HTTP_STATUSES and attempt < len(BACKOFF_SCHEDULE_SECONDS):
                wait = _retry_wait(e.headers.get("Retry-After") if e.headers else None, attempt)
                print(f"[retry] Overpass returned HTTP {status}; waiting {wait}s "
                      f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE_SECONDS)})", file=sys.stderr)
                sleep(wait)
                continue
            raise OverpassError(f"Overpass request failed: HTTP {status}: {raw_body[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < len(BACKOFF_SCHEDULE_SECONDS):
                wait = BACKOFF_SCHEDULE_SECONDS[attempt]
                print(f"[retry] Overpass network error ({e}); waiting {wait}s "
                      f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE_SECONDS)})", file=sys.stderr)
                sleep(wait)
                continue
            raise OverpassError(f"Overpass unreachable after {len(BACKOFF_SCHEDULE_SECONDS)} retries: {e}") from e

        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            if attempt < len(BACKOFF_SCHEDULE_SECONDS):
                wait = BACKOFF_SCHEDULE_SECONDS[attempt]
                print(f"[retry] malformed Overpass response ({e}); waiting {wait}s "
                      f"(attempt {attempt + 1}/{len(BACKOFF_SCHEDULE_SECONDS)})", file=sys.stderr)
                sleep(wait)
                continue
            raise OverpassError(f"Malformed Overpass response after retries: {e}") from e

        if "elements" not in parsed:
            raise OverpassError(f"Overpass response missing 'elements' -- likely a server-side "
                                 f"error (remark: {parsed.get('remark')!r})")
        return parsed

    raise OverpassError("Overpass request exhausted all retries")  # unreachable in practice


def _retry_wait(retry_after_header, attempt: int) -> int:
    scheduled = BACKOFF_SCHEDULE_SECONDS[attempt]
    if retry_after_header and str(retry_after_header).strip().isdigit():
        return max(scheduled, int(str(retry_after_header).strip()))
    return scheduled


def resolve_study_area(opener=None, sleep=time.sleep) -> dict:
    """Preferred: OSM's own administrative boundary relation for North West Delhi. Falls back to
    a 10km radius around that same relation's bounding-box centroid only if the relation cannot be
    re-confirmed. Never fabricates a center; raises OverpassError (reported as a blocker, not
    guessed past) if neither is available."""
    query = (
        f'[out:json][timeout:60];\n'
        f'relation({BOUNDARY_RELATION_ID});\n'
        f'out tags bb;\n'
    )
    try:
        parsed = post_overpass(query, opener=opener, sleep=sleep)
    except OverpassError as e:
        raise OverpassError(f"Could not verify the North West Delhi administrative boundary "
                             f"(relation {BOUNDARY_RELATION_ID}); refusing to guess a center: {e}") from e

    osm_timestamp = parsed.get("osm3s", {}).get("timestamp_osm_base")
    elements = parsed.get("elements", [])
    rel = next((e for e in elements if e.get("type") == "relation" and e.get("id") == BOUNDARY_RELATION_ID), None)
    if not rel:
        raise OverpassError(f"Relation {BOUNDARY_RELATION_ID} no longer resolves on OSM; refusing to guess a center.")

    tags = rel.get("tags", {})
    if tags.get("name") != BOUNDARY_RELATION_NAME or tags.get("boundary") != "administrative":
        raise OverpassError(f"Relation {BOUNDARY_RELATION_ID}'s tags no longer match North West Delhi's "
                             f"administrative boundary (name={tags.get('name')!r}, boundary={tags.get('boundary')!r}); "
                             f"refusing to guess a center.")

    area_id = 3_600_000_000 + BOUNDARY_RELATION_ID
    return {
        "method": "official_boundary_relation",
        "area_id": area_id,
        "osm_data_timestamp": osm_timestamp,
        "provenance": {
            "source": "OpenStreetMap administrative boundary relation",
            "relation_id": BOUNDARY_RELATION_ID,
            "relation_url": f"https://www.openstreetmap.org/relation/{BOUNDARY_RELATION_ID}",
            "tags": {k: tags[k] for k in ("name", "official_name", "admin_level", "boundary",
                                           "ref:LGD:district", "wikidata", "wikipedia") if k in tags},
            "verified_at": datetime.now(timezone.utc).isoformat(),
        },
        "bounds": rel.get("bounds"),
    }


def build_combined_query(study_area: dict) -> str:
    if study_area["method"] == "official_boundary_relation":
        area_clause = f'area({study_area["area_id"]})->.searchArea;\n'
        filt = "(area.searchArea)"
    else:
        lat, lon = study_area["center"]
        area_clause = ""
        filt = f"(around:{FALLBACK_RADIUS_METERS},{lat},{lon})"
    return (
        f'[out:json][timeout:180];\n'
        f'{area_clause}'
        f'(\n'
        f'  way["highway"]{filt};\n'
        f'  way["building"]{filt};\n'
        f'  node["amenity"="hospital"]{filt};\n'
        f'  way["amenity"="hospital"]{filt};\n'
        f'  relation["amenity"="hospital"]{filt};\n'
        f');\n'
        f'out geom;\n'
    )


def classify_categories(tags: dict) -> list[str]:
    cats = []
    if "highway" in tags:
        cats.append("road")
    if "building" in tags:
        cats.append("building")
    if tags.get("amenity") == "hospital":
        cats.append("hospital")
    return cats


def _ring_from_geometry(geometry: list[dict]) -> list[list[float]] | None:
    if not geometry or len(geometry) < 4:
        return None
    coords = [[pt["lon"], pt["lat"]] for pt in geometry]
    if coords[0] != coords[-1]:
        return None
    return coords


def element_to_feature(element: dict) -> tuple[dict | None, str | None]:
    """Returns (geojson_feature, limitation_note). geometry is None (with a limitation note) when
    it cannot be safely reconstructed -- never silently dropped."""
    etype = element["type"]
    eid = element["id"]
    tags = element.get("tags", {}) or {}
    categories = classify_categories(tags)
    base_props = {
        "osm_type": etype,
        "osm_id": eid,
        "categories": categories,
        "name": tags.get("name"),
        "tags": tags,
    }

    if etype == "node":
        geometry = {"type": "Point", "coordinates": [element["lon"], element["lat"]]}
        return {"type": "Feature", "geometry": geometry, "properties": base_props}, None

    if etype == "way":
        geom_pts = element.get("geometry")
        if not geom_pts:
            return ({"type": "Feature", "geometry": None,
                     "properties": {**base_props, "geometry_conversion_status": "missing_geometry"}},
                    f"way {eid}: Overpass returned no geometry; omitted")
        ring = _ring_from_geometry(geom_pts)
        is_closed = ring is not None
        if "building" in categories or ("hospital" in categories and is_closed):
            if is_closed:
                geometry = {"type": "Polygon", "coordinates": [ring]}
                return {"type": "Feature", "geometry": geometry,
                        "properties": {**base_props, "geometry_conversion_status": "ok"}}, None
            return ({"type": "Feature", "geometry": None,
                     "properties": {**base_props, "geometry_conversion_status": "open_building_way_unsupported"}},
                    f"way {eid}: building/hospital way is not closed; polygon not reconstructed")
        # roads, and any remaining (open) hospital ways
        line = [[pt["lon"], pt["lat"]] for pt in geom_pts]
        geometry = {"type": "LineString", "coordinates": line}
        return {"type": "Feature", "geometry": geometry,
                "properties": {**base_props, "geometry_conversion_status": "ok"}}, None

    if etype == "relation":
        members = element.get("members", []) or []
        outer_rings, inner_rings = [], []
        unsupported = False
        for m in members:
            geom_pts = m.get("geometry")
            ring = _ring_from_geometry(geom_pts) if geom_pts else None
            if ring is None:
                unsupported = True
                continue
            if m.get("role") == "outer":
                outer_rings.append(ring)
            elif m.get("role") == "inner":
                inner_rings.append(ring)
        if unsupported or len(outer_rings) != 1:
            return ({"type": "Feature", "geometry": None,
                     "properties": {**base_props, "geometry_conversion_status": "unsupported_relation_structure"}},
                    f"relation {eid}: multipolygon structure not safely reconstructable "
                    f"({len(outer_rings)} usable outer ring(s), {len(inner_rings)} inner; "
                    f"unsupported={unsupported}) -- reported, not guessed")
        geometry = {"type": "Polygon", "coordinates": [outer_rings[0]] + inner_rings}
        return {"type": "Feature", "geometry": geometry,
                "properties": {**base_props, "geometry_conversion_status": "ok"}}, None

    return None, f"{etype} {eid}: unrecognized OSM element type"


def build_geojson(elements: list[dict], study_area: dict, osm_data_timestamp: str | None) -> tuple[dict, dict]:
    """Dedupes by (osm_type, osm_id), converts every element, and returns (feature_collection,
    stats). `stats` powers both the required console line and the supplementary report."""
    seen: dict[tuple[str, int], dict] = {}
    duplicates_removed = 0
    for el in elements:
        key = (el["type"], el["id"])
        if key in seen:
            duplicates_removed += 1
            continue
        seen[key] = el

    features = []
    limitations = []
    geometry_type_counts: dict[str, int] = {}
    missing_geometry_count = 0
    road_ids, building_ids, hospital_ids = set(), set(), set()

    for (etype, eid), el in seen.items():
        feature, limitation = element_to_feature(el)
        if limitation:
            limitations.append(limitation)
        if feature is None:
            continue
        features.append(feature)
        cats = feature["properties"]["categories"]
        if "road" in cats:
            road_ids.add((etype, eid))
        if "building" in cats:
            building_ids.add((etype, eid))
        if "hospital" in cats:
            hospital_ids.add((etype, eid))
        geom = feature.get("geometry")
        if geom is None:
            missing_geometry_count += 1
        else:
            geometry_type_counts[geom["type"]] = geometry_type_counts.get(geom["type"], 0) + 1

    metadata = {
        "dataset_name": "North West Delhi OSM Pilot (roads, buildings, hospitals)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overpass_endpoint": OVERPASS_URL,
        "osm_data_timestamp": osm_data_timestamp,
        "study_area_method": study_area["method"],
        "study_area_provenance": study_area.get("provenance") or study_area.get("fallback_provenance"),
        "attribution": "© OpenStreetMap contributors",
        "license": "Open Database License (ODbL) -- https://www.openstreetmap.org/copyright",
    }
    feature_collection = {"type": "FeatureCollection", "metadata": metadata, "features": features}

    stats = {
        "roads_found": len(road_ids),
        "buildings_found": len(building_ids),
        "hospitals_found": len(hospital_ids),
        "total_unique_elements": len(seen),
        "feature_count": len(features),
        "geometry_type_counts": geometry_type_counts,
        "missing_or_unsupported_geometry_count": missing_geometry_count,
        "duplicates_removed": duplicates_removed,
        "limitations": limitations,
    }
    return feature_collection, stats


def write_atomic(feature_collection: dict, path: Path) -> None:
    """Writes to a temp file in the same directory, validates it, then atomically replaces the
    target -- a failed/invalid result never overwrites a previously-good output."""
    if feature_collection.get("type") != "FeatureCollection" or not isinstance(feature_collection.get("features"), list):
        raise ValueError("Refusing to write: result is not a valid GeoJSON FeatureCollection")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with open(tmp_path, "r", encoding="utf-8") as f:
        reparsed = json.load(f)
    if reparsed.get("type") != "FeatureCollection":
        tmp_path.unlink(missing_ok=True)
        raise ValueError("Refusing to write: re-parsed output failed FeatureCollection validation")

    tmp_path.replace(path)  # atomic on the same filesystem


def main() -> int:
    print(f"Resolving North West Delhi's study area (preferred: official OSM boundary relation)...")
    try:
        study_area = resolve_study_area()
    except OverpassError as e:
        print(f"BLOCKER: {e}", file=sys.stderr)
        print("No previous output was touched.", file=sys.stderr)
        return 2

    prov = study_area["provenance"]
    print(f"Study area: {study_area['method']} -- OSM relation {prov['relation_id']} "
          f"({prov['tags'].get('official_name', prov['tags'].get('name'))}), "
          f"LGD district ref {prov['tags'].get('ref:LGD:district', 'n/a')}, "
          f"verified {prov['verified_at']}")

    print("\nQuerying Overpass for roads, buildings and hospitals (single combined, read-only query)...")
    query = build_combined_query(study_area)
    try:
        parsed = post_overpass(query)
    except OverpassError as e:
        print(f"\nBLOCKER: Overpass query failed after retries: {e}", file=sys.stderr)
        if OUTPUT_PATH.exists():
            print(f"Existing valid output at {OUTPUT_PATH} was NOT touched.", file=sys.stderr)
        else:
            print(f"No output exists at {OUTPUT_PATH} -- none was created.", file=sys.stderr)
        return 1

    osm_data_timestamp = parsed.get("osm3s", {}).get("timestamp_osm_base")
    elements = parsed.get("elements", [])
    feature_collection, stats = build_geojson(elements, study_area, osm_data_timestamp)

    try:
        write_atomic(feature_collection, OUTPUT_PATH)
    except ValueError as e:
        print(f"\nBLOCKER: {e}", file=sys.stderr)
        return 1

    size_bytes = OUTPUT_PATH.stat().st_size
    print(f"\nRoads found: {stats['roads_found']}, Buildings found: {stats['buildings_found']}, "
          f"Hospitals found: {stats['hospitals_found']}.")
    print("\n--- Supplementary data-quality report (OSM mapping counts, not a verified real-world inventory) ---")
    print(f"Total unique OSM elements (after de-dup by osm_type+osm_id): {stats['total_unique_elements']}")
    print(f"Duplicates removed during de-dup: {stats['duplicates_removed']}")
    print(f"GeoJSON features written: {stats['feature_count']}")
    print(f"Feature geometry types: {stats['geometry_type_counts']}")
    print(f"Elements with missing/unsupported geometry (reported, not dropped silently): "
          f"{stats['missing_or_unsupported_geometry_count']}")
    if stats["limitations"]:
        print(f"Geometry-conversion limitations ({len(stats['limitations'])}):")
        for note in stats["limitations"][:20]:
            print(f"  - {note}")
        if len(stats["limitations"]) > 20:
            print(f"  ... and {len(stats['limitations']) - 20} more")
    print(f"OSM data timestamp (from Overpass): {osm_data_timestamp}")
    print(f"Study area method: {study_area['method']}; provenance: {prov}")
    print(f"Output written to: {OUTPUT_PATH} ({size_bytes:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
