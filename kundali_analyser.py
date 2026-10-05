"""Kundali (Vedic birth chart) analysis, built on top of the planetary longitudes
`zodiac_core.generate_kundali()` already computes. Two things this module adds that the raw
chart doesn't have:

1. A **Moon-based (Chandra Lagna) house chart** — House 1 = the sign the Moon occupies, houses
   then run forward through the zodiac from there. This is DIFFERENT from the Ascendant-based
   whole-sign "houses" already stored in `kundali["houses"]` (used by the existing Kundali
   modal/`app._kundali_view()`) — that one keeps House 1 = the Ascendant's sign. Both are
   legitimate, standard Vedic charts; the Founder asked specifically for the Moon-based one on
   the Private Account page (2026-10-04): "My Private Account Vedic chart image should display
   Libra as first house [Moon's sign]... continue same till 12th house."
2. An automated analysis: Drishti (planetary aspects), strong/weak houses, elemental balance,
   and the current Vimshottari Dasha (based on the Moon's nakshatra) — none of which the raw
   chart dict computes.

Nothing here touches ephemeris math; `kundali` is always the already-computed dict from
`zodiac_core.generate_kundali()` (stored as JSON in `user_zodiac.birth_chart`).
"""
from __future__ import annotations

import datetime as dt

from zodiac_core import NAKSHATRA_NAMES, SIDEREAL_SIGNS, ZODIAC_RANGES, _NAKSHATRA_SPAN

SIGN_ELEMENT = {z["sign"]: z["element"] for z in ZODIAC_RANGES}

# The 9 nakshatra lords, repeating 3x across the 27 nakshatras -- also the fixed Vimshottari
# Dasha cycle order (each nakshatra's lord starts that nakshatra's ruling planet's own dasha
# cycle at birth).
DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
NAKSHATRA_LORDS = DASHA_ORDER * 3
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}
assert sum(DASHA_YEARS.values()) == 120

BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
MALEFICS = {"Saturn", "Mars", "Rahu", "Ketu"}

# Drishti (full aspect): every planet aspects the 7th house from itself; these four also cast
# additional special aspects. (Sun, Moon, Mercury, Venus aspect only the 7th.)
SPECIAL_ASPECTS = {
    "Mars": (4, 8), "Jupiter": (5, 9), "Saturn": (3, 10), "Rahu": (4, 8, 12), "Ketu": (3, 10),
}

# The 10 chart points shown on a Kundali, in a fixed display order.
POINT_ORDER = ["Ascendant", "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]


def _degree_str(degree: float) -> str:
    d = int(degree)
    m = int(round((degree - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}°{m:02d}′"


def _nakshatra_info(sign: str, degree: float) -> dict:
    """sign+degree-within-sign -> nakshatra name, lord, pada, and how far through that
    nakshatra (0-1) -- the last is what the Dasha balance-at-birth calculation needs."""
    lon = SIDEREAL_SIGNS.index(sign) * 30 + float(degree)
    index = int(lon // _NAKSHATRA_SPAN) % 27
    offset = (lon % _NAKSHATRA_SPAN)
    pada = int(offset // (_NAKSHATRA_SPAN / 4)) + 1
    return {
        "name": NAKSHATRA_NAMES[index], "lord": NAKSHATRA_LORDS[index], "pada": pada,
        "index": index, "fraction_elapsed": offset / _NAKSHATRA_SPAN,
    }


def _chart_points(kundali: dict) -> dict:
    """All 10 points (Ascendant, Sun, Moon, 5 planets, Rahu, Ketu) as {sign, degree}."""
    points = {
        "Ascendant": {"sign": kundali["ascendant"]["sign"], "degree": kundali["ascendant"]["degree"]},
        "Sun": {"sign": kundali["sun"]["sign"], "degree": kundali["sun"]["degree"]},
        "Moon": {"sign": kundali["moon"]["sign"], "degree": kundali["moon"]["degree"]},
    }
    points.update(kundali["planets"])
    return points


def moon_based_houses(kundali: dict) -> dict:
    """House 1 = the Moon's own sign (Chandra Lagna), houses then run forward through the
    zodiac. Returns {house_num (1-12): {"sign": ..., "points": [point names occupying it]}}."""
    points = _chart_points(kundali)
    moon_index = SIDEREAL_SIGNS.index(kundali["moon"]["sign"])
    houses = {}
    for house_num in range(1, 13):
        sign = SIDEREAL_SIGNS[(moon_index + house_num - 1) % 12]
        occupants = [name for name, p in points.items() if p["sign"] == sign and name != "Ascendant"]
        houses[house_num] = {"sign": sign, "points": occupants}
    return houses


def _house_of_sign(sign: str, moon_index: int) -> int:
    return (SIDEREAL_SIGNS.index(sign) - moon_index) % 12 + 1


def planetary_table(kundali: dict) -> list[dict]:
    """One row per chart point, in POINT_ORDER, with sign/element/nakshatra/degree/Moon-based
    house -- the detailed table shown below the chart image."""
    points = _chart_points(kundali)
    moon_index = SIDEREAL_SIGNS.index(kundali["moon"]["sign"])
    rows = []
    for name in POINT_ORDER:
        p = points[name]
        nak = _nakshatra_info(p["sign"], p["degree"])
        rows.append({
            "point": name, "sign": p["sign"], "element": SIGN_ELEMENT[p["sign"]],
            "nakshatra": nak["name"], "nakshatra_lord": nak["lord"], "pada": nak["pada"],
            "degree": _degree_str(p["degree"]) if name != "Ascendant" else _degree_str(p["degree"]),
            "house": _house_of_sign(p["sign"], moon_index),
        })
    return rows


def aspects(kundali: dict) -> dict:
    """{point name: [house numbers it aspects]} -- Drishti, Moon-based houses. Ascendant (a
    point, not a planet) casts no aspect."""
    points = _chart_points(kundali)
    moon_index = SIDEREAL_SIGNS.index(kundali["moon"]["sign"])
    out = {}
    for name in POINT_ORDER:
        if name == "Ascendant":
            continue
        own_house = _house_of_sign(points[name]["sign"], moon_index)
        offsets = (7,) + SPECIAL_ASPECTS.get(name, ())
        out[name] = sorted({((own_house - 1 + off) % 12) + 1 for off in offsets})
    return out


def house_strength(kundali: dict) -> dict:
    """{house_num: {"occupants": [...], "status": "strong"|"weak"|"neutral"|"empty"}} --
    benefic occupants (Jupiter/Venus/Mercury/Moon) make a house strong, malefic occupants
    (Saturn/Mars/Rahu/Ketu) or no occupants make it weak; Sun-only or mixed stays neutral."""
    houses = moon_based_houses(kundali)
    out = {}
    for n, h in houses.items():
        occupants = h["points"]
        if not occupants:
            status = "weak"
        else:
            has_benefic = any(p in BENEFICS for p in occupants)
            has_malefic = any(p in MALEFICS for p in occupants)
            if has_benefic and not has_malefic:
                status = "strong"
            elif has_malefic and not has_benefic:
                status = "weak"
            else:
                status = "neutral"
        out[n] = {"sign": h["sign"], "occupants": occupants, "status": status}
    return out


def elemental_balance(kundali: dict) -> dict:
    """Fire/Earth/Air/Water counts across the 9 planets (Sun, Moon, 5 visible planets, Rahu,
    Ketu -- the Ascendant is a point in space, not a planet, so it's excluded) + dominant
    element."""
    points = _chart_points(kundali)
    counts = {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0}
    for name, p in points.items():
        if name == "Ascendant":
            continue
        counts[SIGN_ELEMENT[p["sign"]]] += 1
    dominant = max(counts, key=counts.get)
    return {"counts": counts, "dominant": dominant}


def vimshottari_dasha(dob_iso: str, kundali: dict, today: dt.date | None = None, periods: int = 9) -> dict:
    """The Vimshottari Mahadasha sequence from birth (120-year cycle), which planet's period is
    current, and the next few periods ahead ("lucky periods ahead"). Years are treated as
    365.25-day Julian years, the standard software approximation."""
    today = today or dt.date.today()
    dob = dt.date.fromisoformat(dob_iso)
    nak = _nakshatra_info(kundali["moon"]["sign"], kundali["moon"]["degree"])
    start_lord_index = DASHA_ORDER.index(nak["lord"])

    sequence = []
    cursor = dob
    # The birth nakshatra's own lord runs for only the REMAINING fraction of its full period
    # (the rest was "used up" before birth, astrologically) -- the balance-of-dasha-at-birth.
    first_lord = DASHA_ORDER[start_lord_index]
    remaining_years = DASHA_YEARS[first_lord] * (1 - nak["fraction_elapsed"])
    end = cursor + dt.timedelta(days=remaining_years * 365.25)
    sequence.append({"lord": first_lord, "start": cursor.isoformat(), "end": end.isoformat()})
    cursor = end
    for i in range(1, periods):
        lord = DASHA_ORDER[(start_lord_index + i) % 9]
        end = cursor + dt.timedelta(days=DASHA_YEARS[lord] * 365.25)
        sequence.append({"lord": lord, "start": cursor.isoformat(), "end": end.isoformat()})
        cursor = end

    current = None
    current_index = None
    for i, period in enumerate(sequence):
        if period["start"] <= today.isoformat() <= period["end"]:
            current, current_index = period, i
            break
    upcoming = sequence[current_index + 1: current_index + 4] if current_index is not None else []
    return {"sequence": sequence, "current": current, "upcoming": upcoming}


# ---- North Indian style chart (SVG) ----
# A square, its 2 corner-to-corner diagonals, and the diamond formed by joining the 4 edge
# midpoints -- the classic North Indian Vedic chart construction. That produces exactly 12
# regions: 4 "kite" quadrilaterals at the N/E/S/W edge midpoints (the kendra houses 1/4/7/10,
# each bounded by two diamond edges and a vertex at the chart's center) and 8 triangles at the
# 4 corners (2 per corner, split by the diagonal). House numbering is fixed by position --
# House 1 is always the top kite -- and runs clockwise from there; it's the SIGN label written
# inside each cell that changes from person to person (here: the Moon-based house's own sign).
# Coordinates below are for a 400x400 box; every vertex is a corner, an edge midpoint, the
# center, or a diagonal/diamond-edge crossing point -- derived from the four line equations
# (both diagonals, both pairs of diamond edges) rather than guessed.
_W = 400
_HOUSE_POLYGONS = {
    1: [(200, 0), (300, 100), (200, 200), (100, 100)],
    2: [(200, 0), (400, 0), (300, 100)],
    3: [(400, 0), (400, 200), (300, 100)],
    4: [(400, 200), (300, 300), (200, 200), (300, 100)],
    5: [(400, 400), (400, 200), (300, 300)],
    6: [(400, 400), (300, 300), (200, 400)],
    7: [(200, 400), (300, 300), (200, 200), (100, 300)],
    8: [(200, 400), (100, 300), (0, 400)],
    9: [(0, 400), (100, 300), (0, 200)],
    10: [(0, 200), (100, 100), (200, 200), (100, 300)],
    11: [(0, 200), (0, 0), (100, 100)],
    12: [(0, 0), (200, 0), (100, 100)],
}
# Where the house number goes in each cell -- near its outward tip for the kites, near its
# corner for the triangles -- kept clear of the centroid, which is where the sign/planets go.
_NUMBER_POS = {
    1: (200, 28), 2: (330, 35), 3: (365, 70), 4: (372, 200), 5: (365, 330), 6: (330, 365),
    7: (200, 372), 8: (70, 365), 9: (35, 330), 10: (28, 200), 11: (35, 70), 12: (70, 35),
}
# (2026-10-05 fix: houses 2/6/8/12 previously used the x-coordinate belonging to their mirror-
# image neighbor, so their number label rendered inside the ADJACENT kite house (1 or 7) instead
# of their own triangle -- verified by point-in-polygon check against _HOUSE_POLYGONS, and the
# corrected positions cross-checked via two independent 90-degree-rotation derivations from the
# 8 already-correct houses, both landing on the same point.)

_PLANET_ABBR = {
    "Ascendant": "As", "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me",
    "Jupiter": "Ju", "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke",
}


def _centroid(poly: list[tuple[float, float]]) -> tuple[float, float]:
    n = len(poly)
    return sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n


def chart_svg(kundali: dict, width: int = 360) -> str:
    """A self-contained North Indian style SVG: 12 houses, each labelled with its sign and the
    points occupying it, House 1 = the Moon's sign."""
    houses = moon_based_houses(kundali)
    scale = width / _W
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {width}" width="{width}" height="{width}" role="img" aria-label="Vedic birth chart">']
    lines.append(f'<rect x="1" y="1" width="{width-2}" height="{width-2}" fill="#0b1220" stroke="#e8b23d" stroke-width="2"/>')
    # Outer square sides double as the edges already drawn by the rect; add diagonals + diamond.
    def pt(x, y):
        return f"{x*scale:.1f},{y*scale:.1f}"
    for a, b in [((0, 0), (_W, _W)), ((_W, 0), (0, _W)),
                 ((200, 0), (0, 200)), ((200, 0), (_W, 200)), ((_W, 200), (200, _W)), ((0, 200), (200, _W))]:
        lines.append(f'<line x1="{a[0]*scale:.1f}" y1="{a[1]*scale:.1f}" x2="{b[0]*scale:.1f}" y2="{b[1]*scale:.1f}" stroke="#e8b23d" stroke-width="1"/>')
    for house_num, poly in _HOUSE_POLYGONS.items():
        h = houses[house_num]
        cx, cy = _centroid(poly)
        nx, ny = _NUMBER_POS[house_num]
        lines.append(f'<text x="{nx*scale:.1f}" y="{ny*scale:.1f}" fill="#6b7a99" font-size="{11*scale:.1f}" text-anchor="middle">{house_num}</text>')
        label = SIGNS_SHORT.get(h["sign"], h["sign"][:3])
        cell_lines = [label] + ([", ".join(_PLANET_ABBR.get(p, p[:2]) for p in h["points"])] if h["points"] else [])
        ty = cy - (len(cell_lines) - 1) * 7
        for cl in cell_lines:
            lines.append(f'<text x="{cx*scale:.1f}" y="{ty*scale:.1f}" fill="#f4d58d" font-size="{12*scale:.1f}" text-anchor="middle" font-weight="600">{cl}</text>')
            ty += 14
    lines.append("</svg>")
    return "".join(lines)


SIGNS_SHORT = {
    "Aries": "Ar", "Taurus": "Ta", "Gemini": "Ge", "Cancer": "Cn", "Leo": "Le", "Virgo": "Vi",
    "Libra": "Li", "Scorpio": "Sc", "Sagittarius": "Sg", "Capricorn": "Cp", "Aquarius": "Aq", "Pisces": "Pi",
}


def _ascendant_note(kundali: dict) -> str:
    """One-line clarification shown under the chart: this Kundali is sidereal (Lahiri), while
    the profile's own "Sun Sign" badge elsewhere in the app is tropical -- the two legitimately
    differ by design (see zodiac_core.py's own module docstring), and without this note a user
    could easily read the mismatch as a bug. Also flags when the Ascendant sits close enough to
    a sign boundary that the result is unusually sensitive to the exact recorded birth minute --
    verified during the 2026-10-05 UI fix pass that this is a real, data-precision question, not
    a computation error (see docs/dashboard_fixes_2026_10_05.md)."""
    note = ('Vedic Kundali uses sidereal (Lahiri); Qumanity profile "Sun Sign" uses tropical. '
            "Both are correct for their purpose.")
    deg = (kundali.get("ascendant") or {}).get("degree")
    if deg is not None and (deg < 1.0 or deg > 29.0):
        note += (" Your Ascendant sits very close to a sign boundary, so this result is "
                  "unusually sensitive to your exact recorded birth minute.")
    return note


def analyse(dob_iso: str, kundali: dict, today: dt.date | None = None) -> dict:
    """Everything the Private Account's Kundali Analysis section needs, in one call."""
    return {
        "chart_svg": chart_svg(kundali),
        "houses": moon_based_houses(kundali),
        "table": planetary_table(kundali),
        "aspects": aspects(kundali),
        "house_strength": house_strength(kundali),
        "elemental_balance": elemental_balance(kundali),
        "dasha": vimshottari_dasha(dob_iso, kundali, today),
        "ascendant_note": _ascendant_note(kundali),
    }
