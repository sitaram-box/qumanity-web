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
- **Open-license alternative (not public domain, but clean text):** `ebible.org/hincv/copyright.htm` — Biblica's "Open Hindi Contemporary Version." © 1978–2019 Biblica, Inc., released under **CC BY-SA 4.0** ("This work is made available under the Creative Commons Attribution-ShareAlike 4.0 International License"). Requires attribution to Biblica and that any derivative stay under CC BY-SA (share-alike); the "Biblica®" trademark can't be used on modified text without separate permission. Verse text was not fetched this session (not required for the rights report), so this remains a documented lead, not an imported collection.
- **Decision:** `pending_rights_review`. No Hindi Bible content is served. Next step: either get a clean transcription of the 1914 BFBS edition verified against the page images, or adopt the Biblica CC BY-SA 4.0 edition (fetch its actual verse text and confirm the share-alike attribution can be met) in a follow-up pass.

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

- Tanzil also hosts multiple Urdu translations (e.g. Jalandhry). Fetched directly: `tanzil.net/trans/`'s Terms of Use section:
  > "The translations provided at this page are for non-commercial purposes only." "If used otherwise, you need to obtain necessary permission from the translator or the publisher." "Redistributing the following list in another website is not allowed, unless direct permission is granted by the Tanzil Project."
- This last clause is genuinely ambiguous — it could mean "don't republish our index/catalog page" or "don't republish the translation text on your own site," and this session could not resolve which. A sample was retrieved for internal verification only and is **not** published.
- **Decision:** `pending_rights_review`. Before publishing Urdu verses, email the Tanzil Project (via their `tanzil-text` Google Group, linked from the download page) and get explicit written confirmation. The Arabic text's approval is independent and does not wait on this.
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
- **Decision:** `pending_rights_review`, bordering on `not_permitted` given the explicit
  non-grants found. **No Sikh text — Gurmukhi or any named translation — is published.** No
  `Poems/sikh/` directory exists; no `religious_traditions`/`text_collections` row claims Sikh
  content is available (the tradition simply has zero eligible collections, so the Religion
  Selector and `resolve_collection()` both correctly omit it).
- **Recommended next step (not pursued this session):** contact the Khalis Foundation and
  separately the Sant Singh Khalsa translation's current publisher for explicit written permission
  to display a short rotating excerpt, non-commercially, with attribution.

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

- No genuinely public-domain or openly-licensed Hindi Dhammapada translation could be confirmed.
  One unverified lead (a Rahul Sankrityayan Pali-Sanskrit-Hindi edition; Sankrityayan died 1963,
  so a work of his could plausibly already be public domain in India under the life+60 rule) was
  found but its scan authenticity and exact publication facts were not independently confirmed.
- **Decision:** `pending_rights_review`. No Hindi Dhammapada file exists.

---

## 6. Jain, Other, Prefer not to say

Not independently re-researched this session (out of the five traditions this task named as
in-scope). The pre-existing finding from `docs/audit_multi_religion_marquee_proposal_2026_11.md`
stands: Jain sourcing is mixed/unresolved (JainQQ-hosted scans carry explicit modern copyright
notices; JLOR, announced 2024, has unconfirmed terms) and was not revisited. "Other" and "prefer
not to say" are not specific traditions and have no text collection to research. Neither has a
`religious_traditions` row, matching their pre-existing "profile-accepted only, no symbol, no
content" status.

---

## 7. Summary table

| Tradition | Collection | Languages served | Rights decision | Status |
|---|---|---|---|---|
| Hindu | Original Qumanity poetry | hi | `approved` | **Live** |
| Hindu | Gita Press Vinaya Patrika | — | `not_permitted` | Blocked |
| Christian | Psalms, KJV | en | `approved` | **Live** |
| Christian | Hindi Bible (1914 BFBS) | — | `pending_rights_review` (rights OK, text not safe) | Blocked |
| Muslim | Quran, Al-Fatiha, Tanzil Arabic | ar | `approved_with_conditions` | **Live** |
| Muslim | Quran, Urdu (Tanzil) | — | `pending_rights_review` | Blocked |
| Sikh | Guru Granth Sahib (any source) | — | `pending_rights_review` | Blocked |
| Buddhist | Dhammapada, Pali + Müller English | pi, en | `approved` / `approved_with_conditions` | **Live** |
| Buddhist | Dhammapada, Hindi | — | `pending_rights_review` | Blocked |
| Jain | — | — | not researched this session (pre-existing: unresolved) | Blocked |

Every "Live" row above is reflected in `religious_text_core.seed_builtin_collections()`,
`Poems/<dir>/README.md`, and `.gitignore`'s carve-out list. Every "Blocked" row has zero text in
this repository and zero code path that can serve it — `resolve_collection()` returns `None` for
any religion with no `review_status='approved' AND marquee_eligible=1` row, which `api_poems_meta`
reports as `coming_soon`, never invented or substituted content.
