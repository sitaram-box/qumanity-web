# Buddhist marquee source — Dhammapada

| Item | Status |
|---|---|
| Pali root text | Dhammapada, Ch. 1 (Yamakavagga), vv. 1-5. Mahāsaṅgīti/Chaṭṭha Saṅgāyana edition lineage, retrieved live from SuttaCentral's own API (`suttacentral.net`), 2026-11-02. |
| Pali rights | Public domain. SuttaCentral's own stated position (corroborated via their `bilara-data` GitHub repository and a mirror of their copyright page, since the live `/licensing` page is a JS single-page app that could not be fetched directly this session): "The original texts of Buddhism in Pali, Chinese, Sanskrit, Tibetan, and other languages are in the public domain." **Condition: re-confirm directly at `suttacentral.net/licensing` in a real browser before relying on this further** (not yet done — flagged honestly, see `docs/marquee_religious_text_sources.md`). |
| English translation | F. Max Müller (1881), *Sacred Books of the East*, Vol. X. Retrieved live from Project Gutenberg eBook #2017, 2026-11-02. |
| English rights | Public domain. Project Gutenberg's own standard, unrestricted license applies to this ebook; publication year (1881) places it in the public domain worldwide regardless. High confidence. |
| Hindi translation | **Not included.** No genuinely public-domain or openly-licensed Hindi Dhammapada translation could be confirmed. One unverified lead (a Rahul Sankrityayan Pali-Sanskrit-Hindi edition) surfaced but its scan authenticity/publication facts were not independently confirmed — not used. Marked `pending_rights_review`, no file exists for it. |

Five verses only (`dhammapada_pi/pali.json`, `dhammapada_en/english_muller.json`), same
`{id, marker, text}` shape every other marquee source uses, selected for a scrolling marquee
rather than reproducing the full 423-verse text. `marker` carries the canonical chapter:verse
citation (`Dhammapada 1.1`–`1.5`).

Required attribution:
- Pali: "Pali text: Mahāsaṅgīti (Chaṭṭha Saṅgāyana) edition, via SuttaCentral.net — public domain."
- English: "English translation: F. Max Müller (1881), *Sacred Books of the East* Vol. X — public domain (Project Gutenberg eBook #2017)."

See `docs/marquee_religious_text_sources.md` for the full research trail, including why Sujato's
alternative CC0 SuttaCentral translation was considered but not used here (Müller's Gutenberg
provenance needed no manual follow-up condition, so it was preferred for a first launch).
