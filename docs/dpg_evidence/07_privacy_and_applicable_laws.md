# Qumanity: Privacy and Applicable Laws

**DPG Standard Indicator 7: Adherence to Privacy and Applicable Laws**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.
Contact: founder@qumanity.in

## Contents

- [7.1 What the DPG Standard requires](#71-what-the-dpg-standard-requires)
- [7.2 Applicable laws](#72-applicable-laws)
- [7.3 Personal data collected](#73-personal-data-collected)
- [7.4 Payment information](#74-payment-information)
- [7.5 How personal data is protected](#75-how-personal-data-is-protected)
- [7.6 Gaps and actions](#76-gaps-and-actions)
- [7.7 Evidence for the application form](#77-evidence-for-the-application-form)

## 7.1 What the DPG Standard requires

The project must state the privacy and other laws it is subject to, and show that it complies with them, for example through a published privacy policy and the measures it takes to protect personal data.

## 7.2 Applicable laws

| Law | Why it applies |
|---|---|
| Digital Personal Data Protection Act, 2023 (India) | Qumanity collects personal data of members in India. Qumanity is the Data Fiduciary. |
| Digital Personal Data Protection Rules, 2025 | Notice, consent, security, breach-reporting and retention rules. Most provisions come into force in May 2027. |
| Information Technology Act, 2000, with the Intermediary Guidelines, 2021 | Members post content on Collective Boards and in Citizen Reports, so Qumanity acts as an intermediary for that content (see Document 09). |
| Copyright Act, 1957 | Ownership and licensing of the code and content (Documents 02 and 03). |

Members outside India can register. Qumanity follows the DPDP Act as its baseline for all members. Laws of other countries, such as the EU GDPR for members in the EU, have not yet been assessed (action 7 in 7.6).

## 7.3 Personal data collected

Read from `db/schema.sql` and the column migrations in `app.py` on 11 October 2026.

| Data | Required? | Why it is collected |
|---|---|---|
| Name, gender | Required | Identity, and the one-man-one-woman council rule |
| Date and time of birth | Required | Sun sign and element, election cycles, age band |
| Birth location and present location (to village level) | Required | Places the member in the Village-to-Earth location chain |
| Languages | Required | Interface language |
| Private ID and PIN | Generated | Sign-in. The PIN is stored only as a salted hash. |
| Email, phone | Optional | Communication only (PIN reset, notifications). Not used to sign in. |
| Relationship status, children, work profile | Optional | Self-described profile fields |
| Referrer | Recorded when one member registers another | Assisted registration |
| Posts, votes, reports, messages, Qoin and karma history | Created by use | Core civic functions |

Public statistics are published only as aggregates: counts by gender, age band and sun sign for each location (`/api/location/stats/<level>/<id>`, JSON and CSV), with counts from 1 to 4 shown as `"<5"`. No user IDs, names or per-user rows are included.

### Messages and council records

Added 18 October 2026, read from migrations 019 to 024 and the routes that use them (commit 274c073), and updated the same day for c09b91f, which lets a sender read the replies to their own council message or Admin query. None of these records appears in any public statistic or public export.

| Data | Who can read it | How long it is kept | Exported? |
|---|---|---|---|
| Qmail username and address history (`users.qmail_username`, `qmail_addresses`). Optional: only members who activate Qmail have one | The address is suggested to members connected to its owner (shared groups or chats), and is returned with the owner's name to any signed-in member who enters the owner's 12-digit Public ID. The address contains the member's Account ID, which encodes their initials, gender, age band at registration, sun-sign element and present location id (to village level) (`id_generator._build_id`) | Every past address is kept. An old address still delivers for 30 days after the Account ID changes, then stops | No |
| Qmail messages (`qmail_messages`) | The sender and the recipient. No route gives the Admin or a council access | Indefinitely. There is no route to delete a message | No |
| Qmail attachments (`qmail_attachments`), up to 2 MB each, stored in the database | For a member message: its sender and recipient. For a council message: its sender, that village's serving council heads, and the Admin | With the message, indefinitely | No |
| Qmail drafts (`qmail_drafts`) | The member who wrote the draft | Until the member deletes it or sends it. There is no automatic cleanup, so an abandoned draft is kept indefinitely. This is a limitation of the prototype (7.6, row 12) | No |
| Council queue messages (`qpunch_queue_messages`): messages sent to a village's council address | The sender, the village's council heads serving at the time of reading, and the Admin. The sender sees their own message with the text and time of each council reply, but not who replied or the action log (`GET /api/qmail/sent/council/<id>`). The message stays with the seat, so council heads elected later can read earlier messages. The sender's account is attached; there is no anonymous option | Indefinitely. Closing a message changes its status and does not delete it | No |
| Council action log (`qpunch_queue_actions`): every view, reply and close, with the council member who did it and the reply text | The Admin and the serving council heads, inside the message's detail view. The sender sees only the text and time of each reply (`GET /api/qmail/sent/council/<id>`), never the views, the closes or who acted | Indefinitely (append-only) | No |
| Member queries (`admin_queries`, `admin_query_replies`) | The Admin, and the member who asked: they see their own query with the text and time of each reply, but not who replied (`GET /api/queries/mine/<id>`) | Indefinitely | No. The member-facing route to submit a query is not wired yet, so no member can file one today |
| Admin export log (`admin_export_log`): which admin exported, when, with which filters, how many rows, and in which format | No route reads it; it is visible only with direct database access | Indefinitely | No |

### The one export that contains personal data (Admin only)

Separate from the public, non-personal exports above and in Document 06. `GET /api/admin/users/export` (JSON) and `GET /api/admin/users/export.csv` return, for real members filtered by location and registration period, each member's internal id, 9-digit Private ID, Account ID, name, present-location chain and registration time. Both routes require the Admin (`_is_admin()`); the Admin Panel's council scope (7.5) does not reach them. Every successful export writes one row to `admin_export_log`, the same posture as the existing log of Private ID reveals (`id_recovery_reveals`). Demo and removed accounts are excluded.

## 7.4 Payment information

Qumanity does not collect or process payment information. There is no payment processor integrated into the platform. Qoins are earned through civic activity and stored as internal platform data only.

## 7.5 How personal data is protected

- **Sign-in:** PINs are hashed with scrypt, werkzeug's default in `generate_password_hash` (stored hashes begin `scrypt:32768:8:1`). After repeated wrong PINs the account is locked for a period (`pin_fails`, `pin_locked_until`).
- **Phone app sessions:** signed tokens that expire after 30 days.
- **Secret key:** the server refuses to run on Railway with the default development secret.
- **Hidden identity:** the data model supports replacing a member's name with their Account ID and capping their visible location at State level wherever strangers can see them (`hide_identity`). There is no member-facing switch for it yet.
- **Anonymous Citizen Reports:** a member can file a report anonymously. The council handling it sees "Anonymous Citizen"; only the platform administrator can see the real identity.
- **No advertising, tracking or data sale:** the code contains no analytics or advertising SDK. If SMTP is configured, each registration emails the new member's name, location chain and a masked Private ID to the Admin's mailbox through the SMTP provider. No other third party receives member data. The email shows only the last four digits of the Private ID and never contains the full ID (`email_core.py`). Whether production has SMTP configured is not recorded in the repository, so this is stated conditionally (Document 04, section 4.4).
  *Correction, 18 October 2026: this line previously said "Member data is not shared with third parties." The optional registration email added in commit f2788bf (18 October 2026) makes that conditional on SMTP configuration.*
- **Database files** are kept out of the public repositories (`.gitignore`). The old demo account list (`DEMO_ACCOUNTS.md`) was also scrubbed from git history.
- **Demo accounts:** `docs/ELECTION_PILOT.md` lists 500 demo Private IDs used for local election testing. These accounts are not present in the production database. No Private ID of a live account is published in the repository. The 50 board-test accounts share a PIN set in `scripts/seed_demo_voters.py`, but their Private IDs are not published. These are demo accounts. They contain no personal data, the testing scheduler casts their votes only on labelled test posts, and they are excluded from every public count. The platform does not otherwise restrict a signed-in demo account, so someone who also knew one of their Private IDs could post and vote as an ordinary member of the pilot village. Two stray demo accounts (users 25 and 26) were retired on 17 October 2026. They are flagged `is_demo=1` and `is_removed=1`, cannot sign in, and are excluded from every count.
- **Founder's Private ID rotated:** as a precaution, the founder's own Private ID was replaced after an earlier ID had appeared in repository files. The old ID was removed from the files and from git history, and the new ID is not published.
- **Birth charts are private:** a member's full chart (`/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>` and the `/kundali/<id>` page) requires sign-in and is returned only to that member.
- **Qmail addresses reveal profile attributes:** an address takes the form `<username>-<Account ID>@qumanity.in`, and the Account ID encodes the member's initials, gender, age band at registration, sun-sign element and present location to village level. Anyone who has a member's 12-digit Public ID can obtain that member's address and name, and read those attributes from it. This is a deliberate consequence of addresses being derivable rather than stored slugs; it is recorded here so the exposure is visible rather than incidental.
- **Admin routes:** every `/api/admin/` route requires sign-in and an admin Private ID, except four Admin Panel routes that also admit a village council head during their current term: `GET /api/admin/panel/feed`, `GET /api/admin/panel/council/<id>`, `POST /api/admin/panel/council/<id>/reply` and `POST /api/admin/panel/council/<id>/close`. They exist so that a village council can read and answer the messages residents send to its council address. Through them a head sees only their own village's council messages, never Citizen Reports in the panel, ID-recovery requests, member queries or the member export. A message from another village returns 404, the same as one that does not exist. The term is re-checked on every request, so a head whose term has ended loses access on their next request. Every view, reply and close is logged (`qpunch_queue_actions`) (`_is_admin_panel_user()` in `app.py`, `docs/ADMIN_PANEL.md` section 8).
  *Correction, 18 October 2026: this line previously said every `/api/admin/` route requires an admin Private ID. Commit 0635c72 (18 October 2026) opened the four routes above to serving village council heads.*
- **No external images in messages:** images can be sent only as Qmail attachments, served through a signed-in, access-checked route. A message cannot load an image from an outside URL, so no third party learns who opened a message or when.
- **Wallet values are private:** anyone can see how many Qoins a wallet holds, but its rupee value is shown only to its owner, or for a location wallet, to that location's council and the administrator. Public statistics leave out members' karma and Qoin totals for any location with one to four members.

## 7.6 Gaps and actions

| # | Gap | Action | Status |
|---|---|---|---|
| 1 | The registration page says "you agree to Qumanity's Privacy Policy", but the link goes nowhere (`href="#"`) | Write and publish a privacy policy and terms of service at qumanity.in, and link them from registration in the website and app | Pending |
| 2 | No way for a member to download or delete their own data (DPDP Act, sections 11 and 12) | Add "export my data" and "delete my account" to the Private account settings | Pending |
| 3 | `/api/location/members/village/<id>` lists names, gender and age category of a village's members without sign-in | Require sign-in, or limit the list to members of that village | Pending (code) |
| 4 | Aggregate stats for a small village can single out individuals (for example, the only woman aged 76+) | Suppress any count below 5, in both the JSON stats and the CSV export (Document 06, action 2) | Done, 14 October 2026, for `/api/location/stats` (JSON and CSV), and 17 October 2026 for the Earth, subcontinent, location-elements, global-elements and India-scoreboard routes (265a2f4, 57bafba). The country and continent routes are not yet suppressed (Document 06, 6.5 #5) |
| 5 | Birth date and time are collected for every member. Under the DPDP Act a member under 18 is a child, and processing needs verifiable parental consent | Set a minimum age, or add a parental-consent step for under-18s | Pending |
| 6 | No named contact for data requests and grievances | Name founder@qumanity.in as the grievance contact in the privacy policy | Pending |
| 7 | Non-Indian members | Decide whether to restrict registration to India, or assess GDPR and other laws | Pending |
| 8 | `/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>` and the `/kundali/<id>` page show any member's birth chart (and, on the page, name) without sign-in. User IDs are sequential, so every chart can be listed | Require sign-in and return a chart only to its owner; the app already uses `/api/me/kundali` | Done, 14 October 2026: all three require sign-in and return the chart only to its owner |
| 9 | `POST /api/admin/sync-folders` has no sign-in or admin check | Add the admin check used by the other `/api/admin` routes | Done, 14 October 2026 |
| 10 | `docs/ELECTION_PILOT.md` lists 500 demo Private IDs (not present in production), and the 50 live board-test accounts share a PIN set in `scripts/seed_demo_voters.py` | Disclose it (7.5 and Document 05, 5.2) | Disclosed. Tracked in Document 10, row 28 |
| 11 | Qmail messages, attachments and council queue messages are kept indefinitely, and a member cannot delete them | Set a retention period, and cover these records in "delete my account" (action 2) | Pending |
| 12 | There is no automatic cleanup of Qmail drafts, so an abandoned draft is kept indefinitely. This is a limitation of the prototype | Set a retention period for drafts, or delete drafts with the account (action 2) | Pending |
| 13 | A member writing to their village council is not told that the message stays with the seat and can be read by council heads elected later. Checked 18 October 2026: the compose form in `templates/qmail.html` and `static/js/qmail.js` is the same for member and council addresses and shows no such notice | Show a one-line notice in the compose form, before sending, when the To address is a council address | Pending |

## 7.7 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Laws the project complies with | Digital Personal Data Protection Act, 2023 and Rules, 2025; Information Technology Act, 2000 |
| Privacy policy URL | To be published at qumanity.in (action 1) |
| Does the project collect PII? | Yes. Listed in 7.3, with the protections in 7.5 |
