# Christian marquee source — Hindi (Biblica Open Hindi Contemporary Version)

| Item | Status |
|---|---|
| Collection | Biblica "Open Hindi Contemporary Version" (हिंदी समकालीन संस्करण-स्वतंत्र उपलब्धि) |
| Language | Hindi (`hi`) |
| Religion | Christian |
| Edition | Copyright © 1978, 2009, 2016, 2019 by Biblica, Inc. |
| Source | `ebible.org/hincv/` (per-chapter pages, e.g. `ebible.org/hincv/PSA023.htm`) |
| License | Creative Commons Attribution-ShareAlike 4.0 International — <https://creativecommons.org/licenses/by-sa/4.0/> |
| Retrieved | 2026-11-02, fetched live, verse by verse, directly from the pages above |
| Coverage | **Partial** — 8 individually selected Psalm verses, not the complete Hindi Bible. Deliberately mirrors `Poems/christian/psalms_kjv_en.json`'s own 8-verse selection (same Psalm references, Psalm 23/46/100/118/121/34/37/19) so the English and Hindi Christian collections read as companions, not two unrelated selections. |

## License terms (quoted directly from `ebible.org/hincv/copyright.htm`, re-verified 2026-11-02)

> "This work is made available under the Creative Commons Attribution-ShareAlike 4.0 International
> License (CC BY-SA)."

Conditions: (1) include the copyright and source information; (2) if you change the text, make
clear the original licensor does not necessarily endorse your changes; (3) redistribute any
contribution under the same license; (4) a derivative work (not a verbatim, unmodified copy) must
**remove the Biblica® trademark symbol** and instead use the license's own derivative-work
attribution wording, quoted directly from the same page:

> "The original work by Biblica, Inc. is available for free at www.biblica.com and open.bible."

**Qumanity's use is treated as a derivative work**, not an unmodified copy: eight verses were
individually selected out of the full Hindi Bible and reformatted into this project's own
`{id, marker, text}` JSON shape. Accordingly:

- The Biblica® trademark symbol is **not** used anywhere in Qumanity's own UI or documentation for
  this collection — "Biblica" is named as the publisher without the registered-trademark mark.
- The derivative-work attribution line above is used verbatim (see `attribution_text` in
  `religious_text_core.py`'s seed entry for this collection).
- This file itself discloses the change made (selection + JSON reformatting) per condition (2).
- The resulting JSON file is itself released under CC BY-SA 4.0 (condition 3) — any reuse of
  `poems_hindi.json` in this directory must carry the same license.

## Required attribution text

"Hindi text: Biblica Open Hindi Contemporary Version. The original work by Biblica, Inc. is
available for free at www.biblica.com and open.bible. Licensed CC BY-SA 4.0
(creativecommons.org/licenses/by-sa/4.0/). Eight verses selected and reformatted by Qumanity."

## Verifying or correcting an entry

Each `marker` is the canonical Book Chapter:Verse citation. To check or correct a verse, open the
matching chapter page at `ebible.org/hincv/<BOOK><CHAPTER>.htm` (e.g. `PSA023.htm` for Psalm 23)
and compare the cited verse number's text directly against that live page — never guess or
paraphrase a correction. Any future addition to this collection must go through the same
verbatim-retrieval process documented in `docs/marquee_religious_text_sources.md`, never an
AI-generated or machine-translated substitute.

Same `{id, marker, text}` shape every other marquee source uses, selected for a scrolling marquee
rather than reproducing the full Bible. Served when a Christian reader selects Hindi as their
reading language (`?religion=christian&lang=hi`) — the English KJV collection
(`Poems/christian/psalms_kjv_en.json`) remains the Christian default language and is unaffected by
this addition.
