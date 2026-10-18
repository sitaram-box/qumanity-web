# Qumanity: Relevance to the UN Sustainable Development Goals

**DPG Standard Indicator 1: Relevance to Sustainable Development Goals**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.
Repositories: [qumanity-web](https://github.com/sitaram-box/qumanity-web) (Flask website and the single API backend) and [qumanity-app](https://github.com/sitaram-box/qumanity-app) (React Native / Expo phone app, a client of the same API).

## Contents

1. [Scope and method](#1-scope-and-method)
2. [SDG 16: Peace, Justice and Strong Institutions (primary)](#2-sdg-16-peace-justice-and-strong-institutions-primary)
3. [SDG 10: Reduced Inequalities](#3-sdg-10-reduced-inequalities)
4. [SDG 11: Sustainable Cities and Communities](#4-sdg-11-sustainable-cities-and-communities)
5. [SDG 9: Industry, Innovation and Infrastructure](#5-sdg-9-industry-innovation-and-infrastructure)
6. [SDG 17: Partnerships for the Goals](#6-sdg-17-partnerships-for-the-goals)
7. [Implementation status](#7-implementation-status)
8. [Summary](#8-summary)

## 1. Scope and method

Qumanity is a civic participation platform organised around eight nested location levels (Village, Tehsil, District, State, Zone, Country, Continent, Earth). Each level has a Collective Board where residents post and vote, and a council whose two elected seats (Nayak and Nayika) are filled through zodiac-sign election cycles.

Every claim below refers to a feature in the qumanity-web repository and is linked to the design note that documents it. Target wording is quoted from the UN 2030 Agenda (sdgs.un.org). The design rests on research published as *Qumanity: A Quantum-Informed Governance Protocol*, SSRN, DOI [10.2139/ssrn.6985123](https://doi.org/10.2139/ssrn.6985123).

The five goals below are those suggested in the brief, and the review kept all five. SDG 16 is primary because Qumanity's core functions (resident voting, elected councils, citizen reports, public audit trails) are governance functions. The other four are supporting goals.

## 2. SDG 16: Peace, Justice and Strong Institutions (primary)

**Targets addressed**

- **16.6:** Develop effective, accountable and transparent institutions at all levels.
- **16.7:** Ensure responsive, inclusive, participatory and representative decision-making at all levels.
- **16.10:** Ensure public access to information and protect fundamental freedoms, in accordance with national legislation and international agreements.

**How Qumanity advances these targets.** Residents of a location vote +1, 0 or −1 on Collective Board posts. A post whose score reaches the level's threshold within a fixed window is elevated to the next level, so local priorities rise through the hierarchy by residents' votes rather than by an intermediary's choice (16.7). Councils are held to deadlines: a Citizen Report filed at village level must receive a council response within 10 days, or it can be escalated upward, where a fresh 10-day deadline applies (16.6). Aggregate statistics for any location can be read without signing in, and council announcements reach every resident of that location (16.10). Councils can also post council updates on their Collective Board: public notices that residents read and react to, but do not vote on.

**Concrete example.** A resident files a Citizen Report about a local issue from their Village page. The current village council members become its holders, and each acknowledgement, extension or escalation is recorded with a timestamp in an append-only escalation path that the reporter can follow. If the reporter chooses anonymity, their identity is masked from the council (the Admin can still see it).

**Evidence:** [docs/voting_logic.md](../voting_logic.md), [docs/reports_design.md](../reports_design.md), [docs/announcements_design.md](../announcements_design.md), [docs/lunar_cycle_system.md](../lunar_cycle_system.md) (audit trail of every data transfer between levels), `board_core.create_council_update` (council updates).

## 3. SDG 10: Reduced Inequalities

**Targets addressed**

- **10.2:** By 2030, empower and promote the social, economic and political inclusion of all, irrespective of age, sex, disability, race, ethnicity, origin, religion or economic or other status.
- **10.3:** Ensure equal opportunity and reduce inequalities of outcome, including by eliminating discriminatory laws, policies and practices and promoting appropriate legislation, policies and action in this regard.

**How Qumanity advances these targets.** Registration is open to anyone and is free. Each registration mints one ₹1-reference Qoin, shared 10 paise at a time between the member's eight location wallets, the member who registered them and the new member. The new member's share is released when they cast their first election vote. An existing member can register someone who lacks a device or literacy through assisted registration. The interface is available in 13 languages (English plus 12 Indian languages), and each member chooses the language the interface uses (10.2). The Qumanity Story (the long-form introduction on the home page) is currently in English only, with translations planned. Leadership is spread rather than concentrated: each village runs one election cycle per zodiac sign and elects 24 leaders a year (12 signs × one man and one woman) (10.3).

**Concrete example.** A helper signs in and registers an elderly neighbour through assisted registration. The neighbour receives their own Private ID and PIN, and the helper is recorded as referrer. No payment is needed at any step.

**Evidence:** [docs/qoins_earn_reference.md](../qoins_earn_reference.md), [docs/phone_app_api.md](../phone_app_api.md) (assisted registration), [docs/i18n_multilanguage_2026_10.md](../i18n_multilanguage_2026_10.md), [docs/zodiac_council_voting.md](../zodiac_council_voting.md).

## 4. SDG 11: Sustainable Cities and Communities

**Targets addressed**

- **11.3:** By 2030, enhance inclusive and sustainable urbanization and capacity for participatory, integrated and sustainable human settlement planning and management in all countries.
- **11.a:** Support positive economic, social and environmental links between urban, peri-urban and rural areas by strengthening national and regional development planning.

**How Qumanity advances these targets.** Only people who presently live in a place can post and vote on its board. Residents of a settlement therefore decide which local issues are raised and elevated (11.3). Rural villages and urban sectors use the same mechanism and the same escalation path from village to tehsil, district and state, so issues from rural areas reach regional levels on the same terms as urban ones (11.a). Within a large village, council members can create sub-groups for housing societies or resident welfare associations.

**Concrete example.** The hierarchy covers about 620,000 Indian villages. A resident of a village in Bawana tehsil, Delhi, posts on their village board. If the post passes the village threshold, it moves to the Bawana tehsil board, where residents of neighbouring urban and rural villages vote on it.

**Evidence:** [docs/sub_groups.md](../sub_groups.md), [docs/user_restrictions.md](../user_restrictions.md), [docs/location_consolidation_report.md](../location_consolidation_report.md), [docs/voting_logic.md](../voting_logic.md).

## 5. SDG 9: Industry, Innovation and Infrastructure

**Targets addressed**

- **9.1:** Develop quality, reliable, sustainable and resilient infrastructure, including regional and transborder infrastructure, to support economic development and human well-being, with a focus on affordable and equitable access for all.
- **9.c:** Significantly increase access to information and communications technology and strive to provide universal and affordable access to the Internet in least developed countries by 2020.

**How Qumanity advances these targets.** Qumanity is shared digital civic infrastructure. One Flask backend serves both the website and the phone app through a single API, and the platform runs on a low-cost stack (SQLite, one server process), which keeps hosting costs affordable for a small independent operator (9.1). Its location data covers the 10 countries of the Indian subcontinent, including UN-listed least developed countries such as Afghanistan and Myanmar. Participation needs only a phone with the app or a browser (9.c). While target 9.c's 2020 deadline has passed, its intent (universal and affordable ICT access) remains relevant and guides Qumanity's infrastructure choices.

**Concrete example.** A member signs in on the phone app with their 9-digit Private ID and 5-digit PIN and uses the same account, wallet and boards as on the website. No email address is needed.

**Evidence:** [docs/phone_app_api.md](../phone_app_api.md), [docs/private_id_and_login.md](../private_id_and_login.md), [docs/go_live_hardening_2026_10.md](../go_live_hardening_2026_10.md).

## 6. SDG 17: Partnerships for the Goals

**Target addressed**

- **17.18:** By 2020, enhance capacity-building support to developing countries, including for least developed countries and small island developing States, to increase significantly the availability of high-quality, timely and reliable data disaggregated by income, gender, age, race, ethnicity, migratory status, disability, geographic location and other characteristics relevant in national contexts.

**How Qumanity advances this target.** For every location from Village to Earth, Qumanity publishes aggregate statistics that anyone can read without signing in: the number of registered members, broken down by gender, four age bands, sun-sign element and sun sign, together with the total karma and total Qoin balance of its members. Both totals are left out for any location with one to four members. The data is disaggregated by gender, age and geographic location, three of the characteristics 17.18 names. The figures are counts only; no individual records are exposed (Document 06). Qumanity takes no payments: Qoins are earned through civic activity and are never bought.

**Concrete example.** `/api/location/stats/<level>/<location_id>` returns total members, a gender breakdown, four age bands, element counts and sign counts for any location, for example https://qumanity.in/api/location/stats/village/CS.DL.3.4.1A. `/api/karma/collective/<level>/<location_id>` returns the location's collective karma, and `/api/wallet/balance/<location_type>/<location_id>` returns how many Qoins its wallet holds. The rupee value of a wallet is shown only to its owner, or for a location wallet, to that location's council and the administrator.

**Evidence:** Document 06 (Mechanism for Extracting Non-PII Data), sections 6.2 and 6.6; [docs/qoins_earn_reference.md](../qoins_earn_reference.md) for how Qoins are earned.

## 7. Implementation status

- **Running on the website:** registration, sign-in with Private ID and PIN, Collective Boards with vote-based escalation, Citizen Reports, announcements, karma, Qoin wallets (Qoins are earned only; payments were removed entirely), Qoin rewards for every positively voted post at each level it clears, recognition stars, council updates, public location statistics, and the interface in 13 languages (English plus 12 Indian languages). The Qumanity Story is currently in English only, with translations planned.
- **Piloted:** zodiac council elections run in one pilot village (Rohini Sector 24, Delhi). Above village level, no elected councils exist yet, and Citizen Reports and announcements fall back to the Founder/Admin.
- **Testing:** an Admin-controlled Post Testing cycle in which demo accounts make one clearly labelled test post a month and vote weekly, so that the reward, freeze and elevation rules run end to end. Test posts are hidden from real members while voting is open, are labelled "Demo · Test" afterwards, never credit a real wallet, and are excluded from all member counts. No scheduler runs the 500 election-pilot demo accounts. The voting logic exists (`election_core.auto_vote`) and can be triggered manually by an admin via `POST /api/admin/election/auto-vote`. Nothing schedules it automatically. The automated election testing cycle is planned, not built.
- **Built, not yet active:** the lunar-cycle pipeline that moves records and aggregates level by level. By design it starts at Chaitra Navratri 2027, after a one-year bootstrap.
- **Not built:** the distributed node network (PLNN) and kiosks described in the White Paper v4.0.

## 8. Summary

Qumanity primarily advances SDG 16 (Peace, Justice and Strong Institutions), with supporting contributions to SDGs 10, 11, 9 and 17. Residents vote on local issues, which rise through eight location levels by score. Each elected council pair is one man and one woman. Citizen Reports carry a 10-day response deadline at every level. Aggregate statistics are public. These features target 16.6, 16.7 and 16.10 directly. The supporting goals rest on free and assisted registration with an interface in 13 languages (English plus 12 Indian languages; the Qumanity Story is currently in English only, with translations planned) (SDG 10), the same participation rules for rural and urban settlements (SDG 11), low-cost shared infrastructure serving web and mobile (SDG 9), and disaggregated public location statistics (SDG 17).
