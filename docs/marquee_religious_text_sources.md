# Marquee Religious Text Sources — Rights & Provenance Research (2026-11-02)

Research conducted for the Universal Multi-Religion, Multi-Language Marquee implementation.
Every collection actually imported into `religious_text_core.py`'s DB-backed library (seeded in
`religious_text_core.seed_builtin_collections()`) is documented here, alongside every collection
that was investigated and explicitly **not** imported. Nothing in this document is a secondary
source's claim stated as fact unless the primary source page was actually fetched this session
(via WebFetch/curl) and is quoted or closely paraphrased below.

**Decision legend:** `approved` / `approved_with_conditions` / `pending_rights_review` /
`not_permitted` / `source_unverified`. Only `approved` and `approved_with_conditions` collections
are seeded with `review_status='approved', marquee_eligible=1` (i.e. actually servable); every
condition attached to an `approved_with_conditions` row is also recorded in that row's
`license_notes` column and in the collection's own `Poems/<dir>/README.md`.

---

## 1. Hindu

### 1a. Original Qumanity Hindi poetry — `hindu_original` — **approved**

- **Text/work:** Newly-composed Hindi Ram-bhakti poetry (not a translation or adaptation of any
  existing work).
- **Original language:** Hindi (Devanagari).
- **Translator/author:** Qumanity (original authorship, composed 2026-11-01).
- **Source:** `Poems/hindu_original/poems_hindi.json`, 20 poems.
- **Rights:** Original authorship — no third-party rights question at all.
- **Attribution:** "Original Qumanity Hindi poetry, composed 2026-11-01."
- **Decision:** `approved`. Labeled accurately as "मौलिक राम-भक्ति कविताएँ" ("original Ram-devotion
  poems") — never "Vinaya Patrika," never attributed to Gita Press.

### 1b. Gita Press Hindi Vinaya Patrika translation — **not_permitted / pending_rights_review**

- **Text/work:** *Vinaya Patrika* (Tulsidas) — the original Awadhi/Braj Bhasha composition is
  public domain by age.
- **Translation in question:** Hanuman Prasad Poddar's Hindi translation.
- **Rights:** In copyright in India until 1 January 2032 (life + 60 years; Poddar d. 1971). This
  specific translation was present in this repository, was the subject of a DMCA/rights takedown,
  and was purged on 2026-10-07 — see `docs/marquee_poems_archive/README.md` for the incident
  record.
- **Decision:** `not_permitted`. Re-confirmed this session: no documentary evidence of publication
  permission for this specific translation exists anywhere in this repository. Per this task's own
  decision rule, the public default therefore uses 1a (original Qumanity poetry) instead. A
  copyright-information page or a general reference to Gita Press is explicitly **not** treated as
  proof of permission.

---

## 2. Christian

### 2a. Psalms, King James Version — `christian_psalms_kjv` — **approved** (pre-existing, re-confirmed)

- **Text/work:** Psalms, King James Version (1611).
- **Source:** `Poems/christian/psalms_kjv_en.json`, 8 verses.
- **Rights:** Public domain worldwide. The one narrow exception is the Crown's UK printing patent,
  which restricts *commercial printing* of the KJV within the United Kingdom only — not a
  copyright, and does not reach this non-commercial display use anywhere.
- **Attribution:** "Psalms, King James Version (1611) — public domain."
- **Decision:** `approved`.

### 2b. Hindi Bible — **pending_rights_review** (rights confirmed for one edition; text not safe to publish)

Researched this session via `archive.org` item/metadata pages (primary source, fetched directly):

- **Candidate 1 — 1914 BFBS North India Auxiliary Hindi Bible** (`archive.org/details/holybiblecontain00unse_56`): publisher British and Foreign Bible Society, Allahabad, 1914, committee translation (no individual translator named). Archive.org's own `copyright` metadata field: **"This item is in the public domain."** `notes` field: **"No Copyright."** This is an explicit, edition-specific statement from the hosting institution, not generic "the Bible is old" reasoning, and 1914 is comfortably pre-1929.
  - **Rights status: `public_domain` — confirmed, high confidence.**
  - **Publishable text status: NOT YET.** The only text layer retrieved (the item's OCR `.txt` export) is heavily character-garbled (e.g. "आुत्चावा" for "यहोवा," "चरबाहा" for "चरवाहा"). Per this task's own rule against publishing unverified/reconstructed text, **no Hindi Bible JSON file was created**. Before this can move to `approved`, someone needs to either transcribe Psalm 23 directly from the page-image scan (not the OCR layer), or locate a clean existing digital transcription of this specific 1914 edition.
- **Candidate 2 — 1851 Allahabad Presbyterian Mission Press Bible** (`archive.org/details/holybibleinhindi00alla`): `possible-copyright-status: NOT_IN_COPYRIGHT`, but confirmed (via its own table of contents) to cover only Genesis–2 Kings — does not contain Psalms. Ruled out for this use.
- **Candidate 3 — 1845 Allahabad "Psalms and Proverbs in Kaithi Hindi"** (`archive.org/details/psalmsproverbsin00alla`): also `NOT_IN_COPYRIGHT`, and does contain Psalms, but its OCR layer is severely corrupted — unusable for verbatim quotation this session.
- **Candidate 4 — Biblica "Open Hindi Contemporary Version"** (`ebible.org/hincv/copyright.htm`), re-researched in depth: © 1978–2019 Biblica, Inc., **CC BY-SA 4.0**, exact terms quoted directly from the primary source: *"This work is made available under the Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA)."* / *"You must also make your derivative work available under the same license (CC BY-SA)."* / *"you may copy and redistribute this unmodified work as long as you keep the Biblica® trademark intact."* **Real verse text was retrieved this pass** from `ebible.org/hincv/PSA023.htm` (fetched live, not reconstructed) — confirming the page genuinely hosts verse-level Hindi text matching Psalm 23 (first few words: "याहवेह मेरे चरवाहा हैं..."). Share-alike scope assessed: a standalone JSON file containing only the licensed Hindi verses, kept separate from the application's own code, is defensibly a "collection" rather than a merged "adaptation" under CC's own framework — a reasonable, commonly-used interpretation, not a guaranteed legal conclusion. Contact route: Biblica's Permission Request Form (`biblica.com/permission-request-form/`); `open.bible/contact` as a secondary route specific to this open edition.
  - **Revised decision for this candidate: `approved_with_conditions`.** Conditions: (1) publish the Hindi JSON/data file itself under CC BY-SA 4.0 with visible attribution ("Biblica®... available at biblica.com and open.bible"); (2) keep the Hindi text in its own clearly-licensed file/module, never inlined into general application code; (3) never use the Biblica® trademark/name in the UI beyond the required attribution without separate written permission; (4) a courtesy notice to Biblica via `open.bible/contact` is recommended though not strictly required by the license.
- **Decision for the Hindi Bible collection overall: still `pending_rights_review` for import purposes.** Candidate 1 (1914 BFBS) remains rights-clear but textually unusable (OCR-garbled, no clean transcription found anywhere this session, including a direct check of Hindi Wikisource, which has no Bible/Psalms content at all). Candidate 4 (Biblica CC BY-SA 4.0) now has both verified terms AND verified real text — **the clearer path of the two** — but per this task's own authorization boundary ("do not import... until the owner has reviewed and explicitly approved"), **no Hindi Bible JSON file has been created and no collection has been seeded.** Recommended next step: owner review of Candidate 4's CC BY-SA 4.0 conditions above, then import if approved.

---

## 3. Muslim

### 3a. Quran, Surah Al-Fatiha, Arabic (Uthmani Mushaf) — `muslim_quran_tanzil_arabic` — **approved_with_conditions**

- **Text/work:** Quran, Surah 1 (Al-Fatiha), all 7 ayahs, Uthmani Mushaf script.
- **Source:** Tanzil Project (`tanzil.net`). Fetched directly this session: `tanzil.net/docs/Text_License` (license page) and a live download of the actual Uthmani Arabic text.
- **License, quoted verbatim from the primary source:**
  > "Tanzil Quran Text — Copyright (C) 2007-2021 Tanzil Project — License: Creative Commons Attribution 3.0."
  > "Permission is granted to copy and distribute verbatim copies of this text, but CHANGING IT IS NOT ALLOWED."
  > "This Quran text can be used in any website or application, provided that its source (Tanzil Project) is clearly indicated, and a link is made to tanzil.net to enable users to keep track of changes."
- **Conditions (binding):** (1) verbatim text only — no re-diacritization/re-wording/re-segmentation beyond normal ayah boundaries; (2) visible "Tanzil Project" credit; (3) a clickable link to `tanzil.net`; (4) standing, not one-time, attribution.
- **Attribution:** "Quran text: Tanzil Project (tanzil.net), Uthmani Mushaf, CC BY 3.0."
- **Decision:** `approved_with_conditions`, all conditions met in `Poems/muslim/README.md` and the marquee's own attribution display. High confidence (primary source fetched directly, exact terms quoted).

### 3b. Urdu translation — **pending_rights_review**

- Tanzil also hosts multiple Urdu translations (e.g. Jalandhry, Maududi). Fetched directly: `tanzil.net/trans/`'s Terms of Use section:
  > "The translations provided at this page are for non-commercial purposes only." "If used otherwise, you need to obtain necessary permission from the translator or the publisher." "Redistributing the following list in another website is not allowed, unless direct permission is granted by the Tanzil Project."
- This last clause is genuinely ambiguous — it could mean "don't republish our index/catalog page" or "don't republish the translation text on your own site." A re-fetch this session of `tanzil.net/trans/`, `tanzil.net/docs/faq`, and a check for `tanzil.net/docs/Translation_License` (does not exist — empty wiki stub) did not resolve it. The FAQ confirms embedding Tanzil's own Quran Navigator *widget* is explicitly permitted, but says nothing about embedding individual translated verses outside that widget — **the ambiguity stands.**
- **Named-translator rights, researched in depth this session:**
  - **Fateh Muhammad Jalandhry** (d. 18 December 1982): confirmed via Pakistan's Copyright Ordinance 1962 s.18 (copyright "subsists until 50 years from the beginning of the calendar year next following the year in which the author dies") that his translation (*Fath al-Hamid*, 1960) remains **under copyright in Pakistan through 1 January 2033**, and would be protected longer still under India's life+60 reciprocity. **Confirmed still active, not expired.** No specific rights-holder (estate/publisher) identified.
  - **Abul A'la Maududi** (d. 1979), *Tafheem-ul-Quran*: published by Idara Tarjuman-ul-Quran, Lahore. No live website, contact page, or stated licensing policy could be found for this publisher via web search — **contact route unresolved.**
- **Tanzil contact route:** none found. The FAQ references "our contact page" without a working link; no email address was located anywhere on `tanzil.net`'s fetchable pages. Reaching Tanzil would require a site visit beyond what was fetchable this session (e.g. checking the live site's own footer directly).
- **Draft permission-request message prepared for owner review (not sent):** *"Hello Tanzil Project team, Qumanity (qumanity.in) is a small non-commercial, open-source civic/cultural platform. We already display a verbatim Al-Fatiha excerpt from your Arabic Quran text (CC BY 3.0) with attribution. We'd like to ask whether we may also display a small number of rotating Urdu verse excerpts (not your full translation catalog or index page) sourced via your translations list, shown in a structured JSON format with full attribution to Tanzil and the respective translator. Could you confirm whether this falls under your redistribution restriction, or whether you're able to grant permission for this limited, non-commercial, attributed use?"*
- **Decision:** remains `pending_rights_review`. Nothing found this session moves it to `approved_with_conditions` — Jalandhry's translation is confirmed still copyrighted, Maududi's publisher has no verifiable contact, and Tanzil's own clause and contact route both remain unresolved. The Arabic text's approval is independent and does not wait on this.
- **Alternative worth a look if Tanzil stalls:** `quran.com` / `api.quran.com`, a widely-used API with clearer per-resource licensing metadata. Not deep-dived this session.

---

## 4. Sikh

### 4a. Guru Granth Sahib (Gurbani) — **pending_rights_review, bordering on not_permitted**

The underlying composition (finalized 1708) is public domain by age in every jurisdiction. The
open question was narrower: does a *specific digital transcription or translation* carry its own,
separate, still-active rights? Primary sources fetched directly this session:

- **SikhiToTheMax** (`sikhitothemax.org`): both its About and Terms pages render client-side via
  JavaScript; WebFetch received only the empty app shell. **No terms could be confirmed.**
- **Sri Granth** (`srigranth.org`): an Ang-1 content page *did* render (Mool Mantar/Japji Sahib in
  Gurmukhi, Devanagari, Roman transliteration and English, with named translators Bhai Baljinder
  Singh, Dr. Kulbir Thind, Dr. Sant Singh Khalsa, Bhai Manmohan Singh). The page's own footer
  states, verbatim: **"© SriGranth.org, a Sri Guru Granth Sahib resource, all rights reserved."**
  This is an explicit non-grant.
- **BaniDB / Khalis Foundation** (`github.com/KhalisFoundation/banidb-api`, the data backend
  behind SikhiToTheMax/BaniDB): the README states, verbatim: *"we have chosen to take a controlled
  approach in order to allow for collaboration but also ensure fidelity of Gurbani data"* and
  *"[we] have seen too many instances of Gurbani being misused and altered to feel comfortable
  making the data completely open."* The repository's MIT license badge covers the *software*,
  not the Gurbani text dataset, which this same README explicitly says is deliberately **not**
  made fully open.
- **gurbanifiles.org, banidb.com, searchgurbani.com:** no terms/license page could be located for
  any of these.
- **Sant Singh Khalsa's English translation** (searched via SikhNet/SikhiWiki/mail.sikhs.org): no
  public-domain or open-license statement found. The only rights statement located is that the
  translator gave a *limited, named grant* to specific platforms (SikhNet, SGPC.net,
  Sikhitothemax) — not an open license to a third party like Qumanity.
- **Re-checked this session, with a specific focus on finding a LICENSE file (not just README
  prose) and real contact routes:**
  - `github.com/KhalisFoundation/banidb-api`'s actual LICENSE file **is** MIT (copyright (c) 2019
    Khalis Foundation) — but confirmed this covers the API/server **code only**; the README's own
    "Secure" section still explicitly withholds the Gurbani **data** from being "completely open."
    Unchanged conclusion: code is open, text dataset is not.
  - **New lead:** `github.com/shabados/database` (Shabad OS, a separate project from Khalis
    Foundation/BaniDB) explicitly states the Gurmukhi/panthic text is "public domain... as a work
    of factual compilation with originality." This is a self-asserted claim, not court-tested, and
    explicitly forbids "derogatory treatments (adding to, deleting from, altering, adapting)" the
    words. **It does not cover any English translation** the way it covers the Gurmukhi original —
    its listed translations are Sahib Singh's and Manmohan Singh's, not Sant Singh Khalsa's, with
    no public-domain statement for them at all. A promising lead for the Gurmukhi original only,
    not yet sufficient on its own (self-asserted, and the translation question remains open).
  - **SGPC** (Shiromani Gurdwara Parbandhak Committee): no published digitization/licensing policy
    found. Only found: SGPC publicly asserting its own copyright in broadcast-rights disputes (a
    Delhi High Court case over Golden Temple Gurbani telecast rights) — i.e. evidence SGPC *does*
    assert rights in some Gurbani-adjacent contexts, not evidence of an open policy.
  - **Contact routes found:** Khalis Foundation — a real nonprofit, physical address (142 N.
    Milpitas Blvd, Ste 276, Milpitas, CA 95035), phone/WhatsApp +1 (510) 394-0102, and a contact
    form on `khalisfoundation.org`; no public email found. Sant Singh Khalsa's translation
    rights-holder: **not found** (SikhNet's own copyright-policy page 404'd; no publisher, trust,
    or estate identified).
- **Draft permission-request message prepared for owner review (not sent):** *"Hello, we're
  building Qumanity (qumanity.in), a non-commercial, open-source civic/spiritual platform. We'd
  like to display a small number of rotating Gurbani verses (Gurmukhi original plus a named English
  translation) with full attribution to Khalis Foundation/BaniDB, in a structured JSON format, for
  non-commercial educational use only. Would Khalis Foundation be willing to grant permission for
  this limited use, and if so, under what conditions (attribution text, verse count limits, update
  process)?"*
- **Decision:** remains `pending_rights_review`, bordering on `not_permitted`. Nothing found this
  session changes that — the Shabad OS lead is interesting for the Gurmukhi original alone but
  self-asserted and still leaves the translation question fully open. **No Sikh text — Gurmukhi or
  any named translation — is published.** No `Poems/sikh/` directory exists; no
  `religious_traditions`/`text_collections` row claims Sikh content is available.
- **Recommended next step:** send the Khalis Foundation draft above (owner review required first;
  real contact route now identified, above) and separately attempt to identify Sant Singh Khalsa's
  current translation rights-holder before reconsidering this tradition.

---

## 5. Buddhist

### 5a. Dhammapada, Pali root text (Ch. 1, Yamakavagga, vv. 1–5) — part of `buddhist_dhammapada` — **approved_with_conditions**

- **Source:** SuttaCentral (`suttacentral.net`), Mahāsaṅgīti/Chaṭṭha Saṅgāyana edition lineage,
  retrieved live from SuttaCentral's own API (`suttacentral.net/api/suttas/dhp1-20/...`).
- **License finding:** SuttaCentral's `/licensing` page is a JavaScript single-page app that could
  not be fetched directly this session (both WebFetch and curl returned only the empty app
  shell). The public-domain claim was instead corroborated via (a) SuttaCentral's own
  `bilara-data` GitHub repository README, (b) a mirror of SuttaCentral's 2016 copyright page
  (`dhammatalks.net/suttacentral/sc2016/sc/copyright.html`), which states verbatim: *"The original
  texts of Buddhism in Pali, Chinese, Sanskrit, Tibetan, and other languages are in the public
  domain"* / *"Copyright assertions regarding such material have no legal basis,"* and (c)
  SuttaCentral community forum threads repeating the same claim.
- **Condition:** a human should open `suttacentral.net/licensing` directly in a real browser once,
  to get the primary-page quote, before this is treated as fully closed-out. Recorded in
  `Poems/buddhist/README.md` and this collection's `license_notes`.
- **Decision:** `approved_with_conditions`, medium-high confidence (multiple consistent
  SC-affiliated sources, not one secondary blog).

### 5b. Dhammapada, English translation (F. Max Müller, 1881) — part of `buddhist_dhammapada` — **approved**

- **Source:** Project Gutenberg eBook #2017 (`gutenberg.org/ebooks/2017`), fetched live.
- **License:** Project Gutenberg's own standard, unrestricted license for this ebook; "Public
  domain in the USA" per the ebook's own header. Publication year 1881 places it in the public
  domain worldwide regardless of the Gutenberg-specific terms.
- **Decision:** `approved`, high confidence, no open conditions.
- **(SuttaCentral also offers a CC0 2021 translation by Bhikkhu Sujato** — `bilara-data`'s README
  requires CC0 for every SC-hosted translation, and a forum-quoted attribution line confirms this
  specific translation is released that way. Not used here only because Müller's Gutenberg
  provenance needed no follow-up condition at all, making it the simpler choice for a first
  launch — not a rights problem with Sujato's translation. Worth adding alongside Müller in a
  future pass.)

### 5c. Dhammapada, Hindi translation — **pending_rights_review**

- **Rahul Sankrityayan's 1933 Hindi translation, re-researched in depth this session** — the
  actual 1933 scan was located and its OCR text retrieved directly: `archive.org/details/
  dhammapadarahulsankrityayan1933_565_R`. Title page confirms: धम्मपद (Pali text with Sanskrit
  chhāyā and Hindi translation), translator Rahul Sankrityayan, published by Mahabodhi Sabha,
  Sarnath (Banaras), 1933, printed in Prayag — independently corroborated by a Konkani Vishwakosh
  encyclopedia entry on Sankrityayan. Sankrityayan died 1963; under India's Copyright Act
  (life+60), this 1933 work would have entered India's public domain on **1 January 2024** — a
  plausible, now better-evidenced conclusion, but still the researcher's own inference from the
  death date, not a court or publisher determination.
  - **Complication found this session:** archive.org hosts **two different scans of the same
    book with conflicting license tags** — one (uploaded 2020, "Public Library of India"
    collection) tagged CC0 1.0; another (uploaded 2012, Digital Library of India/sanskritebooks.org)
    tagged CC BY-NC-ND 3.0 (non-commercial, no-derivatives). Both tags are uploader-applied
    defaults from mass-digitization projects, not legal determinations — neither is authoritative.
  - **US/URAA complication:** a 1933 India-first-published work whose Indian copyright was still
    active on the URAA reference date (1 January 1996) could have had its US copyright *restored*
    under the URAA, running from the author's death rather than simple publication-year math —
    this could mean continued US copyright well past 2024 even with India's term lapsed. Not
    resolved this session; needs a specific URAA legal check, which matters because Qumanity is a
    US-reachable public website.
  - A clean verbatim Hindi sample could not be isolated from the OCR (the Pali columns are
    legible; the Hindi-translation columns are garbled) — consistent with the general finding that
    OCR text from 1930s Devanagari scans is not publication-ready.
- **Other candidates checked:** the Vipassana Research Institute publishes a Hindi Dhammapada PDF
  (`vridhamma.org`/`tipitaka.org/hindi-docs`) but its footer states "© 2010 Vipassana Research
  Institute, All Rights Reserved," with downloads explicitly restricted to personal use —
  **not usable.** SuttaCentral itself hosts no Hindi translation of the Dhammapada at all
  (confirmed via its own API — Hindi is absent from both its segmented and unsegmented language
  lists).
- **Decision:** remains `pending_rights_review`. The Sankrityayan 1933 edition is the most
  promising lead (now with confirmed publication facts), but three unresolved issues — conflicting
  archive.org license tags, the unresolved URAA question, and no clean verbatim text — keep it
  short of `approved`. No Hindi Dhammapada file exists. Recommended next step: a one-time
  legal/rights confirmation covering both the India life+60 and US/URAA questions, plus either a
  clean manual transcription or a second, better OCR pass against the page images.

---

## 6. Jain

**Fresh research this session** — not investigated in the prior pass beyond the pre-existing,
unresolved finding in `docs/audit_multi_religion_marquee_proposal_2026_11.md`.

### 6a. Tattvartha Sutra (Umaswati/Umasvami) — **pending_rights_review**

- **Cross-sect status, verified:** confirmed via its own Wikipedia entry that the Tattvartha Sutra
  is accepted as authoritative across all major Jain schools (Digambara, Svetambara, and minor
  sub-traditions including Sthanakavasi and Terapanthi) — the earliest Jain text with that
  cross-sect status, though the two main traditions still dispute the author's own sect
  affiliation and their recensions differ in places.
- **Nathmal Tatia / Institute of Jainology English translation:** no copyright page, license, or
  rights statement located anywhere. First published 1994 (HarperCollins, San Francisco),
  sponsored by the Institute of Jainology; reissued 2010 by Yale University Press ("That Which
  Is," Sacred Literature Trust Series). Both standard copyrighted trade publications — **treat as
  fully copyrighted**, likely jointly held by the Institute of Jainology/Yale UP, until directly
  confirmed otherwise.
- **Older public-domain candidate:** J.L. Jaini's English translation (*Tattvarthadhigama Sutra*,
  Central Jaina Publishing House, Arrah, 1920; translator died 1927) — a 1920 US-reachable
  publication is public domain by age. BUT the only full-text copy located is on `jainqq.org`,
  whose footer explicitly states "Copyright © Jain Education International. All rights reserved."
  / "For Private & Personal Use Only" — **a restrictive wrapper around the content, not citable
  as-is**, even though the underlying 1920 translation is almost certainly itself PD. A HathiTrust
  catalog record exists (`catalog.hathitrust.org/Record/000014059`) but a usable full-text link
  could not be retrieved this session — the best concrete next research step.
- **Decision:** `pending_rights_review`.

### 6b. Namokar Mantra (Navkar Mantra) — **pending_rights_review**

- **Universal status, verified:** confirmed as the foundational prayer recited across Jain
  traditions. Real sectarian variation exists in wording — Svetambaras generally use the "Namo"
  form, Digambaras generally the "Ṇamō" form — so it is not one single fixed text across sects,
  though both communities accept its role.
- **Prakrit original:** ancient (attested as early as the Hathigumpha inscription), effectively
  public domain by age.
- **Translations:** a Jain Education International-hosted "Illustrated Namokara Mahamantra"
  edition is marked "All rights reserved" (translation-specific, not usable). The one usable lead:
  **Wikipedia's own rendering** (retrieved live this session), licensed **CC BY-SA 4.0**
  (reusable non-commercially with attribution and share-alike) — a workable fallback translation
  source, though not an institutional Jain source.
- **Verbatim sample retrieved this session** (from Wikipedia, not reconstructed from memory):
  Prakrit lines "णमो अरिहंताणं" / "णमो सिद्धाणं" / "णमो आयरियाणं" / "णमो उवज्झायाणं" / "णमो लोए
  सव्व साहूणं," with English gloss "I bow to the Arihants" / "I bow to the Siddhas" / "I bow to
  the Acharyas" / "I bow to the Upadhyayas" / "I bow to all of the Sages of the world" — retained
  here only as research evidence of what was found, not yet imported into any collection file.
- **Institutional sources checked, rights quoted directly:**
  - `jainelibrary.org`/`jainqq.org` (JLOR): "Copyright © Jain Education International. All rights
    reserved." / "For Private & Personal Use Only." — explicitly restrictive, not usable.
  - `jainpedia.org`: its `/about/copyright/` page states original JAINpedia content is licensed
    CC BY-NC-SA 3.0, with third-party material requiring separate written consent — but the live
    Tattvartha Sutra article page's own footer shows "© 2026 JAINPEDIA, All Rights Reserved," a
    **conflicting signal** needing direct clarification before relying on the CC terms.
- **Decision:** `pending_rights_review` — the most promising path of the two Jain candidates
  researched (ancient Prakrit original + a CC BY-SA-licensed Wikipedia translation as a workable
  attributable fallback), but not yet clear enough to import. Recommended next step: either (a)
  directly resolve JAINpedia's CC-BY-NC-SA-vs-"all rights reserved" footer discrepancy with the
  Institute of Jainology, or (b) locate a clean HathiTrust/archive.org scan of J.L. Jaini's 1920
  Tattvartha Sutra translation that bypasses `jainqq.org`'s rights-claimed wrapper.

### Note on sectarian diversity

Jain tradition has real sectarian diversity (Digambara, Svetambara, and further sub-traditions).
Neither candidate above is presented as representing "Jainism" as a monolith — the Tattvartha
Sutra's cross-sect acceptance and the Namokar Mantra's sect-specific wording variants are both
noted explicitly above.

## 7. Other, Prefer not to say

Not specific traditions; no text collection is meaningful for either. Neither has a
`religious_traditions` row, matching their pre-existing "profile-accepted only, no symbol, no
content" status.

---

## 8. Summary table

| Tradition | Collection | Languages served | Rights decision | Status |
|---|---|---|---|---|
| Hindu | Original Qumanity poetry | hi | `approved` | **Live** |
| Hindu | Gita Press Vinaya Patrika | — | `not_permitted` | Blocked |
| Christian | Psalms, KJV | en | `approved` | **Live** |
| Christian | Hindi Bible, 1914 BFBS | — | `pending_rights_review` (rights OK, text not safe) | Blocked |
| Christian | Hindi Bible, Biblica Open Hindi CV | — | `approved_with_conditions` (owner review required before import) | Blocked |
| Muslim | Quran, Al-Fatiha, Tanzil Arabic | ar | `approved_with_conditions` | **Live** |
| Muslim | Quran, Urdu (Tanzil/Jalandhry/Maududi) | — | `pending_rights_review` | Blocked |
| Sikh | Guru Granth Sahib (any source) | — | `pending_rights_review`, bordering `not_permitted` | Blocked |
| Buddhist | Dhammapada, Pali + Müller English | pi, en | `approved` / `approved_with_conditions` | **Live** |
| Buddhist | Dhammapada, Hindi (Sankrityayan 1933) | — | `pending_rights_review` | Blocked |
| Jain | Tattvartha Sutra | — | `pending_rights_review` | Blocked |
| Jain | Namokar Mantra | — | `pending_rights_review` | Blocked |

Every "Live" row above is reflected in `religious_text_core.seed_builtin_collections()`,
`Poems/<dir>/README.md`, and `.gitignore`'s carve-out list. Every "Blocked" row has zero text in
this repository and zero code path that can serve it — `resolve_collection()` returns `None` for
any religion with no `review_status='approved' AND marquee_eligible=1` row, which `api_poems_meta`
reports as `coming_soon`, never invented or substituted content. **The Biblica Hindi Bible row is
the one candidate found this session with both verified license terms AND verified real text** —
it remains Blocked only because this task's own authorization boundary requires explicit owner
review before any import, not because of any remaining rights gap.
