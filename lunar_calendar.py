"""Lunar cycle detection + Vedic Chandra Maas naming (Phase 1 of the lunar-cycle archival system —
see docs/lunar_cycle_system.md for the complete design, docs/phase_build_plan.md for what's built
vs. still to come). Detection and naming only: no DB schema changes, no pipeline, not wired into
production anywhere in this phase.

Reuses the exact sidereal setup zodiac_core.py already established (Lahiri ayanamsa, Moshier
analytic ephemeris -- no external ephemeris data files needed, which matters on Railway), AND
reuses lunar_core.py's own `_elongation()` (the Sun-Moon angle) rather than redefining it --
lunar_core.py already has real, working Purnima/Amavasya-adjacent phase-finding (used for the
"upcoming moon phase" display feature), just scoped to "the NEXT occurrence from now," not "every
occurrence across an arbitrary range" -- which is what THIS module adds on top, for naming whole
cycles and scanning a year at a time. Finding the exact Purnima/Amavasya MOMENT uses that same
elongation angle, which is ayanamsa-independent (it's a difference of two longitudes in the same
frame, so any constant sidereal offset cancels out) -- sidereal only matters afterward, for naming
a month from the Sun's rashi at its own Purnima.

Naming rule (see docs/phase_build_plan.md for why this reconciles the two ways the original spec
described it): a "cycle" is one Amavasya-to-Amavasya window; it is named by the Sun's sidereal
rashi (Lahiri) at THAT window's own Purnima -- Mesha->Chaitra, Vrishabha->Vaishakha, ... ,
Meena->Phalguna, the standard purnimanta simplification.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import swisseph as swe

from lunar_core import _elongation  # reused as-is, see module docstring

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

swe.set_sid_mode(swe.SIDM_LAHIRI)
_SIDEREAL_FLAGS = swe.FLG_SIDEREAL | swe.FLG_MOSEPH  # for naming (Sun's sidereal rashi) only

# Purnimanta Vedic month order, index 0 = Mesha's month (Chaitra) through index 11 = Meena's
# month (Phalguna) -- the rashi the Sun occupies AT a month's own Purnima names that month.
VEDIC_MONTHS = [
    "Chaitra", "Vaishakha", "Jyeshtha", "Ashadha", "Shravana", "Bhadrapada",
    "Ashwin", "Kartik", "Margashirsha", "Pausha", "Magha", "Phalguna",
]

_TRANSLATIONS_FILE = Path(__file__).resolve().parent / "translations" / "lunar_months.json"
_SUPPORTED_LANGS = ("en", "hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "ur", "or", "as")


def _load_translations() -> dict:
    return json.loads(_TRANSLATIONS_FILE.read_text(encoding="utf-8"))


# ---- Julian day <-> datetime, matching zodiac_core.generate_kundali()'s own swe.julday usage ----

def _jd_ut(utc_dt: dt.datetime) -> float:
    return swe.julday(
        utc_dt.year, utc_dt.month, utc_dt.day,
        utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600,
    )


def _jd_to_utc(jd: float) -> dt.datetime:
    y, m, d, h = swe.revjul(jd)
    hour = int(h)
    minute_frac = (h - hour) * 60
    minute = int(minute_frac)
    second = round((minute_frac - minute) * 60)
    out = dt.datetime(y, m, d, hour, minute, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=second)
    return out


def _find_phase_crossing(jd_lo: float, jd_hi: float, target: float) -> float:
    """Bisect for the jd in [jd_lo, jd_hi] where elongation crosses `target` (0 or 180), assuming
    exactly one such crossing in that bracket (true for the 1-day steps _scan_phases uses -- the
    Moon never gains more than ~15 degrees on the Sun in a day, far under the 180-degree target
    spacing, so a bracket is never ambiguous)."""
    def signed(jd: float) -> float:
        return (_elongation(jd) - target + 180.0) % 360.0 - 180.0

    lo, hi = jd_lo, jd_hi
    sign_lo = signed(lo) < 0
    for _ in range(50):  # (hi - lo) <= 1 day; 50 halvings is far beyond sub-second precision
        mid = (lo + hi) / 2.0
        if (signed(mid) < 0) == sign_lo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _scan_phases(jd_start: float, jd_end: float) -> list[tuple[float, str]]:
    """Every Amavasya ('new') and Purnima ('full') moment in [jd_start, jd_end], via daily
    stepping (well under the ~29.53-day synodic month, so no crossing is ever skipped) plus a
    running UNWRAPPED cumulative elongation, so every 180-degree multiple is caught exactly once
    regardless of the 0/360 wraparound."""
    events: list[tuple[float, str]] = []
    step = 1.0
    jd = jd_start
    prev_mod = _elongation(jd)
    cumulative = prev_mod
    next_multiple = (int(cumulative // 180.0) + 1) * 180.0
    while jd < jd_end:
        nxt = jd + step
        nxt_mod = _elongation(nxt)
        delta = nxt_mod - prev_mod
        if delta < 0:
            delta += 360.0
        cumulative_next = cumulative + delta
        while next_multiple <= cumulative_next:
            target = next_multiple % 360.0
            jd_exact = _find_phase_crossing(jd, nxt, target)
            is_full = (round(next_multiple / 180.0) % 2) == 1
            events.append((jd_exact, "full" if is_full else "new"))
            next_multiple += 180.0
        jd, prev_mod, cumulative = nxt, nxt_mod, cumulative_next
    events.sort(key=lambda e: e[0])
    return events


def _sun_sidereal_rashi(jd: float) -> int:
    lon = swe.calc_ut(jd, swe.SUN, _SIDEREAL_FLAGS)[0][0]
    return int(lon // 30.0) % 12


def _month_for_purnima(purnima_jd: float) -> str:
    return VEDIC_MONTHS[_sun_sidereal_rashi(purnima_jd)]


def _amavasya_window(moment: dt.datetime) -> tuple[float, float, float]:
    """(start_amavasya_jd, mid_purnima_jd, end_amavasya_jd) for the Amavasya-to-Amavasya window
    containing `moment`. Scans a +/-40 day bracket around it -- comfortably more than one synodic
    month (29.53 days) on each side, so the window containing `moment`, plus its own Purnima, are
    always found regardless of where `moment` falls inside it."""
    utc = moment.astimezone(dt.timezone.utc) if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)
    jd = _jd_ut(utc)
    events = _scan_phases(jd - 40, jd + 40)
    amavasyas = sorted(e[0] for e in events if e[1] == "new")
    purnimas = sorted(e[0] for e in events if e[1] == "full")
    # A tiny (~1 second) tolerance: `moment` is often an Amavasya datetime that's already been
    # rounded to the second (e.g. round-tripped through a printed table), which can otherwise
    # land a fraction of a second on the wrong side of the exact boundary it's meant to BE,
    # silently picking the previous cycle instead of the one that starts at it.
    eps = 1.0 / 86400.0
    idx = max(i for i, a in enumerate(amavasyas) if a <= jd + eps)
    start_jd, end_jd = amavasyas[idx], amavasyas[idx + 1]
    mid_jd = next(p for p in purnimas if start_jd < p < end_jd)
    return start_jd, mid_jd, end_jd


def _year_scan_range(year: int, month: int | None) -> tuple[float, float]:
    if month:
        start_y, start_m = year, month
        end_y, end_m = (year, month + 1) if month < 12 else (year + 1, 1)
    else:
        start_y, start_m = year, 1
        end_y, end_m = year + 1, 1
    start = _jd_ut(dt.datetime(start_y, start_m, 1, tzinfo=dt.timezone.utc)) - 5
    end = _jd_ut(dt.datetime(end_y, end_m, 1, tzinfo=dt.timezone.utc)) + 5
    return start, end


# ---- Public API ----

def compute_purnima(year: int, month: int | None = None) -> list[dt.datetime]:
    """All Purnima (Full Moon) moments in `year` (or `year`-`month`), as IST datetimes."""
    start, end = _year_scan_range(year, month)
    events = _scan_phases(start, end)
    out = [_jd_to_utc(jd).astimezone(IST) for jd, kind in events if kind == "full"]
    return [d for d in out if d.year == year and (month is None or d.month == month)]


def compute_amavasya(year: int, month: int | None = None) -> list[dt.datetime]:
    """All Amavasya (New Moon) moments in `year` (or `year`-`month`), as IST datetimes."""
    start, end = _year_scan_range(year, month)
    events = _scan_phases(start, end)
    out = [_jd_to_utc(jd).astimezone(IST) for jd, kind in events if kind == "new"]
    return [d for d in out if d.year == year and (month is None or d.month == month)]


def upcoming_events(count: int = 6, from_moment: dt.datetime | None = None) -> list[dict]:
    """The next `count` Purnima/Amavasya events on/after `from_moment` (defaults to now, IST),
    each as {'phase': 'Purnima'|'Amavasya', 'datetime': ..., 'vedic_month': ...}."""
    from_moment = from_moment or dt.datetime.now(IST)
    utc = from_moment.astimezone(dt.timezone.utc) if from_moment.tzinfo else from_moment.replace(tzinfo=dt.timezone.utc)
    jd0 = _jd_ut(utc)
    window_days = 40
    events: list[tuple[float, str]] = []
    while len(events) < count:
        events = [e for e in _scan_phases(jd0, jd0 + window_days) if e[0] >= jd0]
        window_days += 40
    out = []
    for jd, kind in events[:count]:
        moment = _jd_to_utc(jd).astimezone(IST)
        out.append({
            "phase": "Purnima" if kind == "full" else "Amavasya",
            "datetime": moment.isoformat(),
            "vedic_month": _month_for_purnima(jd) if kind == "full" else get_vedic_month_name(moment),
        })
    return out


def get_vedic_month_name(moment: dt.datetime) -> str:
    """The Vedic Chandra Maas name for the Amavasya-to-Amavasya cycle containing `moment` --
    named from the Sun's sidereal rashi at that cycle's own Purnima."""
    _, mid_jd, _ = _amavasya_window(moment)
    return _month_for_purnima(mid_jd)


def get_current_cycle_id(moment: dt.datetime | None = None) -> str:
    """'{Month}_{Year}' for the lunar cycle containing `moment` (defaults to now, IST). Year is
    the Gregorian year of the cycle's own Purnima (the moment that names it)."""
    moment = moment or dt.datetime.now(IST)
    _, mid_jd, _ = _amavasya_window(moment)
    month = _month_for_purnima(mid_jd)
    year = _jd_to_utc(mid_jd).astimezone(IST).year
    return f"{month}_{year}"


def get_cycle_dates(cycle_id: str) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    """(start_amavasya, mid_purnima, end_amavasya) as IST datetimes, reverse-engineered from a
    cycle_id like 'Chaitra_2027' -- scans the named year (+/- 35 days margin, since a given Vedic
    month's Purnima can land in either of two adjacent Gregorian months) for the Purnima whose
    Sun-sidereal rashi matches that month, then finds the Amavasyas either side of it."""
    try:
        month_name, year_str = cycle_id.rsplit("_", 1)
        year = int(year_str)
    except ValueError as e:
        raise ValueError(f"Malformed cycle_id: {cycle_id!r} (expected '{{Month}}_{{Year}}')") from e
    if month_name not in VEDIC_MONTHS:
        raise ValueError(f"Unknown Vedic month: {month_name!r}")
    target_rashi = VEDIC_MONTHS.index(month_name)

    jan1 = _jd_ut(dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
    dec31 = _jd_ut(dt.datetime(year, 12, 31, tzinfo=dt.timezone.utc))
    events = _scan_phases(jan1 - 35, dec31 + 35)
    purnimas = sorted(e[0] for e in events if e[1] == "full")
    amavasyas = sorted(e[0] for e in events if e[1] == "new")

    matches = [
        p for p in purnimas
        if _sun_sidereal_rashi(p) == target_rashi
        and _jd_to_utc(p).astimezone(IST).year == year
    ]
    if not matches:
        raise ValueError(f"No Purnima found for cycle_id {cycle_id!r} in {year}")
    mid_jd = matches[0]
    start_jd = max(a for a in amavasyas if a < mid_jd)
    end_jd = min(a for a in amavasyas if a > mid_jd)

    to_ist = lambda jd: _jd_to_utc(jd).astimezone(IST)
    return to_ist(start_jd), to_ist(mid_jd), to_ist(end_jd)


def translated_cycle_display_name(cycle_id: str) -> dict[str, str]:
    """{'en': 'Chaitra Purnima to Vaishakha Amavasya 2027', 'hi': '...', ...} for all 13 languages
    -- the `display_names` block of a cycle_metadata.json (see docs/lunar_cycle_system.md)."""
    start_jd_month, year = cycle_id.rsplit("_", 1)
    start_dt, mid_dt, end_dt = get_cycle_dates(cycle_id)
    end_month = get_vedic_month_name(end_dt + dt.timedelta(days=1))  # a day into the next window
    translations = _load_translations()
    out = {}
    for lang in _SUPPORTED_LANGS:
        start_month_name = translations[start_jd_month][lang]
        end_month_name = translations[end_month][lang]
        purnima_word = translations["_suffixes"]["Purnima"][lang]
        amavasya_word = translations["_suffixes"]["Amavasya"][lang]
        out[lang] = f"{start_month_name} {purnima_word} to {end_month_name} {amavasya_word} {year}"
    return out


def archive_folder_name(cycle_id: str) -> str:
    """'{StartMonth}_Purnima-to-{EndMonth}_Amavasya_{Year}' -- always English, filesystem-safe."""
    start_month, year = cycle_id.rsplit("_", 1)
    _, _, end_dt = get_cycle_dates(cycle_id)
    end_month = get_vedic_month_name(end_dt + dt.timedelta(days=1))
    return f"{start_month}_Purnima-to-{end_month}_Amavasya_{year}"
