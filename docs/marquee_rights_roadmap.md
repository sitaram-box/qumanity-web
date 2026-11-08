# Marquee Religious Text Rights — Roadmap (2026-11-02)

> **Superseded 2026-11-08.** The Poems Marquee feature this roadmap was written for has been
> discontinued entirely (owner legal decision — Gita Press denied permission for the Hindi Vinaya
> Patrika translation, and the owner chose to remove the whole feature rather than continue with
> the other, already-cleared collections). This document is preserved as the historical
> rights-research record; none of the next-step outreach described below is still active work.
> See `docs/HANDOVER.md` §9.1 for the current-state record.

## 1. Purpose and scope

This is the practical, owner-facing roadmap for the Marquee's six religious-text areas: what is
live, what is blocked, exactly who to contact next, and what has to happen before any further
content import. It sits alongside, and does not replace, `docs/marquee_religious_text_sources.md`
(the detailed research findings, exact quotes, and primary-source citations) and
`docs/MASTER_STATUS.md` (the whole-project status tracker, which links here). Every contact
detail and draft message below is reproduced from that research document, not reconstructed from
memory — where that document has no verified contact route, this roadmap says so plainly rather
than inventing one.

**This document does not authorize sending any outreach.** Every "prepared" message below is a
draft for the owner's own review and, if the owner chooses, the owner's own sending. Nothing in
this repository sends email, letters, contact-form submissions, or messages on its own.

## 2. Status at a glance — all six areas

| # | Tradition | Area | Status |
|---|---|---|---|
| 1 | Hindu | Gita Press Vinaya Patrika | ⚠️ Awaiting rights-holder response |
| 2 | Christian | Biblica Hindi Bible | ✅ **Live** — approved with conditions |
| 3 | Muslim | Urdu Quran | ⚠️ Pending Tanzil Project clarification |
| 4 | Sikh | Gurbani | ⚠️ Pending Khalis Foundation / rights-holder response |
| 5 | Buddhist | Hindi Dhammapada | ⚠️ New research required |
| 6 | Jain | Jain texts | ⚠️ Dedicated research not yet completed |

Five of six areas are not currently servable by the Marquee — confirmed directly against the
database: `religious_text_core.resolve_collection()` returns `None` for every one of them, which
`api_poems_meta()` reports as `coming_soon`, never substituted content. Only the Christian Hindi
collection (row 2) has moved from pending to live, via commit `fbc0a5e`
(`fbc0a5ed2ab0c55c183786be6e464f7f14eaec1f`, 2026-11-02, owner-authorized).

---

## 3. Hindu — Gita Press Vinaya Patrika

**Status: awaiting rights-holder response.**

- Qumanity's permission letter has already been sent (see `scripts/make_gita_press_letter.py`,
  the printable letter generator, and `/copyright/gita-press`'s own public notice, which states
  "We have written to Gita Press requesting a licence for the translation").
- No verified publication permission has yet been established.
- The Gita Press Vinaya Patrika text remains unavailable in the public Marquee.
- The Hindu default continues to use the original Qumanity Hindi poetry collection
  (`Poems/hindu_original/`), never labeled or attributed to Gita Press.

**Next step:** await a response to the letter already sent. **Do not send duplicate
correspondence during this task or as a result of this roadmap.** If a response arrives, review
its scope against: website display, digital redistribution, the specific translation/edition
named, commercial use, and required attribution — then seek owner approval before enabling any
text.

**Contact on file** (from the existing letter, not independently re-verified this pass — postal
only, no verified Gita Press email address exists in this repository):
- Organization: Gita Press, Gorakhpur
- Address: Gorakhpur, Uttar Pradesh, India (postal)
- No verified direct contact route found for email, phone, or an online contact form.

**Qumanity's own sender details used on that letter** (for reference, not an outreach target):
Rohit Mudgal, founder@qumanity.in, qumanity.in.

**Revisit point:** when a response arrives, or when the owner explicitly authorizes a follow-up
pass.

---

## 4. Christian — Biblica Hindi Bible

**Status: Live — approved with conditions.**

- Biblica Open Hindi Contemporary Version is available in the Christian Marquee today.
- Collection: `Poems/christian/hindi_biblica/poems_hindi.json` — eight selected Psalm verses
  (Psalm 23:1, 46:1, 100:5, 118:24, 121:1-2, 34:8, 37:4, 19:14), **not the complete Hindi Bible**.
- Distributed under the verified CC BY-SA 4.0 terms recorded in
  `Poems/christian/hindi_biblica/README.md` and `docs/marquee_religious_text_sources.md` §2b.
- Required attribution and the license's share-alike obligation must continue to be respected on
  every future change to this file.
- Existing English KJV Psalms remain available separately and are the Christian default language
  — unaffected by the Hindi addition.

**Next step:** no new rights clearance is currently required for this specific, already-approved
collection, subject to continued compliance with its license (attribution intact, no use of the
Biblica® trademark symbol in Qumanity's own UI/docs, any redistribution of the JSON file itself
kept under the same CC BY-SA 4.0 license). Any **expansion** — more verses, a different book, a
different Biblica edition — must be independently checked against the applicable terms before
import; this roadmap does not pre-approve a larger Biblica collection.

**Contact route for future licensing questions** (from `docs/marquee_religious_text_sources.md`
§2b, re-verified live this session): Biblica's Permission Request Form —
`https://www.biblica.com/permission-request-form/`; `open.bible/contact` as the secondary route
specific to this open edition. Last verified: 2026-11-02.

**This collection is never to be re-classified as pending.**

---

## 5. Muslim — Urdu Quran

**Status: pending Tanzil Project clarification.**

- The Arabic Quran collection (Surah Al-Fatiha, Tanzil Project, CC BY 3.0) is already available
  and unaffected by this roadmap.
- The Urdu Quran collection remains blocked.
- Fateh Muhammad Jalandhry's translation is confirmed still under copyright (Pakistan's Copyright
  Ordinance 1962, 50 years from the year after the author's 1982 death → protected through 1
  January 2033).
- Abul A'la Maududi's *Tafheem-ul-Quran* publisher (Idara Tarjuman-ul-Quran, Lahore) has no
  locatable website or contact route.
- Tanzil Project's own terms for translated text carry an ambiguous redistribution clause that
  remains unresolved.

**Next step:** the draft email to Tanzil Project is already prepared below. **The owner must send
it; this task does not send it.** Ask for written clarification on the exact Urdu
translation/edition, and whether it may be redistributed as a structured JSON collection and
displayed on Qumanity's public website — covering translator, copyright holder, license,
attribution requirements, commercial-use conditions, and redistribution permission.

**Contact route:** `No verified direct contact found.` `docs/marquee_religious_text_sources.md`
§3b records that no email address or working contact-page link was located anywhere on
`tanzil.net`'s fetchable pages this session — their own FAQ references "our contact page" without
providing its URL. **Next research action:** locate a working contact route by visiting the live
site directly (e.g. its footer) before the prepared message below can actually be sent anywhere.

**Prepared outreach message** (draft only, for owner review — not sent), reproduced exactly from
`docs/marquee_religious_text_sources.md` §3b:

> "Hello Tanzil Project team, Qumanity (qumanity.in) is a small non-commercial, open-source
> civic/cultural platform. We already display a verbatim Al-Fatiha excerpt from your Arabic Quran
> text (CC BY 3.0) with attribution. We'd like to ask whether we may also display a small number
> of rotating Urdu verse excerpts (not your full translation catalog or index page) sourced via
> your translations list, shown in a structured JSON format with full attribution to Tanzil and
> the respective translator. Could you confirm whether this falls under your redistribution
> restriction, or whether you're able to grant permission for this limited, non-commercial,
> attributed use?"

**Dependency and timing:** (1) locate a real Tanzil contact route; (2) owner sends the prepared
request through it; (3) await written clarification; (4) reassess the collection when it arrives.
If no response arrives within a reasonable period, a follow-up should be proposed explicitly by
the owner, not assumed or scheduled automatically here. **Do not import Urdu Quran text before
written approval.**

---

## 6. Sikh — Gurbani

**Status: pending Khalis Foundation / rights-holder response.**

- No Gurbani collection — Gurmukhi original, transliteration, or any translation — is currently
  approved for public redistribution.
- SriGranth.org's own footer states "all rights reserved" — an explicit non-grant.
- Khalis Foundation/BaniDB's GitHub repository has a real MIT LICENSE file, but it covers the
  API/server code only; their own README explicitly withholds the Gurbani text dataset itself
  from being "completely open."
- A newer lead, `github.com/shabados/database` (Shabad OS, a separate project), self-asserts the
  Gurmukhi original is public domain — not court-tested, and does not cover any English
  translation.
- Original Gurmukhi text, digital transcription, transliteration, translation, and commentary are
  treated here as separate materials with potentially separate rights, never assumed identical.

**Next step:** use the verified Khalis Foundation contact route below to request written
clarification about redistribution and public display of their source data, and of any proposed
Punjabi or Hindi translation. Contact any identified translation rights-holder (e.g. for Sant
Singh Khalsa's English translation) separately — none was identified this session; see below.
**Do not interpret the MIT code license, or the Shabad OS self-asserted claim, as permission to
redistribute scripture data or any translation.**

**Contact details** (from `docs/marquee_religious_text_sources.md` §4a, verified live this
session):
- Organization: Khalis Foundation
- Address: 142 N. Milpitas Blvd, Ste 276, Milpitas, CA 95035
- Phone/WhatsApp: +1 (510) 394-0102
- Contact form: `khalisfoundation.org`
- Email: `No verified direct contact found.`
- Sant Singh Khalsa translation rights-holder: `No verified direct contact found` — SikhNet's own
  copyright-policy page 404'd; no publisher, trust, or estate was identified this session.
- Last verified: 2026-11-02.

**Prepared outreach message** (draft only, for owner review — not sent), reproduced exactly from
`docs/marquee_religious_text_sources.md` §4a:

> "Hello, we're building Qumanity (qumanity.in), a non-commercial, open-source civic/spiritual
> platform. We'd like to display a small number of rotating Gurbani verses (Gurmukhi original
> plus a named English translation) with full attribution to Khalis Foundation/BaniDB, in a
> structured JSON format, for non-commercial educational use only. Would Khalis Foundation be
> willing to grant permission for this limited use, and if so, under what conditions (attribution
> text, verse count limits, update process)?"

**Dependency and timing:** (1) owner reviews and, if they choose, sends the prepared message via
the contact form or phone/WhatsApp above; (2) separately, identify Sant Singh Khalsa's current
translation rights-holder, since no contact route exists for that yet; (3) await written
clarification for both the source data and any translation; (4) reassess each independently when
a reply arrives. If no reply arrives, establish a follow-up point rather than assuming permission.
**Do not import or publish any Gurbani text until the applicable rights and terms are verified.**

---

## 7. Buddhist — Hindi Dhammapada

**Status: new research required.**

- Pali Dhammapada and English (F. Max Müller, 1881, Project Gutenberg) are already available and
  unaffected by this roadmap.
- Hindi Dhammapada remains blocked.
- The Rahul Sankrityayan 1933 translation (Mahabodhi Sabha, Sarnath) was investigated: its
  publication facts are confirmed, and a work of his would plausibly be public domain in India
  from 1 January 2024 (life+60, d. 1963) — but archive.org hosts two scans of the same book with
  **conflicting license tags** (CC0 vs. CC BY-NC-ND), neither authoritative, and the US/URAA
  copyright-restoration question for a 1933 India-first-published work remains unresolved, which
  matters because Qumanity is a US-reachable website.
- No sufficiently verified Hindi translation is currently approved; no clean verbatim text could
  be extracted from the available OCR either.

**Next step:** conduct new, targeted research — investigate the translator, publication date,
publisher, edition, and original source for any Hindi Dhammapada candidate; examine actual primary
licensing evidence rather than uploader-applied digitization tags; specifically resolve the
India-life+60-vs-US/URAA conflict for the Sankrityayan candidate (likely needs a one-time
legal/rights confirmation, not further web research alone) before it can be considered further;
check whether a digital transcription introduces its own separate rights issue; if the 1933
candidate remains ambiguous after that, investigate alternative editions rather than treating it
as the only path. **Do not use automated machine translation as a substitute for a verified
edition.**

**Contact route:** `No verified rights-holder contact identified yet` — this tradition's next step
is research, not outreach; a specific contact only becomes relevant once a specific candidate
edition and its rights-holder are identified.

**Dependency and timing:** research can begin immediately — it does not depend on any external
reply. Milestone 1: identify a specific source and edition. Milestone 2: establish its rights and
attribution requirements (including the India/US question above). Milestone 3: seek owner approval
before importing any content.

---

## 8. Jain — Jain texts

**Status: dedicated research not yet completed.**

- No Jain content is currently available in the Marquee.
- Two initial candidates were researched this cycle: the **Tattvartha Sutra** (confirmed accepted
  across Digambara, Svetambara, and minor sub-traditions — the earliest Jain text with that
  cross-sect status) and the **Namokar Mantra** (the tradition's universal prayer, with real
  sect-specific wording variants between Digambara and Svetambara usage).
- Tattvartha Sutra: the common Nathmal Tatia/Institute of Jainology English translation (1994
  HarperCollins / 2010 Yale UP) is fully copyrighted. An older, plausibly public-domain English
  translation (J.L. Jaini, 1920) exists but the only accessible copy found is wrapped in
  jainqq.org's own "All rights reserved, for private & personal use only" notice — not citable as
  found.
- Namokar Mantra: the Prakrit original is public domain by age; a CC BY-SA 4.0-licensed Wikipedia
  translation was identified as a workable fallback, but this is the most promising lead of the
  two, not yet approved.
- The rights of original Sanskrit/Prakrit texts, modern translations, scholarly editions, and
  digital transcriptions must be established separately — none assumed from another.

**Next step:** start a dedicated research phase. For the Tattvartha Sutra: either resolve
JAINpedia's own conflicting CC-BY-NC-SA-vs-"all rights reserved" footer signal directly with the
Institute of Jainology, or locate a clean HathiTrust/archive.org scan of J.L. Jaini's 1920
translation that bypasses jainqq.org's restrictive wrapper. For the Namokar Mantra: confirm the
Wikipedia CC BY-SA 4.0 translation's suitability as a durable source, or identify an institutional
alternative. In both cases, identify the relevant publisher, institution, translator, or
rights-holder where possible, and do not claim that one text represents all Jain traditions.

**Contact route:** `No verified rights-holder contact identified yet` for either candidate; this
is itself one of the next research actions (JAINpedia/Institute of Jainology for the Tattvartha
Sutra path).

**Dependency and timing:** research can begin immediately. Milestone 1: identify a specific
source and edition (Tattvartha Sutra via a resolved-rights path, or Namokar Mantra via the
Wikipedia CC BY-SA lead). Milestone 2: establish rights and attribution requirements. Milestone 3:
seek owner approval before importing content.

---

## 9. Timeline and dependency roadmap

| Priority | Collection | Immediate action | Dependency | Revisit point |
|---|---|---|---|---|
| 1 | Urdu Quran | Locate a real Tanzil contact route, then owner sends the prepared request | Written clarification from Tanzil | After response, or an owner-scheduled follow-up |
| 2 | Sikh Gurbani | Owner uses the verified Khalis Foundation contact form/phone | Written source + translation rights clarification | After response |
| 3 | Hindi Dhammapada | Begin new source research; resolve the India/US rights conflict for the 1933 candidate | Reliable edition and verified license evidence | At completion of research |
| 4 | Jain | Begin dedicated text/source research (Tattvartha Sutra and Namokar Mantra) | A specific approved text and translation rights | After first source review |
| Monitoring | Gita Press | Await the letter already sent | Gita Press permission | On reply, or an owner-approved follow-up |
| Live maintenance | Biblica Hindi Bible | Maintain attribution and CC BY-SA 4.0 compliance | Existing license obligations | On every future edit to this collection |

A sensible **internal** review cadence (e.g. a fortnightly check of outstanding correspondence) is
reasonable for the owner to adopt, but this is a suggestion for the owner's own process, distinct
from any claim about when a rights-holder will actually reply — no external response date is
promised or assumed anywhere in this document.

This timeline makes explicit: the four still-blocked collections cannot move to import merely
because research is complete — written licensing evidence **and** owner approval are both
required; content import is always a separate, future, explicitly-authorized task; and the
existing approved collections (Hindu original poetry, Christian English + Hindi, Muslim Arabic,
Buddhist Pali + English) all remain live throughout, regardless of how long the remaining rights
work takes.

## 10. Approval gates before any future content import

For every one of the four still-blocked collections, all of the following must be true before a
future task may import it:

1. A specific source, edition, and (where applicable) translator has been identified.
2. Primary-source licensing or permission evidence has been directly verified — not inferred from
   a secondary source, an uploader's own license tag, or the age of the underlying scripture alone.
3. The exact attribution and any share-alike/non-commercial/no-derivative conditions have been
   recorded.
4. The owner has explicitly reviewed and approved the specific source and its terms.
5. The actual text has been verbatim-retrieved from the verified source — never machine-translated
   or reconstructed from memory.

The Gita Press text additionally requires a documented, affirmative response to the letter already
sent (a non-response is not approval).

## 11. Revision history

- 2026-11-02: initial version, created as a standalone roadmap alongside
  `docs/marquee_religious_text_sources.md` (the detailed research record) and
  `docs/MASTER_STATUS.md` (the whole-project tracker, which links here). Reflects the state
  immediately after the Biblica Hindi Bible import (commit `fbc0a5e`) — the only one of the six
  areas currently live. All contact details, draft messages, and findings above are reproduced
  from the research document as it stood this date, not reconstructed from memory; any contact
  route not found in that document is marked `No verified direct contact found` here rather than
  invented.
