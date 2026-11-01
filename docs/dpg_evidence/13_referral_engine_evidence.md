# Qumanity: Referral Engine Evidence

**Supplement to the DPG Standard Indicator 5 (Documentation) and Indicator 1 (SDG Relevance)
evidence.** Not itself a DPG Standard indicator — a factual evidence section the main 01-09 pack
did not previously cover.

> **DPG Evidence Refresh — 2026-11-01.** Internal correction pass, not a DPGA resubmission. This
> is a new addition, not a revision of a previously submitted claim.

## What this covers, and an important distinction made up front

The repository contains **two separate, unrelated features that both use the word "referral,"**
and conflating them would misrepresent what each actually does. Both are documented here, clearly
separated, with implemented behavior distinguished from planned/partial behavior throughout:

1. **Registration referral attribution and the weekly volume bonus** — a logged-out registrant
   may name an existing member as their referrer (a free-text "Referred By" Public ID field); the
   referrer gets a small, immediate Qoin credit and may earn a one-time weekly bonus at volume
   thresholds. This is implemented, wired into the live registration flow, and has dedicated test
   coverage.
2. **The council-approved "Referrer" role and referral code** (`board_core.py`) — a village
   volunteer applies to become a "Referrer," a council member approves the application and a
   unique `REF-XXXXXX` code is minted for them. This has real backend routes and authorization, but
   — established directly from the source below, not assumed — **no code anywhere in this
   repository ever resolves or redeems that code, no frontend template or script references it,
   and no test file exercises it.** It is backend infrastructure for a feature whose actual
   redemption path was never built. This is stated plainly because the mere existence of
   `referrers.code` and `referrers.uses` could otherwise be mistaken for evidence that redemption
   works; it does not.

Every claim below is re-verified against the current repository, 2026-11-01.

## 1. Registration referral attribution and the weekly volume bonus

### Architecture and core module responsibilities

No dedicated `referral_core.py` exists; this feature is split across `app.py` (resolution and
registration-time wiring), `wallet_core.py` (the Qoin credit and bonus logic), and
`migrations/030_referral_bonus_awards.py` (the bonus-award ledger's schema).

### Referral creation, code generation, attribution, and validation

There is no separately "generated" referral code for this path — a referrer is identified by their
own pre-existing, permanent 12-digit Public ID (`account_ids.search_code`), the same identifier
already used throughout the app for account lookup (e.g. `social_core.find_person()`'s own exact-
code search). Two distinct ways a referrer gets attributed, both writing `users.referred_by_user_id`
(`app.py:121`, a plain nullable column on `users`):

- **Assisted registration**: an existing member physically does the registering for someone else
  (`helper_user_id`); that helper is unconditionally the new user's referrer (`app.py:4448`,
  written right after the `INSERT`, before the field below is even consulted).
- **Self-registration with a named referrer**: an optional "Referred By (Public ID)" field on the
  ordinary registration form (`app.py:4508-4520`). Resolution strips non-digits and matches against
  `account_ids.search_code WHERE is_current = 1`; a blank or unrecognized Public ID is never an
  error — the referral is simply absent, exactly as if the field had never existed (the block has
  no `else`/raise branch at all, `app.py:4508-4520`). Deliberately **no PIN or identity check** on
  the named Public ID (`app.py:4506`'s own comment: "naming someone as your referrer doesn't let
  you act as them, so it doesn't need that bar").
- An autocomplete endpoint, `GET /api/public-ids/suggest` (`app.py:2679-2703`), backs the field:
  public (registration happens logged out), requires a minimum 6-digit prefix before it will even
  query, returns only the bare 12-digit code (never a name or location), excludes demo/removed
  accounts, and is rate-limited (30 requests/IP/minute). Frontend: `static/js/register.js:279-292`
  (debounced fetch), `static/js/register.js:1402` (the field's value is sent as
  `referred_by_public_id` in the registration payload, but only when the registration is **not**
  assisted — `hasHelper ? "" : state.form.referredByPublicId`, consistent with the assisted path
  already having its own referrer).

### Reward handling (only where the implementation actually proves it)

Two separate, real reward mechanisms, both confirmed in source:

1. **Per-referral Qoin split** (`wallet_core.apply_free_registration`, `wallet_core.py:88-100`):
   registration is always free — no payment, no donation — but a single notional ₹1 Qoin is still
   minted and split 10 paise per share across 10 shares (8 location tiers, the referrer, the new
   user). With a referrer present, they receive 10 paise (`"free_registration_referrer"`, tagged
   with `related_user_id` for traceability); with none, that 10 paise folds into the new user's own
   share instead (20 paise total). This is unconditional on there being a referrer at all — it is
   not itself the "bonus."
2. **Weekly volume bonus** (`wallet_core.check_and_award_bonus`, `wallet_core.py:357-401`): counts
   how many users a given referrer has referred (`users.referred_by_user_id`, not
   `wallet_transactions` — a single 10-paisa credit is sub-rupee and often never reaches the
   transaction ledger at all, so it is not a reliable per-referral signal to count) in the current
   ISO calendar week (UTC-based boundary, deliberately not local time — `wallet_core.py:367-369`'s
   own comment on why), and awards a one-time tier bonus the first time a threshold is crossed:
   `BONUS_TIERS = ((3, 1), (7, 3), (15, 7))` — 3 referrals in a week → +1 Qoin, 7 → +3, 15 → +7
   (`wallet_core.py:354`, "approved by the founder as-is — not meant to be tuned casually").
   Idempotency is enforced by a real database constraint, not application logic alone:
   `referral_bonus_awards` has `UNIQUE (referrer_user_id, period_type, period_key, tier)`
   (`migrations/030_referral_bonus_awards.py:21`), so calling `check_and_award_bonus` again for
   an already-awarded tier/week is a safe no-op (caught `sqlite3.IntegrityError`, rolled back,
   returns `None` — `wallet_core.py:389-398`), never a double mint.

### Eligibility, duplicate handling, abuse prevention

- A referrer cannot be the registrant themselves — `app.py:4515` explicitly excludes
  `row["user_id"] != user_id` when resolving a self-named Public ID (self-referral via the
  assisted path is structurally impossible, since the helper and the new account are always
  different rows).
- The autocomplete endpoint's rate limit (30/IP/minute) and 6-digit minimum are the only abuse
  controls found; there is no broader fraud/velocity check on referral attribution itself (e.g. no
  limit on how many *different* new accounts may name the same referrer in a short window beyond
  the bonus tiers' own natural weekly reset).
- No eligibility gate (e.g. `is_demo`/`is_removed`) was found on the *referrer* side of either the
  per-referral credit or the weekly bonus count — a demo or removed account could in principle
  still accumulate `referred_by_user_id` attributions and a bonus if one named them, since neither
  `apply_free_registration` nor `check_and_award_bonus` checks the referrer's own status column.
  This is reported as an observed gap, not a claim that it has been exploited.

### Relevant routes, migrations, and frontend integration

- Registration itself: `POST /api/auth/register` (the existing route; referral resolution is one
  step inside it, `app.py:4508-4520`).
- `GET /api/public-ids/suggest` (`app.py:2679-2703`).
- `migrations/030_referral_bonus_awards.py` — the `referral_bonus_awards` table only; the
  per-referral credit itself needs no migration (`wallet_transactions` already existed).
- Frontend: `templates/register.html`'s "Referred By (Public ID)" field, `static/js/register.js`
  (lines above).

### Relevant tests

`tests/test_referral_engine.py` (14 checks) — per its own docstring, covers exactly: resolution of
`referred_by_public_id` into `referrer_user_id` feeding the existing, unchanged
`apply_free_registration` split; a blank/unrecognized Public ID never being an error; and 3
referrals in the same ISO week awarding tier 1 (+1 Qoin) exactly once via
`referral_bonus_awards`. It does **not** test the eligibility gap noted above, the autocomplete
endpoint's own rate limit, or tiers 2/3.

### Current limitations

- No referrer-side eligibility check (demo/removed accounts can apparently still earn referral
  credit and bonuses — see above).
- Only tier 1 of the three `BONUS_TIERS` has direct test coverage.
- No UI surface was found that shows a referrer their own referral count, credited paisa, or bonus
  history distinct from their general wallet transaction list.

## 2. The council-approved "Referrer" role and referral code (`board_core.py`)

### Architecture

Lives entirely inside `board_core.py`'s "Referrers" section (lines 664-717), using its own
sub-schema (`SUB_SCHEMA`, `board_core.py:541-549`):

- `referrer_applications` — `user_id`, `note`, `status` (`pending`|`approved`|`rejected`),
  `decided_by`, `decided_at`.
- `referrers` — `user_id` (primary key — one code per user), `code` (unique), `approved_by`,
  `uses` (integer, defaults to 0).

### Application, approval, and code generation (implemented)

- `apply_as_referrer(conn, user_id, note)` (`board_core.py:666-673`) — inserts a pending
  application; refuses a second pending application or a second application from someone who
  already holds a code.
- `list_referrer_applications(conn)` (`board_core.py:676-678`) — all pending applications, for
  council review.
- `decide_referrer_application(conn, admin_id, application_id, approve)`
  (`board_core.py:691-702`) — on approval, calls `_new_referral_code()` (`board_core.py:681-688`,
  a 6-character code from a 33-character alphabet excluding visually ambiguous characters, prefixed
  `REF-`, retried up to 50 times against a uniqueness check) and inserts the `referrers` row.
- Routes, all `@login_required`, council-admin-gated where relevant (`app.py:910-958`):
  `POST /api/referrer/apply`, `GET /api/referrer/me`, `GET /api/referrer/applications`
  (403 for a non-admin), `POST /api/referrer/applications/<id>/decide` (403 for a non-admin).

### Redemption — not implemented, despite the function existing

- `referrer_for_code(conn, code)` (`board_core.py:705-707`) — resolves a code string to the
  referrer's `user_id`. **Searched this entire repository; this function is never called from
  anywhere** (confirmed via `grep -rn "referrer_for_code" app.py` and across every `*_core.py`
  module — zero call sites outside its own definition).
- `record_referral_use(conn, code)` (`board_core.py:715-717`) — increments `referrers.uses`.
  **Also never called from anywhere.** `referrers.uses` can therefore never be anything other than
  its default of 0 in the current codebase; no path exists that would increment it.
- No template or JavaScript file in `templates/` or `static/js/` references this feature at all —
  no "Apply to be a Referrer" UI, no field anywhere that accepts a `REF-XXXXXX` code, no display of
  `my_referrer_code()`'s own result. `my_referrer_code(conn, user_id)` (`board_core.py:710-712`) —
  the one read function that *is* reachable via `GET /api/referrer/me` — has a working route, but
  nothing in the frontend calls that route either, confirmed by the same repository-wide search.

**Conclusion, stated plainly so it is not mistaken for a working feature:** the application,
council-approval, and code-minting pipeline is real, implemented, and backend-authorized
correctly. The actual *use* of a minted `REF-XXXXXX` code — the part that would make this a
functioning referral program rather than an unused code generator — does not exist anywhere in the
current code, frontend, or tests. This is reported as an honest limitation, not inferred to be
"planned" or "coming soon" — no roadmap or TODO referencing this gap was found in the repository to
support that framing either way.

### Eligibility, duplicate handling, abuse prevention

- One code per user, enforced by `referrers.user_id` being the primary key.
- Code uniqueness enforced by a real `UNIQUE` constraint plus the generator's own retry loop.
- No duplicate-application guard beyond "a pending application already exists" / "you already
  hold a code" (`board_core.py:667-670`) — there is no limit on how many times a *rejected*
  applicant may reapply.
- Since the code is never redeemable anywhere, no abuse-prevention question about redemption
  (double-use, self-referral, etc.) is currently applicable — there is nothing to abuse yet.

### Relevant tests

**None.** No test file in `tests/` references `apply_as_referrer`, `decide_referrer_application`,
`referrer_applications`, `referrers`, `referrer_for_code`, or `record_referral_use` (confirmed by a
repository-wide search of `tests/`). This subsystem has zero automated regression coverage.

### Current limitations (summary)

- No redemption path exists for a minted referral code anywhere in the application.
- No frontend UI exists for applying, viewing a held code, or entering one.
- Zero test coverage.
- `referrers.uses` is dead data — always 0, since nothing increments it.

## Evidence summary

| | Status |
|---|---|
| Source evidence (registration attribution + bonus) | `app.py` (lines 121, 2679-2703, 4508-4520), `wallet_core.py` (lines 88-100, 349-401), `migrations/030_referral_bonus_awards.py`, `static/js/register.js` (lines 279-292, 1402) |
| Source evidence (council Referrer role) | `board_core.py` (lines 541-549, 664-717), `app.py` (lines 910-958) |
| Test evidence | `tests/test_referral_engine.py` — 14 checks (registration attribution + bonus tier 1 only); **zero** tests for the council Referrer role |
| Operational evidence | None independently verified this pass — all testing ran against local throwaway databases |
| Known limitations | No referrer-side eligibility gate on the attribution path; only tier 1 of 3 bonus tiers is tested; the entire council Referrer-code system has no redemption path, no frontend, and no tests |
