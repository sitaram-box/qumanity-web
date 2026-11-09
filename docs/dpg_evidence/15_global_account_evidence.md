# Qumanity: Global Account Evidence

**Supplement to the DPG Standard Indicator 5 (Documentation) and Indicator 1 (SDG Relevance,
worldwide reach) evidence.** Not itself a DPG Standard indicator — a factual evidence section the
main 01-09 pack did not previously cover, because this feature was built and shipped after that
pack's own last refresh pass (2026-11-01/02). Added 2026-11-09; every citation below is verified
against the current repository, not restated from a handover document.

## What this covers

A member whose **Present Location's** country is outside the 10 Public Account Activation
countries registers as a **Global Account** instead of a Public Account: Global, Personal and
Private access, but no local Public Timeline and no Q-Punch (Village Council election)
eligibility. This directly extends the project's SDG-relevance claim of worldwide, free
registration (Document 01, §1) — before this feature, registration outside the Sub-continent was
not possible at all.

## Classification: derived, never a persisted flag

`account_core.account_access_type(present_location)` (`account_core.py:56-71`) returns
`"public"` if `present_location["country"]["id"]` is one of ten fixed ids
(`SUBCONTINENT_COUNTRY_IDS`, `account_core.py:19-22`: India, Nepal, Bhutan, Bangladesh, Myanmar,
Sri Lanka, Pakistan, Balochistan, Afghanistan, Maldives), else `"global"`. This is computed live
from `users.present_location_json` on every call — there is no `account_type` or
`is_global_account` column in the `users` table; `app.py`'s `_profile_for()`
(`app.py:3183`) computes it fresh for every `/api/me` response rather than reading a cached
value, specifically so it can never drift out of sync with a later council-approved location
correction.

## Registration

`api_auth_register()` (`app.py:4305`) branches on `is_global_account = present_country_id not in
SUBCONTINENT_COUNTRY_IDS` (`app.py:4376`). For a Global Account, `present_location` must stop at
`{continent, country}` — any `state`/`zone`/`district`/`tehsil`/`village` key is rejected outright
(400), never silently dropped, and the continent/country pair is checked against the real
7-continent/229-country world database (`account_core.is_valid_global_country()`) rather than
trusted as two independent client-supplied facts. Birth Location was never restricted to the 10
countries and is unaffected by this feature either way.

## Backend enforcement — not new authorization code, existing checks correctly excluding an empty location

Q-Punch (Village Council election) ineligibility and local Public Timeline exclusion are not new
rules written for this feature — they are the *absence* of a matching location chain for every
pre-existing check: `board_core.chain_of()` produces no chain entries below Country for a Global
Account's location (no village/tehsil/district/state/zone), so `board_view()`/`create_post()`/
`cast_vote()` all correctly exclude it the same way they already excluded an India resident with
no Tehsil set. `election_core._present_village_id()` additionally re-derives
`account_core.account_access_type()` from the same `present_location_json` directly (not merely
the presence of a village key) before ever returning a village id to `nomination_eligible()`/
`voting_eligible()` — closing a specific, confirmed gap (a stale or malformed location record
carrying a village id could otherwise have granted eligibility; see the 2026-11-08 hardening
history in `docs/HANDOVER.md` §9.3 for the full account).

## Global voting on Country/Continent/Earth-level posts

A Global Account *can* vote on Collective Board posts that have risen to Country, Continent, or
Earth level — scoped by shared geography (a Japan account can vote alongside India/Nepal/etc. at
Continent level, since both share `continent.id = "O_AS"`; Country-level posts are visible only
to residents of that exact country; Earth level is universal for every account type). This is the
existing `cast_vote()`/`chain_of()` contract working as designed for any account whose location
reaches that level — not a Global-Account-specific carve-out.

## The account-ID-request security correction ("C1")

A second, independent path that can change `users.present_location_json` —
`social_core.request_new_account()`/`decide_account_request()` (the dedicated "request a new
Account ID" flow, reached via `POST /api/people/account-ids/request` and
`POST /api/admin/account-ids/<id>/decide`) — was found, during an independent adversarial
pre-merge audit, to apply none of the validation the registration/profile-change paths already
had. This would have let a Global Account submit a fabricated Public/India village location and,
once an admin approved it, cross the Global↔Public boundary and acquire real Q-Punch village
eligibility. Fixed by moving the shared validator,
`account_core.validate_present_location_change()`, into this same dependency-light module (so
`social_core.py` can call it without a circular import) and calling it at both submission and
approval in this second path, mirroring the first. Full detail, including the live-reproduced
exploit and its closure, is in `docs/HANDOVER.md` §9.3 — not duplicated here to avoid the two
documents drifting apart on the same facts.

## Relevant routes

| Route | Core function |
|---|---|
| `POST /api/auth/register` | `api_auth_register()` — same route Public Accounts use; branches internally |
| `GET /api/me` | `_profile_for()` — returns `is_global_account: boolean`, derived live |
| `POST /api/people/account-ids/request` | `social_core.request_new_account()` (validated, see above) |
| `POST /api/admin/account-ids/<id>/decide` | `social_core.decide_account_request()` (re-validated at approval) |

## Relevant tests

| Suite | What it verifies |
|---|---|
| `tests/test_global_account.py` (136 checks) | Registration (Japan, Kenya, client-flag-spoofing, fabricated-village rejection), Dashboard tab assertions against actual rendered HTML, direct backend rejection of Public routes, Country/Continent/Earth voting scope, Q-Punch/election rejection, profile-change-request hardening, full ancestry-chain validation, admin-simulation bypass checks, registration-Village corrective checks |
| `tests/test_account_id_request_security.py` (31 checks) | The C1 security correction — submission/approval validation, the real exploit reproduced through the actual HTTP routes and confirmed rejected, approval-time revalidation against changed account state, Path B regression |
| `tests/test_election_winner_tally.py` (25 checks) | An unrelated Q-Punch winner-tally bug found and fixed in the same engagement, re-tallying a closed election cycle correctly when votes arrive after it was first observed as closed |

## Evidence summary

| | Status |
|---|---|
| Source evidence | `account_core.py` (full module, new), `app.py` (`api_auth_register()`, `_profile_for()`, lines cited above), `social_core.py` (`request_new_account()`, `decide_account_request()`), `election_core.py` (`_present_village_id()`) |
| Test evidence | 136 + 31 + 25 = 192 directly-dedicated checks, plus the full backend suite (33 files, 1,370 checks at time of this feature's release) showing no regression |
| Operational evidence | Confirmed live on production (`https://web-production-126c3f.up.railway.app`) by direct, read-only inspection of the deployed registration page and `/api/me` response after the release that shipped this feature — see `docs/HANDOVER.md` §9.3/§14 |
| Remaining limitations | No Global↔Public account-type transition workflow exists in the product yet (a documented gap, not a bug — see `docs/HANDOVER.md` §9.3); the mobile app's own parallel implementation of this feature is tracked separately in `Qumanity_App`, not this evidence pack |
