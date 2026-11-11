# Summary of Changes — White Paper v3.0 (June 2026) → v4.0 (November 2026)

For the founder's records. Evidence column cites the file or code checked. Only changes actually made to the paper are listed.

## A. Planned features reclassified (no longer stated as present fact)

| # | v3.0 claim | Problem | v4.0 treatment | Evidence |
|---|---|---|---|---|
| 1 | Title: "Decentralized, Offline-First Governance Ecosystem" | Single central Flask/SQLite server; no offline mode | Removed from title; offline-first marked **[PLANNED]** | HANDOVER §2; no service worker or offline queue in web or app code |
| 2 | "Native iOS/macOS application for village kiosks… Swift/SwiftUI" | The app is Expo / React Native, cross-platform, not a kiosk app; no Swift code exists | "Cross-platform mobile app (Expo / React Native)", **[IN DEVELOPMENT]** | `Qumanity_App/mobile/package.json`; no `.swift` files |
| 3 | "Biometric authentication" (fingerprint and face) | No biometric authentication; sign-in is Private ID + PIN | **[PLANNED]** | PRODUCT_TRUTH_AUDIT C14, C24 |
| 4 | "Offline-first operation… actions queue locally" | Not built | **[PLANNED]** | as #1 |
| 5 | Marketplace, Justice Module, Health & Education services, Voice Interface | No backend code for any | **[PLANNED]**; restorative-justice section labelled planned | AUDIT C22, C27 |
| 6 | PLNN presented as the existing foundation | Not built; one central server | **[PLANNED]**, with an explicit "No part of PLNN is built yet" | HANDOVER §2 |
| 7 | Village kiosks as how citizens use the system | No kiosk exists | **[PLANNED]**; kiosk Agent role marked design goal | AUDIT C15, C16 |
| 8 | "Immutable ledger of every vote, ethical action, and community decision" | Karma entries are recorded individually, but there is no tamper-evident ledger and "every vote" is not on a public ledger | Sentence removed; tamper-evident design moved to **[DESIGN GOAL]** | `docs/karma.md` |
| 9 | "Every action recorded, every ledger public" | Overstated | "Recorded and visible to the community it affects" | — |
| 10 | "Quantum Information Theory" as a foundation; "Blockchain" keyword | No quantum technology; not a blockchain | Quantum stated as a metaphor only; both keywords removed | AUDIT C17 |
| 11 | Phase 9 "Quantum OS… conscious AI layer" | No work started | "Long-term research aspiration; no work started" | — |

## B. Claims corrected to match the code

| # | v3.0 claim | Reality | v4.0 | Evidence |
|---|---|---|---|---|
| 12 | "Points convert to Qoins" | Karma is never converted to Qoins (founder decision, 2026-09-29) | Karma and Qoins described as separate; Karma is never money | `docs/karma.md`; HANDOVER §1 |
| 13 | Karma value table in ₹ (plant a tree ₹10, teach ₹20…) | No verification workflow; nothing pays these | Moved to "verified-service Karma [DESIGN GOAL]"; real Karma sources described | `karma_core` |
| 14 | "Non-inflationary; fixed denominations; weekly settlement" | No such mechanism | Removed | — |
| 15 | PostgreSQL (production) | Code uses SQLite; PostgreSQL migration is planned | SQLite today, PostgreSQL planned | `db.py`; HANDOVER §2 |
| 16 | "A district-level pilot is underway"; Phase 5 "District-level kiosk deployment — Underway" | One village (Rohini Sector 24), no kiosks | "Village-level pilot", one village | `election_core.PILOT_VILLAGE_ID` |
| 17 | Voters: "members of the current elemental cycle (Fire, Earth, Air, Water)" | Voters are residents born under the cycle's sun sign | Corrected | `election_core.voting_eligible()` |
| 18 | Nominees "Yuvak life stage (25–49)" | Code allows ages 25–60 (Yuvak or Vridh), requires Karma ≥ 200 and male/female | Corrected; glossary note added | `election_core.nomination_eligible()` |
| 19 | "Five leadership roles per council" | Only Nayak and Nayika exist, in one village | Role table marks Mentor, Manager and Agent as design goals (names kept as in the paper) | AUDIT C28 |
| 20 | Eight levels listed without Zone, counting "Citizen" as a level | Geography includes Zone between State and Country | Levels now Village → Tehsil → District → State → Zone → Country → Continent → Earth | HANDOVER §4 |
| 21 | "Public ID" for the present-location key | Product calls it Account ID | Renamed, with a note | HANDOVER §9.3 |
| 22 | "12 Indian languages" | English plus 12 Indian languages (13-language interface) | Corrected | `static/locales/`, HANDOVER |
| 23 | Marketplace "using Karma Points" | Karma is not currency | Changed to Qoins; status planned | `docs/karma.md` |
| 24 | Access and erasure promised unqualified | Self-service export and deletion not built | Status column: Access partial, Erasure planned | HANDOVER §5 |
| 25 | Repository "github.com/sitaram-box/QUMANITY"; "docs/technical-architecture/" | Actual remote is `qumanity-web`; docs are in `docs/ARCHITECTURE.md` | Updated | `git remote -v` |
| 26 | Roadmap Phase 3 "Next", Phase 4 "Planned" | Dashboard and the app are further along | Statuses updated | HANDOVER §0.H |
| 27 | Qoins origin not described | Qoins are minted via registration, referrals and rising board posts; not purchased | Described per the repo white paper | `docs/QUMANITY_WHITEPAPER.md` |

## C. Founder decisions applied

| # | Change |
|---|---|
| 28 | **Author** changed to "Rohit Mudgal (Founder, Qumanity)". |
| 29 | **All mentions of SITA Foundation / Sekyor Intelligence Tantra Foundation removed** (cover, abstract, executive summary, former section 10.4, glossary, references, keywords). Former 10.4 is now "Stewardship" and names the founder. |
| 30 | **Section 6, the Quantum Spiritual Interface, removed entirely**, with its feature-table row and every other reference to it (it had none in the abstract or glossary). All content naming deities or faith traditions as part of that feature went with it. Sections renumbered; the table of contents has no QSI entry. |
| 31 | **Section 4.6 pilot status** filled with the founder's wording: one council seated; simulated demo voters. |
| 32 | Role names kept as the paper's (Mentor, Nayak, Nayika, Manager, Agent). |
| 33 | Repository URL set to `github.com/sitaram-box/qumanity-web`. |

## D. Content added from the repo white paper (`docs/QUMANITY_WHITEPAPER.md`, 2 Nov 2026)

| # | Addition |
|---|---|
| 34 | Q-Punch implementation boundary: council addresses reachable at village level only (§4.3) |
| 35 | Q-Map section (§5.5) and Crowdsourced Location System section (§5.6) |
| 36 | New §8: AGPL-3.0 licence, DPG Standard as internal self-assessment, **not certification**, responsible-use principles, social impact stated as design goals |
| 37 | Motivation disclaimer at the end of §3 and a statement that Qoins and Karma are not financial instruments or voting weight |
| 38 | Technology stack aligned (Leaflet, OpenStreetMap, JSON master data) |
| 39 | Table of contents added, renumbered sections 6–12 |

## E. Not imported from the repo white paper

The repo white paper (2 Nov) contains a section on the **Multi-Religion Marquee**. HANDOVER §9.1 records that the owner discontinued the Marquee on 8 Nov 2026 and removed all religious-text content, so that section is out of date and was **not** imported.

## F. Left unchanged on purpose

Philosophy and Vedic framing (including the Rta, Ashrama and Vasudhaiva Kutumbakam references and the scholarly citations), sections 2 and 3, the vision statements, and the Bohr & Heisenberg citation (labelled conceptual inspiration).

## G. Items checked and found not to apply to this paper

The paper never mentions quadratic voting, Q-Pay, a donation split, or "24 leaders per year", and it contains no village count. v4.0 adds "more than 635,000 villages" as the audited figure.

## H. Final decisions (founder, applied)

1. **Vedic framing kept.** The Vedic framing, the Upaniṣad, Ṛgveda and Manusmṛiti references and the motto "Vasudhaiva Kutumbakam" stay. Only the QSI feature was removed.
2. **DPG wording.** The paper says Qumanity is "built for the Digital Public Goods (DPG) Standard" (§8.2) and the keyword reads "Digital Public Goods Standard". Nowhere does it imply certification. The sentence "It is not a claim of formal certification. Qumanity has not represented itself as having received Digital Public Goods Registry acceptance" is kept. The pitch one-pager's feature 3 is now "Built for the Digital Public Goods Standard", with "(not yet certified)" added, and the deck no longer suggests a DPG badge.
3. **Role names.** The paper's names (Mentor, Nayak, Nayika, Manager, Agent) are used. The About page was not changed. It lists Technology Head, Welfare Officer and Spiritual Mentor and can be aligned later.
4. **SSRN revision.** At the event, say "an updated version is in review". Send the corrected PDF directly if asked.
