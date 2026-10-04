# Lunar-cycle archival system — complete design (2026-10-05)

Single source of truth for the whole system, as specified by the Founder. This document describes
the FULL design across all 5 phases; only **Phase 1** (lunar detection + Vedic naming) is built as
of this writing — see `docs/phase_build_plan.md` for what's built vs. still to come.

## Context

Qumanity runs on Flask, deployed on Railway (`https://web-production-126c3f.up.railway.app`), with
a single SQLite database (`/data/qumanity_prototype.db`) and a nested folder tree at
`/data/0_Earth` (Asia/India/Zone/State/District/Tehsil/Village). Users are identified by a 9-digit
Private ID + 5-digit PIN. Locations have 8 levels: Earth → Continent → Country → Zone → State →
District → Tehsil → Village.

## Core concept

There is only ONE database — the "Village DB" — holding all raw user activity. Higher levels
(Tehsil, District, ... Earth) are **aggregation views** that temporarily hold data passed up from
the level below, one level per lunar cycle, until it finally lands in `0_Earth` archive folders.

## The 8 transfers (every Krishna Paksha — the ~15-day waning phase after Purnima)

| Day | Transfer |
|---|---|
| 1-2 | Village → Tehsil |
| 3-4 | Tehsil → District |
| 5-6 | District → State |
| 7-8 | State → Zone |
| 9-10 | Zone → Country |
| 11-12 | Country → Continent |
| 13-14 | Continent → Earth |
| 15 | Earth → 0_Earth archive |

## What each level holds (steady state — 8 cycles in flight at once)

| Level | Holds data from cycle |
|---|---|
| Village | N (current, being written to) |
| Tehsil | N-1 |
| District | N-2 |
| State | N-3 |
| Zone | N-4 |
| Country | N-5 |
| Continent | N-6 |
| Earth | N-7 |
| 0_Earth archive | N-8 (fully archived) |

## What gets transferred

Moving from level L to L+1 carries: (a) raw records (posts, votes, comments, wallet transactions,
karma entries, chat messages, user-level data) and (b) aggregated summaries (counts, top
contributors, statistics). **Higher levels never display the transferred raw data publicly** — it
sits in the backend for council members to analyze; only the aggregate is shown publicly.

## Bootstrap phase (Year 1)

Year 1 runs Chaitra Navratri to Chaitra Navratri (the Amavasya around early April). During Year 1,
all 12 lunar cycles accumulate data at Village level — **no pipeline transfers happen**. The
pipeline activates at Year 2's first Amavasya.

## Pipeline timeline after activation (Year 2 onward)

Once active: Cycle 1's data reaches the `0_Earth` archive after ~9 lunar cycles (~9 months).
Cycles 1-9 complete the pipeline during Year 2. Cycles 10, 11, 12 reach Earth level by Year 2's
end, then complete to `0_Earth` during Year 3's Krishna Paksha (day 13-14).

## Safety rule

At all times the DB keeps the current cycle (N, live, being written to) and the previous cycle
(N-1, live, readable for user continuity). **Only cycles N-2 and older are ever subjects of the
pipeline.**

## Council members — a separate track

Council member records do **not** follow the lunar pipeline. They archive at their own term end
(their zodiac-month cycle ending, one year later). Election data follows electoral timing, not
lunar timing.

## Vedic naming, with multi-language support

Every lunar cycle gets a Vedic month name (Chaitra, Vaishakha, Jyeshtha, Ashadha, Shravana,
Bhadrapada, Ashwin, Kartik, Margashirsha, Pausha, Magha, Phalguna), translated into all 13
supported languages (English, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi,
Gujarati, Punjabi, Urdu, Odia, Assamese) — see `translations/lunar_months.json`.

**Cycle ID** (filesystem-safe, always English): `{Month}_{Year}`, e.g. `Chaitra_2027`.

**Archive folder name**: `{StartPurnima}-to-{EndAmavasya}_{Year}`, e.g.
`Chaitra_Purnima-to-Vaishakha_Amavasya_2027`.

**Display names** (translated, stored in `cycle_metadata.json`): e.g.
`"en": "Chaitra Purnima to Vaishakha Amavasya 2027"`,
`"hi": "चैत्र पूर्णिमा से वैशाख अमावस्या 2027"`, one entry per supported language.

## Filesystem path (always English)

```
/0_Earth/Asia/India/Central State/Delhi/North West Delhi/Bawana/Rohini Sector-24/
    archives/
        Chaitra_Purnima-to-Vaishakha_Amavasya_2027/
            cycle_metadata.json
            posts.json
            votes.json
            comments.json
            wallet_transactions.json
            karma_entries.json
            chat_messages.json
```

## Cycle metadata structure

```json
{
  "cycle_id": "Chaitra_2027",
  "display_names": {
    "en": "Chaitra Purnima to Vaishakha Amavasya 2027",
    "hi": "चैत्र पूर्णिमा से वैशाख अमावस्या 2027",
    "...": "one entry per supported language"
  },
  "start_date": "ISO timestamp of start Amavasya",
  "start_phase": "Amavasya",
  "start_vedic_name": "Phalguna_Amavasya",
  "mid_date": "ISO timestamp of Purnima",
  "mid_phase": "Purnima",
  "mid_vedic_name": "Chaitra_Purnima",
  "end_date": "ISO timestamp of next Amavasya",
  "end_phase": "Amavasya",
  "end_vedic_name": "Chaitra_Amavasya",
  "archived_at": "ISO timestamp",
  "archive_level": "Village",
  "records_archived": {"posts": 1234, "votes": 5678}
}
```

## Important rules (every phase)

1. Never modify the existing DB schema in Phase 1 — detection only.
2. Never wire the pipeline into production before Phase 3/5 build it.
3. Never delete existing data.
4. Use `pyswisseph` (already a dependency, same library the kundali system uses).
5. All times are IST (+05:30) unless stated otherwise.
6. Vedic months follow the standard North Indian tradition (Chandra Maas named from its own
   Purnima) — see `docs/phase_build_plan.md` for the exact reconciliation used in code between
   "name the cycle from its Amavasya" and "name the month from its Purnima."
