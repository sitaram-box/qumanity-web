# Qumanity: Open Licensing

**DPG Standard Indicator 2: Use of Approved Open Licences**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.
Repositories (public): [qumanity-web](https://github.com/sitaram-box/qumanity-web) and [qumanity-app](https://github.com/sitaram-box/qumanity-app).

## Contents

- [2.1 What the DPG Standard requires](#21-what-the-dpg-standard-requires)
- [2.2 License chosen](#22-license-chosen)
- [2.3 Why AGPL-3.0 for Qumanity](#23-why-agpl-30-for-qumanity)
- [2.4 License compliance plan](#24-license-compliance-plan)
- [2.5 License text](#25-license-text)
- [2.6 Third-party dependency licensing](#26-third-party-dependency-licensing)
- [2.7 Effect on the phone app](#27-effect-on-the-phone-app)
- [2.8 Reference URLs](#28-reference-urls)

## 2.1 What the DPG Standard requires

The DPG Standard requires open-source software to be released under a licence approved by the Open Source Initiative (OSI). The licence must be published with the source, in a public repository, so that anyone can see the terms that govern use, modification and redistribution.

## 2.2 License chosen

**GNU Affero General Public License, version 3 (AGPL-3.0).** SPDX identifier: `AGPL-3.0-only`.

Official text: https://www.gnu.org/licenses/agpl-3.0.html

AGPL-3.0 is on the OSI's list of approved licences.

## 2.3 Why AGPL-3.0 for Qumanity

**Qumanity is a civic commons, not a proprietary product.** Qumanity holds the boards, councils, citizen reports and community wallets of the places that use it. The people who rely on that infrastructure need to be able to inspect it and adapt it, and that ability should not depend on who runs a particular copy. The licence is chosen to keep the code, and every improved version of it, available to them.

**AGPL-3.0 prevents proprietary forks, including hosted ones.** Under the ordinary GPL, a company can modify the software, run it only on its own servers and never release the changes, because offering a service over a network is not "distribution". AGPL-3.0 closes this gap. Section 13 requires anyone who modifies the program and lets users interact with it over a network to offer those users the corresponding source code of the modified version. A hosted "Qumanity as a service" fork therefore has to stay open.

**Commercial use remains permitted.** AGPL-3.0 restricts closing the source, not charging money. A panchayat, cooperative, NGO or business may deploy Qumanity, run it for others, charge for hosting, support or training, and build services around it. The one condition is that changes they make to Qumanity are shared under the same licence with the people who use their deployment.

**Precedents among digital public goods.** The two most widely used open-source platforms for citizen participation are licensed under AGPL-3.0, and both are listed in the DPG Registry: [Decidim](https://digitalpublicgoods.net/r/decidim) (Barcelona) and [CONSUL Democracy](https://www.digitalpublicgoods.net/r/consul-democracy) (Madrid). They are the closest functional peers to Qumanity. Indian digital public infrastructure has chosen differently: MOSIP uses MPL-2.0 and eGov's DIGIT uses MIT (both checked against their repositories' LICENSE files). So AGPL-3.0 follows the civic-participation precedent, not the Indian identity and municipal-services one.

**Consistency with a dependency already in the stack.** Qumanity's astronomical calculations (sun signs, lunar cycles, sunrise times) use pyswisseph, which is itself licensed under AGPL-3.0 (see 2.6). A program that includes it is already bound by AGPL-3.0 terms when it is distributed or served over a network. Licensing Qumanity's own code under AGPL-3.0 makes the whole program consistent, instead of leaving a permissively licensed codebase that cannot in practice be used on proprietary terms.

**Stewardship.** Qumanity is stewarded by its founder as an individual while the legal entity Qumanity Lok LLP is in registration. The licence choice stands on its own merits, not on the steward's legal form.

**Comparison with MIT and Apache 2.0.** Both are OSI-approved and would satisfy the DPG Standard. Both let anyone take the code, change it and release the result as closed software, including as a hosted service, with no obligation to share improvements. Apache 2.0 adds an explicit patent grant, but AGPL-3.0 also contains one (section 11). Under either permissive licence, a well-funded operator could build a closed version of Qumanity, become the version that communities depend on, and leave the open project behind. AGPL-3.0 prevents that outcome while still allowing commercial deployment. The cost is that some companies choose not to adopt AGPL software at all. The owner accepts that cost.

## 2.4 License compliance plan

- **LICENSE file.** The canonical, unmodified AGPL-3.0 text goes in a file named `LICENSE` at the root of both qumanity-web and qumanity-app. GitHub then detects it and shows "AGPL-3.0 license" on each repository page.
- **Copyright and licence notice.** Each README states the licence and the copyright holder: "Copyright (C) 2026 Rohit Mudgal (individual). Qumanity is licensed under the GNU Affero General Public License v3.0." Status on 14 October 2026: not yet in either README (Document 10, 10.4 step 6). Contributors keep the copyright in their own contributions (below). The phone app's `package.json` gets `"license": "AGPL-3.0-only"`.
- **Website footer.** The footer of qumanity.in shows "Licensed under AGPL-3.0" and links to the public source repository. The link is what section 13 asks of a network service, and it is the simplest way for any operator of a modified copy to comply. Today the footer markup is repeated in five templates (home, about, register, elements, kundali view), so each one needs the line.
- **Contributors keep their copyright.** No Contributor License Agreement is required. Contributors keep the copyright in their contributions and license them to everyone under AGPL-3.0, the same licence the project uses ("inbound = outbound"). A short CONTRIBUTING file will say so, and will ask for a Developer Certificate of Origin sign-off (`Signed-off-by:` on each commit) as a lightweight record of each contributor's right to submit their code. One consequence is that relicensing the project later would require agreement from every contributor. The owner accepts this, because it is part of what makes the commitment to openness credible.
- **No effect on user data.** The licence governs the source code only. It grants no rights over the personal data of registered members, including demo accounts. That data stays under Qumanity's privacy policy and India's Digital Personal Data Protection Act, 2023, covered in later indicators.

## 2.5 License text

The `LICENSE` file will contain the canonical AGPL-3.0 text from gnu.org (661 lines, 34,523 bytes), unmodified. It is not repeated here.

## 2.6 Third-party dependency licensing

Licences below were read from each package's published metadata (PyPI wheels and source distributions, the repositories' `requirements.txt` and `package.json`) on 2026-10-06.

**Website and server (qumanity-web)**

| Component | Licence | Note |
|---|---|---|
| Flask | BSD-3-Clause | Web framework |
| Werkzeug, Jinja2, itsdangerous, click | BSD-3-Clause | Installed with Flask |
| blinker | MIT | Installed with Flask |
| SQLite (Python `sqlite3`) | Public domain | Database |
| pyswisseph | AGPL-3.0 | Verified, see below |
| timezonefinder | MIT | Time zone from coordinates |
| APScheduler | MIT | Scheduled jobs |
| gunicorn | MIT | Production server |
| openpyxl | MIT | Spreadsheet export |
| pycountry | LGPL-2.1-only | Country and language codes |
| Leaflet 1.9.4 | BSD-2-Clause | India map |
| three.js 0.160.0 | MIT | Earth globe |
| earcut 2.2.4 | ISC | Polygon triangulation for the globe |
| Fraunces and Inter fonts | SIL Open Font License 1.1 | Loaded from Google Fonts |
| Natural Earth country borders | Public domain | Globe map data |

**Phone app (qumanity-app)**

| Component | Licence |
|---|---|
| React, React Native, React Native Web | MIT |
| Expo SDK and Expo Router, with the `expo-*` modules | MIT |
| react-native-screens, react-native-safe-area-context, react-native-svg, react-native-webview | MIT |
| TypeScript (development only) | Apache-2.0 |
| vitest (development only) | MIT |

**pyswisseph check.** Version 2.10.3.2 declares "GNU Affero General Public License v3" in its package metadata and ships the full AGPL-3.0 text as `LICENSE.txt`. The Swiss Ephemeris C library it wraps is dual-licensed by Astrodienst: AGPL-3.0, or the paid Swiss Ephemeris Professional License. Qumanity uses it under AGPL-3.0. Qumanity calls only the built-in Moshier ephemeris (`FLG_MOSEPH`), so no separate ephemeris data files are distributed. pyswisseph is not GPL-2.0-only, so there is no incompatibility. AGPL-3.0 is the licence the combined program already needs.

**pycountry check.** LGPL-2.1 is OSI-approved. Its section 3 allows it to be used under GPL v2 or any later version, which makes it compatible with an AGPL-3.0 program that imports it as a library.

**External services.** Qumanity does not depend on any external proprietary service for its core functionality. Qoins — the platform's internal community currency — are earned through civic activity (karma, service, post elevation rewards, voting) rather than purchased. No payment processor, no card data, and no financial PII are handled by the platform.

No dependency introduces a proprietary or non-OSI licence.

## 2.7 Effect on the phone app

The phone app in qumanity-app (React Native and Expo) is licensed under the same AGPL-3.0 as the website and API it talks to. Both the client that people install and the server that holds their boards, councils and wallets therefore stay in the commons. Anyone who distributes a modified app must provide its source under the same terms.

The iOS App Store has historically required distribution terms that conflict with copyleft licences for apps that include third-party contributions (see the 2011 VLC removal). Qumanity's current codebase has no external contributors, so the app can be distributed under AGPL-3.0 as-is. If external contributions are added later and iOS App Store distribution becomes a requirement, the owner will adopt a Contributor License Agreement at that point.

## 2.8 Reference URLs

- AGPL-3.0 text: https://www.gnu.org/licenses/agpl-3.0.html
- OSI listing: https://opensource.org/licenses/AGPL-3.0
- FSF page: https://www.gnu.org/licenses/why-affero-gpl.html
