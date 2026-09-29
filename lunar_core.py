"""Real lunar phase + eclipse calculations via pyswisseph (Moshier
analytical ephemeris — no external data files, no fabricated dates).

New/Full Moon times are found by root-finding the Sun-Moon elongation
angle (monotonic between syzygies, ~12.19 deg/day); eclipses use
swisseph's own dedicated eclipse-search functions.
"""

from __future__ import annotations

import datetime as _dt

import swisseph as swe

_EPHE_FLAGS = swe.FLG_MOSEPH
_DELHI_GEOPOS = (77.2090, 28.6139, 0)  # lon, lat, alt — representative India location for visibility checks

PHASE_NAMES = [
    (0, "New Moon"), (45, "Waxing Crescent"), (90, "First Quarter"),
    (135, "Waxing Gibbous"), (180, "Full Moon"), (225, "Waning Gibbous"),
    (270, "Last Quarter"), (315, "Waning Crescent"), (360, "New Moon"),
]


def _jd_now(dt_utc: _dt.datetime | None = None) -> float:
    dt_utc = dt_utc or _dt.datetime.now(_dt.timezone.utc)
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                       dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600)


def _elongation(jd: float) -> float:
    sun = swe.calc_ut(jd, swe.SUN, _EPHE_FLAGS)[0][0]
    moon = swe.calc_ut(jd, swe.MOON, _EPHE_FLAGS)[0][0]
    return (moon - sun) % 360.0


def _jd_to_iso(jd: float) -> tuple[str, str]:
    y, m, d, h = swe.revjul(jd)
    dt_utc = _dt.datetime(y, m, d, tzinfo=_dt.timezone.utc) + _dt.timedelta(hours=h)
    return dt_utc.date().isoformat(), dt_utc.strftime("%H:%M")


def get_current_lunar_phase(dt_utc: _dt.datetime | None = None) -> dict:
    jd = _jd_now(dt_utc)
    elong = _elongation(jd)
    illum = swe.pheno_ut(jd, swe.MOON, _EPHE_FLAGS)[1]
    phase_name = "New Moon"
    for lo, name in reversed(PHASE_NAMES[:-1]):
        if elong >= lo:
            phase_name = name
            break
    return {
        "elongation_degrees": round(elong, 2),
        "illuminated_fraction": round(illum, 4),
        "phase_name": phase_name,
        "as_of_utc": _dt.datetime.now(_dt.timezone.utc).isoformat() if dt_utc is None else dt_utc.isoformat(),
    }


def _find_next_elongation(jd0: float, target_deg: float) -> float:
    """Root-find the next time elongation == target_deg (mod 360), after jd0."""
    elong0 = _elongation(jd0)
    delta = (target_deg - elong0) % 360.0
    if delta == 0:
        delta = 360.0
    rough = jd0 + delta / 12.19086

    lo, hi = rough - 1.0, rough + 1.0

    def f(jd):
        # signed distance to target, unwrapped to (-180, 180]
        d = (_elongation(jd) - target_deg + 180) % 360 - 180
        return d

    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0:
        f_lo, lo = f(lo - 1.0), lo - 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _sun_moon_sign(jd: float) -> tuple[str, str]:
    from zodiac_core import SIDEREAL_SIGNS, _lon_to_sign, _lon_to_nakshatra
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    moon_lon = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL | swe.FLG_MOSEPH)[0][0]
    sign, _ = _lon_to_sign(moon_lon)
    nak, _, _ = _lon_to_nakshatra(moon_lon)
    return sign, nak


def get_upcoming_lunar_events(dt_utc: _dt.datetime | None = None) -> list[dict]:
    """Next New Moon, next Full Moon, and the next lunar/solar eclipse
    visible from India (Delhi as a representative point)."""
    jd0 = _jd_now(dt_utc)
    events = []

    for target, label in ((0.0, "New Moon"), (180.0, "Full Moon")):
        jd = _find_next_elongation(jd0, target)
        date, time_ = _jd_to_iso(jd)
        sign, nak = _sun_moon_sign(jd)
        events.append({
            "event_type": label, "date": date, "time": time_,
            "zodiac_sign": sign, "nakshatra": nak,
            "description": f"Next {label.lower()}", "is_visible_in_india": True,
        })

    try:
        lun = swe.lun_eclipse_when_loc(jd0, _DELHI_GEOPOS, _EPHE_FLAGS, backwards=False)
        jd_max = lun[1][0]
        date, time_ = _jd_to_iso(jd_max)
        sign, nak = _sun_moon_sign(jd_max)
        events.append({
            "event_type": "Lunar Eclipse", "date": date, "time": time_,
            "zodiac_sign": sign, "nakshatra": nak,
            "description": "Next lunar eclipse visible from India (checked at Delhi)",
            "is_visible_in_india": True,
        })
    except Exception as e:
        events.append({"event_type": "Lunar Eclipse", "date": None, "time": None,
                        "zodiac_sign": None, "nakshatra": None,
                        "description": f"Could not compute: {e}", "is_visible_in_india": False})

    try:
        sol = swe.sol_eclipse_when_loc(jd0, _DELHI_GEOPOS, _EPHE_FLAGS, backwards=False)
        jd_max = sol[1][0]
        date, time_ = _jd_to_iso(jd_max)
        sign, nak = _sun_moon_sign(jd_max)
        events.append({
            "event_type": "Solar Eclipse", "date": date, "time": time_,
            "zodiac_sign": sign, "nakshatra": nak,
            "description": "Next solar eclipse visible from India (checked at Delhi)",
            "is_visible_in_india": True,
        })
    except Exception as e:
        events.append({"event_type": "Solar Eclipse", "date": None, "time": None,
                        "zodiac_sign": None, "nakshatra": None,
                        "description": f"Could not compute: {e}", "is_visible_in_india": False})

    events.sort(key=lambda e: e["date"] or "9999")
    return events
