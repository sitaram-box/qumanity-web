#!/usr/bin/env python3
"""Build static/data/india_districts_tehsils.json — real District and
Tehsil names/ids from SITAXML.xml, nested under their State, for the
cascading Zone -> State -> District -> Tehsil location-selection tool.

Villages are deliberately excluded (out of scope for this phase) and
their elements are cleared immediately during the streaming parse so a
635-district, 5971-tehsil extract doesn't require holding the full
50MB/621,057-village tree in memory.

IMPORTANT — naming note: the source brief for this tool asked for
"District = Lok Sabha constituency" and "Tehsil = Vidhan Sabha
constituency". SITAXML.xml has no such data — no constituency numbers,
no MP/MLA fields, nothing distinguishing an electoral constituency from
a revenue-administration division. Its <Public_District>/<Public_Tehsil>
elements are the real administrative districts/tehsils (635 districts is
close to India's actual district count; 5,971 "tehsils" doesn't match
either chamber's real seat count — Lok Sabha has 543 seats, Vidhan Sabha
assemblies total roughly 4,000). This script extracts the real data under
its real labels (District/Tehsil) rather than fabricating a Lok
Sabha/Vidhan Sabha correspondence the source doesn't contain.
"""
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# SITAXML_SOURCE_PATH overrides this -- see scripts/extract_india_states.py's own note; this
# script is also superseded by Qumanity_Master.json as the authoritative India source (see
# docs/india_location_fix.md) and is kept only for historical reference.
SRC = os.environ.get(
    "SITAXML_SOURCE_PATH",
    str(Path.home() / "Desktop" / "Windows Data" / "sita foundation" / "SITA Project Data" / "SITAXML.xml"),
)
OUT = str(REPO_ROOT / "static" / "data" / "india_districts_tehsils.json")


def main():
    states = {}  # state_id -> {id, name, districts: [...]}
    current_state_id = None
    current_district = None

    for event, el in ET.iterparse(SRC, events=("start", "end")):
        tag = el.tag
        if event == "start" and tag == "Public_State":
            current_state_id = el.get("id")
            states[current_state_id] = {"id": current_state_id, "name": (el.get("Name") or "").strip(), "districts": []}
        elif event == "end" and tag == "Public_State":
            current_state_id = None
            el.clear()
        elif event == "start" and tag == "Public_District":
            current_district = {"id": el.get("id"), "name": (el.get("Name") or "").strip(), "tehsils": []}
        elif event == "end" and tag == "Public_District":
            if current_state_id is not None:
                states[current_state_id]["districts"].append(current_district)
            current_district = None
            el.clear()
        elif event == "end" and tag == "Public_Tehsil":
            if current_district is not None:
                current_district["tehsils"].append({"id": el.get("id"), "name": (el.get("Name") or "").strip()})
            el.clear()
        elif event == "end" and tag == "Public_Village":
            el.clear()  # never retained — villages are out of scope for this phase

    out = {"states": states}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    n_districts = sum(len(s["districts"]) for s in states.values())
    n_tehsils = sum(len(d["tehsils"]) for s in states.values() for d in s["districts"])
    print(f"States: {len(states)}  Districts: {n_districts}  Tehsils: {n_tehsils}")
    import os
    print(f"Wrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
