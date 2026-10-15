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

Status checked against the code on 14 October 2026.

| # | Gap | Source document | Priority | Target date | Status |
|---|---|---|---|---|---|
| 1 | Privacy Policy and Terms of Service pages not published (the registration link goes to `#`) | Doc 07, action 1 | High | 31 Dec 2026 | Open |
| 2 | No user-facing "export my data" or "delete my account" | Doc 07, action 2 | High | 31 Dec 2026 | Open |
| 3 | Village member names visible without sign-in | Doc 07, action 3 | High | 31 Dec 2026 | Open |
| 4 | Small-count suppression not implemented in stats endpoints | Doc 07, action 4; Doc 06, 6.5 #2 | High | 31 Dec 2026 | Done, 14 Oct 2026, for `/api/location/stats` (JSON and CSV). See row 23 |
| 5 | No minimum age or parental-consent gate | Doc 07, action 5 | Medium | 31 Mar 2027 | Open |
| 6 | No named grievance contact | Doc 07, action 6 | Medium | 31 Mar 2027 | Open |
| 7 | Non-Indian member compliance (GDPR) not assessed | Doc 07, action 7 | Medium | 31 Mar 2027 | Open |
| 8 | No "Report abusive content" feature | Doc 09, action 1 | High | 31 Dec 2026 | Open |
| 9 | No "Block member" feature | Doc 09, action 2 | High | 31 Dec 2026 | Open |
| 10 | No published community rules | Doc 09, action 3 | Medium | 31 Mar 2027 | Open |
| 11 | No member-facing "hidden identity" switch | Doc 09, action 7 | Low | 30 Jun 2027 | Open |
| 12 | CSV export for public stats not implemented | Doc 06, 6.5 #1 | Medium | 31 Mar 2027 | Done, 14 Oct 2026 |
| 13 | `docs/INSTALL.md`, `ENVIRONMENT.md` and `.env.example` not yet created; `ARCHITECTURE.md`, `API.md` and `DATA_MODEL.md` drafted in the evidence pack, to be copied into the repo | Doc 05, 5.4 | Medium | 31 Mar 2027 | Done, 14 Oct 2026: all six files are in qumanity-web |
| 14 | `Qumanity_Master.json` (village data) not yet published, for example as a Release asset, with its source and licence | Doc 05, 5.3 #3 | High | 31 Dec 2026 | Open |
| 15 | `QM_EARTH_ROOT` and other defaults point at the founder's Mac | Doc 05, 5.3 #2 | Medium | 31 Mar 2027 | Done, 14 Oct 2026: defaults are repo-relative (`./0_Earth`) |
| 16 | Firebase admin tooling still in qumanity-app (`tools/ops`, `firebase/`), unused by the app | Doc 04, 4.6 #1 | Medium | 31 Mar 2027 | Open |
| 17 | Unreferenced images `earth3.jpeg` and `earth13.png` of unknown source | Doc 03, action 7 | Low | 30 Jun 2027 | Open |
| 18 | Website named a former steward (12 places in `home.html`, `about.html` and an `app.py` docstring) and calls Qumanity "non-profit stewarded" | Doc 03, action 2 | High | 31 Dec 2026 | Partly done, 14 Oct 2026: no page names the former steward. Seven lines still describe Qumanity as stewarded by a non-profit organisation (`home.html` 68; `about.html` 108, 717, 843, 844, 948, 985) |
| 19 | White Paper and Technical Architecture cite `github.com/sitaram-box/QUMANITY` instead of the two submitted repositories | Doc 03, action 9 | Low | Next document versions | Open |
| 20 | Public birth-chart and kundali routes return a member's full chart and name by sequential user ID. De-anonymization chain (`/api/user/zodiac/<id>`, `/api/user/kundali/summary/<id>`, `/kundali/<id>`) | Doc 07, action 8 | High (was Blocking) | Before public flip | Done, 14 Oct 2026 |
| 21 | Unauthenticated admin action endpoint. Anyone can trigger a full database-to-folder sync without signing in (`POST /api/admin/sync-folders`) | Doc 07, action 9 | High (was Blocking) | Before public flip | Done, 14 Oct 2026 |
| 22 | Donation fields left from the payment code (`donation` in the register response, `max_donation`, the `topup` split in `/api/qoins/preview`) | `docs/API.md` | Low | 30 Jun 2027 | Done, 14 Oct 2026: removed from every response (an unused `topup_split` helper remains in `qoin_core.py`) |
| 23 | `/api/earth/stats`, `/api/country/stats/<id>` and `/api/continent/stats/<id>` return demographic counts without small-count suppression | Doc 06, 6.5 #5 | Medium | 31 Mar 2027 | Open |
| 24 | The public qumanity-app repository has no `LICENSE` file and still contains the removed payment code (`mobile/src/components/Payment.tsx` and Razorpay calls). The LICENSE and the removal exist only as uncommitted changes on the founder's machine | Doc 02, 2.4; Doc 04, 4.6 #2 | High | Before submission | Open |

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

Applies to qumanity-web and qumanity-app. Status checked on 14 October 2026.

| # | Step | Status |
|---|---|---|
| 1 | Remove `DEMO_ACCOUNTS.md` and scrub it from git history (Doc 05, 5.3 #8) | Done: removed from the tree, added to `.gitignore` and scrubbed from git history (no commit touches it) |
| 2 | Scrub the founder's real Private ID from history (Doc 05, 5.3 #9) | Done: scrubbed from the tree and from history, and the live ID has been rotated |
| 3 | Confirm no real credentials remain in the current tree | Done: secrets scan clean |
| 4 | Confirm GitHub Support has purged the cached commit 0d73ea3 (`refs/pull/1/head`) (Doc 03, action 11) | Not done: the GitHub Support purge was not pursued. Optional, residual step |
| 5 | Copy `docs/dpg_evidence/` into the repo, without the working file `part2_sita_sweep.md` | Pending: before submitting |
| 6 | Name the owner in both READMEs ("Copyright (C) 2026 Rohit Mudgal (individual)", Qumanity Lok LLP in registration), add `author` to `mobile/package.json`, and push the qumanity-app `LICENSE` (Doc 03, action 1) | Pending: neither README names the owner, and qumanity-app on GitHub has no LICENSE file (row 24 of 10.2) |
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
