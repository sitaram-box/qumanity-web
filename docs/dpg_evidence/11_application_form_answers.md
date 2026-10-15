# Qumanity: DPG Application Form Answers

**Supplement to the DPG evidence pack: the answer to paste into each application-form field**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

Each row gives the proposed answer, the evidence document it comes from, and its status on 14 October 2026:
- **Ready:** the answer can be submitted as written.
- **Pending code:** the answer depends on a code change that belongs to the code project.
- **Pending founder:** the answer needs a decision, a document or an action from the owner.

Field names follow the nine indicators of the DPG Standard and the general section of the DPGA submission form. They are paraphrased, so check the wording against the live form when filling it in.

## Cover letter

Qumanity is submitted with every open gap disclosed. Nothing in this pack has been softened to read as finished.

- **The two Blocking code fixes are closed.** Members' birth charts now require sign-in and are returned only to their owner, and `POST /api/admin/sync-folders` requires sign-in and an admin check (Document 07, actions 8 and 9; Document 10, 10.2 rows 20 and 21).
- **Both repositories are public:** https://github.com/sitaram-box/qumanity-web and https://github.com/sitaram-box/qumanity-app.
- **Document 10 is the evidence for every answer marked "planned"** in this form: each open gap has a priority and a target date there, and the plan is updated, with the date, whenever a gap closes.
- **Every open gap is disclosed.** The open items are listed at the end of this document and in Document 10.

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
| G9 | Deployment stage | Live in production with a pilot. Running: registration, sign-in, Collective Boards, Citizen Reports, announcements, karma, Qoin wallets and public location statistics. Qoins are earned only; payments were removed entirely. The lunar-cycle pipeline is built and activates at Chaitra Navratri 2027 by design; the node network and kiosks are not built | Doc 01, §7 | Ready |

## Indicator 1: Relevance to the SDGs

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 1.1 | SDGs the project is relevant to | SDG 16 (primary); SDGs 10, 11, 9 and 17 (supporting) | Doc 01, §2 to §6 | Ready |
| 1.2 | Evidence for SDG 16 | Targets 16.6, 16.7 and 16.10: resident voting with vote-based escalation, elected councils, Citizen Reports with a 10-day deadline, public aggregate statistics | Doc 01, §2 | Ready |
| 1.3 | Evidence for SDG 10 | Targets 10.2 and 10.3: free and assisted registration, 13 interface languages (the Founder's Message is currently English-only), one-man-one-woman council seats | Doc 01, §3 | Ready |
| 1.4 | Evidence for SDG 11 | Targets 11.3 and 11.a: the same participation rules for rural villages and urban sectors | Doc 01, §4 | Ready |
| 1.5 | Evidence for SDG 9 | Targets 9.1 and 9.c: low-cost shared infrastructure serving web and phone from one API | Doc 01, §5 | Ready |
| 1.6 | Evidence for SDG 17 | Target 17.18: public aggregate statistics for every location, by gender, age band, element and sun sign, with collective karma and Qoin balances. Counts only, no individual records | Doc 01, §6; Doc 06, §6.2 | Ready |

## Indicator 2: Open licensing

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 2.1 | License | GNU Affero General Public License v3.0 (`AGPL-3.0-only`), OSI approved | Doc 02, §2.2 | Ready |
| 2.2 | License URL (web) | https://github.com/sitaram-box/qumanity-web/blob/main/LICENSE | Doc 02, §2.4 | Ready: the LICENSE URL resolves |
| 2.3 | License URL (app) | https://github.com/sitaram-box/qumanity-app/blob/main/LICENSE | Doc 02, §2.4 and §2.7 | Pending founder: the URL does not resolve yet. qumanity-app on GitHub has no LICENSE file; it exists only on the founder's machine and needs to be pushed (Doc 10, 10.2 row 24) |

## Indicator 3: Clear ownership

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 3.1 | Is ownership of the project clearly defined? | Yes | Doc 03, §3.7 | Ready |
| 3.2 | Owner | Rohit Mudgal (individual). Qumanity Lok LLP is in registration, and the IP will be assigned to it by a Copyright Assignment Deed once the LLP is registered | Doc 03, §3.2 | Ready |
| 3.3 | Evidence of ownership (URL) | The LICENSE and the README ownership section of qumanity-web | Doc 03, §3.7 | Pending founder, final step: the LICENSE URL resolves, but neither README names the owner yet (Doc 10, 10.4 step 6). Ready once the copyright line is added |
| 3.4 | Supporting documents | LICENSE and README notices; the Copyright Assignment Deed once the LLP exists | Doc 03, §3.7; Doc 10, §10.3 | Pending founder: the deed follows LLP registration. Submit without it and add it later |

## Indicator 4: Platform independence

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 4.1 | Does the project have mandatory dependencies on closed or proprietary components? | No | Doc 04, §4.7 | Ready |
| 4.2 | If so, open alternatives | Not applicable. Payments were removed entirely; hosting (Railway), CDNs and fonts all have open, self-hostable alternatives listed in Doc 04 | Doc 04, §4.4 and §4.5 | Ready |
| 4.3 | Supporting evidence | `requirements.txt`, `mobile/package.json`, `Procfile`, Doc 02 §2.6 and Doc 04 | Doc 04, §4.7 | Ready |

## Indicator 5: Documentation

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 5.1 | Documentation URL | https://github.com/sitaram-box/qumanity-web/tree/main/docs | Doc 05, §5.5 | Ready: the repository is public |
| 5.2 | Setup and deployment guide | `docs/INSTALL.md`, with `ENVIRONMENT.md` and `.env.example` | Doc 05, §5.3 and §5.4 | Ready: `INSTALL.md`, `ENVIRONMENT.md` and `.env.example` are in the repository |
| 5.3 | Architecture and API documentation | `docs/ARCHITECTURE.md`, `docs/API.md` (all 149 routes) and `docs/DATA_MODEL.md` | Doc 05, §5.3 and §5.4 | Ready: all three are in the repository |

## Indicator 6: Mechanism for extracting non-PII data

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 6.1 | Does the project collect non-PII data, and can it be extracted? | Yes. Aggregate counts by gender, age band, element and sun sign for every location, plus collective karma and Qoin balances, through public endpoints | Doc 06, §6.2 and §6.6 | Ready |
| 6.2 | Format | JSON and CSV | Doc 06, §6.2 and §6.3 | Ready: the CSV variant is implemented |
| 6.3 | Endpoint and sample URL | `/api/location/stats/<level>/<location_id>` (JSON) and the same path with `.csv` (CSV); sample https://qumanity.in/api/location/stats/village/CS.DL.3.4.1A | Doc 06, §6.6 | Ready: verified live by the founder. Do not cite the zodiac or kundali routes here (Doc 06, §6.4 note) |
| 6.4 | Is the extracted data free of PII? | Yes. The stats endpoints return counts only, and any count from 1 to 4 is shown as "<5". The older Earth, country and continent routes are not yet suppressed (Doc 10, 10.2 row 23) | Doc 06, §6.4 | Ready: small-count suppression is implemented |

## Indicator 7: Privacy and applicable laws

| # | Form field | Proposed answer | Source | Status |
|---|---|---|---|---|
| 7.1 | Laws and regulations the project complies with | Digital Personal Data Protection Act, 2023 and Rules, 2025; Information Technology Act, 2000 with the Intermediary Guidelines, 2021; Copyright Act, 1957 | Doc 07, §7.2 and §7.7 | Ready |
| 7.2 | Privacy policy URL | To be published at qumanity.in | Doc 07, §7.7, action 1 | Pending founder: the policy needs writing, and the page and registration link need code |
| 7.3 | Does the project collect PII? | Yes. Name, gender, birth date, time and place, present location, languages, optional email and phone. PINs are stored as scrypt hashes. No payment information | Doc 07, §7.3 to §7.5 | Ready |
| 7.4 | Steps taken to comply | Hashed PINs (scrypt) with lockout, signed expiring tokens, aggregate-only public data with small-count suppression, birth charts visible only to their owner, admin routes gated, the founder's own Private ID rotated as a precaution, anonymous Citizen Reports, no tracking or data sale | Doc 07, §7.5 | Ready: routes gated, verified live by the founder |
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
| 9.2 | 9A: How is PII protected? | As 7.4 | Doc 07, §7.5; Doc 09, §9.2 | Ready: routes gated, verified live by the founder |
| 9.3 | 9B: Does the project collect, store or distribute content? | Yes: board posts, Citizen Reports and messages | Doc 09, §9.7 | Ready |
| 9.4 | 9B: Content moderation policy and mechanism | Community vote today. Report tools and published community rules are planned | Doc 09, §9.4 and §9.6 #1, #3 | Pending code (Report) and Pending founder (community rules, grievance officer) |
| 9.5 | 9C: Does the project facilitate interactions between users? | Yes. Messaging needs the recipient's consent first | Doc 09, §9.5 and §9.7 | Ready |
| 9.6 | 9C: Protection from harassment, including for minors | Block member, Report, and a minimum age or parental consent | Doc 09, §9.6 #1, #2, #6 | Pending code (Block, Report) and Pending founder (the minimum-age decision) |

## Count

| Status | Fields |
|---|---|
| Ready | 38 |
| Pending code | 3 (2 of them also Pending founder) |
| Pending founder | 6 (2 of them also Pending code) |
| Total | 45 |

## Fields still open

These answers can be submitted as "planned", with Document 10 as the evidence, but they are the open gaps a reviewer will see:

1. **7.2 (privacy policy URL):** the policy is still to be written and published (Doc 07, action 1).
2. **7.5 (export and delete my data):** still to be built (Doc 07, action 2).
3. **9.4 and 9.6 (moderation and harassment):** Report and Block are still to be built (Doc 09, actions 1 and 2), and the minimum-age decision is open (action 6).

Two final steps for the founder before the form is submitted, so that fields 2.3 and 3.3 become Ready:

4. **Push the qumanity-app `LICENSE` file and the payment-code removal** (Doc 10, 10.2 row 24).
5. **Add the copyright line naming the owner to both READMEs** (Doc 10, 10.4 step 6).

3.4 (Copyright Assignment Deed) follows the LLP registration and can be added after submission.
