# Multi-language (i18n), election visibility fix, Statistics icon, Founder's Message (2026-10-04)

## 1. Multi-language system

**Max 3 languages per user, unchanged**: mother tongue (locked) + English (locked) + one optional
daily-use/third language of the member's own choice — this was already the model
(`app._user_languages()`); nothing about the 3-language cap changed.

**New: a server-persisted Preferred Language.** `users.preferred_language` (new column, a language
code) decides which of those (up to) 3 languages the whole UI shows in — set from the Private tab's
new "Preferred language" radio picker, or by picking a language from the header dot, both calling
`POST /api/user/languages {preferred: code}`. It now follows the member across devices/browsers
(the old system only remembered a choice in that one browser's `localStorage`).

**Translation data lives in `static/locales/<code>.json`** (one small file per language, fetched on
demand — `scripts/build_ui_locales.py` regenerates them), not bundled inline in `i18n.js` as before.
12 languages have real content: **hi, bn, ur, mr, te, ta, gu, kn, or, ml, pa, as** — all 12 of the
"Indian" language group. The other 10 Sub-continent languages (Pashto, Sindhi, Saraiki, Nepali,
Burmese, Sinhala, Dari, Balochi, Dzongkha, Dhivehi) fall back to English — a deliberate scope cut:
producing confidently-accurate short-UI-string translations for those is lower-confidence territory,
and 12 languages × ~79 keys was already a large volume of real content to generate carefully.
Extending to the rest is just "add a `static/locales/<code>.json` file" — no code change.

**Two bounded "proper noun" vocabularies, also translated into the same 12 languages**:
- `static/data/location_names_i18n.json` — the 7 continents, 10 Sub-continent countries, India's 5
  zones and 37 states (59 places total). District/Tehsil/Village (620,000+ entries) are **not**
  translated — not feasible to hand-translate at that volume; a real fix needs a live
  machine-translation API, which needs its own cost/provider decision before building.
- `static/data/zodiac_terms_i18n.json` — planet names, weekday names, the 12 zodiac sign names
  (reused for Surya Maas/solar months, since a solar month literally is the sun's own sign), and
  Chandra Maas (lunar month) names. Nakshatra/Tithi names are already Sanskrit terms transliterated
  consistently across the Devanagari-family scripts, so they read correctly already; a Dravidian
  script equivalent pass is a documented gap, not attempted here.
- Neither of these is wired into the live UI yet (Kundali's planet table, the Locations table,
  Time-box's panchang labels still show English/already-transliterated-Sanskrit) — the DATA is
  built and verified, but substituting it into those specific render paths is still open.

**Anonymous visitors (homepage, About) now get a real language switcher** (`static/js/home_i18n.js`)
offering **all 23** Qumanity-supported languages (reads `static/data/languages.json` directly, since
there's no "this visitor's 3 languages" concept pre-registration) — reusing the exact same
`static/locales/` files. Verified live: switching to Hindi translates the nav, hero headline/lead,
CTA buttons and the Founder's Message preview correctly.

**Marquee poems now follow the preferred-language choice** (`static/js/poems.js` listens for the
`qm-lang` event both `i18n.js` and `home_i18n.js` dispatch) — but only switches if a poem
*translation file* actually exists for that language (`Poems/poems_<lang>.json`); poems are a
different, much larger translation task (237 full poems per language) than UI strings, so this is a
"follow if available" sync, not a guarantee every UI language has poems too.

**A real bug found and fixed while building this**: tagging an element with `data-i18n` that
contains nested HTML (`<em>`, `<b>`, a child `<span>`) destroys that formatting, because the
textContent-based swap (`el.textContent = translatedText`) strips tags — and this fires even in
English, on every page load, since `loadAndApply()` always runs once. The homepage hero's `<em>`
and `<b>` emphasis spans were rewritten to tag the whole sentence as one plain-text unit instead
(losing the inline emphasis, keeping correct grammar per language — translating individual
word-fragments out of a sentence breaks word order in most other languages anyway).

## 2. Election visibility — sign-gated, not just village-gated

**The bug**: `GET /api/election/candidates` returned every approved candidate's full profile
(name, manifesto, karma) to *any* visitor, regardless of their own zodiac sign — so a Taurus member
could see the full Libra candidate list and (if the UI didn't otherwise block it) attempt to vote.
`election_core.nomination_eligible()`/`voting_eligible()` already blocked the *write* side (you
can't actually nominate or vote for the wrong sign), but nothing blocked the *read* side.

**The fix**: the route now requires login, checks the viewer's own `sun_sign` against the cycle's
`zodiac_sign`, and returns `{"restricted": true, "your_sign": ..., "cycle_sign": ..., "male": [],
"female": []}` — no candidate data at all — for anyone who doesn't match. `static/js/dashboard.js`
shows an explanatory message instead of the candidate list when restricted. Verified live: a
Taurus-born test account got `restricted: true` with empty arrays; a Libra-born one saw the real
3+3 candidates.

**What was already correct and untouched**: `member_guide()` (used by `/api/election/status`)
already computes the right "this isn't your month, your sign's turn is X starting Y" message for
non-matching members — that's unchanged. **Winners stay visible to everyone** once decided —
`council_roster()` / `GET /api/election/council` was never sign-gated and still isn't; that's by
design (results are public, candidacy during an active cycle is not).

## 3. Statistics icon

Not removed — it was never a *button* in the first place. `qm-stats-col` has always been its own
always-rendered column beside the board (not behind a toggle), and on a narrow/stacked layout
(`max-width: 900px`, which collapses the 3-column grid to 1 column) that column ends up stacked
*after* the location-explorer tree and the whole Collective Board feed — on a phone-width screen
that's a long scroll down, easy to miss, which is almost certainly what "I can't find it" meant in
practice.

**Fix**: added a `📊 Stats` button to the board header (`static/js/board.js`'s `.bd-head`, next to
the existing `☰ Groups` and `⚖️ Q-Punch` buttons, matching the Founder's own mockup), which smooth-
scrolls straight to the already-rendered stats column. No data/layout restructuring — the stats
panel's own content and loading logic are untouched, this just makes it easy to find.

## 4. Founder's Message

New `founder_core.py` (`founder_messages` table: title/preview_text/full_text/language/
published_at/is_active, seeded once with the Founder's own English text verbatim) +
`GET /api/founder-message?lang=` + a dedicated `/founders-message` page
(`templates/founders_message.html`) + a homepage preview section with a translated preview
sentence and a "Read Full Message" button.

**Scope decision**: only the short homepage *preview* sentence is translated (via the same 12-
language `static/locales/` system, key `founder_preview`) — the full ~1,500-word letter itself
stays English-only for now. Translating that much prose accurately into 12 languages in one pass
wasn't attempted; the `language` column on `founder_messages` exists specifically so a real
translation can be added later as additional rows, without a schema change.

Section headings in the stored text are marked with a `## ` prefix (parsed by the template) rather
than guessed from formatting — this was a real bug on the first pass (an ALL-CAPS heuristic that
never matched this Title-Case text); fixed by marking headings explicitly instead of inferring them.

## 5. Logo redesign (cow horns / Gau Mata symbolism) — NOT done, by the Founder's own answer

A separate request asked for the logo to be redesigned around cow-horn/teat imagery with explicit
Hindu religious symbolism (Gau Mata, the four Purusharthas), plus matching "Why the Cow?" sections
on the homepage/About page. This directly reverses an explicit prior decision on record
([[project-logo-languages-poems]]: *"The user REJECTED a Shiva Linga / tilak / सीताराम / globe
version; don't reintroduce religious symbols"*, 2026-09-29). Flagged the conflict and asked before
touching anything. **The Founder's answer: they will produce reference images separately
themselves; leave the logo exactly as it is for now.** No logo or philosophy-section work was done.
The current atom/orbits logo (shared between website and app, see
[[project-logo-languages-poems]]) stays as the live logo on both until the Founder brings back
actual reference images to work from.
