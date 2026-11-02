# Muslim marquee source — Quran (Surah Al-Fatiha, Arabic only)

| Item | Status |
|---|---|
| Arabic text | Surah Al-Fatiha (Surah 1), all 7 ayahs, Uthmani Mushaf script. Retrieved live, verbatim, from the Tanzil Project (`tanzil.net`), 2026-11-02. |
| Arabic rights | **Approved with conditions.** Tanzil Project's own license page (`tanzil.net/docs/Text_License`, fetched directly this session): "Tanzil Quran Text — Copyright (C) 2007-2021 Tanzil Project — License: Creative Commons Attribution 3.0." "Permission is granted to copy and distribute verbatim copies of this text, but CHANGING IT IS NOT ALLOWED." "This Quran text can be used in any website or application, provided that its source (Tanzil Project) is clearly indicated, and a link is made to tanzil.net..." |
| Urdu translation | **Not included.** Tanzil also hosts Urdu translations (e.g. Jalandhry), but their own terms page carries an ambiguous clause — "Redistributing the following list in another website is not allowed, unless direct permission is granted by the Tanzil Project" — that was not resolved this session. **Do not publish Urdu translation text until the Tanzil Project (via their `tanzil-text` Google Group) confirms in writing that displaying rotating excerpts, non-commercially, with attribution, is permitted.** See `docs/marquee_religious_text_sources.md`. |

**Conditions attached to the Arabic text's approval (binding, not optional):**
1. Display ayahs character-for-character unmodified — no re-diacritization, re-wording, or re-segmentation beyond normal ayah boundaries.
2. Visibly credit "Tanzil Project" as the source.
3. Include a clickable link to `tanzil.net` near the widget.
4. Keep this attribution standing/permanent, not a one-time credit.

Required attribution text: "Quran text: Tanzil Project (tanzil.net), Uthmani Mushaf, CC BY 3.0."

Seven ayahs only (`quran_ar/alfatiha.json`), same `{id, marker, text}` shape every other marquee
source uses. `marker` carries the canonical Surah:Ayah citation. Arabic is right-to-left — the
frontend (`static/js/poems.js`) sets `dir="rtl"` on this collection's rendered segments based on
`text_collection_languages.script_direction` (see `religious_text_core.py`), never assumed from
the language code alone.

See `docs/marquee_religious_text_sources.md` for the full research trail.
