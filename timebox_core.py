"""Time-box: local time, sunrise/sunset, Vedic panchang and today's sky for a user's present country.

Everything is computed with Swiss Ephemeris (sidereal, Lahiri), the same set-up zodiac_core uses for birth charts.
Places are resolved to their country's representative point until finer coordinates are stored per location.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import swisseph as swe

swe.set_sid_mode(swe.SIDM_LAHIRI)
_FLAGS = swe.FLG_SIDEREAL | swe.FLG_MOSEPH

# country code -> (lat, lng, IANA timezone)
COUNTRY_GEO = {
    "IND": (26.85, 80.95, "Asia/Kolkata"), "NPL": (27.70, 85.32, "Asia/Kathmandu"), "BTN": (27.47, 89.64, "Asia/Thimphu"),
    "BGD": (23.81, 90.41, "Asia/Dhaka"), "MMR": (19.76, 96.08, "Asia/Yangon"), "LKA": (6.93, 79.86, "Asia/Colombo"),
    "PAK": (33.68, 73.05, "Asia/Karachi"), "BAL": (30.18, 66.99, "Asia/Karachi"), "BLC": (30.18, 66.99, "Asia/Karachi"),
    "AFG": (34.53, 69.17, "Asia/Kabul"), "MDV": (4.18, 73.51, "Indian/Maldives"),
}
DEFAULT_GEO = (26.85, 80.95, "Asia/Kolkata")

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
RASHI = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena"]
# Amanta lunar month is named after the Sun's sidereal sign at the new moon that starts it.
CHANDRA_MAAS = {"Meena": "Chaitra", "Mesha": "Vaishakha", "Vrishabha": "Jyeshtha", "Mithuna": "Ashadha", "Karka": "Shravana", "Simha": "Bhadrapada",
                "Kanya": "Ashwin", "Tula": "Kartika", "Vrishchika": "Margashirsha", "Dhanu": "Pausha", "Makara": "Magha", "Kumbha": "Phalguna"}
TITHIS = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi",
          "Dwadashi", "Trayodashi", "Chaturdashi"]
VAAR = ["Somavara (Monday)", "Mangalavara (Tuesday)", "Budhavara (Wednesday)", "Guruvara (Thursday)", "Shukravara (Friday)", "Shanivara (Saturday)", "Ravivara (Sunday)"]
NAKSHATRAS = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
              "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha",
              "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"]
PLANETS = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN}


def _lon(jd, body):
    return swe.calc_ut(jd, body, _FLAGS)[0][0] % 360


def _jd(utc: dt.datetime) -> float:
    return swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60 + utc.second / 3600)


def _elong(jd):  # Moon - Sun elongation
    return (_lon(jd, swe.MOON) - _lon(jd, swe.SUN)) % 360


def _last_new_moon(jd):
    """Julian day of the most recent new moon at or before jd (elongation -> 0)."""
    t = jd - _elong(jd) / 12.19  # mean rate of elongation, degrees per day
    for _ in range(6):
        e = _elong(t)
        if e > 180: e -= 360
        t -= e / 12.19
    return t


def _hm(jd_ut, tz):
    y, m, d, h = swe.revjul(jd_ut)
    utc = dt.datetime(y, m, d, tzinfo=dt.timezone.utc) + dt.timedelta(hours=h)
    return utc.astimezone(tz).strftime("%H:%M")


def _rise_set(local_date: dt.date, lat, lng, tz):
    start = dt.datetime.combine(local_date, dt.time(0, 0), tzinfo=tz).astimezone(dt.timezone.utc)
    jd0 = _jd(start)
    out = {}
    for key, flag in (("sunrise", swe.CALC_RISE), ("sunset", swe.CALC_SET)):
        try:
            res, tret = swe.rise_trans(jd0, swe.SUN, flag | swe.BIT_DISC_CENTER | swe.FLG_MOSEPH, (lng, lat, 0), 1013.25, 15)
            out[key] = _hm(tret[0], tz) if res == 0 else None
        except Exception:
            out[key] = None
    return out


def panchang(now_utc: dt.datetime, tz: ZoneInfo):
    jd = _jd(now_utc)
    sun, moon = _lon(jd, swe.SUN), _lon(jd, swe.MOON)
    elong = (moon - sun) % 360
    n = int(elong // 12)                          # 0..29
    paksha = "Shukla" if n < 15 else "Krishna"
    idx = n % 15
    tithi = "Purnima" if n == 14 else "Amavasya" if n == 29 else TITHIS[idx]
    nak_i = int(moon // (360 / 27))
    pada = int((moon % (360 / 27)) // (360 / 108)) + 1
    nm = _last_new_moon(jd)
    maas = CHANDRA_MAAS[RASHI[int(_lon(nm, swe.SUN) // 30)]]
    return {
        "tithi": f"{paksha} {tithi}", "vaar": VAAR[now_utc.astimezone(tz).weekday()],
        "nakshatra": f"{NAKSHATRAS[nak_i]} (pada {pada})",
        "chandra_maas": f"{maas} ({paksha} paksha)", "surya_maas": f"{RASHI[int(sun // 30)]} ({SIGNS[int(sun // 30)]})",
    }


def sky_now(now_utc: dt.datetime, lat, lng):
    """Today's sidereal planetary placements with whole-sign houses counted from the rising sign."""
    jd = _jd(now_utc)
    _c, ascmc = swe.houses_ex(jd, lat, lng, b"P", flags=swe.FLG_SIDEREAL)
    asc = ascmc[0] % 360
    pts = {name: _lon(jd, body) for name, body in PLANETS.items()}
    rahu = _lon(jd, swe.MEAN_NODE); pts["Rahu"] = rahu; pts["Ketu"] = (rahu + 180) % 360
    a = int(asc // 30)
    houses = []
    for h in range(1, 13):
        si = (a + h - 1) % 12
        occ = [{"planet": p, "text": f"{int(l % 30)}°{int(round((l % 30 % 1) * 60)):02d}′"} for p, l in pts.items() if int(l // 30) == si]
        houses.append({"n": h, "sign": SIGNS[si], "asc": h == 1, "planets": occ})
    return {"ascendant": f"{SIGNS[a]} {int(asc % 30)}°", "houses": houses}


def timebox(present_location: dict, now_utc: dt.datetime | None = None):
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    code = ((present_location.get("country") or {}).get("code") or "").upper()
    lat, lng, tzname = COUNTRY_GEO.get(code, DEFAULT_GEO)
    tz = ZoneInfo(tzname)
    local = now_utc.astimezone(tz)
    return {
        "place": " · ".join(x["name"] for k in ("village", "district", "country") if (x := present_location.get(k))),
        "lat": lat, "lng": lng, "timezone": tzname, "tz_abbr": local.strftime("UTC%z")[:-2] + ":" + local.strftime("%z")[-2:],
        "iso": local.isoformat(), "time": local.strftime("%H:%M"), "date": local.strftime("%A, %d %B %Y"),
        **_rise_set(local.date(), lat, lng, tz), "panchang": panchang(now_utc, tz), "sky": sky_now(now_utc, lat, lng),
        "note": "Location is the country's reference point until village coordinates are stored.",
    }
