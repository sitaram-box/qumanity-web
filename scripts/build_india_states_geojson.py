#!/usr/bin/env python3
"""Build static/data/india_states.geojson: one dissolved (unioned),
simplified polygon per state/UT, tagged with our own state/zone ids from
india_states.json — for the India map's Leaflet layer.

Source: a modern (2019+, includes Telangana/Ladakh/J&K split) district-
level GeoJSON, dissolved up to state level with shapely since no
ready-made *state*-level file that current was found — the well-known
state-level mirrors (geohacker/india, Subhash9325/...) predate the 2014
Telangana split and are 15-25MB unsimplified besides.

Run once (or whenever the source/india_states.json changes):
    python3 scripts/build_india_states_geojson.py
"""
import json
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

BASE_DIR = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "_india_districts_source.geojson"
STATES_JSON = BASE_DIR / "static" / "data" / "india_states.json"
OUT = BASE_DIR / "static" / "data" / "india_states.geojson"

SIMPLIFY_TOLERANCE_DEG = 0.01  # ~1.1km at India's latitudes — smooth but recognizable at map zoom

# Source dataset name -> our india_states.json name, where they differ.
NAME_ALIASES = {
    "Puducherry": "Pondicherry",
    "Lakshadweep": "Lakshadweep Islands",
}
# Our two separately-listed union territories that this source has already
# merged into one (2020 real-world merger) — both get the same polygon.
MERGED_UT_SOURCE_NAME = "Dadra and Nagar Haveli and Daman and Diu"
MERGED_UT_OUR_NAMES = ["Dadra and Nagar Haveli", "Daman and Diu"]


def load_our_states():
    data = json.loads(STATES_JSON.read_text(encoding="utf-8"))
    by_name = {}
    for zone in data["zones"]:
        for state in zone["states"]:
            by_name[state["name"]] = {
                "id": state["id"], "zone_id": zone["id"], "zone_name": zone["name"], "zone_color": zone["color"],
            }
    return by_name


def main():
    src = json.loads(SRC.read_text(encoding="utf-8"))
    our_states = load_our_states()

    # Group district geometries by state name, dissolve into one shape.
    by_state_name = {}
    for feature in src["features"]:
        name = feature["properties"]["st_nm"]
        by_state_name.setdefault(name, []).append(shape(feature["geometry"]))

    dissolved = {name: unary_union(geoms).simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
                 for name, geoms in by_state_name.items()}

    out_features = []
    matched, unmatched_source, unmatched_ours = [], [], list(our_states.keys())

    for src_name, geom in dissolved.items():
        target_names = MERGED_UT_OUR_NAMES if src_name == MERGED_UT_SOURCE_NAME else [NAME_ALIASES.get(src_name, src_name)]
        for our_name in target_names:
            info = our_states.get(our_name)
            if not info:
                unmatched_source.append(src_name)
                continue
            matched.append(our_name)
            if our_name in unmatched_ours:
                unmatched_ours.remove(our_name)
            out_features.append({
                "type": "Feature",
                "properties": {
                    "name": our_name,
                    "qm_state_id": info["id"],
                    "qm_zone_id": info["zone_id"],
                    "qm_zone_name": info["zone_name"],
                    "qm_zone_color": info["zone_color"],
                },
                "geometry": mapping(geom),
            })

    out = {"type": "FeatureCollection", "features": out_features}
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")

    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB), {len(out_features)} state features")
    print(f"Matched: {len(matched)}/{len(our_states)} of our states")
    print(f"Unmatched source names (no qm state found): {unmatched_source}")
    print(f"Our states with no polygon: {unmatched_ours}")


if __name__ == "__main__":
    main()
