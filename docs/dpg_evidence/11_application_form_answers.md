# Qumanity: DPG Application Form Answers

**Supplement to the DPG evidence pack: the answer to paste into each application-form field**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

Each row gives the proposed answer, the evidence document it comes from, and its status on 17 October 2026, re-checked against the code on 18 October 2026 at commit f1edd55:
- **Ready:** the answer can be submitted as written.
- **Pending code:** the answer depends on a code change that belongs to the code project.
- **Pending founder:** the answer needs a decision, a document or an action from the owner.

Field names follow the nine indicators of the DPG Standard and the general section of the DPGA submission form. They are paraphrased, so check the wording against the live form when filling it in.

## Cover letter

Qumanity is submitted with every open gap disclosed. Nothing in this pack has been softened to read as finished.

- **Both repositories are public under AGPL-3.0:** https://github.com/sitaram-box/qumanity-web and https://github.com/sitaram-box/qumanity-app. This evidence pack is in `docs/dpg_evidence/` of qumanity-web.
- **The two Blocking code fixes are closed.** Members' birth charts now require sign-in and are returned only to their owner, and `POST /api/admin/sync-folders` requires sign-in and an admin check (Document 07, actions 8 and 9; Document 10, 10.2 rows 20 and 21).
- **Public statistics are aggregate only.** Any count from 1 to 4 is shown as "<5" on the location, Earth, element and scoreboard routes. The older country and continent routes are the one remaining exception (Document 10, row 23).
- **One security fix was made during the final review.** Qmail attachments were served inline with the content type the sender's browser declared, so an HTML or SVG attachment could have run script on qumanity.in. They are now always served as downloads with `nosniff`, and only a fixed list of non-executable file types can be uploaded (18 October 2026, f1edd55; Document 09, 9.6 row 8; Document 10, row 31).
- **Statements that stopped being true were corrected, not only added to.** The 18 October 2026 revision found pack statements that the new features had made false: admin-route access and third-party sharing (Document 07), message consent (Document 09 and field 9.5), documentation completeness (Document 05 and field 5.3) and what exports contain (Document 06). Each is corrected in place, with a note saying what it used to say, what changed and when.
- **Payments: none.** Qoins are earned through civic activity and carry a rupee reference value for user clarity.
- **Testing is labelled and disclosed.** An Admin-controlled testing cycle uses 50 demo accounts. They hold no personal data, vote only on labelled test posts, and are excluded from every public count. Their shared PIN is set in the seed script, but their Private IDs are not published (Documents 05, 07 and 09; Document 10, row 28). A second set of 500 demo accounts exists for local election testing. They are not present in production; the file listing them in the repository is a plan, not a live credential (Document 05, 5.2; Document 10, row 28).
- **Five form fields are answered as planned:** 3.4 (the Copyright Assignment Deed, which follows the LLP registration), 7.2 (the privacy policy), 7.5 (export and delete my data, which must now also cover Qmail and council messages), 9.4 (reporting tools and community rules) and 9.6 (blocking and a minimum age).
- **Document 10 is the evidence for every answer marked "planned"**: each open gap, including those that touch no form field, has a priority and a target date there, and the plan is updated, with the date, whenever a gap closes.

## General information

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| G1 | Name | Qumanity | Doc 01, §1 | Ready |
| G2 | Short description | An open-source civic participation platform. Residents post and vote on Collective Boards at eight nested location levels from Village to Earth, elect a council of one man and one woman at each level, and file Citizen Reports that carry a 10-day response deadline. Aggregate statistics for every location are public. | Doc 01, §1 and §8 | Ready |
| G3 | Type of digital public good | Open-source software: a web platform with a single API (qumanity-web) and a phone app that uses it (qumanity-app) | Doc 01, header | Ready |
| G4 | Website | https://qumanity.in | Doc 06, §6.6 | Ready |
| G5 | Source code repository URLs | https://github.com/sitaram-box/qumanity-web and https://github.com/sitaram-box/qumanity-app | Doc 01, header; Doc 10, 10.4 step 8 | Ready: both repositories are public |
| G6 | Owner or organisation | Rohit Mudgal (individual). Qumanity Lok LLP is in registration, and the IP will be assigned to it by a Copyright Assignment Deed once the LLP is registered | Doc 03, §3.2 and §3.7 | Ready |
| G7 | Contact email | founder@qumanity.in | Doc 03, §3.7 | Ready |
| G8 | Where it is deployed | India. Live at qumanity.in with open registration; council elections are piloted in one village (Rohini Sector 24, Delhi). Members outside India can register | Doc 01, §7; Doc 07, §7.2 | Ready |
| G9 | Deployment stage | Live in production with a pilot. Running: registration, sign-in, Collective Boards, Citizen Reports, announcements, karma, Qoin wallets and public location statistics. Qoins are earned only; payments were removed entirely. Posts that residents vote up earn Qoin rewards and recognition stars, and councils publish updates on their boards. Members can message each other through Qmail, an internal mailbox with drafts and attachments on its own `/qmail` page (it does not send or receive internet email), and residents can write to their village council at a permanent council address, where every council action is logged. Council addresses above village are created but cannot yet receive messages. The Admin Panel gives the Admin one review list for Citizen Reports, ID-recovery requests, member queries and council messages, and gives a serving village council head their own village's council messages only. An Admin-controlled testing cycle runs labelled demo posts and votes to exercise these rules. The lunar-cycle pipeline is built and activates at Chaitra Navratri 2027 by design; the node network and kiosks are not built | Doc 01, §7 | Ready |

## Indicator 1: Relevance to the SDGs

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 1.1 | SDGs the project is relevant to | SDG 16 (primary); SDGs 10, 11, 9 and 17 (supporting) | Doc 01, §2 to §6 | Ready |
| 1.2 | Evidence for SDG 16 | Targets 16.6, 16.7 and 16.10: resident voting with vote-based escalation, elected councils, Citizen Reports with a 10-day deadline, council addresses whose every view, reply and close is logged, public aggregate statistics | Doc 01, §2 | Ready |
| 1.3 | Evidence for SDG 10 | Targets 10.2 and 10.3: free and assisted registration, 13 interface languages (the Qumanity Story is currently English-only), one-man-one-woman council seats | Doc 01, §3 | Ready |
| 1.4 | Evidence for SDG 11 | Targets 11.3 and 11.a: the same participation rules for rural villages and urban sectors | Doc 01, §4 | Ready |
| 1.5 | Evidence for SDG 9 | Targets 9.1 and 9.c: low-cost shared infrastructure serving web and phone from one API | Doc 01, §5 | Ready |
| 1.6 | Evidence for SDG 17 | Target 17.18: public aggregate statistics for every location, by gender, age band, element and sun sign, with members' total karma and Qoin balances (left out for locations under five members). Counts only, no individual records | Doc 01, §6; Doc 06, §6.2 | Ready |

## Indicator 2: Open licensing

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 2.1 | License | GNU Affero General Public License v3.0 (`AGPL-3.0-only`), OSI approved | Doc 02, §2.2 | Ready |
| 2.2 | License URL (web) | https://github.com/sitaram-box/qumanity-web/blob/main/LICENSE | Doc 02, §2.4 | Ready: the LICENSE URL resolves |
| 2.3 | License URL (app) | https://github.com/sitaram-box/qumanity-app/blob/main/LICENSE | Doc 02, §2.4 and §2.7 | Ready: the LICENSE URL resolves (published 15 October 2026, 1689b23) |

## Indicator 3: Clear ownership

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 3.1 | Is ownership of the project clearly defined? | Yes | Doc 03, §3.7 | Ready |
| 3.2 | Owner | Rohit Mudgal (individual). Qumanity Lok LLP is in registration, and the IP will be assigned to it by a Copyright Assignment Deed once the LLP is registered | Doc 03, §3.2 | Ready |
| 3.3 | Evidence of ownership (URL) | The LICENSE and the README ownership notice of qumanity-web (https://github.com/sitaram-box/qumanity-web#readme) | Doc 03, §3.7 | Ready |
| 3.4 | Supporting documents | LICENSE and README notices; the Copyright Assignment Deed once the LLP exists | Doc 03, §3.7; Doc 10, §10.3 | Pending founder: the deed follows LLP registration. Submit without it and add it later |

## Indicator 4: Platform independence

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 4.1 | Does the project have mandatory dependencies on closed or proprietary components? | No | Doc 04, §4.7 | Ready |
| 4.2 | If so, open alternatives | Not applicable. Payments were removed entirely; hosting (Railway), CDNs and fonts all have open, self-hostable alternatives listed in Doc 04. Parked Firebase tooling in qumanity-app (`functions/`, `tools/ops`, `firebase/`) is not used by the app and is being removed (Doc 04, 4.6 #1; Doc 10, row 16) | Doc 04, §4.4 and §4.5 | Ready |
| 4.3 | Supporting evidence | `requirements.txt`, `mobile/package.json`, `Procfile`, Doc 02 §2.6 and Doc 04 | Doc 04, §4.7 | Ready |

## Indicator 5: Documentation

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 5.1 | Documentation URL | https://github.com/sitaram-box/qumanity-web/tree/main/docs | Doc 05, §5.5 | Ready: the repository is public |
| 5.2 | Setup and deployment guide | `docs/INSTALL.md`, with `ENVIRONMENT.md` and `.env.example` | Doc 05, §5.3 and §5.4 | Ready: `INSTALL.md`, `ENVIRONMENT.md` and `.env.example` are in the repository |
| 5.3 | Architecture and API documentation | `docs/ARCHITECTURE.md`, `docs/API.md` and `docs/DATA_MODEL.md`, with `docs/QMAIL.md` and `docs/ADMIN_PANEL.md` for the features added on 18 October 2026 | Doc 05, §5.2 and §5.3 #10 | Ready: the repository's `API.md` covers all 178 `/api` routes and `DATA_MODEL.md` every table (065cecc; Doc 10, row 42). *Corrected twice on 18 October 2026: first from Ready to Pending code, when the route count grew from 154 to 176 and the repository's `API.md` and `DATA_MODEL.md` fell behind; then back to Ready at 065cecc, when both were brought up to date from this pack's own copies.* |

## Indicator 6: Mechanism for extracting non-PII data

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 6.1 | Does the project collect non-PII data, and can it be extracted? | Yes. Aggregate counts by gender, age band, element and sun sign for every location, plus members' total karma and Qoin balances (left out for locations under five members), through public endpoints | Doc 06, §6.2 and §6.6 | Ready |
| 6.2 | Format | JSON and CSV | Doc 06, §6.2 and §6.3 | Ready: the CSV variant is implemented |
| 6.3 | Endpoint and sample URL | `/api/location/stats/<level>/<location_id>` (JSON) and the same path with `.csv` (CSV); sample https://qumanity.in/api/location/stats/village/CS.DL.3.4.1A. For any location with one to four members, each count shows "<5" | Doc 06, §6.6 | Ready: verified live by the founder. Do not cite the zodiac or kundali routes here (Doc 06, §6.4 note) |
| 6.4 | Is the extracted data free of PII? | Yes. The stats endpoints return counts only, and any count from 1 to 4 is shown as "<5". The older country and continent routes are not yet suppressed (Doc 10, 10.2 row 23) | Doc 06, §6.4 | Ready: small-count suppression is implemented |

## Indicator 7: Privacy and applicable laws

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 7.1 | Laws and regulations the project complies with | Digital Personal Data Protection Act, 2023 and Rules, 2025; Information Technology Act, 2000 with the Intermediary Guidelines, 2021; Copyright Act, 1957 | Doc 07, §7.2 and §7.7 | Ready |
| 7.2 | Privacy policy URL | To be published at qumanity.in | Doc 07, §7.7, action 1 | Pending founder (the policy text) and Pending code (the page, and the registration link that now goes to `#`) |
| 7.3 | Does the project collect PII? | Yes. Name, gender, birth date, time and place, present location, languages; optional email, phone and profile fields (relationship status, children, work). PINs are stored as scrypt hashes. Members who activate Qmail also have a Qmail address, whose Account ID part encodes their initials, gender, age band, element and village, and their Qmail messages, attachments and drafts are stored, as are messages sent to a council address and the council's logged actions on them. No payment information | Doc 07, §7.3 to §7.5 | Ready |
| 7.4 | Steps taken to comply | Hashed PINs (scrypt) with lockout, signed expiring tokens, aggregate-only public data with small-count suppression, birth charts visible only to their owner, a wallet's rupee value visible only to its owner (or, for a location wallet, its council and the administrator), admin routes gated (four Admin Panel routes also admit a serving village council head, for their own village's council messages only), Qmail messages readable only by sender and recipient, attachments limited to a fixed list of file types and always served as downloads, every council action and every Admin member export logged, a registration email (if SMTP is configured) that carries only a masked Private ID, the founder's own Private ID rotated as a precaution, anonymous Citizen Reports, no tracking or data sale | Doc 07, §7.5 | Ready. The route gating was verified live by the founder before 18 October 2026; the items added on 18 October 2026 (the four scoped Admin Panel routes, the attachment file-type allowlist and download serving, the two audit logs, and the masked-ID registration email) are verified against the code at f1edd55, not live. |
| 7.5 | Data subject rights (access, correction, erasure) | Export my data and delete my account in Private account settings | Doc 07, action 2 | Pending code |

## Indicator 8: Standards and best practices

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 8.1 | Standards followed | HTTP/REST, JSON, HTTPS/TLS, scrypt, HMAC, SQL, GeoJSON, UTF-8, ISO 8601, IANA tz, ISO 639-1, WAI-ARIA, WCAG 2.1 (aspirational) | Doc 08, §8.4 | Ready |
| 8.2 | Best practices | AGPL-3.0 licence; hashed credentials with lockout; aggregate-only public data; honest gap disclosure in Documents 05, 07 and 09 | Doc 08, §8.4 | Ready |

## Indicator 9: Do no harm by design

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 9.1 | 9A: Does the project collect, store or distribute PII? | Yes. See Document 07 | Doc 09, §9.7 | Ready |
| 9.2 | 9A: How is PII protected? | As 7.4 | Doc 07, §7.5; Doc 09, §9.2 | Ready. The route gating was verified live by the founder before 18 October 2026; the items added on 18 October 2026 (the four scoped Admin Panel routes, the attachment file-type allowlist and download serving, the two audit logs, and the masked-ID registration email) are verified against the code at f1edd55, not live. |
| 9.3 | 9B: Does the project collect, store or distribute content? | Yes: board posts, Citizen Reports, chat messages, Qmail messages with attachments, and messages to council addresses | Doc 09, §9.7 | Ready |
| 9.4 | 9B: Content moderation policy and mechanism | Community vote today: posts that close with a negative score are removed. Council updates are not voted on. Report tools and published community rules are planned | Doc 09, §9.4 and §9.6 #1, #3 | Pending code (Report) and Pending founder (community rules, grievance officer) |
| 9.5 | 9C: Does the project facilitate interactions between users? | Yes. Chats require the recipient to accept a request first. Qmail has no request step: a member can be sent a Qmail only after activating Qmail themselves, and then by anyone who has their address or Public ID. Block and report tools are planned | Doc 09, §9.5 and §9.7 | Ready. *Corrected 18 October 2026: previously "Messaging needs the recipient's consent first", which no longer holds for Qmail.* |
| 9.6 | 9C: Protection from harassment, including for minors | Block member, Report, and a minimum age or parental consent | Doc 09, §9.6 #1, #2, #6 | Pending code (Block, Report) and Pending founder (the minimum-age decision) |

## Count

| Status | Fields |
|---|---|
| Ready | 40 |
| Pending code | 4 (3 of them also Pending founder) |
| Pending founder | 4 (3 of them also Pending code) |
| Total | 45 |

Counted from the status column on 18 October 2026: five fields are open (3.4, 7.2, 7.5, 9.4 and 9.6). Field 5.3 moved from Ready to Pending code on 18 October 2026 and back to Ready the same day, once 065cecc brought the repository's documentation up to date (see its correction note).

## Fields still open

These answers can be submitted as "planned", with Document 10 as the evidence, but they are the open gaps a reviewer will see:

1. **7.2 (privacy policy URL):** the policy is still to be written and published, and the page and registration link need code (Doc 07, action 1).
2. **7.5 (export and delete my data):** still to be built (Doc 07, action 2). It must also cover Qmail messages, attachments and council messages, which are kept indefinitely today (Doc 07, action 11).
3. **9.4 and 9.6 (moderation and harassment):** Report and Block are still to be built (Doc 09, actions 1 and 2), and the minimum-age decision is open (action 6).

Fields 2.3 and 3.3 became Ready on 15 October 2026.

3.4 (Copyright Assignment Deed) follows the LLP registration and can be added after submission.
