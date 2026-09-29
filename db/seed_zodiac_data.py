"""Reference data for zodiac_signs and nakshatras — real Vedic/Western
astrological reference data, not placeholders.

Zodiac date ranges are the tropical (Western) convention, per the brief's
own Part 3 table — used for the simple, deterministic "sun sign -> element"
governance classification that has to work from date of birth alone.

Nakshatra degrees and Vimshottari dasha lords are the standard sidereal
27-nakshatra scheme (each 13°20' / 13.3333°), used by the kundali generator
(zodiac_core.generate_kundali), which is sidereal (Lahiri ayanamsa) — see
zodiac_core.py's module docstring for why sun-sign and kundali intentionally
use different zodiacs.
"""

ZODIAC_SIGNS = [
    {"name": "Aries", "element": "Fire", "symbol": "♈", "start": "03-21", "end": "04-19", "ruling_planet": "Mars"},
    {"name": "Taurus", "element": "Earth", "symbol": "♉", "start": "04-20", "end": "05-20", "ruling_planet": "Venus"},
    {"name": "Gemini", "element": "Air", "symbol": "♊", "start": "05-21", "end": "06-20", "ruling_planet": "Mercury"},
    {"name": "Cancer", "element": "Water", "symbol": "♋", "start": "06-21", "end": "07-22", "ruling_planet": "Moon"},
    {"name": "Leo", "element": "Fire", "symbol": "♌", "start": "07-23", "end": "08-22", "ruling_planet": "Sun"},
    {"name": "Virgo", "element": "Earth", "symbol": "♍", "start": "08-23", "end": "09-22", "ruling_planet": "Mercury"},
    {"name": "Libra", "element": "Air", "symbol": "♎", "start": "09-23", "end": "10-22", "ruling_planet": "Venus"},
    {"name": "Scorpio", "element": "Water", "symbol": "♏", "start": "10-23", "end": "11-21", "ruling_planet": "Mars"},
    {"name": "Sagittarius", "element": "Fire", "symbol": "♐", "start": "11-22", "end": "12-21", "ruling_planet": "Jupiter"},
    {"name": "Capricorn", "element": "Earth", "symbol": "♑", "start": "12-22", "end": "01-19", "ruling_planet": "Saturn"},
    {"name": "Aquarius", "element": "Air", "symbol": "♒", "start": "01-20", "end": "02-18", "ruling_planet": "Saturn"},
    {"name": "Pisces", "element": "Water", "symbol": "♓", "start": "02-19", "end": "03-20", "ruling_planet": "Jupiter"},
]

# 27 nakshatras, each 13°20' (13.3333...) of sidereal longitude, starting at
# 0 Aries. Vimshottari dasha lords cycle Ketu-Venus-Sun-Moon-Mars-Rahu-
# Jupiter-Saturn-Mercury, repeated 3x — the standard real sequence.
_VIMSHOTTARI_CYCLE = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]

NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

NAKSHATRA_SPAN = 360.0 / 27  # 13.3333...


def build_nakshatras():
    rows = []
    for i, name in enumerate(NAKSHATRA_NAMES):
        start_degree = i * NAKSHATRA_SPAN
        end_degree = start_degree + NAKSHATRA_SPAN
        sign_index = int(start_degree // 30)  # which of the 12 (sidereal) signs it starts in
        rows.append({
            "name": name,
            "nakshatra_index": i,
            "sign_index": sign_index,
            "start_degree": round(start_degree, 4),
            "end_degree": round(end_degree, 4),
            "ruling_planet": _VIMSHOTTARI_CYCLE[i % 9],
        })
    return rows


def seed(conn):
    cur = conn.cursor()

    sign_ids = {}
    for z in ZODIAC_SIGNS:
        nakshatras_in_sign = [
            n["name"] for n in build_nakshatras()
            if n["sign_index"] == ZODIAC_SIGNS.index(z)
        ]
        cur.execute(
            """INSERT OR IGNORE INTO zodiac_signs
               (name, element, symbol, start_date, end_date, nakshatras, ruling_planet)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (z["name"], z["element"], z["symbol"], z["start"], z["end"],
             __import__("json").dumps(nakshatras_in_sign), z["ruling_planet"]),
        )
    conn.commit()

    for row in cur.execute("SELECT id, name FROM zodiac_signs"):
        sign_ids[row[1]] = row[0]

    sign_names_in_order = [z["name"] for z in ZODIAC_SIGNS]
    for n in build_nakshatras():
        sign_name = sign_names_in_order[n["sign_index"]]
        cur.execute(
            """INSERT OR IGNORE INTO nakshatras
               (name, nakshatra_index, zodiac_id, start_degree, end_degree, ruling_planet)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (n["name"], n["nakshatra_index"], sign_ids[sign_name],
             n["start_degree"], n["end_degree"], n["ruling_planet"]),
        )
    conn.commit()
