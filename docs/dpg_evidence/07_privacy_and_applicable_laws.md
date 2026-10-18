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

## 7.4 Payment information

Qumanity does not collect or process payment information. There is no payment processor integrated into the platform. Qoins are earned through civic activity and stored as internal platform data only.

## 7.5 How personal data is protected

- **Sign-in:** PINs are hashed with scrypt, werkzeug's default in `generate_password_hash` (stored hashes begin `scrypt:32768:8:1`). After repeated wrong PINs the account is locked for a period (`pin_fails`, `pin_locked_until`).
- **Phone app sessions:** signed tokens that expire after 30 days.
- **Secret key:** the server refuses to run on Railway with the default development secret.
- **Hidden identity:** the data model supports replacing a member's name with their Account ID and capping their visible location at State level wherever strangers can see them (`hide_identity`). There is no member-facing switch for it yet.
- **Anonymous Citizen Reports:** a member can file a report anonymously. The council handling it sees "Anonymous Citizen"; only the platform administrator can see the real identity.
- **No advertising, tracking or data sale:** the code contains no analytics or advertising SDK. Member data is not shared with third parties.
- **Database files** are kept out of the public repositories (`.gitignore`). The old demo account list (`DEMO_ACCOUNTS.md`) was also scrubbed from git history.
- **Demo accounts:** `docs/ELECTION_PILOT.md` lists 500 demo Private IDs used for local election testing. These accounts are not present in the production database. No Private ID of a live account is published in the repository. The 50 board-test accounts share a PIN set in `scripts/seed_demo_voters.py`, but their Private IDs are not published. These are demo accounts. They contain no personal data, the testing scheduler casts their votes only on labelled test posts, and they are excluded from every public count. The platform does not otherwise restrict a signed-in demo account, so someone who also knew one of their Private IDs could post and vote as an ordinary member of the pilot village. Two stray demo accounts (users 25 and 26) were retired on 17 October 2026. They are flagged `is_demo=1` and `is_removed=1`, cannot sign in, and are excluded from every count.
- **Founder's Private ID rotated:** as a precaution, the founder's own Private ID was replaced after an earlier ID had appeared in repository files. The old ID was removed from the files and from git history, and the new ID is not published.
- **Birth charts are private:** a member's full chart (`/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>` and the `/kundali/<id>` page) requires sign-in and is returned only to that member.
- **Admin routes:** every `/api/admin/` route requires sign-in and an admin Private ID.
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

## 7.7 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Laws the project complies with | Digital Personal Data Protection Act, 2023 and Rules, 2025; Information Technology Act, 2000 |
| Privacy policy URL | To be published at qumanity.in (action 1) |
| Does the project collect PII? | Yes. Listed in 7.3, with the protections in 7.5 |
