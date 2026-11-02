# Qumanity: A Digital Public Infrastructure for Nested Human Governance

*A high-level project white paper for partners, institutions, developers, and other
stakeholders — not a legal guarantee, a formal Digital Public Goods (DPG) certification, or a
promise of future implementation. Statements about what exists today are distinguished throughout
from statements about where the project intends to go.*

**Document status**: project overview, current as of 2 November 2026. Implementation details
change as the project develops; where this document states that something is implemented, that
reflects the state of the `qumanity-web` repository at the commit noted in its companion technical
documents (`docs/HANDOVER.md`, `docs/MASTER_STATUS.md`).

---

## Executive Summary

Qumanity — the name is literal shorthand for **Quantum + Humanity** — is a civic participation
platform designed to connect people, their communities, and their geography to a transparent,
nested structure of governance. It organizes participants around the real places they live, from a
single village up to a notional "Earth" level, and gives each of those levels a shared space to
post, discuss, and — where elections have reached that level — be represented by elected local
councils. The platform issues each member a verified identity, a small civic-service-earned wallet
(Qoins), and a recognition score (Karma) that is deliberately kept separate from that wallet. Its
long-term vision is a *nested governance* model in which local knowledge and local participation
connect upward into larger structures of representation and accountability, rather than being
disconnected from them. That full vision is a multi-year undertaking; what is described in this
document as *implemented* is the working foundation built so far, and what is described as
*planned* is the roadmap toward it — the two are kept explicitly distinct throughout.

---

## The Problem

Civic and governance platforms, where they exist at all, are often built around one of two
patterns: a single centralized system that serves an entire nation or region, with limited
mechanisms for ordinary residents to participate directly in representation, or a collection of
disconnected local tools — a community forum here, a municipal portal there — with no shared
structure connecting them to anything above the local level. Neither pattern is unique to any one
country or system, and this is not a claim that existing platforms are uniformly deficient; it is
simply the design problem Qumanity starts from:

- Governance systems can be highly centralized, with few accessible, transparent channels for
  day-to-day civic participation at the level where people actually live.
- Local knowledge — what a specific village or neighborhood actually needs — can be disconnected
  from the larger structures that make decisions affecting it.
- Public information and civic participation are often fragmented across systems that don't share
  a common geographical or organizational structure.
- Communities frequently lack digital infrastructure that reflects how they are actually organized
  — administratively, socially, and geographically.

These are framed here as general motivations for the project's design, not as a claim that
Qumanity has already solved them at scale.

---

## The Qumanity Vision

### Quantum + Humanity, and nested governance

The name reflects the project's organizing idea: a transparent, nested record of people, time, and
place — not a claim about quantum computing. The platform's structure mirrors how human
settlements are actually organized, nesting outward from the most local unit to the whole planet,
so that participation and representation can, in principle, flow from the bottom up rather than
only from the top down.

### Eight geographical levels

Every member, discussion, and governance mechanism in Qumanity is scoped to one of eight nested
levels:

1. **Village**
2. **Tehsil**
3. **District**
4. **State**
5. **Zone**
6. **Country**
7. **Continent**
8. **Earth**

This hierarchy gives the platform a common structure for organizing people, civic discussion, and
— as the governance layer matures — representation, so that a village-level conversation and a
country-level one share the same underlying geography rather than living in separate, incompatible
systems.

### Q-Punch councils and the current implementation boundary

**Q-Punch** is Qumanity's name for its council-addressing and participatory-governance mechanism —
the means by which a location, not just an individual member, can be written to and represented.
The long-term design envisions an elected council (one man, one woman, chosen through the
platform's zodiac-cycle election mechanism) at every one of the eight levels. **As implemented
today, this reachability is limited to the village level only** — the platform's own
configuration (`QPUNCH_REACHABLE_LEVELS`) explicitly restricts which level of council address can
actually receive a message, and only one village has so far run a real election cycle. Addresses
for higher levels are created and displayed once a location's member count crosses that level's
threshold, but cannot yet receive messages, because elected councils above the village level do
not yet exist. This is a clear distinction between the architectural vision (eight levels of
participatory governance) and the current, narrower implementation (one level, piloted in one
location).

### Qoins and Karma

Qumanity describes two internal concepts related to participation, each implemented only to the
degree described here:

- **Qoins** are a civic-service-earned unit recorded in each member's own wallet — minted through
  defined platform mechanics (such as registration and referral activity) rather than purchased,
  traded on an open market, or convertible to external currency in the current implementation.
- **Karma** is a separate recognition score reflecting community-recognized contribution (such as
  posts the community has voted to recognize). **Karma is deliberately never convertible to
  Qoins** — this separation is an explicit design decision, not an oversight.

Neither concept currently functions as a financial instrument, an investment, or a governance
voting weight; this document makes no claim about future tokenomics, rewards, or exchange value
beyond what is described here.

---

## The Technology Stack

Qumanity's current website is built on a deliberately simple, well-understood technology
foundation:

- **Python** as the programming language, with **Flask** as the web application framework.
- **SQLite** as the current relational database.
- Server-rendered **Jinja templates**, plain **HTML, CSS, and JavaScript** for the web interface —
  no front-end framework and no build step, which keeps the codebase approachable for new
  contributors.
- **Leaflet**, an open-source mapping library, for interactive maps.
- **OpenStreetMap (OSM)** data for the current mapping pilot (see "The Q-Map" below).
- Structured **JSON-based geographical master data**, organized by the eight-level hierarchy
  described above, as the single source of truth for place names and identifiers.

This architecture is the foundation the project's next client — a phone application — is designed
to build on, communicating with the same backend through the same API, rather than reimplementing
identity, geography, or governance logic independently. **The phone application has not yet been
released**; it is the next phase of the project, described further under Roadmap below.

---

## The Q-Map

**Q-Map** is Qumanity's interactive geographical interface — a public page (`/qmap`) that renders
real map data without requiring a visitor to sign in.

- The current map is a **North West Delhi pilot** — a defined, bounded research area, not a
  complete map of India or any other country. It currently covers roughly 25,000 mapped features.
- Roads, buildings, and hospitals are rendered as **independent, togglable map layers**, loaded
  from a locally stored OpenStreetMap-derived dataset rather than live external queries, which
  keeps the public page fast and avoids placing continuous load on third-party mapping
  infrastructure.
- The map carries visible OpenStreetMap attribution, as required by OSM's Open Database License
  (ODbL) — Qumanity does not claim ownership of the underlying map data, and the obligation to
  attribute it is treated as mandatory, not optional.
- For a signed-in member, Q-Map can additionally show that member's **own** GPS-based location and
  any OpenStreetMap features matched near it — but this is handled carefully:
  - GPS capture is subject to explicit user **consent**, recorded and versioned, and a change in
    the platform's consent terms requires a fresh confirmation rather than silently reinterpreting
    an older one.
  - Feature matching uses a defined **200-metre radius** around a member's own accepted location
    reading.
  - **Personal proximity information is restricted to the authenticated member it belongs to** —
    it is never exposed to another user, and raw GPS coordinates are never included in any public
    response or ordinary map popup.
  - **The public base map itself contains no personal data at all.** Visibility of the pilot map
    to the general public must not be confused with access to any individual's location — those
    are kept on opposite sides of Qumanity's sign-in boundary by design.

The North West Delhi pilot is explicitly a starting point. Expanding geographical coverage is a
roadmap item, not a current claim (see Roadmap below).

---

## The Multi-Religion Marquee

The **Marquee** is Qumanity's reading and content-presentation feature — a rotating display of
short devotional or reflective texts, built on a database architecture (four linked tables:
traditions, text collections, language editions, and individual text entries) designed to support
many religious traditions and languages, each gated by its own verified rights status.

A text collection is only ever shown to readers once it has been explicitly reviewed and marked
both rights-approved and eligible — there is no fallback to unverified or placeholder content. The
Marquee distinguishes original Qumanity-authored content (such as its own Hindi devotional poetry)
from externally sourced religious texts, and treats licensing, attribution, and explicit permission
as prerequisites for presenting any external text, not an afterthought.

**Currently available, with their licensing basis**:
- Christian tradition: the Psalms in English (King James Version) and a selection of eight Psalm
  verses in Hindi (Biblica's Open Hindi Contemporary Version, used under its CC BY-SA 4.0 license
  as a documented derivative excerpt — not a complete Bible translation).
- Muslim tradition: Surah Al-Fatiha of the Quran in Arabic, sourced from the Tanzil Project under
  its CC BY 3.0 license.
- Buddhist tradition: the opening verses of the Dhammapada in Pali and in the Max Müller 1881
  English translation (public domain).
- Hindu tradition: original Qumanity-authored Hindi devotional poetry, published by the project
  itself.

**Several other traditions and languages remain under active rights research and are not yet
available** in the live Marquee — including an Urdu translation of the Quran, Sikh Gurbani, a Hindi
translation of the Dhammapada, and Jain scriptural texts — each blocked specifically on verifying
source permissions, not on any remaining engineering work. A collection's availability in the
architecture never implies that its content has cleared rights review; the two are tracked and
reported separately.

---

## The Crowdsourced Location System

Any platform organized around real-world geography will encounter places its canonical directory
does not yet contain. Qumanity handles this with a deliberately bounded, three-layer fallback
rather than letting unverified submissions quietly become authoritative:

1. A member can register under a **provisional** location — a candidate village or tehsil not yet
   in the verified directory — alongside fully optional GPS observations.
2. Once a provisional location accumulates a defined number of qualifying, genuinely present
   resident members (currently 24), it is automatically promoted to **active** status **within the
   provisional-location system itself**.
3. That activation is explicitly **not** the same thing as being written into Qumanity's canonical,
   verified geography file. A provisional location becoming "active" makes it usable and visible
   within the platform's own provisional records; folding it into the authoritative master
   directory, with a permanent, stable identifier, remains a separate, deliberately human-reviewed
   step that the current system does not perform automatically.

This separation — an engaged, growing local presence being allowed to function, without silently
rewriting the platform's canonical record of places — is intended to let genuine local participation
help surface real gaps in geographical coverage, while protecting the reliability of data that the
rest of the platform (membership counts, governance scoping, council addressing) depends on
staying stable.

---

## The DPG Standard and Evidence

Qumanity has been designed with reference to the **Digital Public Goods (DPG) Standard** — the
nine-indicator framework used to assess whether a digital solution is open, reusable, and
responsibly built — and the project has produced an internal evidence pack assessing itself
against each indicator, covering areas such as:

- Open and reusable licensing (the project is licensed AGPL-3.0).
- Documentation of the architecture, API surface, and data model.
- Privacy and security practices, including the consent and access-control patterns described
  above.
- Data integrity and the controlled-change rules governing the platform's geographical identifiers.
- Licensing and rights review for any externally sourced content.

**This evidence work is internal self-assessment and preparation, not a claim of formal
certification.** Qumanity has not represented itself, in any of its own documentation, as having
received Digital Public Goods Registry acceptance or external endorsement from the Digital Public
Goods Alliance or any other certifying body. The evidence pack itself explicitly describes its own
periodic updates as internal correction passes, not resubmissions to any registry. A reviewer
examining the project should understand three distinct things: (1) the DPG principles the project
is designed to support, (2) the evidence currently documented in support of that, and (3) the gaps
that remain open and would need to be closed, and externally reviewed, before any formal
certification claim would be appropriate. Those open gaps — including publishing a privacy policy,
building member-facing data export/delete tools, and adding content moderation (report/block)
mechanisms — are tracked candidly in the project's own forward plan rather than omitted.

---

## Social Impact

Qumanity's intended, design-level goals are:

- Making civic participation more accessible at the village level, where many residents have the
  least existing digital infrastructure built around them.
- Helping communities represent their own local knowledge and needs in a structured, durable way.
- Connecting local geographical and civic information to larger administrative and governance
  structures, rather than leaving it isolated.
- Supporting transparent, traceable participation — every governance action in the platform's
  design is attributable and auditable, not anonymous by default.
- Providing a shared digital foundation that both local and higher-level institutions could, in
  principle, build on.

These are presented as **intended benefits and design goals**, reflecting what the platform is
built to enable, not as independently measured outcomes. Qumanity has not conducted a formal,
external impact evaluation, and this document makes no claim of having already transformed
governance outcomes at any scale.

---

## Roadmap

The following are **planned, future work** — explicitly not current functionality:

- **Phone application.** Build the project's next client application on the existing backend,
  reusing its established identity, geography, privacy, and consent model rather than
  reimplementing any of it independently.
- **Expanded geographical mapping.** Progressively extend Q-Map's coverage beyond the North West
  Delhi pilot, with the same sourcing, validation, attribution, and quality-control standards
  already applied to the pilot area.
- **Further Q-Map capability.** Add further mapping features and geographical coverage in
  controlled stages, rather than all at once.
- **More religious traditions and languages in the Marquee.** New collections will be added only
  after source verification, a licensing review, and explicit eligibility approval — never
  speculatively.
- **Continued geographical data quality work.** Ongoing, carefully controlled improvement of the
  canonical location hierarchy, without destabilizing the stable identifiers the rest of the
  platform depends on.
- **Governance expansion beyond the village level.** Extending Q-Punch council reachability, and
  running elections, above the village level is a substantial undertaking that will be pursued only
  through explicit design review, approval, and dedicated implementation — not assumed to follow
  automatically from the existing architecture.

---

## Architecture and Responsible-Use Principles

Principles that any future development on Qumanity — including the phone application — is expected
to preserve:

- Geography identifiers are stable and load-bearing; they are not renumbered, reparented, or
  deduplicated without an approved, reviewed process.
- GPS and location data collection is consent-based, versioned, and never retroactively
  reinterpreted under a changed consent policy.
- Access to personal location data requires authentication and is scoped strictly to the member it
  belongs to.
- Public map/content data and private member data are kept clearly separated.
- Religious and other externally sourced content is rights-gated before publication, never
  published speculatively.
- OpenStreetMap attribution and license obligations are treated as mandatory wherever OSM-derived
  data is shown.
- Changes to the canonical geography are controlled and reviewed, not automated or silent.
- Implementation status is reported on an evidence basis — a feature is described as implemented,
  partial, piloted, or planned based on what the code and tests actually show, not on intention
  alone.

---

## Sources and References

This document summarizes, and should be read alongside, the project's own technical and evidence
documentation:

- `docs/HANDOVER.md` — the full technical handover, covering architecture, every major subsystem,
  and current implementation status in detail.
- `docs/MASTER_STATUS.md` — a concise, frequently updated status tracker.
- `docs/location_architecture_decision.md` — the canonical-geography architecture decision record.
- `docs/india_location_integrity_report.md` and `docs/india_dedup_migration_plan.md` — the location
  data-quality audit and its (currently unexecuted) remediation plan.
- `docs/marquee_religious_text_sources.md` and `docs/marquee_rights_roadmap.md` — the religious-text
  rights research and outreach plan.
- `docs/dpg_evidence/` — the internal DPG Standard evidence pack, including
  `10_forward_plan.md` (the tracked list of open gaps) and `11_application_form_answers.md`.
- OpenStreetMap's own copyright and licensing terms: `https://www.openstreetmap.org/copyright`.
- The Tanzil Project (Quran text licensing) and Biblica (Hindi Psalms licensing) — see
  `docs/marquee_religious_text_sources.md` for the specific license terms applied to each.

Where a statement in this document reflects a project design intention rather than a measured
result, that distinction has been made explicit in context.

---

*Published as a project overview. For technical detail, consult the technical documents listed
above; for questions about this document, contact the project through the channels listed on the
Qumanity website's About page.*
