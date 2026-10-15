# Qumanity: Platform Independence

**DPG Standard Indicator 4: Platform Independence**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

## Contents

- [4.1 What the DPG Standard requires](#41-what-the-dpg-standard-requires)
- [4.2 Statement](#42-statement)
- [4.3 Technology stack](#43-technology-stack)
- [4.4 Hosting and delivery](#44-hosting-and-delivery)
- [4.5 Removed proprietary dependencies](#45-removed-proprietary-dependencies)
- [4.6 Remaining actions](#46-remaining-actions)
- [4.7 Evidence for the application form](#47-evidence-for-the-application-form)

## 4.1 What the DPG Standard requires

The project must not have a mandatory dependency on a closed or proprietary component. If it uses one, the project must show that an open alternative can replace it without significant change to the core.

## 4.2 Statement

Qumanity is fully open-source from top to bottom. Every component in the technology stack is licensed under an OSI-approved license. There are no closed or proprietary dependencies.

## 4.3 Technology stack

Read from `requirements.txt`, `.python-version` and `mobile/package.json` on 11 October 2026. Licences are listed in Document 02, section 2.6.

| Layer | Components |
|---|---|
| Backend | Python 3.12, Flask, Werkzeug, Jinja2, gunicorn |
| Database | SQLite (PostgreSQL-compatible) |
| Scheduler | APScheduler |
| Astronomy | pyswisseph (built-in Moshier ephemeris, no data files) |
| Geo/timezone | timezonefinder, pycountry |
| Maps | Leaflet, three.js, earcut, Natural Earth data |
| Fonts | Fraunces, Inter (SIL OFL) |
| Phone app | React Native, Expo, react-native-* modules |
| Spreadsheet export | openpyxl |
| Payments | None. Qoins are earned through civic activity and carry a rupee reference value for user clarity. Qoins are internal to the platform. |

## 4.4 Hosting and delivery

None of the following is required by the software. Each can be swapped without code changes to the core.

| Item | Current use | Open alternative |
|---|---|---|
| Railway (hosting) | Runs qumanity.in. The app starts from a plain `Procfile` (`gunicorn app:app`) with no Railway-specific code. Railway is only detected to refuse an insecure default secret key. | Any Linux server, container host or PaaS that runs Python |
| unpkg.com (CDN) | Serves Leaflet 1.9.4, three.js 0.160.0 and earcut 2.2.4 to the browser | Self-host the same files under `static/` |
| Google Fonts | Serves Fraunces and Inter (SIL OFL) | Self-host the font files |
| Open-Meteo API | Optional current-weather line on the dashboard (`static/js/dash_extras.js`). Open-Meteo is itself open-source (AGPL-3.0) | Remove the widget, or self-host Open-Meteo |
| Expo | Builds the phone app. The Expo SDK is MIT-licensed | Build locally with the open-source Expo and React Native toolchain |

## 4.5 Removed proprietary dependencies

An earlier development prototype included an optional Razorpay payment integration for accepting voluntary donations from registered users. This integration was removed on 11 October 2026 to ensure that Qumanity has zero proprietary dependencies and handles no financial PII. Qoins — the platform's internal currency — are earned through civic activity (karma, service, post elevation rewards, voting) rather than purchased. Qoins carry a rupee reference value for user clarity, but no real-money transaction occurs within the platform.

Migration `014_drop_payment_orders.py` drops the old `payment_orders` table when it is empty, and otherwise leaves existing rows as historical data that nothing reads or writes. How Qoins are earned is described in `docs/qoins_earn_reference.md`.

## 4.6 Remaining actions

| # | Action | Status |
|---|---|---|
| 1 | Remove the parked Firebase tooling in qumanity-app (`tools/ops`, which uses the proprietary Firebase Admin SDK, plus `firebase.json`, `.firebaserc` and `firebase/`). The phone app itself does not use Firebase at runtime. | Pending |
| 2 | Push the payment-code removal in qumanity-app. It is done on the founder's machine, but the public repository still contains `mobile/src/components/Payment.tsx` and the Razorpay calls (checked 14 October 2026) | Pending: before submission |
| 3 | Optionally self-host the CDN scripts and fonts so the site works with no third-party requests | Optional |

## 4.7 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Does the project have mandatory dependencies on closed components? | No |
| Supporting evidence | `requirements.txt`, `mobile/package.json`, `Procfile`, Document 02 section 2.6, and this document |
