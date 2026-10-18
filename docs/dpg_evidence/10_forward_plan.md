# Qumanity: Forward Plan

**Supplement to the DPG evidence pack (not a required DPG document)**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

## Contents

- [10.1 Purpose](#101-purpose)
- [10.2 Outstanding code gaps](#102-outstanding-code-gaps)
- [10.3 Legal and entity gaps](#103-legal-and-entity-gaps)
- [10.4 Repository public flip checklist](#104-repository-public-flip-checklist)
- [10.5 DPG iteration plan](#105-dpg-iteration-plan)
- [10.6 Long-term roadmap](#106-long-term-roadmap)

## 10.1 Purpose

This is a roadmap for closing the gaps identified in the DPG evidence pack. It is not a required DPG document. It is included so reviewers can see a credible path to full compliance: every gap disclosed in Documents 03 to 09 appears here once, with a priority and a target date.

Target dates are proposed. High priority is due by 31 December 2026 and Medium by 31 March 2027, ahead of the DPDP Rules taking effect in May 2027. Low priority is due by 30 June 2027. Blocking items had to be closed before the repositories were made public (10.4, step 8). Both Blocking items (rows 20 and 21) were closed on 14 October 2026, and none is open now. The owner confirms or changes the dates.

## 10.2 Code gaps

Status checked against the code on 17 October 2026, and again on 18 October 2026.

This row list was re-audited against the code on 17 October 2026. Rows 20 and 21 (Blocking for the public flip) were closed before submission, and rows 18 and 24 were closed after the last revision. The list reflects the code at commit 971de33.

The list was re-checked against the code on 18 October 2026 at commit c09b91f, after Qmail, Q-Punch council addresses, the council queue, the Admin Panel's council scope, attachments, drafts and the `/qmail` page were added. Rows 1 to 30 were unchanged by that code except rows 8 and 9, whose scope now includes Qmail. Rows 31 to 44 are new: rows 31 and 44 were found and fixed during the 18 October 2026 pack review, rows 42 and 43 were closed the same day by the documentation commit 065cecc, and the rest are open. Both were found by checking a pack claim against what the routes actually do, not by reading the tests, so this pack pass also served as a second review of the code.

| # | Gap | Source document | Priority | Target date | Status |
|---|---|---|---|---|---|
| 1 | Privacy Policy and Terms of Service pages not published (the registration link goes to `#`) | Doc 07, action 1 | High | 31 Dec 2026 | Open |
| 2 | No user-facing "export my data" or "delete my account" | Doc 07, action 2 | High | 31 Dec 2026 | Open |
| 3 | Village member names visible without sign-in | Doc 07, action 3 | High | 31 Dec 2026 | Open |
| 4 | Small-count suppression not implemented in stats endpoints | Doc 07, action 4; Doc 06, 6.5 #2 | High | 31 Dec 2026 | Done, 14 Oct 2026, for `/api/location/stats` (JSON and CSV). See rows 23 and 27 |
| 5 | No minimum age or parental-consent gate | Doc 07, action 5 | Medium | 31 Mar 2027 | Open |
| 6 | No named grievance contact | Doc 07, action 6 | Medium | 31 Mar 2027 | Open |
| 7 | Non-Indian member compliance (GDPR) not assessed | Doc 07, action 7 | Medium | 31 Mar 2027 | Open |
| 8 | No "Report abusive content" feature, for posts, messages, Qmail messages and profiles (Qmail added to its scope on 18 October 2026) | Doc 09, action 1 | High | 31 Dec 2026 | Open |
| 9 | No "Block member" feature; a block must also stop Qmail (Qmail added to its scope on 18 October 2026) | Doc 09, action 2 | High | 31 Dec 2026 | Open |
| 10 | No published community rules | Doc 09, action 3 | Medium | 31 Mar 2027 | Open |
| 11 | No member-facing "hidden identity" switch | Doc 09, action 7 | Low | 30 Jun 2027 | Open |
| 12 | CSV export for public stats not implemented | Doc 06, 6.5 #1 | Medium | 31 Mar 2027 | Done, 14 Oct 2026 |
| 13 | `docs/INSTALL.md`, `ENVIRONMENT.md` and `.env.example` not yet created; `ARCHITECTURE.md`, `API.md` and `DATA_MODEL.md` drafted in the evidence pack, to be copied into the repo | Doc 05, 5.4 | Medium | 31 Mar 2027 | Done, 14 Oct 2026: all six files are in qumanity-web |
| 14 | `Qumanity_Master.json` (village data) not yet published, for example as a Release asset, with its source and licence | Doc 05, 5.3 #3 | High | 31 Dec 2026 | Open |
| 15 | `QM_EARTH_ROOT` and other defaults point at the founder's Mac | Doc 05, 5.3 #2 | Medium | 31 Mar 2027 | Done, 14 Oct 2026: defaults are repo-relative (`./0_Earth`) |
| 16 | Firebase tooling still in qumanity-app (`functions/`, `tools/ops`, `firebase/`, `firebase.json`, `.firebaserc`), unused by the app | Doc 04, 4.6 #1 | Medium | 31 Mar 2027 | Open |
| 17 | Unreferenced images `earth3.jpeg` and `earth13.png` of unknown source | Doc 03, action 7 | Low | 30 Jun 2027 | Open |
| 18 | Website named a former steward (12 places in `home.html`, `about.html` and an `app.py` docstring) and calls Qumanity "non-profit stewarded" | Doc 03, action 2 | High | 31 Dec 2026 | Done, 15 Oct 2026 (e9d08e8): no page names the former steward or describes Qumanity as non-profit |
| 19 | White Paper and Technical Architecture cite `github.com/sitaram-box/QUMANITY` instead of the two submitted repositories | Doc 03, action 9 | Low | Next document versions | Open |
| 20 | Public birth-chart and kundali routes return a member's full chart and name by sequential user ID. De-anonymization chain (`/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>`, `/kundali/<id>`) | Doc 07, action 8 | High (was Blocking) | Before public flip | Done, 14 Oct 2026 |
| 21 | Unauthenticated admin action endpoint. Anyone can trigger a full database-to-folder sync without signing in (`POST /api/admin/sync-folders`) | Doc 07, action 9 | High (was Blocking) | Before public flip | Done, 14 Oct 2026 |
| 22 | Donation fields left from the payment code (`donation` in the register response, `max_donation`, the `topup` split in `/api/qoins/preview`) | `docs/API.md` | Low | 30 Jun 2027 | Done, 14 Oct 2026: removed from every response (the unused `TOPUP_SPLIT`, `topup_split` and `MAX_DONATION` remain in `qoin_core.py`) |
| 23 | `/api/country/stats/<id>` and `/api/continent/stats/<id>` return demographic counts without small-count suppression | Doc 06, 6.5 #5 | Medium | 31 Mar 2027 | Open |
| 24 | The public qumanity-app repository had no `LICENSE` file and still contained the removed payment code (`mobile/src/components/Payment.tsx` and Razorpay calls) | Doc 02, 2.4; Doc 04, 4.6 #2 | High | Before submission | Done, 15 Oct 2026 (1689b23): the LICENSE is published and the payment code is removed |
| 25 | The home page footer said "All rights reserved" beside the AGPL-3.0 link | Doc 02, 2.4 | High | Before submission | Done, 17 Oct 2026 (45b2e4c): the footer reads "© 2026 Rohit Mudgal" |
| 26 | `total_humans` means "born here" on the country and continent routes and "lives here" on `/api/location/stats` | Doc 06, 6.2 | Low | 30 Jun 2027 | Open |
| 27 | The subcontinent, location-elements, global-elements, India-scoreboard and Earth routes returned person counts (and percentages) without suppression, and location stats returned members' karma and Qoin totals for groups under five | Doc 06, 6.5 #6 | High | 31 Dec 2026 | Done, 17 Oct 2026 (265a2f4, 57bafba) |
| 28 | `docs/ELECTION_PILOT.md` lists 500 demo Private IDs, and the seed script documents their shared PIN. Those accounts are not present in production; the list is a plan for local election testing. The 50 live board-test accounts share a PIN set in `scripts/seed_demo_voters.py`, but their Private IDs are not published; a signed-in demo account is not otherwise restricted | Doc 05, 5.2; Doc 07, 7.6 #10 | Low | 30 Jun 2027 | Open (disclosed) |
| 29 | Member counts are refreshed by a scheduled backfill, not updated live when a member moves | `docs/member_count_design.md` | Low | When the pilot passes 100 members | Open |
| 30 | `mobile/package.json` (qumanity-app) has no `author` field | Doc 03, 3.6 #1 | Low | Before submission | Done, 17 October 2026 (2bceb74) |
| 31 | Qmail attachments were served inline with the sender-declared content type and no file-type allowlist, so an HTML or SVG attachment could run script on qumanity.in | Doc 09, action 8 | High | Before submission | Done, 18 Oct 2026 (f1edd55): served as downloads with `nosniff`, with a 15-type allowlist enforced on upload |
| 32 | No automated browser-level regression test that the Qmail text renderer keeps `<script>` inert and `javascript:` links unclickable | Doc 09, action 9 | Medium | 31 Mar 2027 | Open |
| 33 | Qmail messages, attachments and council queue messages are kept indefinitely and a member cannot delete them | Doc 07, action 11 | High | 31 Dec 2026 | Open (to be delivered with row 2) |
| 34 | Abandoned Qmail drafts are never cleaned up automatically | Doc 07, action 12 | Low | 30 Jun 2027 | Open |
| 35 | A member writing to their village council is not told that the message stays with the seat and can be read by council heads elected later | Doc 07, action 13 | Medium | 31 Mar 2027 | Open |
| 36 | The member-facing route to submit an Admin query is not wired (`admin_queries_core.create()` exists; no route calls it). The asker can already read the replies (`GET /api/queries/mine/<id>`, row 44), but that view is in `/qmail`, which needs Qmail activated, so the submission work must also give a member without Qmail a way to open it | Doc 09, 9.4 | Low | 30 Jun 2027 | Open |
| 37 | A council cannot start a new conversation with a member; it can only reply. Needs a way to record a message as sent by the council (`sent_as_level`, `sent_as_location_id`, which do not exist yet) | `docs/QMAIL.md`, section 11 | Low | 30 Jun 2027 | Open |
| 38 | Council addresses above village are created and shown but cannot receive messages, because no elected councils exist above village | Doc 01, section 7; `docs/QMAIL.md`, section 11 | Low | When elected councils exist above village | Open |
| 39 | Council addresses are created only when the member-count recompute next runs, and only the manual backfill script runs it, so an address can lag the count | Doc 06, 6.2 | Low | 30 Jun 2027 | Open (related to row 29) |
| 40 | Attachments are stored as SQLite BLOBs, a prototype choice; move them to object storage if attachment volume outgrows SQLite | Doc 04, 4.3 | Low | If attachment volume outgrows SQLite | Open |
| 41 | The test scripts hard-code the founder's checkout path; four of them also read files through it | Doc 05, 5.3 #11 | Medium | 31 Mar 2027 | Open |
| 42 | The repository's `docs/API.md` (170 of 176 routes) and `docs/DATA_MODEL.md` (lists 67 tables and omits 10 of the 74 in a freshly migrated database; migrations to 018) do not cover the 18 October 2026 additions | Doc 05, 5.3 #10 | High | Before submission | Done, 18 Oct 2026 (065cecc): the repository's `docs/API.md`, `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` now match this pack's copies byte for byte (178 routes; 74 tables on boot plus 2 on first use; migrations 001–003 and 007–024) |
| 43 | `README.md`'s feature tour does not mention Qmail, council addresses or the Admin Panel | Doc 05, 5.3 #12 | Medium | Before submission | Done, 18 Oct 2026 (065cecc): a new README section covers all three and links `docs/QMAIL.md` and `docs/ADMIN_PANEL.md`. The same commit removed README statements that were no longer true (Doc 05, 5.2) |
| 44 | A member who wrote to their council, or sent the Admin a query, was notified of a reply but no route returned the reply text, so they could not read it; the notification also never cleared | Doc 07, 7.3 | High | Before submission | Done, 18 Oct 2026 (c09b91f): the sender reads their original with each reply's text and time (`GET /api/qmail/sent/council/<id>`, `GET /api/queries/mine/<id>`), never the action log, and opening it clears the notification |

## 10.3 Legal and entity gaps

| # | Action | Target date | Notes |
|---|---|---|---|
| 1 | Register Qumanity Lok LLP (Doc 03, action 3) | [founder to set] | MCA filing in progress |
| 2 | Sign the Copyright Assignment Deed (Doc 03, action 4) | [founder to set] | After LLP registration |
| 3 | File trademark applications for "Qumanity" and the logo (Classes 9, 42, 45) (Doc 03, action 5) | [founder to set] | After LLP registration |
| 4 | Transfer the domain qumanity.in to the LLP (Doc 03, action 6) | [founder to set] | After LLP registration |
| 5 | Publish the Privacy Policy under Qumanity Lok LLP | [founder to set] | After LLP registration. Until then, publish it under the current owner (10.2 #1) |
| 6 | Update the copyright notice in LICENSE and README to name the LLP | [founder to set] | After the assignment |

## 10.4 Repository public flip checklist

Applies to qumanity-web and qumanity-app. Status checked on 17 October 2026.

| # | Step | Status |
|---|---|---|
| 1 | Remove `DEMO_ACCOUNTS.md` and scrub it from git history (Doc 05, 5.3 #8) | Done: removed from the tree, added to `.gitignore` and scrubbed from git history (no commit touches it) |
| 2 | Scrub the founder's real Private ID from history (Doc 05, 5.3 #9) | Done: scrubbed from the tree and from history, and the live ID has been rotated |
| 3 | Confirm no real credentials remain in the current tree | Done: secrets scan clean |
| 4 | File a DMCA takedown notice so that GitHub purges the cached commit 0d73ea3 (`refs/pull/1/head`) (Doc 03, action 11) | Done: DMCA takedown notice filed with GitHub on 17 October 2026 (Ticket #4870732). |
| 5 | Copy `docs/dpg_evidence/` into the repo, without the working file `part2_sita_sweep.md` | Done, 15 October 2026 (6209f4f): the pack is in `docs/dpg_evidence/`, without `part2_sita_sweep.md` |
| 6 | Name the owner in both READMEs ("Copyright (C) 2026 Rohit Mudgal (individual)", Qumanity Lok LLP in registration), add `author` to `mobile/package.json`, and push the qumanity-app `LICENSE` (Doc 03, action 1) | Done: both READMEs name the owner and the qumanity-app LICENSE is published (15 October 2026), and the `author` field was added on 17 October 2026 (2bceb74) |
| 7 | Close the public kundali and zodiac routes (require sign-in and restrict to self), AND add sign-in plus admin check to `POST /api/admin/sync-folders` (10.2 rows 20 and 21). Both are hard gates: step 8 cannot start until both are done | Done, 14 October 2026: routes and admin sync gated |
| 8 | Flip both repositories to public | Done: both repositories are public |

## 10.5 DPG iteration plan

If the DPGA requests changes, or the annual review finds remaining gaps, this Forward Plan is the working document for iteration. It will be updated quarterly, and whenever a gap is closed. Each closed row records the date and the commit that closed it.

## 10.6 Long-term roadmap

- Full API reference as an OpenAPI specification, generated from the Flask URL map
- OWASP ASVS assessment
- WCAG 2.1 accessibility audit
- Community rules and grievance officer documentation
- Kiosk and offline-node pilot in one village
- Self-host the CDN scripts and fonts so the site makes no third-party requests (Doc 04, 4.6 #3, optional)
- Move both repositories to a Qumanity GitHub organisation once the LLP exists (Doc 03, action 10, optional)
