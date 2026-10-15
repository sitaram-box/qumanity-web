# Qumanity: Non-PII Data Extraction

**DPG Standard Indicator 6: Mechanism for Extracting Data and Content**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

## Contents

- [6.1 What the DPG Standard requires](#61-what-the-dpg-standard-requires)
- [6.2 What exists today](#62-what-exists-today)
- [6.3 Proposed CSV export](#63-proposed-csv-export)
- [6.4 What is excluded by design](#64-what-is-excluded-by-design)
- [6.5 Gaps and actions](#65-gaps-and-actions)
- [6.6 Evidence for the application form](#66-evidence-for-the-application-form)

## 6.1 What the DPG Standard requires

If the project collects or stores non-personally identifiable data, there must be a way to extract or import that data in a non-proprietary format such as CSV, JSON or XML.

## 6.2 What exists today

Checked against `app.py` and `elemental_core.py` on 14 October 2026. Every endpoint below is public: none needs sign-in.

**Demographics: `GET /api/location/stats/<level>/<location_id>` (JSON) and `GET /api/location/stats/<level>/<location_id>.csv` (CSV)**

`level` is one of continent, country, zone, state, district, tehsil or village. An optional `?basis=birth|present` chooses birth or present location (default present). The JSON response:

| Field | Content |
|---|---|
| `level`, `location_id`, `basis` | Echo of the request |
| `total_humans` | Number of registered members in the location |
| `gender` | Counts for `male`, `female` and `both` (the app's third category) |
| `age_bands` | Four bands with code, label and count: 0–24, 25–49, 50–75, 76+ |
| `elements` | Counts by sun-sign element (Fire, Earth, Air, Water) |
| `signs` | Counts by sun sign, Aries to Pisces |
| `karma_total` | The location's collective karma score |
| `qoins_wallet_balance` | The Qoin balance of the location's wallet |

**Small-count suppression.** Every person count (`total_humans`, `gender`, `age_bands`, `elements`, `signs`) from 1 to 4 is returned as the string `"<5"` instead of a number, in both JSON and CSV. A true 0 stays 0. Karma and Qoin totals are sums, not person counts, so they are not suppressed (`_suppress_small_count` in `app.py`).

The older Earth, country and continent routes (`/api/earth/stats`, `/api/country/stats/<id>`, `/api/continent/stats/<id>`) return the same demographic fields by birth location, without suppression (6.5 #5).

The location's karma and Qoin balance are also available on their own at `GET /api/karma/collective/<level>/<location_id>` and `GET /api/wallet/balance/<location_type>/<location_id>`.

**No personal data**

The query behind the demographics endpoint reads only gender, date of birth, sun sign and element. It returns counts, never rows: no user IDs, names, contact details, birth dates or per-user records. Date of birth is used only to place each member in an age band.

**Sample JSON response** (structure as returned; numbers illustrative):

```json
{
  "level": "village",
  "location_id": "CS.DL.3.4.1A",
  "basis": "present",
  "total_humans": 1247,
  "gender": {"male": 620, "female": 623, "both": "<5"},
  "age_bands": [
    {"code": "A1", "label": "0–24", "count": 312},
    {"code": "A2", "label": "25–49", "count": 435},
    {"code": "A3", "label": "50–75", "count": 380},
    {"code": "A4", "label": "76+", "count": 120}
  ],
  "elements": {"Fire": 310, "Earth": 315, "Air": 300, "Water": 322},
  "signs": {"Aries": 102, "Taurus": 108, "...": 0},
  "karma_total": 12450,
  "qoins_wallet_balance": 12500
}
```

## 6.3 CSV export

**Endpoint:** `GET /api/location/stats/<level>/<location_id>.csv`, with the same `?basis=` option. It returns `text/csv` with a download filename such as `qumanity_stats_village_CS.DL.3.4.1A.csv`.

**Columns:** two columns, `metric,value`, one row per aggregate. This one layout works for every level. It holds every field of the JSON response, with the same small-count suppression.

```
metric,value
level,village
location_id,CS.DL.3.4.1A
basis,present
total_members,1247
gender.male,620
gender.female,623
gender.both,<5
age.0-24,312
age.25-49,435
age.50-75,380
age.76+,120
element.fire,310
element.earth,315
element.air,300
element.water,322
sun_sign.Aries,102
sun_sign.Taurus,108
...
karma_total,12450
qoins_wallet_balance,12500
```

`qoins_wallet_balance` is the location wallet's balance. A "Qoins in circulation" figure across all member wallets would need a new aggregate; the code doesn't compute one today.

**Included:** aggregate counts and totals for one location.
**Excluded:** per-user rows, PII and contact details (see 6.4).
**Sign-in:** not required.

## 6.4 What is excluded by design

No export, in JSON or CSV, ever includes:
- User IDs (internal, Private ID or Account ID)
- Names
- Email addresses
- Phone numbers
- Birth date and time
- Individual member locations
- Any per-user row

Note: the routes `/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>` and the `/kundali/<id>` page are not part of the non-PII surface and must not be cited as evidence of it. Since 14 October 2026 they require sign-in and return a chart only to the member it belongs to (Document 07, action 8). The stats endpoints above are aggregate only.

## 6.5 Gaps and actions

| # | Action | Status |
|---|---|---|
| 1 | Add the `.csv` variant of `/api/location/stats/<level>/<location_id>`, with karma and Qoin balance included | Done, 14 October 2026 |
| 2 | Suppress small counts in both JSON and CSV (Document 07, action 4) | Done, 14 October 2026: counts from 1 to 4 are shown as `"<5"` |
| 3 | Document every public stats endpoint in `docs/API.md` (Document 05) | Done, 14 October 2026 |
| 4 | Check one live sample URL on qumanity.in | Done: verified live by the founder |
| 5 | Apply the same suppression to `/api/earth/stats`, `/api/country/stats/<id>` and `/api/continent/stats/<id>` | Pending (code) |

## 6.6 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Does the project allow non-PII data export? | Yes |
| Format | JSON and CSV |
| Endpoint | `/api/location/stats/<level>/<location_id>` (JSON) and `/api/location/stats/<level>/<location_id>.csv` (CSV) |
| Sample URL | https://qumanity.in/api/location/stats/village/CS.DL.3.4.1A (the pilot village, Rohini Sector 24) |
