# Qumanity architecture

This describes the qumanity-web repository as of 11 October 2026, updated 14 October 2026 and 17 October 2026. It is written for a developer who has not seen the code before. For setup see `docs/INSTALL.md`, for the routes see `docs/API.md`, and for the tables see `docs/DATA_MODEL.md`.

## Components

```
  Browser (Jinja pages + vanilla JS,            Phone app (qumanity-app,
  Leaflet maps, three.js globe)                 React Native / Expo)
        |  cookie session                              |  Authorization: Bearer <token>
        +--------------------+   HTTPS   +-------------+
                             v           v
                 Flask application (app.py, ~3,570 lines)
                 - page routes (/, /register, /dashboard, ...)
                 - JSON API (/api/..., about 150 routes)
                 - business logic in the *_core.py modules
                             |
                             v
                 SQLite database (QM_DB_PATH)
                 64 application tables, created and migrated on boot
                             |
         +-------------------+---------------------+
         v                                         v
  APScheduler jobs (in-process)            0_Earth folder archive (QM_EARTH_ROOT)
  - 00:00 daily: DB -> folder sync          - one folder per location, Earth -> Village
  - 00:00 IST daily: lunar-cycle pipeline   - per-cycle archives written by archive_writer.py
    tick (aggregate, transfer, archive)     - Qumanity_Master.json location source
  - 1st of month 02:00 IST: Post Testing
    cycle, monthly post job
  - Monday 02:00 IST: Post Testing cycle,
    weekly vote job
```

- **One backend.** The website and the phone app call the same `/api` routes. The app signs in with a bearer token signed by the server (`itsdangerous`); the website uses Flask's signed session cookie. A valid token is treated exactly like a session.
- **Server-rendered pages, light client.** Pages are Jinja templates with plain JavaScript in `static/js/`. There is no front-end framework or build step.
- **Astronomy is local.** Sun sign, nakshatra, lunar phase and sunrise are computed in-process with pyswisseph's built-in Moshier ephemeris, so no data files or outside services are needed.
- **Scheduled work runs inside the web process** (APScheduler `BackgroundScheduler`). Set `QM_DISABLE_SCHEDULER` to switch off the lunar pipeline job, for example in tests.
- **Start-up.** On import, `app.py` runs `ensure_database_ready()`, which applies `db/schema.sql`, every module's own tables and `migrations/` through `tools/run_migrations.py`. It then starts all four scheduler jobs (daily folder sync, daily lunar pipeline tick, and the Post Testing cycle's monthly post job and weekly vote job). Production runs `gunicorn --workers 1 app:app` (`Procfile`). The single worker matters because the scheduler lives in-process.

## Module map

Every Python module at the repository root.

| Module | Purpose |
|---|---|
| `app.py` | Flask app: configuration, sign-in, every page and `/api` route, start-up and scheduler wiring |
| `db.py` | SQLite connection helper (`get_db`) |
| `id_generator.py` | Generates the 9-digit Private ID and Account IDs; age bands |
| `zodiac_core.py` | Sun sign, nakshatra and Vedic birth chart from birth date, time and place (pyswisseph, IANA time zones) |
| `kundali_analyser.py` | Moon-based analysis of a birth chart |
| `elemental_core.py` | Personal elemental balance, and location-level demographics (gender, age band, element, sign) |
| `lunar_core.py` | Lunar phase and eclipse calculations |
| `lunar_calendar.py` | Detects lunar cycles and names them (Chandra Maas) |
| `timebox_core.py` | Local time, sunrise and sunset, panchang for a member's country |
| `board_core.py` | Collective Boards: posts voted up from Village to Earth; village sub-groups and group chat |
| `social_core.py` | Personal groups (Family, Friends, Business, Custom), message requests, private chats, identity masking |
| `reactions_core.py` | Agree / Disagree / Read reactions on group messages |
| `reports_core.py` | Citizen Reports: filed to the council, 10-day deadline, escalation, anonymity |
| `announcements_core.py` | One-way council announcements to a location |
| `notify_core.py` | Unread-notification counts |
| `karma_core.py` | Individual and collective karma scores |
| `qoin_core.py` | Qoin denominations, currency reference values, post rewards and post prices (pure functions) |
| `wallet_core.py` | Qoin wallets for each member and each location, transactions, weekly history |
| `election_core.py` | Village Council elections by zodiac sign (pilot village), Lok Sabha cycle settings |
| `perception_core.py` | Yearly Pro/Anti sentiment voting on countries and zones |
| `visibility_core.py` | When election-history and perception results may be shown |
| `review_core.py` | App tour status and the one-time member rating |
| `logout_review_core.py` | Optional rating on logout, once per lunar cycle |
| `recovery_core.py` | Forgotten PIN (one-time code) and forgotten Private ID (admin-reviewed) |
| `founder_core.py` | The Founder's Message on the homepage, in English only |
| `cycle_middleware.py` | Stamps every activity row with the current lunar `cycle_id` |
| `pipeline_core.py` | Aggregates a cycle's activity and transfers it up one level (Village to Earth) |
| `pipeline_scheduler.py` | Daily job that runs the pipeline on the lunar schedule, with a Year-1 bootstrap gate |
| `test_cycle_scheduler.py` | Monthly/weekly jobs that run the Post Testing cycle: one test post per demo voter per month, one top-up voting round per week |
| `archive_writer.py` | Writes a finished cycle's Earth-level data to the `0_Earth` folder tree, with checksums |
| `folder_connector.py` | Creates a member's folder in the `0_Earth` location tree on registration |
| `folder_sync.py` | Daily mirror of location statistics from the database to the folder tree |

Supporting folders: `db/` (base schema and first-run seed), `migrations/` (001–014), `tools/` (migration runner and verification scripts), `scripts/` (one-off data import and build scripts), `templates/`, `static/` (CSS, JS, map data, locales, images), `translations/`.

## Data model summary

67 tables (68 including SQLite's internal `sqlite_sequence`). Full list in `docs/DATA_MODEL.md`.

| Subsystem | Tables | What they hold |
|---|---|---|
| Identity and sign-in | 7 | Members, Account IDs, onboarding, OTP codes, ID-recovery requests and reveals, profile-change requests |
| Astrology | 5 | Zodiac signs and nakshatras (reference data), each member's chart and elemental profile, location element counts |
| Location | 1 | Indian villages (the rest of the hierarchy lives in JSON files and in each member's location JSON) |
| Collective Boards and groups | 7 | Posts, votes, comments, sub-groups, members and chat, volunteers |
| Personal social | 7 | Personal groups and members, group messages, private chats and messages, people requests, read state |
| Reactions and ratings | 4 | Message reactions, business ratings, app reviews, logout reviews |
| Karma | 3 | Karma entries, collective karma and its log |
| Qoins | 4 | Wallets, wallet transactions, physical denominated Qoins, recognition stars |
| Referrals | 2 | Referrers and referrer applications |
| Elections and councils | 7 | Election cycles, candidates, votes, village councils, cycle configuration, election history |
| Perception | 4 | Country and zone sentiment votes and frozen yearly totals |
| Citizen Reports | 2 | Reports and their updates |
| Announcements and notices | 4 | Announcements, reads, admin notifications, the Founder's Message |
| Lunar-cycle pipeline | 6 | Cycle state, lunar events, pipeline bootstrap and state, level holdings, transfer log |
| Post Testing cycle | 1 | Feature-scoped testing windows (start/end date, status, demo user count, vote distribution) |
| System | 3 | Applied migrations, system settings, account-ID requests |
