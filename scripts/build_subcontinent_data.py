#!/usr/bin/env python3
"""Builds the Indian Sub-continent's Public-timeline data for the app from
the compiled master file (Desktop/0_Earth/Qumanity_Master.json, names/ids
only) plus the existing India data files.

Writes (all under static/data/):
  subcontinent_states.json     countries -> zones -> states, all 9 countries
  subcontinent_districts.json  state id -> districts -> tehsils (+ direct_villages count)
  subcontinent.geojson         the 10 countries dissolved into ONE shape (outline + fill/border cells)
  subcontinent_land.geojson    all other land (drawn uniform black around it)
and imports the 8 new countries' villages into india_villages (the table
name is historical; tehsil_id there is simply the village's parent id --
the tehsil, or the district for villages that hang directly off a district).
Also adds Balochistan (its own country in the master) to global_countries.json.

Idempotent: safe to re-run after the master is recompiled.
    python3 scripts/build_subcontinent_data.py
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

from shapely import clip_by_rect
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "static" / "data"


def _resolve_master_json() -> Path:
    """Same MASTER_JSON_PATH env var + fallback order as scripts/import_india_villages.py
    (2026-10-11, removing a hardcoded single-developer-Mac path)."""
    candidates = []
    env = os.environ.get("MASTER_JSON_PATH")
    if env:
        candidates.append(Path(env).expanduser())
    candidates += [
        Path("/data/Qumanity_Master.json"),
        BASE / "Qumanity_Master.json",
        Path("~/Desktop/0_Earth/Qumanity_Master.json").expanduser(),
    ]
    for c in candidates:
        if c.exists():
            return c
    print("ERROR: Qumanity_Master.json not found. Tried:")
    for c in candidates:
        print(f"  {c}")
    sys.exit(1)


MASTER = _resolve_master_json()
DB = BASE / "qumanity_prototype.db"

# code -> (country id, display order)
SUBCONTINENT_CODES = ["IND", "NPL", "BTN", "BGD", "MMR", "LKA", "PAK", "BLC", "AFG", "MDV"]
NEW_CODES = [c for c in SUBCONTINENT_CODES if c != "IND"]
# Balochistan has no polygon of its own in the 110m borders file -- it sits
# inside Pakistan's, which is already part of the dissolved outline.
BORDER_ISO3 = ["IND", "NPL", "BTN", "BGD", "MMR", "LKA", "PAK", "AFG", "MDV"]
NE50 = BASE / "scripts" / "_ne_50m_admin_0_countries.geojson"
INDIA_STATES_GEO = DATA / "india_states.geojson"

# Public-timeline tier names per country, taken from the folder names used in
# Desktop/0_Earth (India keeps Zone/State/District/Tehsil/Village). null = the
# tier doesn't exist / isn't asked for: each non-India country has a single zone
# equal to the country itself, and Balochistan/Maldives a single state, so those
# are auto-selected and hidden.
TIER_LABELS = {
    "IND": {"zone": "Zone", "state": "State", "district": "District", "tehsil": "Tehsil", "village": "Village"},
    "NPL": {"zone": None, "state": "Province", "district": "District", "tehsil": "Local Level", "village": "Ward"},
    "BTN": {"zone": None, "state": "Dzongkhag", "district": "Gewog", "tehsil": "Chiwog", "village": "Village"},
    "BGD": {"zone": None, "state": "Division", "district": "District", "tehsil": "Upazila", "village": "Village"},
    "MMR": {"zone": None, "state": "State / Region", "district": "District", "tehsil": "Township", "village": "Village"},
    "LKA": {"zone": None, "state": "Province", "district": "District", "tehsil": "DS Division", "village": "GN Division"},
    "PAK": {"zone": None, "state": "Province", "district": "District", "tehsil": "Tehsil", "village": "Village"},
    "BLC": {"zone": None, "state": None, "district": "District", "tehsil": "Tehsil", "village": "Village"},
    "AFG": {"zone": None, "state": "Province", "district": "District", "tehsil": None, "village": "Village"},
    "MDV": {"zone": None, "state": None, "district": "Atoll", "tehsil": "Area", "village": "Island"},
}


def load_master_asia():
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    asia = next(c for c in master["Continents"] if c["id"] == "O_AS")
    return {c["id"].split("_")[-1]: c for c in asia["Countries"]}


def build_states(asia):
    india = json.loads((DATA / "india_states.json").read_text(encoding="utf-8"))
    countries = []
    for code in SUBCONTINENT_CODES:
        node = asia[code]
        if code == "IND":
            zones = india["zones"]
        else:
            zones = [
                {
                    "id": z["id"],
                    "name": z["name"],
                    "states": [{"id": s["id"], "name": s["name"]} for s in z["States"]],
                }
                for z in node["Zones"]
            ]
        countries.append({"id": node["id"], "code": code, "name": node["name"], "labels": TIER_LABELS[code], "zones": zones})
    return {"id": "SUBCONTINENT", "name": "Indian Sub-continent", "countries": countries}


def build_districts_and_villages(asia):
    india = json.loads((DATA / "india_districts_tehsils.json").read_text(encoding="utf-8"))
    states = dict(india["states"])
    villages = []  # (id, parent_id, name)
    for code in NEW_CODES:
        for zone in asia[code]["Zones"]:
            for st in zone["States"]:
                districts = []
                for d in st.get("Districts") or []:
                    tehsils = []
                    for t in d.get("tehsils") or []:
                        tehsils.append({"id": t["id"], "name": t["name"]})
                        for v in t.get("villages") or []:
                            villages.append((v["id"], t["id"], v["name"]))
                    direct = d.get("villages") or []
                    for v in direct:
                        villages.append((v["id"], d["id"], v["name"]))
                    entry = {"id": d["id"], "name": d["name"], "tehsils": tehsils}
                    if direct:
                        entry["direct_villages"] = len(direct)
                    districts.append(entry)
                states[st["id"]] = {"name": st["name"], "districts": districts}
    return {"states": states}, villages


def _round_coords(obj, nd=3):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], nd), round(obj[1], nd)]
        return [_round_coords(o, nd) for o in obj]
    return obj


def _polygons(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    return [g for part in geom.geoms for g in _polygons(part)]


def _cells(geom, step, window=None, coarse=None):
    """Cut `geom` into grid cells (each stays small so the globe's flat
    triangles don't sink under the sphere). `window` = (x0, y0, x1, y1) gets
    `step`-degree cells, everything else `coarse`-degree cells."""
    out = []
    minx, miny, maxx, maxy = geom.bounds

    def sweep(x0, y0, x1, y1, st):
        x = x0
        while x < x1:
            y = y0
            while y < y1:
                for g in _polygons(clip_by_rect(geom, x, y, x + st, y + st)):
                    if g.area > 1e-7:
                        out.append(g)
                y += st
            x += st

    if window is None:
        sweep((minx // step) * step, (miny // step) * step, maxx, maxy, step)
        return out
    wx0, wy0, wx1, wy1 = window
    sweep(wx0, wy0, wx1, wy1, step)
    # coarse cells for the rest of the world, skipping the window
    x = -180.0
    while x < 180:
        y = -90.0
        while y < 90:
            if not (x >= wx0 and x + coarse <= wx1 and y >= wy0 and y + coarse <= wy1):
                for g in _polygons(clip_by_rect(geom, x, y, x + coarse, y + coarse)):
                    if g.area > 1e-7:
                        out.append(g)
            y += coarse
        x += coarse
    return out


def _feature(role, geom, extra=None):
    props = {"name": "Indian Sub-continent", "qm_country_id": "SUBCONTINENT", "qm_continent_code": "AS", "role": role}
    props.update(extra or {})
    g = mapping(geom)
    return {"type": "Feature", "properties": props,
            "geometry": {"type": g["type"], "coordinates": _round_coords(g["coordinates"])}}


def build_map_layers():
    """Vector layers for the globe (no raster texture -> crisp at any zoom):
      subcontinent.geojson       outline (border line + hit-test), fill cells, border-band cells
      subcontinent_land.geojson  every other land area, cut into cells (drawn uniform black)
    The sub-continent is the 10 countries plus the whole of India as drawn in
    the app's own India map (india_states.geojson), dissolved into ONE shape."""
    ne = json.loads(NE50.read_text(encoding="utf-8"))
    region_parts, all_land = [], []
    for f in ne["features"]:
        g = shape(f["geometry"])
        all_land.append(g)
        if f["properties"].get("ADM0_A3") in BORDER_ISO3 + ["KAS"]:
            region_parts.append(g)
    india = json.loads(INDIA_STATES_GEO.read_text(encoding="utf-8"))
    region_parts += [shape(f["geometry"]).buffer(0) for f in india["features"]]

    region = unary_union([g.buffer(0.05) for g in region_parts]).buffer(-0.05)
    region = unary_union([Polygon(p.exterior) for p in _polygons(region)])  # drop interior holes
    # Maldives' atolls are far thinner than the closing buffer above, so add them
    # back fattened (~0.3 deg) -- otherwise the 10th country would vanish.
    mdv = [shape(f["geometry"]) for f in ne["features"] if f["properties"].get("ADM0_A3") == "MDV"]
    region = unary_union([region] + [g.buffer(0.3) for g in mdv])
    region = region.simplify(0.01, preserve_topology=True)
    assert region.is_valid

    band = region.buffer(0.15).difference(region.buffer(-0.15))
    fill_cells = _cells(region, 0.6)
    band_cells = _cells(band, 0.6)
    layers = {
        "type": "FeatureCollection",
        "features": [
            _feature("outline", region),
            _feature("fill", MultiPolygon(fill_cells)),
            _feature("border", MultiPolygon(band_cells)),
        ],
    }

    land = unary_union([g.buffer(0.01) for g in all_land]).simplify(0.015, preserve_topology=True)
    land = land.difference(region.buffer(0.15))
    land_cells = _cells(land, 1.0, window=(20, -20, 150, 70), coarse=4.0)
    land_layer = {"type": "FeatureCollection", "features": [_feature("land", MultiPolygon(land_cells))]}
    return layers, land_layer


def add_balochistan_to_world(asia):
    path = DATA / "global_countries.json"
    world = json.loads(path.read_text(encoding="utf-8"))
    asia_cont = next(c for c in world["continents"] if c["code"] == "AS")
    if any(co["code"] == "BLC" for co in asia_cont["countries"]):
        return False
    asia_cont["countries"].append({"code": "BLC", "id": asia["BLC"]["id"], "name": asia["BLC"]["name"], "city_count": 0})
    path.write_text(json.dumps(world, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main():
    asia = load_master_asia()
    (DATA / "subcontinent_states.json").write_text(
        json.dumps(build_states(asia), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    districts, villages = build_districts_and_villages(asia)
    (DATA / "subcontinent_districts.json").write_text(
        json.dumps(districts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    layers, land_layer = build_map_layers()
    (DATA / "subcontinent.geojson").write_text(json.dumps(layers, separators=(",", ":")), encoding="utf-8")
    (DATA / "subcontinent_land.geojson").write_text(json.dumps(land_layer, separators=(",", ":")), encoding="utf-8")
    parts = len(layers["features"][1]["geometry"]["coordinates"])

    conn = sqlite3.connect(DB)
    conn.executemany("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
                     [(vid, parent, name) for vid, parent, name in villages])
    conn.commit()
    conn.close()

    added = add_balochistan_to_world(asia)
    print(f"states file: {len(SUBCONTINENT_CODES)} countries; districts file: {len(districts['states'])} states")
    print(f"villages imported: {len(villages)}; fill cells: {parts}; Balochistan added to world list: {added}")


if __name__ == "__main__":
    main()
