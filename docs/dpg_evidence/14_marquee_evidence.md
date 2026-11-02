# Qumanity: Multi-Religion Marquee Evidence

**Supplement to the DPG Standard Indicator 5 (Documentation) and Indicator 1 (SDG Relevance)
evidence.** Not itself a DPG Standard indicator — a factual evidence section the main 01-09 pack
did not previously cover, following the same pattern as `12_family_tree_evidence.md` and
`13_referral_engine_evidence.md`.

> **New, 2026-11-02.** Every claim below cites source file:line evidence from the current
> repository and real test evidence, written the same day the underlying feature was committed —
> re-verified directly, not carried over from any prior session's own summary.

## What this covers

The Poems Marquee's Universal Multi-Religion, Multi-Language architecture: the database schema,
the public-default/profile-religion/independent-reading-religion resolution chain, the Religion
and Language Selectors, rights-gating enforcement, which collections are actually live, and which
remain blocked pending rights research (`docs/marquee_religious_text_sources.md` has the full
research trail; this document covers the *code*, not the rights findings themselves).

## Database architecture (`religious_text_core.py`, new module)

**Four tables**, not five — see the correction note below:

- `religious_traditions` — one row per tradition (`id` a stable slug, e.g. `"hindu"`,
  `"muslim"`), `display_name`, `default_label` (the gold-chip text, e.g. "सीताराम"),
  `default_language`, `sort_order`. A tradition the profile-religion dropdown accepts
  (`RELIGION_BELIEF_VALUES`, `app.py`) but with no `religious_traditions` row at all (jain, other,
  prefer_not_to_say) correctly gets no gold-chip label and is never offered by the Religion
  Selector — there is no fallback/guessed label path.
- `text_collections` — one row per named edition/collection (`slug` unique), `tradition_id`,
  `display_title`, `is_original_work`, source/attribution metadata, and the actual rights gate:
  `rights_status` (`public_domain`|`cc_licensed`|`rights_cleared`|`pending_rights_review`|
  `source_unverified`|`not_permitted`), `review_status` (`draft`|`in_review`|`approved`|
  `suspended`|`retired`), `marquee_eligible` (boolean). **Only a row with
  `review_status='approved' AND marquee_eligible=1` is ever resolvable** — the single choke point
  is `resolve_collection()` (`religious_text_core.py`), whose own `WHERE` clause enforces exactly
  this.
- `text_collection_languages` — one row per language variant of a collection (`language_code`,
  `display_name`, `script_direction` [`ltr`|`rtl`], `is_original_language`, `translator_name`).
- `text_entries` — the actual verses, one row per `(collection_language_id, ordinal)`, with
  `external_ref` (canonical citation, e.g. `"Surah 1:1"`) and the display `marker`/`text` fields.

**Correction to an earlier-session proposal document**
(`docs/audit_multi_religion_marquee_proposal_2026_11.md` §3.6): that proposal's schema also
specified a fifth table, `religion_collection_access`, for a future many-to-many
religion<->collection relationship. **It was not built.** `text_collections.tradition_id` already
gives every current collection a direct, sufficient mapping, and the many-to-many case (e.g. a
future shared "interfaith" collection) has no concrete use yet. This is a deliberate scope
decision recorded in `religious_text_core.py`'s own comments, not an oversight — any owner-facing
report that describes "five tables" should be read as describing that earlier proposal, not the
implementation that actually shipped.

Seeding (`religious_text_core.seed_builtin_collections()`) is idempotent, keyed by `slug` — each
insert is guarded by `SELECT id FROM text_collections WHERE slug = ?` before writing, so re-running
it (which happens on every app boot via `tools/run_migrations.py`'s `_ensure_source_tables()`) is a
no-op once a collection exists. Verified directly this session: a fresh tempfile database seeded
twice in a row (once implicitly via test setup, once via a direct `seed_builtin_collections(conn)`
call) produces no duplicate `text_collections` rows.

## Religion resolution chain

Three distinct religion concepts, never conflated:

1. **A member's own profile religion** (`users.religion_belief`) — set once at registration or via
   an admin-approved change request; never written by anything in this feature.
2. **The resolved default reading religion** — `_marquee_religion_for_session()` (`app.py`):
   `DEFAULT_MARQUEE_RELIGION` ("hindu") for a logged-out visitor, a member with no profile
   religion, or (defensively) a stored value outside `RELIGION_BELIEF_VALUES`; otherwise the
   member's own profile religion verbatim, even if it currently has no content (the "coming soon"
   case is reported, never silently swapped to Hindu).
3. **The independent reading religion** — an explicit, allowlist-checked `?religion=`/`&lang=`
   query parameter on `GET /api/poems/meta` and `GET /api/poems/<lang>/<index>` (`app.py`, same two
   routes as before this feature — no new route was added). `api_poems_meta()` builds
   `available_codes` from `religious_text_core.list_available_traditions(conn)` (traditions with at
   least one approved+eligible collection) and only honors the query parameter if it is in that
   set; otherwise it silently falls through to (2). This is also the structural reason a reading
   religion switch can never write `users.religion_belief` — nothing in this chain has a write path
   to that column at all.

## Religion Selector and Language Selector (`static/js/poems.js`, `templates/_poems_marquee.html`)

A third accordion section, "Reading tradition" (`#pm-religionhead`/`#pm-religionmenu`), added
alongside the pre-existing Speed and Language sections inside the same settings popover
(`#pm-combomenu`). `buildReligionMenu()` populates it from `meta.available_religions` — the exact
same list `api_poems_meta()` used to validate the query parameter, so the UI can never offer a
choice the backend would reject. Selecting a tradition (`setReligion()`) re-fetches meta with
`?religion=<code>`, rebuilds the gold chip (`syncChip()`, now driven by the server's own `label`
field rather than a hardcoded client table), rebuilds the Language Selector for that collection's
own real languages, and persists the choice to `localStorage` under a key scoped per signed-in
member's own Private Code (`reader_scope`, returned by `api_poems_meta()` as `user["private_id_9digit"]`
or `"anon"`) — never a global, unscoped key that could leak one member's reading choice onto
another's session on a shared browser.

RTL rendering (currently exercised by the Arabic Quran collection): each text segment gets
`dir="rtl"`/`"ltr"` from `meta.languages[].dir` (sourced from
`text_collection_languages.script_direction`), applied per-segment only — the marquee's own ticker
scroll direction never flips, matching how a ticker widget conventionally behaves regardless of
the text's own reading direction.

## Rights gating — verified directly this session

`resolve_collection()`'s `WHERE review_status = 'approved' AND marquee_eligible = 1` is the single
enforcement point; confirmed live (fresh tempfile database, `app.test_client()`):

- `GET /api/poems/meta?religion=sikh` and `?religion=jain` both resolve to the requesting session's
  own profile-based default, never `"sikh"`/`"jain"` — neither tradition has an eligible
  collection.
- `GET /api/poems/hi/0?religion=christian`, `GET /api/poems/ur/0?religion=muslim`,
  `GET /api/poems/hi/0?religion=buddhist` (a blocked language within an otherwise-approved
  religion) all 404.
- `available_religions` in every `api_poems_meta()` response lists exactly `hindu`, `christian`,
  `muslim`, `buddhist` — never `sikh`, `jain`, `other`, or `prefer_not_to_say`.

## Approved vs. pending collections

Four collections are `review_status='approved', marquee_eligible=1` today: Hindu (original
Qumanity Hindi poetry, `Poems/hindu_original/`), Christian (Psalms KJV, `Poems/christian/`),
Muslim (Quran Surah Al-Fatiha, Arabic, Tanzil Project, `Poems/muslim/`), Buddhist (Dhammapada ch.
1 vv. 1-5, Pali + English/Müller, `Poems/buddhist/`). Five content areas remain blocked
(`pending_rights_review`, no `Poems/` file exists for any of them, confirmed by direct filesystem
check): Urdu Quran, Sikh Gurbani, Hindi Bible, Hindi Dhammapada, Jain texts. See
`docs/marquee_religious_text_sources.md` for the full research trail and
`docs/MASTER_STATUS.md`'s "Marquee — Pending Rights (Content Only)" section for the owner-facing
summary. The Gita Press Hindi Vinaya Patrika translation is a separate, longer-standing
`not_permitted` finding (no verified publication permission exists in this repository); the public
Hindu default has always used the original Qumanity collection instead, labeled accurately and
never as Vinaya Patrika — see `/copyright/gita-press` and the new `/copyright/religious-texts`
notice page.

## Relevant routes

| Route | Change |
|---|---|
| `GET /api/poems/meta` | Unchanged route; now reads optional `?religion=`/`&lang=`, allowlist-checked |
| `GET /api/poems/<lang>/<index>` | Unchanged route/signature; now reads optional `?religion=`, same allowlist check |
| `POST /api/marquee/hide` / `POST /api/marquee/show` | Unchanged (pre-existing hide/restore preference, unrelated to religion resolution) |

No new route was added for any religion or language — confirmed by `inspect.signature(app.api_poem)`
in `tests/test_poems_marquee.py`, which still asserts the route's only URL-path parameters are
`lang`/`index`.

## Tests

`tests/test_poems_marquee.py` — **193 checks, 0 failures** (re-run 2026-11-02), covering: default
resolution for all four live traditions, JSON validation for every seeded collection file, explicit
absence checks for every blocked collection's `Poems/` file, independent reading-religion selection
with a direct database check that `users.religion_belief` is never written, religion/language
switching across all four collections, missing/unapproved-collection fallback (including a bogus
`?religion=` value), Cache-Control/no-cross-account-leak checks, and the pre-existing hide/show
markup and security-boundary tests carried forward unchanged.

## Evidence summary

| | Status |
|---|---|
| Source evidence | `religious_text_core.py` (new, 375 lines), `app.py` (marquee section, `_marquee_religion_for_session`/`api_poems_meta`/`api_poem`), `static/js/poems.js`, `static/css/poems.css`, `templates/_poems_marquee.html`, `tools/run_migrations.py` (seeding call) |
| Test evidence | `tests/test_poems_marquee.py`, 193 checks, re-run 2026-11-02 |
| Operational evidence | None independently verified this pass — all testing ran against local throwaway databases; production deployment behavior has not been checked |
| Known limitations | Four tables, not the five an earlier proposal document specified (see correction above); five content areas remain blocked pending rights review (see `docs/marquee_religious_text_sources.md`); RTL layout has been exercised for Arabic only, not yet any other RTL script |
