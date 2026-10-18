# Qumanity: Standards and Best Practices

**DPG Standard Indicator 8: Adherence to Standards and Best Practices**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

## Contents

- [8.1 What the DPG Standard requires](#81-what-the-dpg-standard-requires)
- [8.2 Open standards in use](#82-open-standards-in-use)
- [8.3 Standards deliberately not used](#83-standards-deliberately-not-used)
- [8.4 Evidence for the application form](#84-evidence-for-the-application-form)

## 8.1 What the DPG Standard requires

The project must show that it follows relevant open standards, and best practices where they apply, so that it can work with other systems and be maintained by others.

## 8.2 Open standards in use

Each row was checked against the qumanity-web code on 11 October 2026.

| Standard | Where used | Purpose |
|---|---|---|
| HTTP/1.1 (RFC 9110) with REST-style resources | All `/api/...` routes in `app.py`, used by both the website and the phone app | Web API design |
| JSON (RFC 8259) | Every API response, `static/data/*.json`, `static/locales/*.json` | Data interchange |
| HTTPS / TLS 1.2+ | qumanity.in. TLS is terminated by the hosting platform (Railway). | Transport security |
| scrypt (RFC 7914) | PIN hashing through werkzeug's `generate_password_hash`; stored hashes begin `scrypt:32768:8:1` | Credential storage |
| HMAC (RFC 2104) | Signed phone-app tokens (`itsdangerous.URLSafeTimedSerializer`) and Flask's signed session cookie | Tamper-proof sessions |
| SQL (SQLite dialect) | `db/schema.sql`, `migrations/`, all queries | Data storage |
| GeoJSON (RFC 7946) | `static/data/*.geojson` (world borders, India and Sub-continent outlines), drawn by Leaflet and three.js | Geographic data for the maps |
| UTF-8 | `<meta charset="utf-8">` in the page templates; all JSON and locale files, including Devanagari and other Indic scripts | Character encoding |
| ISO 8601 | Dates and timestamps throughout (`date.isoformat()`; `dob` stored as `YYYY-MM-DD`) | Date and time format |
| IANA Time Zone Database | Birth time is converted to UTC using the IANA zone for the birth location (`timezonefinder` with Python's `zoneinfo`, `zodiac_core.py`) | Time zones |
| ISO 639-1 language codes | Interface translations named by code (`static/locales/hi.json`, `ta.json`, `ur.json` and so on) | Language identification |
| WAI-ARIA 1.2 | `aria-label`, `aria-expanded`, `aria-modal` and other attributes in templates and scripts | Accessibility for screen readers |
| WCAG 2.1 (aspirational target) | UI design. Not yet audited. | Accessibility |

HMAC-SHA256 was used only for Razorpay payment-signature checks and was removed with Razorpay. HMAC is still used, through itsdangerous, for signing tokens and cookies.

## 8.3 Standards deliberately not used

| Standard | Status and reason |
|---|---|
| OpenAPI | Not used. API documentation is hand-written: `docs/API.md` lists every route, and `docs/phone_app_api.md` covers the phone app's calls. An OpenAPI file can be generated from Flask's URL map later. |
| OAuth 2.0 / OpenID Connect | Not used, by design. Members sign in with a 9-digit Private ID and a 5-digit PIN. Members without email or phone can still sign in. |
| OWASP ASVS | Not yet assessed. Planned. |
| JSON Schema | Not used. API responses are not schema-validated today. Planned. |
| iCalendar, RSS/Atom | Not used. Nothing in the code produces calendar or feed output. |
| Internet mail (SMTP, RFC 5321) | Not used for Qmail. Qmail addresses (`<username>-<account_id>@qumanity.in` and `<level>-<location_id>@qumanity.in`) look like email addresses but are an internal addressing convention only: Qmail messages stay inside Qumanity, and no route sends or receives internet mail for them (added 18 October 2026). The only SMTP use is the optional registration notice to the Admin (`email_core.py`), which is off unless `SMTP_HOST` and `QM_ADMIN_EMAIL` are set. |

## 8.4 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Standards followed | HTTP/REST, JSON, HTTPS/TLS, scrypt, HMAC, SQL, GeoJSON, UTF-8, ISO 8601, IANA tz, ISO 639-1, WAI-ARIA, WCAG 2.1 (aspirational) |
| Best practices | AGPL-3.0 open licence; hashed credentials with lockout; aggregate-only public data; honest gap disclosure in Documents 05, 07 and 09 |
