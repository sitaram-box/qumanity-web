#!/usr/bin/env python3
"""Build static/data/india_states.json for the registration wizard's
India state picker.

Stream-parses updated_SITAXML.xml for just Zone -> State (id, name),
discarding District/Tehsil/Village nodes as we go to keep memory flat on
the 50MB file, then enriches each state with an approximate centroid
lat/lng (for plotting) and its zone's color (per the brief's Central
/North/South/East/West spec — South's navy is brightened for marker
visibility against the globe's own dark background).
"""
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# SITAXML_SOURCE_PATH overrides this -- the maintainer's own machine is the only place this raw
# census-derived source file normally lives; everyone else must set the env var (2026-10-11,
# removing a hardcoded path that only existed on one developer's Mac).
SRC = os.environ.get("SITAXML_SOURCE_PATH", str(Path.home() / "Desktop" / "updated_SITAXML.xml"))
OUT = str(REPO_ROOT / "static" / "data" / "india_states.json")

CENTROIDS = {
    "CS.CH": (30.7, 76.8), "CS.DL": (28.6, 77.2), "CS.JK": (33.8, 76.6),
    "CS.LA": (34.2, 77.6), "CS.DN": (20.2, 73.0), "CS.DD": (20.4, 72.8),
    "CS.AN": (11.7, 92.7), "CS.LD": (10.6, 72.6), "CS.PY": (11.9, 79.8),
    "CS.AR": (28.2, 94.7), "CS.AS": (26.2, 92.9), "CS.MN": (24.7, 93.9),
    "CS.ME": (25.5, 91.4), "CS.MI": (23.3, 92.8), "CS.NL": (26.2, 94.6),
    "CS.SK": (27.6, 88.5), "CS.TR": (23.8, 91.3),
    "NS.HR": (29.1, 76.1), "NS.HP": (31.9, 77.2), "NS.PB": (31.1, 75.3),
    "NS.RJ": (26.9, 73.8), "NS.UP": (26.8, 80.9), "NS.UT": (30.1, 79.0),
    "WS.CT": (21.3, 81.9), "WS.GA": (15.4, 74.0), "WS.GJ": (22.3, 71.7),
    "WS.MP": (23.5, 78.5), "WS.MH": (19.5, 75.7),
    "SS.AP": (15.9, 79.7), "SS.KA": (14.5, 75.7), "SS.KL": (10.5, 76.3),
    "SS.TN": (11.1, 78.6), "SS.TS": (17.9, 79.5),
    "ES.BH": (25.7, 85.9), "ES.JH": (23.6, 85.3), "ES.OR": (20.5, 84.7),
    "ES.WB": (23.0, 87.8),
}

# Brief's zone colors, with South's navy (#0A1929) brightened — illegible
# as a small marker against the globe's own dark-navy material otherwise.
ZONE_COLORS = {
    "IND/CS": "#FF9933",
    "IND/NS": "#138808",
    "IND/SS": "#4A90D9",
    "IND/ES": "#FFD700",
    "IND/WS": "#FFFFFF",
}


def parse_zones():
    zones = []
    current_zone = None
    for event, el in ET.iterparse(SRC, events=("start", "end")):
        tag = el.tag
        if event == "start" and tag == "Public_Zone":
            current_zone = {"id": el.get("id"), "name": el.get("Name"), "states": []}
        elif event == "end" and tag == "Public_Zone":
            zones.append(current_zone)
            current_zone = None
            el.clear()
        elif event == "end" and tag == "Public_State":
            if current_zone is not None:
                current_zone["states"].append({"id": el.get("id"), "name": el.get("Name")})
            el.clear()
        elif event == "end" and tag in ("Public_District", "Public_Tehsil", "Public_Village"):
            el.clear()
    return zones


def enrich(zones):
    missing = []
    for zone in zones:
        zone["color"] = ZONE_COLORS[zone["id"]]
        for state in zone["states"]:
            centroid = CENTROIDS.get(state["id"])
            if centroid is None:
                missing.append(state["id"])
                centroid = (22.0, 79.0)  # rough India centroid fallback
            state["lat"], state["lng"] = centroid
            state["zone_id"] = zone["id"]
            state["zone_name"] = zone["name"]
            state["color"] = zone["color"]
    if missing:
        print("WARN: no centroid for", missing, "— used India-center fallback")


def main():
    zones = parse_zones()
    enrich(zones)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"zones": zones}, f, ensure_ascii=False, indent=2)

    print("Zones:", len(zones))
    for z in zones:
        print(" ", z["id"], z["name"], "-", len(z["states"]), "states")
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
