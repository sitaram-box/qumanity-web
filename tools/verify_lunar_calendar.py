"""Phase 1 verification script for the lunar-cycle archival system. Run with:

    python3 tools/verify_lunar_calendar.py

Prints a table of every Purnima/Amavasya from April 2026 to April 2027, a set of consistency
checks, and a translation-loading smoke test. See docs/lunar_cycle_system.md /
docs/phase_build_plan.md for the design this verifies.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import datetime as dt

import lunar_calendar as lc


def _events_in_range(start: dt.date, end: dt.date) -> list[tuple[dt.datetime, str]]:
    events: list[tuple[dt.datetime, str]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        for d in lc.compute_purnima(year, month):
            events.append((d, "Purnima"))
        for d in lc.compute_amavasya(year, month):
            events.append((d, "Amavasya"))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    events.sort(key=lambda e: e[0])
    # de-dupe (a month at the scan boundary can be picked up by two adjacent month-scans)
    out, seen = [], set()
    for d, phase in events:
        key = (d.date(), phase)
        if key not in seen:
            seen.add(key)
            out.append((d, phase))
    return out


def print_table() -> list[tuple[dt.datetime, str]]:
    events = _events_in_range(dt.date(2026, 4, 1), dt.date(2027, 4, 30))
    print(f"{'Date':<22} {'Phase':<10} {'Vedic Month':<14} {'Cycle ID'}")
    print("-" * 70)
    for d, phase in events:
        vedic_month = lc.get_vedic_month_name(d)
        cycle_id = lc.get_current_cycle_id(d) if phase == "Amavasya" else "—"
        print(f"{d.strftime('%Y-%m-%d %H:%M %Z'):<22} {phase:<10} {vedic_month:<14} {cycle_id}")
    return events


def check_alternation(events: list[tuple[dt.datetime, str]]) -> bool:
    ok = True
    for i in range(1, len(events)):
        if events[i][1] == events[i - 1][1]:
            print(f"FAIL: two consecutive {events[i][1]} events: {events[i-1][0]} and {events[i][0]}")
            ok = False
    print(("PASS" if ok else "FAIL") + ": Purnima/Amavasya alternate correctly")
    return ok


def check_no_overlap(events: list[tuple[dt.datetime, str]]) -> bool:
    amavasyas = sorted(d for d, phase in events if phase == "Amavasya")
    ok = True
    for i in range(1, len(amavasyas)):
        gap_days = (amavasyas[i] - amavasyas[i - 1]).total_seconds() / 86400
        if not (27.0 <= gap_days <= 32.0):
            print(f"FAIL: suspicious gap between Amavasyas: {gap_days:.2f} days ({amavasyas[i-1]} -> {amavasyas[i]})")
            ok = False
    print(("PASS" if ok else "FAIL") + ": no two cycles overlap (consecutive Amavasyas ~29.5 days apart)")
    return ok


def check_unique_cycle_ids(events: list[tuple[dt.datetime, str]]) -> bool:
    amavasyas = sorted(d for d, phase in events if phase == "Amavasya")
    cycle_ids = [lc.get_current_cycle_id(d) for d in amavasyas]
    ok = len(cycle_ids) == len(set(cycle_ids))
    print(("PASS" if ok else "FAIL") + f": cycle IDs are unique ({cycle_ids})")
    return ok


def check_translations() -> bool:
    import json
    data = json.loads((Path(__file__).resolve().parent.parent / "translations" / "lunar_months.json").read_text(encoding="utf-8"))
    langs = {"en", "hi", "bn", "ta", "te", "kn", "ml", "mr", "gu", "pa", "ur", "or", "as"}
    ok = True
    for month in lc.VEDIC_MONTHS:
        missing = langs - set(data.get(month, {}).keys())
        if missing:
            print(f"FAIL: {month} missing languages: {missing}")
            ok = False
    for suffix in ("Purnima", "Amavasya"):
        missing = langs - set(data.get("_suffixes", {}).get(suffix, {}).keys())
        if missing:
            print(f"FAIL: suffix {suffix} missing languages: {missing}")
            ok = False
    print(("PASS" if ok else "FAIL") + ": translation file has all 13 languages for all 12 months + 2 suffixes")
    print(f'  Sample: Chaitra in Tamil = "{data["Chaitra"]["ta"]}"')
    return ok


def check_sample_metadata() -> bool:
    try:
        cycle_id = "Chaitra_2027"
        start, mid, end = lc.get_cycle_dates(cycle_id)
        display_names = lc.translated_cycle_display_name(cycle_id)
        folder_name = lc.archive_folder_name(cycle_id)
        metadata = {
            "cycle_id": cycle_id,
            "display_names": display_names,
            "start_date": start.isoformat(),
            "start_phase": "Amavasya",
            "mid_date": mid.isoformat(),
            "mid_phase": "Purnima",
            "end_date": end.isoformat(),
            "end_phase": "Amavasya",
            "archive_folder_name": folder_name,
        }
        import json
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        ok = all(k in metadata for k in ("cycle_id", "display_names", "start_date", "mid_date", "end_date"))
    except Exception as e:
        print(f"FAIL: could not generate sample cycle metadata: {e}")
        ok = False
    print(("PASS" if ok else "FAIL") + ": sample cycle metadata generates correctly")
    return ok


def main() -> None:
    print("=" * 70)
    print("Lunar cycle table: April 2026 - April 2027")
    print("=" * 70)
    events = print_table()

    print()
    print("=" * 70)
    print("Consistency checks")
    print("=" * 70)
    results = [
        check_alternation(events),
        check_no_overlap(events),
        check_unique_cycle_ids(events),
        check_translations(),
    ]

    print()
    print("=" * 70)
    print("Sample cycle_metadata.json (Chaitra_2027)")
    print("=" * 70)
    results.append(check_sample_metadata())

    print()
    print("=" * 70)
    all_pass = all(results)
    print("OVERALL:", "ALL CHECKS PASSED" if all_pass else "SOME CHECKS FAILED")
    print("=" * 70)
    print()
    print("Cross-check manually against drikpanchang.com or a similar panchang for a few of the")
    print("dates above, especially the Chaitra_2027 Amavasya (expected around 2027-04-06/07, per")
    print("the Founder's own stated Chaitra Navratri boundary) -- this script cannot reach the")
    print("internet to verify that automatically.")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
