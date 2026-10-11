# Poems marquee archive

The poems marquee (the scrolling strip at the bottom of every page and app screen) is **hidden** as of 2026-10-07. Its code is kept in this repository for future re-enablement.

**IMPORTANT:** The poem files themselves have been moved out of the public repository to prevent distribution of the Poddar Hindi translations. They are preserved on the Founder's local machine and will be re-imported (or replaced with cleanly-licensed translations) when the marquee is re-enabled.

## Source and rights

| Item | Status |
|---|---|
| Original text | *Vinay Patrika* (विनय पत्रिका) by Goswami Tulsidas (d. 1623). Public domain. |
| Hindi translation (`Poems/poems_hindi.json`) | By Hanuman Prasad Poddar (d. 1971). In copyright in India until the end of 2031; enters the public domain on 1 January 2032 (life + 60 years, Copyright Act 1957, s.22). |
| English, Kannada, Malayalam, Tamil and Telugu files | Prepared from the Hindi file. Until their source is confirmed, treat them as derivatives of the Poddar translation, under the same restriction. |

## What is kept, and where

- **Poem data:** six files (`poems_hindi.json`, `poems_english.json`, `poems_kannada.json`, `poems_malayalam.json`, `poems_tamil.json`, `poems_telugu.json`, 237 poems each) moved out of the repository to `~/Desktop/Qumanity_Poems_Private/Poems/` on the Founder's machine. `Poems/` is listed in `.gitignore`. Earlier commits still contain the files until the git history is purged.
- **Website:** `templates/_poems_marquee.html`, `static/js/poems.js`, `static/css/poems.css`, and the `/api/poems/...` routes in `app.py`.
- **Phone app (Qumanity_App):** `mobile/src/components/PoemsMarquee.tsx`.

## How it is switched off

| Where | Flag | Default |
|---|---|---|
| Website | Environment variable `QM_MARQUEE_ENABLED` (read in `app.py`) | `false`: the marquee is not rendered and `/api/poems/...` returns 404 |
| Phone app | `EXPO_PUBLIC_QM_MARQUEE_ENABLED` (read in `mobile/src/config.ts`) | `false`: the marquee component is not mounted |

## To re-enable

1. Copy the files back into `Poems/` at the repository root (or supply new ones) and remove `Poems/` from `.gitignore` only once they are cleanly licensed. Replace `poems_hindi.json` with a cleanly licensed or work-for-hire Hindi translation. Keep the same `{id, marker, text}` format and the same ids.
2. Replace or re-derive the other language files from that new Hindi text.
3. Record the new translator and licence in the table above.
4. Set `QM_MARQUEE_ENABLED=true` on the website (for example in Railway's variables) and `EXPO_PUBLIC_QM_MARQUEE_ENABLED=true` for the app build.
