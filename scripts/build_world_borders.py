#!/usr/bin/env python3
"""Build static/data/world_borders.geojson from Natural Earth's 110m
countries dataset, tagged with OUR OWN continent/country ids (from
global_countries.json — the source of truth for the picker/registration
flow) rather than Natural Earth's own continent classification, so the
map and the picker never disagree about which continent a country is in.

Run once (or whenever the source files change):
    python3 scripts/build_world_borders.py
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_NE = BASE_DIR / "scripts" / "_ne_110m_admin_0_countries.geojson"
SRC_QM_COUNTRIES = BASE_DIR / "static" / "data" / "global_countries.json"
OUT_PATH = BASE_DIR / "static" / "data" / "world_borders.geojson"

COORD_PRECISION = 3  # ~111m at the equator — plenty for 110m-resolution source data


def round_coords(coords):
    if isinstance(coords[0], (int, float)):
        return [round(c, COORD_PRECISION) for c in coords]
    return [round_coords(c) for c in coords]


def build_qm_lookup():
    """iso3 -> (qm_country_id, qm_continent_code, qm_country_name)"""
    qm = json.loads(SRC_QM_COUNTRIES.read_text(encoding="utf-8"))
    lookup = {}
    for continent in qm["continents"]:
        for country in continent["countries"]:
            lookup[country["code"]] = (country["id"], continent["code"], country["name"])
    return lookup


def resolve_iso3(props):
    for key in ("ISO_A3", "ADM0_A3", "ISO_A3_EH", "BRK_A3"):
        val = props.get(key)
        if val and val != "-99":
            return val
    return None


def main():
    ne = json.loads(SRC_NE.read_text(encoding="utf-8"))
    lookup = build_qm_lookup()

    out_features = []
    matched, unmatched = 0, []
    for feature in ne["features"]:
        props = feature["properties"]
        iso3 = resolve_iso3(props)
        qm = lookup.get(iso3)
        if qm:
            matched += 1
            qm_country_id, qm_continent_code, qm_name = qm
        else:
            unmatched.append(props.get("NAME"))
            qm_country_id, qm_continent_code, qm_name = None, None, props.get("NAME")

        out_features.append({
            "type": "Feature",
            "properties": {
                "name": qm_name,
                "iso3": iso3,
                "qm_country_id": qm_country_id,
                "qm_continent_code": qm_continent_code,
            },
            "geometry": {
                "type": feature["geometry"]["type"],
                "coordinates": round_coords(feature["geometry"]["coordinates"]),
            },
        })

    out = {"type": "FeatureCollection", "features": out_features}
    OUT_PATH.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")

    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")
    print(f"Matched {matched}/{len(ne['features'])} Natural Earth features to Qumanity country ids")
    print(f"Unmatched ({len(unmatched)}): {unmatched}")


if __name__ == "__main__":
    main()
