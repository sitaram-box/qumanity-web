# Founder's Message: full translation into all 12 languages (2026-10-05)

Follows up on `docs/founders_message_2026_10.md`, which explicitly deferred this: *"The full
~1,500-word letter itself is still English-only."* The Founder reported the homepage language
picker didn't carry over to `/founders-message`, and asked for a language switcher there plus a
real translated copy of the full letter in every language, not just the homepage preview.

## What was built

1. **A full, original translation of the entire letter into all 12 supported languages** — hi, bn,
   ur, mr, te, ta, gu, kn, or, ml, pa, as. Each is a complete, independent translation (not a
   mechanical pass), done by dedicated translation passes per language, each given the full
   English source plus this project's own already-approved title/preview translations (from
   `scripts/build_ui_locales.py`'s `founder_msg_title`/`founder_preview` keys) to keep terminology
   consistent with the rest of the site. Every translation preserves:
   - the `## `-prefixed heading markers (parsed by `founders_message.html`'s paragraph-splitting
     logic) with the heading text itself translated,
   - the literal `{founder_account_id}` placeholder, untouched, for `founder_core.get_message()`'s
     existing runtime substitution,
   - "Qumanity" left untranslated throughout,
   - the closing three lines (जय श्री राम / Jai Hind / Jai Humanity) unchanged in every language —
     a deliberate choice, not an oversight: this is a fixed, nationwide patriotic closing, not
     ordinary prose to localize.
   Seeded via a new one-off script, `scripts/seed_founder_message_i18n.py` (safe to re-run — it
   UPSERTs by language), into the existing `founder_messages` table `founder_core.py` already had
   ready for exactly this (`language` column, previously only an `'en'` row existed).

2. **A language switcher on `/founders-message` itself** (`static/js/founders_message_i18n.js`,
   `templates/founders_message.html`) — reuses the homepage's own `qm_home_lang` localStorage key
   (`static/js/home_i18n.js`) so a language picked on either page carries over to the other.
   Unlike the homepage's picker (which swaps small `[data-i18n]` strings client-side), this page's
   whole letter is server-rendered from the DB per `?lang=`, so picking a language here is a real
   navigation, not a text swap — the route already supported `?lang=` before this pass; the gap was
   purely that nothing on the page read or wrote the shared language preference, and no row existed
   to serve besides English.
   - On first load with no explicit `?lang=`, it checks `qm_home_lang` and redirects once if a
     non-English language was already chosen elsewhere.
   - Picking a language updates `qm_home_lang` and reloads with `?lang=<code>`.
   - **RTL handling for Urdu**: `<html dir="rtl">` is set when `message.language == 'ur'`, with a
     matching CSS rule flipping the language-picker dropdown's side. Verified live: `dir="rtl"`
     appears only for Urdu, never for the other 11.

## Verified

- All 12 languages render at 200 with the live Account ID correctly substituted into
  `{founder_account_id}` and no leaked, unsubstituted placeholder text.
- Ran an automated cross-script contamination check (grouping every character of every non-English
  `full_text` by Unicode block, e.g. Devanagari vs. Gurmukhi vs. Kannada vs. Telugu) to catch any
  accidental mixing between languages during authoring — caught and fixed one real instance (a few
  stray Gurmukhi characters that had ended up inside the Kannada text from an earlier manual
  correction pass) before it reached the database. Final check: all 12 clean.
- RTL (`dir="rtl"`) confirmed present for Urdu only, absent for every other language.

## Scope note

This only translates the long-form letter and its page. It does not touch the already-translated
homepage preview sentence (unchanged, still correct) or re-open the logo/cow-symbolism question
from earlier in the project (still deferred, per the Founder's own instruction).
