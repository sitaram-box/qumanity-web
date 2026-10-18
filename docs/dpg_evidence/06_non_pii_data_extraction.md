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

Checked against `app.py` and `elemental_core.py` on 17 October 2026. Every endpoint below is public: none needs sign-in.

**Demographics: `GET /api/location/stats/<level>/<location_id>` (JSON) and `GET /api/location/stats/<level>/<location_id>.csv` (CSV)**

`level` is one of continent, country, zone, state, district, tehsil or village. An optional `?basis=birth|present` chooses birth or present location (default present). The JSON response:

| Field | Content |
|---|---|
| `level`, `location_id`, `basis` | Echo of the request |
| `total_humans` | Number of real registered members in the location (demo and retired accounts are excluded) |
| `gender` | Counts for `male`, `female` and `both` (the app's third category) |
| `age_bands` | Four bands with code, label and count: 0–24, 25–49, 50–75, 76+ |
| `elements` | Counts by sun-sign element (Fire, Earth, Air, Water) |
| `signs` | Counts by sun sign, Aries to Pisces |
| `karma_total` | Total karma of the location's members (left out when there are one to four members) |
| `qoins_wallet_balance` | Total Qoin balance of the members' own wallets (left out when there are one to four members) |

**Small-count suppression.** Every person count (`total_humans`, `gender`, `age_bands`, `elements`, `signs`) from 1 to 4 is returned as the string `"<5"` instead of a number, in both JSON and CSV. A true 0 stays 0. Karma and Qoin totals are sums of members' own karma and wallets. For a location with one to four members they would reveal those members' own figures, so both fields are left out of the response entirely (`_location_stats_payload` in `app.py`, since 17 October 2026).

The older country and continent routes (`/api/country/stats/<id>`, `/api/continent/stats/<id>`) return the same demographic fields by birth location, without suppression (6.5 #5). Since 17 October 2026, the same suppression applies to `/api/earth/stats`, `/api/subcontinent/stats`, `/api/location/elements/<id>` and `/api/global/elements` (counts, with the percentage nulled whenever its count is suppressed) and `/api/scoreboard/india`.

Note that `total_humans` on the older country and continent routes counts members **born** in the location, while on `/api/location/stats` (default `basis=present`) it counts members who **live** there. The two are not comparable, and renaming the older field is planned (Document 10, row 26).

The location's karma and Qoin balance are also available on their own at `GET /api/karma/collective/<level>/<location_id>` and `GET /api/wallet/balance/<location_type>/<location_id>`.

**Council addresses as a count signal.** Added 18 October 2026. A location receives a permanent council address (`<level>-<location_id>@qumanity.in`) once its count of real members reaches its level's threshold: 5 for a village, 10 for a tehsil, rising tenfold at each level above to 10,000,000 for Earth. The address is created when `elemental_core.recompute_location_elements()` next runs, not the moment the count is reached, and today only the manual backfill script calls that function, so an address can lag the count. An address existing therefore says that the location had at least that many real members when its count was last recomputed. It is not a public export: a signed-in member sees the addresses for their own location chain on its Q-Punch panel (`GET /api/qpunch/<level>`), and a member who has activated Qmail can learn whether a given village has an address by trying to send to it, though a village below threshold currently produces the same error as a mistyped address (`404`, "That Qmail address isn't recognized"), so the probe is not a reliable way to distinguish 'no address yet' from 'wrong address'. For a village, the threshold equals the suppression threshold, so an address reveals no more than the public statistics already show (a number rather than `"<5"`). The one difference is permanence: an address is never removed, so if a village later falls back to one to four members, its address still shows that it once had at least five while its statistics read `"<5"`. Levels above village have thresholds of 10 or more, above the suppression threshold.

**No personal data**

The query behind the demographics endpoint reads only gender, date of birth, sun sign and element. It returns counts, never rows: no user IDs, names, contact details, birth dates or per-user records. Date of birth is used only to place each member in an age band.

**Sample JSON response** (structure as returned, for a location with at least five members; the numbers and the location ID are illustrative):

```json
{
  "level": "village",
  "location_id": "XX.XX.0.0.0X",
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

For a location with one to four members, such as a small village, every count reads `"<5"` and `karma_total` and `qoins_wallet_balance` are left out.

## 6.3 CSV export

**Endpoint:** `GET /api/location/stats/<level>/<location_id>.csv`, with the same `?basis=` option. It returns `text/csv` with a download filename such as `qumanity_stats_village_CS.DL.3.4.1A.csv`.

**Columns:** two columns, `metric,value`, one row per aggregate. This one layout works for every level. It holds every field of the JSON response, with the same small-count suppression.

```
metric,value
level,village
location_id,XX.XX.0.0.0X
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

With one to four members, the `karma_total` and `qoins_wallet_balance` rows are left out.

`qoins_wallet_balance` is the total of the members' own wallets. A "Qoins in circulation" figure across all member wallets would need a new aggregate; the code doesn't compute one today.

**Included:** aggregate counts and totals for one location.
**Excluded:** per-user rows, PII and contact details (see 6.4).
**Sign-in:** not required.

## 6.4 What is excluded by design

No public export, in JSON or CSV, ever includes:
- User IDs (internal, Private ID or Account ID)
- Names
- Email addresses
- Phone numbers
- Birth date and time
- Individual member locations
- Any per-user row
- Any message content: Qmail messages, attachments, drafts, messages to a council address, or the council action log. These are private communications between members, or between a member and their council, and no route exports them, publicly or to the Admin. Leaving them out keeps the public data surface to aggregates only, so nothing a member writes privately can reach a public dataset.

*Correction, 18 October 2026: this section previously said that no export ever includes user IDs, names or per-user rows. Since commit cf610f5 (18 October 2026), the Admin member export does (below), so the statement now applies to public exports.*

**The one export that contains personal data.** `GET /api/admin/users/export` (JSON) and `GET /api/admin/users/export.csv` return one row per real member, with their Private ID, Account ID, name and location. It is Admin only, every use is logged to `admin_export_log`, and it is not part of the non-PII mechanism this document describes. Document 07, section 7.3, gives its full treatment.

Note: the routes `/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>` and the `/kundali/<id>` page are not part of the non-PII surface and must not be cited as evidence of it. Since 14 October 2026 they require sign-in and return a chart only to the member it belongs to (Document 07, action 8). The stats endpoints above are aggregate only.

## 6.5 Gaps and actions

| # | Action | Status |
|---|---|---|
| 1 | Add the `.csv` variant of `/api/location/stats/<level>/<location_id>`, with karma and Qoin balance included | Done, 14 October 2026 |
| 2 | Suppress small counts in both JSON and CSV (Document 07, action 4) | Done, 14 October 2026: counts from 1 to 4 are shown as `"<5"` |
| 3 | Document every public stats endpoint in `docs/API.md` (Document 05) | Done, 14 October 2026 |
| 4 | Check one live sample URL on qumanity.in | Done: verified live by the founder |
| 5 | Apply the same suppression to `/api/country/stats/<id>` and `/api/continent/stats/<id>` | Pending (code) |
| 6 | Apply suppression to the subcontinent, location-elements, global-elements, India-scoreboard and Earth routes, and to the members' karma and Qoin totals for small groups | Done, 17 October 2026 (265a2f4, 57bafba) |

## 6.6 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Does the project allow non-PII data export? | Yes |
| Format | JSON and CSV |
| Endpoint | `/api/location/stats/<level>/<location_id>` (JSON) and `/api/location/stats/<level>/<location_id>.csv` (CSV) |
| Sample URL | https://qumanity.in/api/location/stats/village/CS.DL.3.4.1A (the pilot village, Rohini Sector 24) |
