#!/usr/bin/env python3
"""Rasterize static/data/world_borders.geojson into an equirectangular PNG
texture (static/images/earth_texture.png) — country fills colored by
continent (India gets its own saffron, per the brief). No border lines are
drawn: the homepage's Earth view is meant to show only the 7 continents as
seamless colored landmasses (same-continent countries share a fill color,
so with no border pixels between them they blend into one shape); per-
country detail lives in the separate 2D continent/country maps instead
(static/js/region_map.js, static/js/india_map.js), not on this texture.
Applied as the sphere's material map in earth-globe.js.

Antimeridian handling: rings that cross +-180 degrees longitude (Russia,
Fiji, the Aleutians...) are longitude-unwrapped first, then drawn on a
3x-wide canvas at three horizontal offsets and cropped back to one world
width — whichever copy overlaps the visible window renders correctly,
avoiding the classic "line straight across the map" artifact.

Run once (or whenever world_borders.geojson changes):
    python3 scripts/build_world_texture.py
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent.parent
BORDERS_PATH = BASE_DIR / "static" / "data" / "world_borders.geojson"
OUT_PATH = BASE_DIR / "static" / "images" / "earth_texture.png"

W, H = 2048, 1024
OCEAN = (10, 25, 41, 255)        # matches earth-globe.js's ocean material (#0A1929)

# Continent fill colors — distinct per continent, coherent with Qumanity's
# palette. No country (India included) gets its own color here: the Earth
# view is meant to show only the 7 continents as seamless colored regions,
# with every country in a continent sharing that one color indistinguishably
# — India only becomes visually distinct once you've actually zoomed into
# Asia's continent map / India's own country view.
CONTINENT_COLORS = {
    "AS": (201, 162, 39, 255),   # gold
    "AF": (46, 139, 87, 255),    # sea green
    "NA": (74, 144, 217, 255),   # blue
    "SA": (232, 93, 78, 255),    # warm orange-red
    "EU": (139, 92, 246, 255),   # violet
    "OC": (45, 212, 191, 255),   # teal
    "AN": (140, 150, 165, 255),  # muted gray — not selectable
}
UNMATCHED_COLOR = (70, 80, 95, 255)   # territories with no qm_country_id


def lng_to_x(lng):
    return (lng + 180.0) / 360.0 * W


def lat_to_y(lat):
    return (90.0 - lat) / 180.0 * H


def unwrap_ring(ring):
    """Remove antimeridian jumps by letting longitude run continuously
    past +-180 where needed (classic angle-unwrap)."""
    out = [list(ring[0])]
    for lng, lat in ring[1:]:
        prev_lng = out[-1][0]
        while lng - prev_lng > 180:
            lng -= 360
        while lng - prev_lng < -180:
            lng += 360
        out.append([lng, lat])
    return out


def ring_to_px(ring, x_offset):
    return [(lng_to_x(lng) + x_offset, lat_to_y(lat)) for lng, lat in ring]


def polygon_rings(geometry):
    """Yield each polygon's list-of-rings (exterior first, then holes) for
    both Polygon and MultiPolygon geometries."""
    if geometry["type"] == "Polygon":
        yield geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for poly in geometry["coordinates"]:
            yield poly


def fill_color_for(props):
    code = props.get("qm_continent_code")
    if code in CONTINENT_COLORS:
        return CONTINENT_COLORS[code]
    return UNMATCHED_COLOR


def main():
    data = json.loads(BORDERS_PATH.read_text(encoding="utf-8"))

    # 3x-wide working canvas so antimeridian-unwrapped rings (which may
    # extend outside the normal -180..180 range) still land somewhere
    # drawable; crop the center world-width slice at the end.
    canvas = Image.new("RGBA", (W * 3, H), OCEAN)
    draw = ImageDraw.Draw(canvas)
    x_offsets = (-W, 0, W)

    # Pass 1: fills
    for feature in data["features"]:
        color = fill_color_for(feature["properties"])
        for rings in polygon_rings(feature["geometry"]):
            unwrapped = [unwrap_ring(r) for r in rings]
            for x_off in x_offsets:
                exterior_px = ring_to_px(unwrapped[0], x_off)
                if len(exterior_px) >= 3:
                    draw.polygon(exterior_px, fill=color)
                for hole in unwrapped[1:]:
                    hole_px = ring_to_px(hole, x_off)
                    if len(hole_px) >= 3:
                        draw.polygon(hole_px, fill=OCEAN)

    final = canvas.crop((W, 0, W * 2, H))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final.save(OUT_PATH)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB, {final.size})")


if __name__ == "__main__":
    main()
