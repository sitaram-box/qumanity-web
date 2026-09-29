"""Zodiac sign, nakshatra, and Vedic kundali (birth chart) calculations.

Two deliberately different zodiacs are used here, for two different jobs:

- ``get_zodiac_sign`` — the TROPICAL (Western) zodiac, using the plain
  Gregorian date ranges from the brief's own Part 3 table. This is what
  drives the Fire/Earth/Air/Water elemental classification used for
  village-level governance division: it must work from date of birth
  alone, for every user, with no birth time/place/ephemeris required.

- ``generate_kundali`` — the SIDEREAL zodiac (Lahiri ayanamsa), which is
  what a Vedic "kundali" and nakshatras actually are; the brief's own
  ``nakshatras`` table and ruling-planet framing only make sense sidereally.
  This needs real ephemeris math (via ``pyswisseph``, Moshier analytical
  ephemeris — accurate to a few arcseconds, no external data files needed)
  and a real birth time + place, converted to UTC via the birth location's
  actual IANA timezone (``timezonefinder`` + stdlib ``zoneinfo``, not a
  crude longitude/15 estimate).

Mixing these up would be wrong, not just inconsistent — a sidereal Sun and
a tropical Sun are ~24 degrees apart and can land in a different sign
entirely near a boundary. Don't use ``generate_kundali``'s sun sign for
the elemental classification, or vice versa.
"""

from __future__ import annotations

import datetime as _dt
from zoneinfo import ZoneInfo

import swisseph as swe
from timezonefinder import TimezoneFinder

swe.set_sid_mode(swe.SIDM_LAHIRI)

_TF = TimezoneFinder()

_EPHE_FLAGS = swe.FLG_SIDEREAL | swe.FLG_MOSEPH

ZODIAC_RANGES = [
    {"sign": "Aries", "element": "Fire", "start": "03-21", "end": "04-19"},
    {"sign": "Taurus", "element": "Earth", "start": "04-20", "end": "05-20"},
    {"sign": "Gemini", "element": "Air", "start": "05-21", "end": "06-20"},
    {"sign": "Cancer", "element": "Water", "start": "06-21", "end": "07-22"},
    {"sign": "Leo", "element": "Fire", "start": "07-23", "end": "08-22"},
    {"sign": "Virgo", "element": "Earth", "start": "08-23", "end": "09-22"},
    {"sign": "Libra", "element": "Air", "start": "09-23", "end": "10-22"},
    {"sign": "Scorpio", "element": "Water", "start": "10-23", "end": "11-21"},
    {"sign": "Sagittarius", "element": "Fire", "start": "11-22", "end": "12-21"},
    {"sign": "Capricorn", "element": "Earth", "start": "12-22", "end": "01-19"},
    {"sign": "Aquarius", "element": "Air", "start": "01-20", "end": "02-18"},
    {"sign": "Pisces", "element": "Water", "start": "02-19", "end": "03-20"},
]

SIDEREAL_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
_NAKSHATRA_SPAN = 360.0 / 27

_PLANETS = {
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
}


def get_zodiac_sign(birth_date: _dt.date) -> dict | None:
    """Tropical sun sign + element from a date of birth alone."""
    date_str = f"{birth_date.month:02d}-{birth_date.day:02d}"
    for z in ZODIAC_RANGES:
        start, end = z["start"], z["end"]
        if start <= end:
            if start <= date_str <= end:
                return z
        else:  # Capricorn wraps New Year (12-22 .. 01-19)
            if date_str >= start or date_str <= end:
                return z
    return None


def _lon_to_sign(lon: float) -> tuple[str, float]:
    lon = lon % 360.0
    index = int(lon // 30)
    return SIDEREAL_SIGNS[index], lon - index * 30


def _lon_to_nakshatra(lon: float) -> tuple[str, int, float]:
    lon = lon % 360.0
    index = int(lon // _NAKSHATRA_SPAN)
    offset_in_nakshatra = lon - index * _NAKSHATRA_SPAN
    pada = int(offset_in_nakshatra // (_NAKSHATRA_SPAN / 4)) + 1
    return NAKSHATRA_NAMES[index], pada, lon


def _resolve_utc_datetime(dob: _dt.date, tob: _dt.time, lat: float, lng: float) -> _dt.datetime:
    """Local civil birth time -> real UTC, using the birth location's
    actual historical timezone (not a longitude/15 guess)."""
    tz_name = _TF.timezone_at(lat=lat, lng=lng) or "UTC"
    local_dt = _dt.datetime.combine(dob, tob, tzinfo=ZoneInfo(tz_name))
    return local_dt.astimezone(_dt.timezone.utc), tz_name


def generate_kundali(dob: _dt.date, tob: _dt.time, lat: float, lng: float) -> dict:
    """Full sidereal (Lahiri) Vedic birth chart: ascendant, sun, moon,
    5 visible planets + Rahu/Ketu, and whole-sign houses."""
    utc_dt, tz_name = _resolve_utc_datetime(dob, tob, lat, lng)
    jd_ut = swe.julday(
        utc_dt.year, utc_dt.month, utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600,
    )

    sun_lon = swe.calc_ut(jd_ut, swe.SUN, _EPHE_FLAGS)[0][0]
    moon_lon = swe.calc_ut(jd_ut, swe.MOON, _EPHE_FLAGS)[0][0]
    rahu_lon = swe.calc_ut(jd_ut, swe.MEAN_NODE, _EPHE_FLAGS)[0][0]
    ketu_lon = (rahu_lon + 180.0) % 360.0

    _cusps, ascmc = swe.houses_ex(jd_ut, lat, lng, b"P", flags=swe.FLG_SIDEREAL)
    asc_lon = ascmc[0]

    sun_sign, sun_deg = _lon_to_sign(sun_lon)
    moon_sign, moon_deg = _lon_to_sign(moon_lon)
    asc_sign, asc_deg = _lon_to_sign(asc_lon)
    moon_nak, moon_pada, _ = _lon_to_nakshatra(moon_lon)

    planets = {}
    for name, code in _PLANETS.items():
        lon = swe.calc_ut(jd_ut, code, _EPHE_FLAGS)[0][0]
        sign, deg = _lon_to_sign(lon)
        planets[name] = {"sign": sign, "degree": round(deg, 2)}
    for name, lon in (("Rahu", rahu_lon), ("Ketu", ketu_lon)):
        sign, deg = _lon_to_sign(lon)
        planets[name] = {"sign": sign, "degree": round(deg, 2)}

    # Whole-sign houses: house 1 = the ascendant's sign, then each sign
    # in zodiac order — the standard Vedic (Rashi chart) house scheme,
    # as opposed to Western sub-degree cusp houses.
    asc_index = SIDEREAL_SIGNS.index(asc_sign)
    houses = {}
    chart_points = dict(planets)
    chart_points["Sun"] = {"sign": sun_sign}
    chart_points["Moon"] = {"sign": moon_sign}
    for house_num in range(1, 13):
        sign = SIDEREAL_SIGNS[(asc_index + house_num - 1) % 12]
        occupants = [p for p, v in chart_points.items() if v["sign"] == sign]
        houses[str(house_num)] = {"sign": sign, "planet": ", ".join(occupants)}

    return {
        "ephemeris": {
            "mode": "moshier-sidereal-lahiri",
            "utc_datetime": utc_dt.isoformat(),
            "birth_timezone": tz_name,
            "julian_day_ut": jd_ut,
        },
        "ascendant": {"sign": asc_sign, "degree": round(asc_deg, 2), "nakshatra": _lon_to_nakshatra(asc_lon)[0]},
        "sun": {"sign": sun_sign, "degree": round(sun_deg, 2), "nakshatra": _lon_to_nakshatra(sun_lon)[0]},
        "moon": {"sign": moon_sign, "degree": round(moon_deg, 2), "nakshatra": moon_nak, "pada": moon_pada},
        "planets": planets,
        "houses": houses,
    }


def generate_kundali_summary(user_zodiac_data: dict) -> str:
    """Readable summary from a user_zodiac row (sun_sign/sun_element are
    tropical; moon_sign/moon_nakshatra/ascendant_sign are sidereal)."""
    sun_sign = user_zodiac_data.get("sun_sign")
    sun_element = user_zodiac_data.get("sun_element")
    moon_sign = user_zodiac_data.get("moon_sign")
    moon_nakshatra = user_zodiac_data.get("moon_nakshatra")
    ascendant = user_zodiac_data.get("ascendant_sign")

    summary = f"You are a {sun_sign} ({sun_element}) with a {moon_sign} Moon"
    if moon_nakshatra:
        summary += f" in {moon_nakshatra} nakshatra"
    summary += ". "
    if ascendant:
        summary += f"Your ascendant (rising sign) is {ascendant}. "
    summary += (
        f"Your birth-date element is {sun_element} — this anchors your place in "
        f"Qumanity's elemental governance cycle, independent of your Vedic kundali above."
    )
    return summary
