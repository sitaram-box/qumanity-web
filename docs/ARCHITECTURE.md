# Qumanity architecture

This describes the qumanity-web repository as of 11 October 2026, updated 14 October 2026, 17 October 2026, 18 October 2026 (commit c09b91f) and 25 October 2026 (profile pictures, the Avatar Sweep, explicit Family Tree growth, the Family Group naming code, and the Middle Name field — migrations 028/029, neither of which added a table, so the table counts below are unchanged). It is written for a developer who has not seen the code before. For setup see `docs/INSTALL.md`, for the routes see `docs/API.md`, and for the tables see `docs/DATA_MODEL.md`.

## Components

```
  Browser (Jinja pages + vanilla JS,            Phone app (qumanity-app,
  Leaflet maps, three.js globe)                 React Native / Expo)
        |  cookie session                              |  Authorization: Bearer <token>
        +--------------------+   HTTPS   +-------------+
                             v           v
                 Flask application (app.py, ~4,770 lines)
                 - page routes (/, /register, /dashboard, /qmail, ...)
                 - JSON API (/api/..., 178 routes)
                 - business logic in the *_core.py modules
                             |
                             v
                 SQLite database (QM_DB_PATH)
                 74 application tables created and migrated on
                 boot, 2 more created on first use
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
| `notify_core.py` | Unread-notification counts, including replies to a member's Admin query or council message |
| `karma_core.py` | Individual and collective karma scores |
| `qoin_core.py` | Qoin denominations, currency reference values, post rewards and post prices (pure functions) |
| `wallet_core.py` | Qoin wallets for each member and each location, transactions, weekly history |
| `election_core.py` | Village Council elections by zodiac sign (pilot village), Lok Sabha cycle settings |
| `perception_core.py` | Yearly Pro/Anti sentiment voting on countries and zones |
| `visibility_core.py` | When election-history and perception results may be shown |
| `review_core.py` | App tour status and the one-time member rating |
| `logout_review_core.py` | Optional rating on logout, once per lunar cycle |
| `recovery_core.py` | Forgotten PIN (one-time code) and forgotten Private ID (admin-reviewed) |
| `qmail_core.py` | Qmail, internal member-to-member messaging addressed `<username>-<account_id>@qumanity.in` (no internet email is sent or received); Q-Punch council addresses and the village-only reachability gate; attachments (2 MB, file-type allowlist) and drafts. See `docs/QMAIL.md` |
| `admin_queries_core.py` | Admin Panel member queries: general questions with no location and no council escalation, read and answered by the Admin. No route lets a member submit one yet; the member who asked can read the replies (`/api/queries/mine/<id>`). See `docs/ADMIN_PANEL.md` |
| `email_core.py` | The optional registration notice to the Admin over SMTP (standard-library `smtplib`, STARTTLS), with a masked Private ID. Does nothing unless `SMTP_HOST` and `QM_ADMIN_EMAIL` are set. See `docs/EMAIL.md` |
| `founder_core.py` | The Founder's Message on the homepage, in English only |
| `cycle_middleware.py` | Stamps every activity row with the current lunar `cycle_id` |
| `pipeline_core.py` | Aggregates a cycle's activity and transfers it up one level (Village to Earth) |
| `pipeline_scheduler.py` | Daily job that runs the pipeline on the lunar schedule, with a Year-1 bootstrap gate |
| `test_cycle_scheduler.py` | Monthly/weekly jobs that run the Post Testing cycle: one test post per demo voter per month, one top-up voting round per week |
| `archive_writer.py` | Writes a finished cycle's Earth-level data to the `0_Earth` folder tree, with checksums |
| `folder_connector.py` | Creates a member's folder in the `0_Earth` location tree on registration |
| `folder_sync.py` | Daily mirror of location statistics from the database to the folder tree |
| `family_core.py` | The Family Tree: Nuclear Family Node units (a unit is a married couple, not a generic container), explicit tree-growth routes (add a unit's missing parents, add a child or sibling-in-law placeholder), and the Family Group naming code (`_name_code`/`_group_name_from_couple`) |
| `profile_picture_core.py` | Profile pictures: Pillow processing (EXIF strip, center-crop, 256×256 JPEG), upload validation, and `hide_identity`-aware serving |

Supporting folders: `db/` (base schema and first-run seed), `migrations/` (001–003 and 007–029; 004–006 are unused), `tools/` (migration runner and verification scripts), `scripts/` (one-off data import and build scripts), `templates/`, `static/` (CSS, JS, map data, locales, images), `translations/`.

## The `/qmail` page

Added 18 October 2026. `/qmail` is a page route, not an `/api` route, so it does not appear in `docs/API.md`. It requires sign-in, and it sends a member who has not activated Qmail back to `/dashboard`, where activation happens.

| File | Role |
|---|---|
| `templates/qmail.html` | The page: inbox, sent, drafts and the compose form |
| `static/js/qmail.js` | The page's script: lists, reading pane, compose with attachment, draft save on close, and the replies to a member's own council message or Admin query (opened from Sent, or from a notification as `/qmail#council-<id>` or `/qmail#query-<id>`) |
| `static/js/qmail_format.js` | The shared renderer for message text (`**bold**`, `_italic_`, `[text](url)`). It builds elements with `createElement` and `textContent` and never builds HTML from message text. Loaded by both `templates/qmail.html` and `templates/dashboard.html` (the Admin Panel's council message view), before each page's own script |
| `static/css/qmail.css` | The page's own stylesheet. The page does not load `dashboard.css`; two small utility classes are copied into this file instead |

The renderer was extracted from `static/js/dashboard.js` into `qmail_format.js` at commit e99eced and rewritten, not moved: the old version built its elements through a helper local to `dashboard.js`, and the new one calls `document.createElement` directly. Its output is the same, but its code is new. It has no automated regression test (Document 09, 9.6 row 9).

## Avatars (`static/js/avatar.js`)

Added 25 October 2026. `window.QMAvatar.render(user, size)` is the one avatar renderer every surface calls — Group Chat, Qmail, the Collective Board, the Admin Panel's query replies, and the Family Tree. It takes `{name, gender, profile_picture_url, hide_identity?, account_id?}` and returns a real `HTMLElement` (an `<img>`, or a colored-initials `<div>` fallback), so it works in plain DOM and, via a `<foreignObject>`, inside the Family Tree's SVG canvas. Loaded on `dashboard.html` and `qmail.html`, before the page's own script. Pictures themselves are served from `GET /api/users/<id>/profile-picture` (`profile_picture_core.py`) — see `docs/HANDOVER.md` §4.14 for the full backend/frontend wiring and its one known gap (the Admin Panel's combined ticket feed isn't wired up yet).

## Data model summary

76 tables in a running database: 74 created on boot, and 2 that their module creates on first use (`chat_read_state` and `election_cycle_config`), plus SQLite's internal `sqlite_sequence`. Full list in `docs/DATA_MODEL.md`.

*Corrected 18 October 2026: this section previously said 67 tables, and the diagram above said 64. Both were checked by building a fresh database: one built from commit c641f2c had 64 tables on boot. The 67 also counted the 2 tables created on first use and a legacy `election_history` table that no current code creates. Migrations 019–024 added 10 tables, so the totals are now 74 on boot and 76 in a running database.*

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
| Elections and councils | 6 | Election cycles, candidates, votes, village councils, cycle configuration, election history (`election_history_entries`; the legacy `election_history` table is no longer created) |
| Perception | 4 | Country and zone sentiment votes and frozen yearly totals |
| Citizen Reports | 2 | Reports and their updates |
| Announcements and notices | 4 | Announcements, reads, admin notifications, the Founder's Message |
| Lunar-cycle pipeline | 6 | Cycle state, lunar events, pipeline bootstrap and state, level holdings, transfer log |
| Post Testing cycle | 1 | Feature-scoped testing windows (start/end date, status, demo user count, vote distribution) |
| Qmail | 4 | Addresses (one row per Account ID a member has had), messages, attachments, drafts |
| Q-Punch council queue | 3 | Council addresses, messages sent to them, and the log of every view, reply and close |
| Admin Panel and export | 3 | Member queries and their replies, the Admin member-export log |
| System | 3 | Applied migrations, system settings, account-ID requests |
