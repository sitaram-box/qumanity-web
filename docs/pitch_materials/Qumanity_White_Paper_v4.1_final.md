# QUMANITY
## A Governance Protocol for Transparent Civilization
### Implemented Foundation and Design Goals — for India and the World

| | |
|---|---|
| **Author** | Rohit Mudgal (Founder, Qumanity) |
| **Date** | November 2026 |
| **Version** | 4.1 (revision of v4.0, November 2026) |
| **Website** | https://qumanity.in |
| **Repository** | github.com/sitaram-box/qumanity-web |
| **Licence** | GNU Affero General Public License v3.0 (AGPL-3.0) |
| **Email** | founder@qumanity.in |
| **Classification** | Public |

*Technical documentation is maintained in the repository (`docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATA_MODEL.md`, `docs/HANDOVER.md`).*

**Revision note.** Version 3.0 described several planned capabilities in the present tense; v4.0 separated what is built from what is designed. **v4.1 (November 2026)** records two changes since v4.0: the Android mobile app has moved from in development to released, downloadable at qumanity.in/app (iOS remains in development); and village-level council elections have been extended by a Q-Punch cascade — 8-seat elemental councils from Tehsil to Earth, a quarterly rotating Head, and an Upper House People's Vote — which is now implemented and covered by automated tests, though it has not yet been run as a real election on a live population above village level (see §4.6, §6, and §9's new Phase 5a). Every capability is marked with one of four statuses:

- **[IMPLEMENTED]** — working in the live system today.
- **[PILOT]** — working, but run in a single village and not yet generally available.
- **[IN DEVELOPMENT]** — being built.
- **[PLANNED]** / **[DESIGN GOAL]** — designed, described and intended, but not yet built.

---

## Table of Contents

- Abstract
- 1. Executive Summary
- 2. Introduction
- 3. The Governance Crisis
- 4. The Qumanity Solution
  - 4.1 Core Principles
  - 4.2 Four Timelines
  - 4.3 Nested Governance: Village → Earth
  - 4.4 Dual-Key Identity
  - 4.5 Karma and Qoins
  - 4.6 Zodiac-Based Elections and the Q-Punch Cascade
- 5. System Architecture
  - 5.1 Three Ecosystem Layers
  - 5.2 High-Level Architecture
  - 5.3 Technology Stack Summary
  - 5.4 PLNN: Planetary Ledger Node Network
  - 5.5 The Q-Map
  - 5.6 The Crowdsourced Location System
- 6. Key Features
- 7. Data Privacy and Ethics
- 8. Open Source, the DPG Standard and Responsible Use
- 9. Implementation Roadmap
- 10. Conclusion and Call to Action
- 11. Glossary
- 12. References

---

## ABSTRACT

Human civilization stands at a critical juncture. Despite unprecedented technological and material progress, governance systems at every level, from villages to nations, remain plagued by corruption, opacity, inequality, ecological destruction, and the manipulation of democratic processes. These failures are not accidental; they are structural consequences of centralized, unaccountable power.

This white paper introduces Qumanity, a governance protocol and civic platform designed to address these systemic failures by embedding transparency, accountability, and participatory decision-making into the architecture of governance itself. It draws conceptual inspiration from Vedic principles of nested self-governance and from the idea of interconnectedness found in quantum science. It uses no quantum technology; the name is shorthand for Quantum + Humanity.

The platform organizes civic life into four timelines — Private, Personal, Public, and Global **[IMPLEMENTED]** — that allow individual reflection to escalate into collective action. A nested governance structure (Village → Tehsil → District → State → Zone → Country → Continent → Earth) ensures that decisions are made at the appropriate scale **[IMPLEMENTED as nested geography and Collective Boards at every level; council elections themselves are a one-village pilot at village level, with the 8-seat elemental cascade architecture from Tehsil to Earth now built and tested but not yet run as a real election above village level]**. Each member holds a dual identity: a Private ID anchored to birth location and an Account ID anchored to present location **[IMPLEMENTED]**. A transparent Karma ledger records verified positive actions **[IMPLEMENTED in part; see Section 4.5]**.

Today Qumanity is delivered as a public website (qumanity.in) offering registration, boards, a family tree, internal messaging, a map, and live statistics **[IMPLEMENTED]**, with an Android mobile app **[IMPLEMENTED]** downloadable at qumanity.in/app (an iOS app is **[IN DEVELOPMENT]**). The wider ecosystem — village kiosks, biometric authentication, offline-first operation, a Planetary Ledger Node Network (PLNN), marketplace, justice, health and education modules, and a voice interface — is the project's **design goal** and is not yet built.

The system is built with Flask and SQLite and is open-source (AGPL-3.0) and auditable; any community can adopt and adapt it. This paper presents the philosophical foundations, the architecture as it exists, the implementation roadmap, and the future vision. It concludes with an invitation to collaborate.

**Keywords:** Governance, Participatory Democracy, Karma, Transparency, Civic Technology, Open-Source, Vedic Philosophy, Digital Public Goods Standard, Qumanity, India

---

## 1. EXECUTIVE SUMMARY

### The Governance Crisis and the Qumanity Solution

Across every scale of human organisation — from the individual to the planet — governance has failed structurally. Power is centralized. Decisions are opaque. Accountability is absent. Citizens vote once every few years and then wait in silence while public funds vanish, communities fracture, and ecosystems collapse. The crisis is not a lack of technology; it is a lack of transparent, participatory, self-correcting governance.

Qumanity (Quantum + Humanity) is a governance protocol — not another platform — developed by its founder. Its goal is to restore transparency, participation, and self-rule through shared public infrastructure: dual-key identities, nested community boards, a transparent record of ethical action, and, as a design goal, village kiosks.

Five ideas define the protocol:
1. **Four Timelines** (Private, Personal, Public, Global) that separate lifelong identity from present governance **[IMPLEMENTED]**.
2. **Nested Governance** from Village to Earth across eight levels **[IMPLEMENTED as geography and boards; village-level councils are a one-village PILOT, extended by an 8-seat elemental council cascade from Tehsil to Earth that is IMPLEMENTED architecturally but has not yet run a real election above village level]**.
3. **Dual-Key Identity** — a birth-based Private ID and a location-based Account ID **[IMPLEMENTED]**.
4. **A Karma ledger** that records verified actions and is kept separate from money **[IMPLEMENTED in part]**.
5. **Zodiac-Based Elections** held in monthly cycles at village level **[PILOT in one village]**, now extended into a cascading 8-seat elemental council from Tehsil to Earth with a quarterly rotating Head and an Upper House People's Vote **[IMPLEMENTED architecture; PILOT not yet run above village level]**.

Two interfaces serve citizens: a website for public transparency, registration and daily participation **[IMPLEMENTED]**, and an Android mobile app that uses the same backend **[IMPLEMENTED]**, downloadable at qumanity.in/app (an iOS app is **[IN DEVELOPMENT]**). A distributed Planetary Ledger Node Network (PLNN) and offline-first village kiosks are the long-term infrastructure vision **[PLANNED]**.

**Status.** Qumanity is live at qumanity.in. Registration, nested geography covering more than 635,000 villages across 10 countries of the Indian sub-continent, the Karma ledger, Collective Boards, the Family Tree and a 13-language interface (English plus 12 Indian languages) are operational. A zodiac-cycle council election is being piloted in one village (Rohini Sector 24, Delhi), and the cascading 8-seat elemental council architecture above it — Tehsil through Earth, with a quarterly rotating Head and an Upper House People's Vote — is built and tested end to end, though no real population has yet elected a Tehsil-and-up council on it. The Android mobile app is live at qumanity.in/app; an iOS app, kiosks, biometrics, marketplace, justice module and national rollout are planned or in development.

> *"Vasudhaiva Kutumbakam" — The world is one family.*

Join us — as a citizen, developer, researcher, or partner — and help build governance infrastructure worthy of humanity.

---

## 2. INTRODUCTION

### 2.1 The Paradox of Progress

Humanity stands at an extraordinary threshold. We have mapped the genome, connected billions through digital networks, and sent instruments to the edge of the solar system. Yet alongside this progress runs an equally unprecedented crisis: poverty persists beside abundance, wars rage beside calls for peace, and ecological systems collapse beside pledges of sustainability.

We are more connected than ever — and more disempowered. The digital revolution promised democratisation. It delivered concentration: a handful of platforms now mediate how citizens speak, shop, learn, and even vote. Governance feedback loops that once operated through village assemblies now operate through algorithms no citizen can audit.

### 2.2 Structural Failure of Existing Governance

Today's dominant models share three structural defects:

- **Centralization of Power:** Decisions that affect a village are made in distant capitals and corporate headquarters. Citizens become subjects of systems they cannot see, let alone shape.
- **Opacity:** Public budgets are published as documents no one reads. Procurement happens behind closed doors. Trust erodes not because people are cynical, but because verification is impossible.
- **Disconnection:** Raise a grievance today; receive a reply in months — if ever. Elections occur every few years; communities live every day. The temporal mismatch between governance and life is the silence in which corruption grows.

### 2.3 The Need for a New Paradigm

The design principles Qumanity sets itself:

| Principle | Description |
|---|---|
| Decentralized | Power nested locally, from the village upward. |
| Transparent | Actions recorded and visible to the community they affect. |
| Participatory | Continuous engagement, not episodic elections. |
| Self-Correcting | Communities vote, escalate, and rotate leadership. |
| Temporal | Governance rhythms aligned with natural cycles, not political convenience. |

India has been the cradle of Dharma, Karma, and Democracy for millennia. The gram sabha predates the nation-state. The concept of Rta — cosmic and social order maintained through righteous conduct — predates the algorithm.

### 2.4 Introducing Qumanity

Qumanity draws on Vedic wisdom and on the idea, from quantum science, that reality is relational. From Vedic tradition it takes nested self-governance, the accountability of Karma, the life stages of Ashrama, and the cosmic order of Rta. From quantum science it takes only a *metaphor* — that every action is connected to every other. The name reflects an organizing idea: a transparent, nested record of people, time, and place. It is not a claim about quantum computing, and the system does not use quantum computing, quantum cryptography, or any quantum hardware.

Qumanity is intended as a protocol, not a platform. Like the Internet Protocol defines how data moves without owning the networks, Qumanity aims to define how citizens govern and account for ethical action — without owning the communities that adopt it.

> *"Qumanity is not a product. It is a promise — that technology can serve humanity, not exploit it."*

---

## 3. THE GOVERNANCE CRISIS

### 3.1 Individual Level
At the individual level, citizens lack a persistent voice. Between elections — often years apart — there is no formal channel to raise concerns, track outcomes, or hold representatives accountable. Poverty is reinforced by digital exclusion: those without smartphones, literacy, or connectivity are locked out of the services that increasingly define civic life.

Community service — teaching children, planting trees, caring for elders — goes unrecognised because no ledger records it. The individual is connected to the world through a screen, yet disconnected from the decisions that shape their daily existence.

### 3.2 Local Level
At the village and town level, corruption thrives where transparency is absent. Public funds are difficult to track. Middlemen intercept resources intended for the poorest. Communities fracture along caste, party, and family lines — partly because no shared system aligns incentives around collective welfare.

Environmental degradation accelerates when local stewardship is disconnected from local governance. Rivers are polluted, forests cleared, and commons depleted — with no accountable ledger linking action to consequence.

### 3.3 National Level
At the national level, electoral cycles are too infrequent to reflect ongoing community needs. Stolen elections, voter manipulation, and media distortion erode the foundation of representative democracy. Inequality widens in both income and voice — the wealthy access power; the poor access none.

Even when elections are free, governance between elections is not. Trust in institutions erodes because institutions demonstrate accountability only during campaigns.

### 3.4 Global Level
At the global level, war persists across regions with no planetary mechanism for transparent resolution. Climate change accelerates while data remains fragmented across agencies that do not share a common ledger. Biodiversity loss proceeds unchecked. International institutions issue commitments that no village can verify and no citizen can enforce.

Surveillance capitalism treats eight billion humans as data products — profiled, targeted, and monetised without consent.

### 3.5 Root Cause
Across every scale, the root cause is identical: **opaque, centralized, unaccountable governance.**

### 3.6 The Cost
The cost of this failure is measured in human suffering (poverty, displacement, violence), ecological collapse (climate disruption, species extinction, resource depletion), and social fragmentation (polarisation, distrust, the death of community). These are not separate crises. They are symptoms of a single structural failure — and they demand a structural response.

*Sections 2 and 3 state the motivation for the design. They are not a claim that every existing platform is deficient, and not a claim that Qumanity has solved these problems at scale. It has not.*

---

## 4. THE QUMANITY SOLUTION

### 4.1 Core Principles

| Principle | Meaning | Status |
|---|---|---|
| Decentralization | Governance nested from village to planet; power and value remain local | Nested structure **[IMPLEMENTED]**; distributed infrastructure **[PLANNED]** |
| Transparency | Community decisions are recorded where the affected community can see them | Boards, posts and scores **[IMPLEMENTED]**; a public ledger of every vote and transaction **[DESIGN GOAL]** |
| Participation | Continuous engagement through posts, elections, karma, and collective boards | **[IMPLEMENTED]**; elections **[PILOT]** |
| Self-Correction | Community scores determine escalation; failed posts archive; councils rotate monthly | Escalation and archive **[IMPLEMENTED]**; rotation **[PILOT]** |

### 4.2 Four Timelines: Private → Personal → Public → Global **[IMPLEMENTED]**

Every citizen navigates four distinct timelines — accounts that separate identity, relationships, governance, and planetary consciousness:

| Timeline | Anchored To | Purpose (today) | Purpose (design goal) |
|---|---|---|---|
| Private | Birth location | Lifelong identity, Qoin wallet, messages, personal history | — |
| Personal | Family and social circle | Relationships, family tree, social connections | — |
| Public | Present location | Village board, council elections (pilot), council address | Marketplace, justice, health and education services |
| Global | Earth → Continent → Country | Planetary statistics, global collective board | — |

Birth identity is immutable; governance rights are anchored to where one lives. A citizen who migrates carries their Private timeline forever but joins a new Public timeline at their destination. The Public timeline is currently active in 10 countries of the Indian sub-continent; members elsewhere join through a Global Account, which has the Private, Personal and Global timelines.

### 4.3 Nested Governance: Village → Earth

Qumanity organises society into eight nested levels:

**Village → Tehsil → District → State → Zone → Country → Continent → Earth**

Every member, discussion, and governance mechanism is scoped to one of these levels.

**Collective Boards [IMPLEMENTED].** Each level has a Collective Board where residents post and vote. Concerns that earn positive support escalate through the levels — a village issue that resonates nationally can ascend toward the planet, validated by community votes at each stage. Concerns that fail to earn support are archived. The system aims to self-correct without censorship.

**Quantum Punch (Q-Punch) Councils [village Nayak/Nayika: PILOT, one village; Tehsil-to-Earth cascade: IMPLEMENTED architecture, not yet run on a real population; Mentor/Manager/Agent: remain DESIGN GOAL].** Q-Punch is Qumanity's council-addressing and participatory-governance mechanism: the means by which a location, not just an individual member, can be written to and represented. The design gives each level a council with five leadership roles:

| Role | Function | Status |
|---|---|---|
| Nayak | Male elected leader (village level) | **[PILOT]**, one village |
| Nayika | Female elected leader (village level) | **[PILOT]**, one village |
| Mentor | Ethical guidance for the council | **[DESIGN GOAL]** |
| Manager | Day-to-day operational administration | **[DESIGN GOAL]** |
| Agent | Kiosk operator; assists citizens with access and literacy | **[DESIGN GOAL]** (depends on kiosks) |

Above the village, the Nayak/Nayika seats are superseded by a different, already-built structure: an 8-seat elemental council (one Male and one Female seat per Fire, Earth, Air and Water) at every level from Tehsil through Earth, with leadership rotating quarterly among the four elements and an Upper House People's Vote standing above every council as a sovereign check. See Section 4.6 for the full mechanics — the cascade is implemented and covered by automated tests, but has not yet been run as a real election above village level.

**Implementation boundary.** The village-level Nayak/Nayika election is a real, running pilot in one location (Rohini Sector 24, Delhi). The Tehsil-to-Earth cascade exists in the live system — any location at those levels can open a Q-Punch council election and see its own 8-seat ballot, quarterly rotation and People's Vote — but no such election has yet been run with that location's real resident population; it has only been exercised in testing and demonstration. A council address (a way to write to a location's council through Qmail) is reachable at village level only; this is unrelated to the cascade's own readiness and is tracked as separate, later work. Mentor, Manager and Agent remain design goals, not built, at any level.

### 4.4 Dual-Key Identity **[IMPLEMENTED]**

Every member holds a Qumanity Identity (QID) with two keys:

| Key | Basis | Changes? |
|---|---|---|
| Private ID (9 digits, with a 5-character PIN) | Birth location | Never — lifelong anchor of accountability |
| Account ID | Present location | Yes — updates, with council approval, when the member relocates |

The Private ID ensures that karma, history, and accountability persist across a lifetime. The Account ID ensures that voting rights, council eligibility, and local board membership reflect where one actually resides. No email address is required to register. Identity is rooted in place, not in a corporate database.

*Note: v3.0 called the second key the "Public ID". The product now calls it the Account ID.*

**The Q-Card [scan-to-login backend IMPLEMENTED; physical card PLANNED].** A forthcoming physical card carries a QR code that resolves straight to a member's own sign-in screen, so a shared or borrowed phone need not have a 9-digit Private ID typed into it. The QR code deliberately never encodes the Private ID, the Account ID, or anything else identifying — only a long, random, unguessable token, and the database stores a one-way hash of that token rather than the token itself. Scanning the card resolves to an account; the PIN is still required to sign in. A lost or damaged card is revoked and replaced from the admin side, and the old card's token is refused the moment a replacement exists for it, never quietly honoured alongside the new one. The scan-to-login backend and the admin issuance/pricing/revocation workflow are built; the printed card itself and batch generation are not yet built.

**Family-verified account recovery [IMPLEMENTED].** A member locked out of their account — PIN forgotten, device lost — can be restored by a nuclear family member already on the platform: a parent, child, sibling or spouse, confirmed against the real relationship graph in that member's own Family Tree (Section 6), not a self-declared claim. Grandparents and grandchildren are deliberately excluded from this channel — close enough to appear in the tree, but not close enough to vouch for someone's identity. The verifying relative approves or denies the request; approval issues a new PIN to the locked-out member without ever exposing it to the verifier.

### 4.5 Karma and Qoins

**Qoins [IMPLEMENTED].** Qoins are a civic-service-earned unit recorded in each member's own wallet. They are minted through defined platform mechanics (such as registration and referral activity, and board posts that rise through the levels). They are not purchased, not traded on an open market, and not convertible to external currency in the current implementation. The platform does not sell them.

**Karma [IMPLEMENTED in part].** Karma is a separate recognition and accountability score. It is **never money and is never converted to Qoins**; this separation is an explicit design decision. Each Karma entry is recorded individually; a member's total is always the sum of their entries, never an editable number.

Karma comes from two sources today:
- **Commercial:** star ratings (1–5) of a real local business, given by a member of the same village.
- **Non-commercial:** a village-level Collective Board post that freezes with a positive score.

A location also carries a **collective Karma** score, raised when a post that has risen beyond the village freezes positively. Individual Karma totals are shown on a member's own account and next to election candidates. In the election pilot, a minimum Karma score of 200 is a condition of candidacy (Section 4.6); neither Karma nor Qoins functions as a financial instrument or as voting weight.

**Verified-service Karma [DESIGN GOAL].** v3.0 listed actions such as planting a tree, teaching for an hour, helping an elder, serving on a village council or cleaning a village area, with set values. These are intended examples. The council-verification workflow they require is not yet built, and no values are paid out for them today.

**Ledger integrity [DESIGN GOAL].** The ledger is transparent and entry-based today. A tamper-evident design (for example a hash-chained audit trail) is planned and is not implemented. This document makes no claim about future tokenomics, rewards, or exchange value.

### 4.6 Zodiac-Based Elections and the Q-Punch Cascade **[Village level: PILOT — one village. Tehsil-and-up cascade: IMPLEMENTED architecture, not yet run on a real population]**

Council elections are designed to occur every zodiac month, aligned with the sun's journey through twelve solar months (Aries to Pisces). In the live pilot (Rohini Sector 24, Delhi) each sign's cycle has an 8-day nomination window followed by a 14-day voting window, electing one Nayak and one Nayika.

| Feature | Description |
|---|---|
| Regular | Citizens always know when the next election occurs |
| Predictable | The calendar is astronomical, not political |
| Fair | Only residents born under the current cycle's sun sign may vote, which limits bloc manipulation |

**Eligibility, as enforced in the pilot:**
- *Voters:* residents of the pilot village, aged 5 or over, born under the cycle's sun sign.
- *Candidates:* residents of the pilot village, aged 25 to 60 (Yuvak or Vridh), born under the cycle's sun sign, with a minimum Karma score of 200, standing for the male or female seat.

**Pilot status.** A pilot election has been held in Rohini Sector 24, Delhi, with one council seated so far. The pilot uses simulated demo voters to test the election mechanics.

Leadership is designed to rotate with the cosmos so that no faction holds power indefinitely. Only one village has run a real election cycle on it.

**Above the village: the Q-Punch cascade [IMPLEMENTED architecture, not yet run on a real population].** Tehsil, District, State, Zone, Country, Continent and Earth each elect an 8-seat council — one Male and one Female seat per element (Fire, Earth, Air, Water) — in a single multi-year term rather than the village's monthly sign cycle (terms lengthen with scale, from 3 years at Tehsil to 15 years at Earth). Each term is split into four quarters, one element's pair leading at a time in Fire → Earth → Air → Water order; within a quarter, the Male candidate needs the approval of at least 51% of an Upper House ballot to hold the Head seat, defaulting to the Female otherwise. The electorate at each level (the "Lower House") is the full set of currently-serving council members from every location directly beneath it, computed live rather than stored. Sovereignty, though, sits above any single council: every location's own resident population (its "Upper House") can call a direct **People's Vote** on any question at any time, and a passed vote (at least 51% of ballots cast) is recorded as binding on that location's council — Head Approval is one standing, built-in instance of this general power, not the whole of it. This architecture is built and covered by automated tests; enforcing a passed People's Vote against a council's own decisions, and the Mentor/Manager/Agent roles below, remain separate, later work.

> *"Your body is made of five elements. Your soul resides in Space. Your actions are recorded in the elements."*

---

## 5. SYSTEM ARCHITECTURE

### 5.1 Three Ecosystem Layers

| Layer | Purpose | Audience | Status |
|---|---|---|---|
| Website | Registration, public transparency, boards, daily participation, national statistics | Everyone | **[IMPLEMENTED]** |
| Mobile app — Android (Expo / React Native) | Daily participation from a phone; a client of the website's API | Citizens | **[IMPLEMENTED]**, downloadable at qumanity.in/app |
| Mobile app — iOS (Expo / React Native) | Same, for iOS | Citizens | **[IN DEVELOPMENT]** |
| PLNN | Planetary Ledger Node Network — distributed data infrastructure | Infrastructure | **[PLANNED]** |

The website is the window, open to all. The mobile app is the daily instrument; it uses the same backend, identity, geography and consent model as the website and does not reimplement them. The Android build is released; the iOS build is in development. PLNN is the long-term foundation intended to keep data sovereign and available when connectivity fails.

### 5.2 High-Level Architecture

**Today:** a single Flask application and SQLite database serve the website and the Android mobile app through the same API (an iOS build is in development). Members sign in with a Private ID and PIN.

**Design goal:** citizens would interact through village kiosks, web browsers, or native apps. Above the interface layer, the protocol would enforce governance rules (timeline separation, nested escalation, karma verification, election cycles). Below, PLNN would distribute data across nested nodes — village, tehsil, district, state, nation, planet — so that no single server owns a community's information. A trust layer would ensure ledger integrity and encrypted private data.

```
Citizen Interfaces  (Web [LIVE] · Mobile app [Android LIVE · iOS IN DEVELOPMENT] · Kiosk [PLANNED])
        ↓
Qumanity Protocol  (Timelines · Governance · Karma · Elections)        [IMPLEMENTED; village elections PILOT, Tehsil+ cascade IMPLEMENTED/untested on a real population]
        ↓
PLNN               (Village → Tehsil → District → State → Nation → Planet)   [PLANNED]
        ↓
Trust Layer        (Encrypted private data · Public ledgers · Audit trail)    [DESIGN GOAL]
```

### 5.3 Technology Stack Summary

| Component | Technology (today) | Planned / design goal |
|---|---|---|
| Backend | Python, Flask | — |
| Database | SQLite | Migration to PostgreSQL |
| Web | Server-rendered Jinja templates, plain HTML, CSS and JavaScript; no front-end framework | — |
| Maps | Leaflet, OpenStreetMap data | Wider coverage |
| Geography data | Structured JSON master data across the eight levels | — |
| Mobile | Expo / React Native (iOS and Android) | Native kiosk client |
| Languages | English plus 12 Indian languages | — |
| Infrastructure | Cloud deployment, single server | Offline-capable local nodes |

Detailed schemas and APIs are documented in the repository (`docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DATA_MODEL.md`).

### 5.4 PLNN: Planetary Ledger Node Network **[PLANNED]**

PLNN is the proposed data-sovereignty layer — communities would own their data at the node level, not corporations or distant governments. Each geographic level would maintain a node that:

| Feature | Description |
|---|---|
| Local Storage | Stores governance data for its jurisdiction |
| Sync | Synchronises with parent and child nodes when connected |
| Offline-First | Citizens act locally; data syncs when connectivity returns |
| Audit Trail | Preserves a public audit trail without exposing private timeline data |

PLNN is not a blockchain for speculation. It is intended as infrastructure for trust — the governance equivalent of roads, electricity, and the postal system. **No part of PLNN is built yet;** the live system is a single central server.

### 5.5 The Q-Map **[IMPLEMENTED — pilot dataset]**

Q-Map is Qumanity's interactive geographical interface — a public page (`/qmap`) that renders real map data without requiring sign-in.

- The current map is a **North West Delhi pilot**: a bounded research area of roughly 25,000 mapped features (roads, buildings and hospitals), not a complete map of India or any other country.
- Roads, buildings and hospitals are independent, togglable layers, loaded from a locally stored OpenStreetMap-derived dataset rather than live external queries.
- Visible OpenStreetMap attribution is displayed, as the Open Database License requires. Qumanity does not claim ownership of the map data.
- For a signed-in member, Q-Map can also show that member's **own** GPS-based location and nearby matched map features (within a 200-metre radius). This requires explicit, recorded and versioned **consent**; a change in the consent terms requires fresh confirmation. This personal information is restricted to the member it belongs to, and raw GPS coordinates are never included in any public response.
- The public base map contains no personal data. Public visibility of the map is not access to any individual's location.

Expanding coverage beyond the pilot is a roadmap item, not a current claim.

### 5.6 The Crowdsourced Location System **[IMPLEMENTED]**

Any platform organized around real-world geography will meet places its canonical directory does not yet contain. Qumanity uses a bounded, three-layer fallback:

1. A member can register under a **provisional** location (a candidate village or tehsil not yet in the verified directory), alongside fully optional GPS observations.
2. Once a provisional location has a defined number of qualifying, genuinely present resident members (currently 24), it is promoted to **active** status **within the provisional-location system only**.
3. That is **not** the same as entering Qumanity's canonical geography file. Adding a place to the authoritative master directory, with a permanent identifier, remains a separate, human-reviewed step that the system does not perform automatically.

Geography identifiers are stable and load-bearing. They are not renumbered, reparented or deduplicated without an approved, reviewed process.

---

## 6. KEY FEATURES

| Feature | Description | Status |
|---|---|---|
| Collective Boards | Post, vote, escalate or archive at every level | **[IMPLEMENTED]** |
| Dual-Key Identity | Private ID + PIN, Account ID, no email required | **[IMPLEMENTED]** |
| Karma ledger | Entry-based reputation record, separate from money | **[IMPLEMENTED in part]** |
| Qoins | Internal civic currency earned through civic activity | **[IMPLEMENTED]** |
| Family Tree | Visual mapping of family relationships across generations, in the Personal timeline | **[IMPLEMENTED]** |
| Family-Verified Account Recovery | A locked-out member is restored by a nuclear family member (parent, child, sibling or spouse) confirmed in their Family Tree | **[IMPLEMENTED]** |
| Q-Card | Physical QR-code card for scan-to-login; token-hash privacy, no identifying data on the code | Backend **[IMPLEMENTED]**; physical card **[PLANNED]** |
| Qmail | Internal member messaging, including messages to a village council address | **[IMPLEMENTED]**; council addresses reachable at village level only |
| Q-Map | Public map with member-private proximity data | **[IMPLEMENTED]**, pilot dataset for North West Delhi |
| Crowdsourced locations | Provisional villages and tehsils, activated by resident count | **[IMPLEMENTED]** |
| Citizen Reports | Issue reports with a response timeline | **[IMPLEMENTED]** |
| Global Account | Registration for members outside the 10 Public Account countries | **[IMPLEMENTED]** |
| Multi-language interface | English plus 12 Indian languages | **[IMPLEMENTED]** |
| Zodiac-Based Elections | Monthly council elections by sun-sign cycle; Nayak and Nayika seats | **[PILOT]**, one village |
| Q-Punch Cascade | 8-seat elemental council from Tehsil to Earth; quarterly Head rotation; Upper House People's Vote | **[IMPLEMENTED]** architecture; not yet run on a real population |
| Mobile app — Android | Android app live and downloadable at qumanity.in/app | **[IMPLEMENTED]** |
| Mobile app — iOS | Same, for iOS | **[IN DEVELOPMENT]** |
| Marketplace | Village-level commerce using Qoins, keeping value in the community (Karma is not currency) | **[PLANNED]** |
| Justice Module (Restorative) | Councils facilitate dialogue, restitution and community healing | **[PLANNED]** |
| Health & Education Services | Community health records, teaching-hour verification, service coordination | **[PLANNED]** |
| Offline-First Operation | Kiosks and apps work without continuous internet and sync later | **[PLANNED]** |
| Village Kiosks | Shared public terminals for people without smartphones | **[PLANNED]** |
| Biometric Authentication | Fingerprint and face login at village kiosks | **[PLANNED]** |
| Voice Interface | Speak concerns in any supported language; routed to the right level | **[PLANNED]** |

Every feature, built or planned, shares one design principle: equal access. The intended end state is that a farmer without a smartphone can walk to a kiosk and be heard, a teacher earns recognition for every hour of instruction, and a council leader is elected by neighbours, not appointed by distant officials. Today, the first of these needs the kiosk work that is still ahead.

---

## 7. DATA PRIVACY AND ETHICS

### 7.1 Core Principles

| Principle | Commitment | Status |
|---|---|---|
| Data Sovereignty | Citizens and communities own their data; Qumanity is infrastructure, not a data broker | Commitment; node-level ownership **[PLANNED]** |
| Minimal Collection | Only data required for governance: identity, location, verified actions | **[IMPLEMENTED]** by design |
| Anonymization | Aggregated statistics never reveal individual Private timeline data | **[IMPLEMENTED]** for published statistics |
| Consent | Personal data shared across timelines only with explicit consent; GPS and map-matching use explicit, versioned consent | **[IMPLEMENTED]** |
| Access | Every citizen can view the data held about them | **[PARTIAL]** — own profile and activity are visible; a full data export is not yet built |
| Correction | Citizens can request correction of inaccurate records | **[IMPLEMENTED]** through council-approved change requests |
| Erasure | Personal data removed on verified request, subject to governance audit | **[PLANNED]** — self-service deletion is not yet built |

### 7.2 Data Classification

| Class | Examples | Visibility |
|---|---|---|
| Private | Birth identity, wallet, messages, personal history | Member only |
| Personal | Family tree, social connections, personal posts | Member and chosen connections |
| Public | Escalated board posts, council elections | Community at present location |
| Governance | Election results, karma verifications | Community and audit bodies; election history is currently restricted during the pilot |
| Aggregated | Village statistics, demographic charts, national trends | Public (anonymized) |

### 7.3 Ethical Safeguards

| Safeguard | Description |
|---|---|
| No algorithmic bias | Elections and karma verification are rule-based, not ML-scored |
| No surveillance | The platform does not track behaviour for profiling or targeting |
| No profit from data | No advertising, no data sales, no attention harvesting |
| No discrimination | All genders, castes, and faiths access the same governance rights at their location |

### 7.4 Restorative Justice Framework **[PLANNED]**

The proposed Justice Module follows restorative, not purely punitive, principles:

| Principle | Description |
|---|---|
| Voice | Every party affected by a harm speaks |
| Accountability | The responsible party acknowledges the harm |
| Restitution | Concrete action to repair damage (karma, service, community work) |
| Reintegration | The community supports return to good standing |
| Prevention | Escalated concerns inform policy at higher governance levels |

This framework draws on village traditions of panchayat mediation and the Vedic principle that Dharma is restored through righteous action, not merely punishment. No justice module exists in the current system.

---

## 8. OPEN SOURCE, THE DPG STANDARD AND RESPONSIBLE USE

### 8.1 Open source
Qumanity is released under the GNU Affero General Public License v3.0. The website and the mobile app are separate open repositories; the app is a client of the website's API.

### 8.2 The DPG Standard
Qumanity is **built for the Digital Public Goods (DPG) Standard**, and the project has produced an internal evidence pack assessing itself against each of the standard's indicators (licensing, documentation, privacy and security, data integrity, and rights review).

**This evidence work is internal self-assessment and preparation. It is not a claim of formal certification.** Qumanity has not represented itself as having received Digital Public Goods Registry acceptance or external endorsement. Known open gaps — including member-facing data export and deletion tools, and content-moderation (report and block) mechanisms — are tracked in the project's own forward plan.

### 8.3 Responsible-use principles
Principles that future development, including the mobile app, is expected to preserve:
- Geography identifiers are stable and are not changed without an approved, reviewed process.
- GPS and location collection is consent-based, versioned, and never reinterpreted under a changed consent policy.
- Access to personal location data requires authentication and is scoped strictly to the member it belongs to.
- Public map data and private member data are kept clearly separate.
- OpenStreetMap attribution and licence obligations are mandatory wherever its data is shown.
- Changes to the canonical geography are controlled and reviewed, not automated or silent.
- Implementation status is reported on an evidence basis: a feature is described as implemented, partial, piloted, or planned based on what the code and tests show, not on intention.

### 8.4 Social impact
Qumanity's goals are design-level: making civic participation more accessible at the village level, helping communities record their own needs in a durable way, connecting local information to larger structures, and supporting transparent, traceable participation. These are intended benefits and **design goals, not measured outcomes**. No formal, external impact evaluation has been conducted.

---

## 9. IMPLEMENTATION ROADMAP

| Phase | Scope | Status (November 2026) |
|---|---|---|
| 1: Website | Public site, registration, geography, about pages, national statistics | ✅ Implemented |
| 2: Backend | Posts, karma ledger, family tree, messaging, admin tools, core protocol | ✅ Implemented; continuing refinement |
| 3: Dashboard | Four-timeline dashboard, elections interface, council management | ✅ Implemented; real council management for the pilot village only — the Tehsil-to-Earth cascade UI is built but untested on a real population |
| 4: Mobile app | Cross-platform app (Expo / React Native) using the website API; later kiosk client and biometric authentication | 🟢 Android released; 🟡 iOS in development (biometrics: planned) |
| 5: Pilot | Village-level election pilot (Rohini Sector 24, Delhi) running; additional pilot villages and kiosk deployment next | 🟡 One-village pilot underway |
| 5a: Governance cascade | 8-seat elemental councils, Tehsil to Earth, with quarterly Head rotation and an Upper House People's Vote | ✅ Implemented and tested; 🟡 awaiting a real election above village level |
| 6: PLNN Nodes | Distributed nodes at state level; offline sync protocol | ⏳ Planned |
| 7: National | State-by-state expansion across India | ⏳ Planned |
| 8: Global | Continental and planetary nodes; international adoption | ⏳ Planned |
| 9: Quantum OS | Exploration of quantum-safe infrastructure and an ethical AI layer | ⏳ Long-term research aspiration; no work started |

**Ongoing, outside the phases:** wider Q-Map coverage (beyond the North West Delhi pilot, with the same sourcing and quality standards); controlled improvement of the canonical location data; and governance expansion above village level, now implemented as the Q-Punch cascade (Phase 5a) — the architecture is built and tested, but running it on a real, live population at Tehsil level or above is still ahead.

Each phase builds on the last. The website establishes public trust. The backend encodes the protocol. The dashboard empowers citizens. The app extends access to phones. The pilot tests the model in real villages. PLNN nodes would distribute sovereignty. National and global scaling extend the protocol. Phase 9 is a research direction for the decades ahead, not a commitment.

---

## 10. CONCLUSION AND CALL TO ACTION

### 10.1 Summary of the Argument
Governance has failed at every scale — individual, local, national, global — because it is opaque, centralized, and unaccountable. Qumanity responds with a single protocol: decentralized, transparent, participatory, self-correcting, and aligned with natural cycles. It is intended to be infrastructure — the governance layer the digital age forgot.

### 10.2 The Vision: A World Transformed
Imagine a world where every citizen has a persistent voice; every village has a transparent ledger; every good deed is recorded and recognised; every council rotates with the cosmos; and every nation nests inside a planetary consciousness that begins at the gram sabha.

This is not utopia. It is engineering — the same way roads, electricity, and clean water are engineering. The foundation of that engineering exists today; most of the structure remains to be built.

### 10.3 The Path Forward
The foundation is live at qumanity.in, and a village-level pilot is underway. What remains is substantial: finishing the iOS app (Android is live at qumanity.in/app), building kiosks for people without smartphones, extending pilots to more villages, running the Q-Punch cascade on a real Tehsil-and-up population for the first time, and earning the trust of communities. That requires more villages, more developers, more partners, and more citizens who refuse to be spectators.

### 10.4 Stewardship
Qumanity is developed and stewarded by its founder, Rohit Mudgal, as open-source public infrastructure. The project does not monetise citizen data, sell governance access, or claim authority over communities that adopt it.

### 10.5 How to Join

| Who You Are | What You Can Do |
|---|---|
| Citizen / User | Register at qumanity.in; participate in your village board |
| Developer | Contribute to the open-source code on GitHub |
| Researcher | Study governance, economics, ethics, or restorative justice through the platform |
| Mobile Developer | Help finish the iOS app (Expo / React Native) — Android is already live at qumanity.in/app |
| Pilot Partner | Help bring a council-election pilot to your village |
| Administrator | Once kiosks exist, operate a village kiosk or serve as a community Agent |
| Philanthropist | Fund pilot deployment, kiosk hardware, or connectivity for underserved villages |

### 10.6 Final Reflection
India gave the world the concept of Dharma — righteous order. It gave the world Democracy — rule by the people. It gave the world the verse that Qumanity carries as its north star:

> *"Vasudhaiva Kutumbakam" — The world is one family.*

Qumanity invites every citizen, on every continent, to live as though this were true — because governance, at last, could make it possible.

**Qumanity — For Humanity, Harmony & Peace.**

---

## 11. GLOSSARY

| Term | Definition |
|---|---|
| Account ID | The identity key tied to present location; updates on relocation (called "Public ID" in v3.0) |
| Ashrama | The four life stages in Vedic tradition, each with distinct duties and rights |
| Balak | The first Ashrama — student / learning phase (ages 0–24) |
| Dharma | Righteous order; the moral and cosmic law governing individual and collective conduct |
| Karma | Action and its consequences; in Qumanity, a reputation score recorded entry by entry. It is not money |
| Nayak | Male elected leader of a Quantum Punch Council |
| Nayika | Female elected leader of a Quantum Punch Council |
| PLNN | Planetary Ledger Node Network — proposed distributed data infrastructure (planned) |
| Private ID | The identity key tied to birth location; never changes. Used with a 5-character PIN to sign in |
| Q-Punch | Quantum Punch — Qumanity's council-addressing and participatory-governance mechanism |
| QID | Qumanity Identity — the dual-key system of Private ID and Account ID |
| Qoins | The platform's internal civic currency, earned through civic activity |
| Rta | Cosmic and social order; the principle that the universe operates by discernible, righteous law |
| Sanyas | The fourth Ashrama — renunciation / wisdom phase (ages 75 and above) |
| Vasudhaiva Kutumbakam | Sanskrit: "The world is one family" — the guiding philosophy of Qumanity |
| Vridh | The third Ashrama — elder / advisory phase (ages 50–75) |
| Yuvak | The second Ashrama — householder / working phase (ages 25–49) |

*In the live election pilot, candidates may be Yuvak or Vridh (ages 25–60).*

---

## 12. REFERENCES

- Mudgal, R. (2026). *Qumanity source code and technical documentation.* github.com/sitaram-box/qumanity-web (`docs/ARCHITECTURE.md`, `docs/HANDOVER.md`)
- Mahā Upaniṣad 6.72 — Vasudhaiva Kutumbakam (the world is one family).
- Ṛgveda 10.85 — Rta (cosmic order) as foundational principle.
- Chāndogya Upaniṣad — Pañca Mahābhūta (five elements) and the nature of existence.
- Kautilya. *Arthaśāstra* — Village-level governance and economic organisation.
- Manusmṛiti, Chapter 6 — Ashrama (four stages of life).
- Constitution of India, Article 243 — Panchayati Raj institutions and gram sabha.
- Constitution of India, Article 243G — Powers and responsibilities of panchayats.
- Gandhi, M. K. — Gram swaraj (village self-rule) as the foundation of democracy.
- Ambedkar, B. R. — Constitutional democracy and local self-governance.
- Bohr, N. & Heisenberg, W. — Quantum complementarity and the relational nature of observation (cited as conceptual inspiration only).
- Ostrom, E. (1990). *Governing the Commons* — Nested governance and community self-organisation.
- United Nations. (2015). SDG 16: Peace, justice, and strong institutions.
- India Digital Personal Data Protection Act, 2023 — Data protection framework.
- OpenStreetMap contributors. Copyright and licence: https://www.openstreetmap.org/copyright
