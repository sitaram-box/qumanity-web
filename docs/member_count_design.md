# Member Count Design (2026-10-17)

## The rule

A user counts toward the total members of exactly one location: their **present residence**
(`users.present_location_json`), never their birth location, work location, or anywhere they're
currently traveling. Present location is residence, set only by an explicit, user-initiated
action — never GPS, IP geolocation, or a scheduled job (audited directly against the code: every
write site to `present_location_json` traces back to a `@login_required` route reading a
client-submitted request body, with the two location-*change* paths additionally requiring
council/admin approval of a member-submitted request).

`location_elements.total_users` reflects this residence-only population
(`is_demo=0 AND is_removed=0`, present-location-keyed). `location_elements.birth_users` is
separate, metadata-only — "how many real users were born here" — never counted toward
`total_users`, never driving membership, voting, or participation.

## The `birth_users` column

`location_elements.birth_users` (migration 018) counts real users (`is_demo=0 AND is_removed=0`)
whose **birth** location matches this row — the same population `update_location_stats()` has
always tracked, kept entirely separate from `total_users` (present-location membership). A
location can have one without the other: a user's birth village gets `birth_users` credit with
`total_users=0` if they no longer live there; the village they live in now gets `total_users`
credit with `birth_users=0` if nobody who lives there was born there.

This is metadata, not membership — it answers "where did this location's people come from," never
"who is a member here." It does not drive voting, board posting, participation, or any count the
site presents as "N members." Exposed via `/api/location/elements/<id>` and `/api/global/elements`
(`location_elements_row_to_dict()`), with small-count suppression applied to `birth_users` alone —
`total_users` on those same two endpoints is not yet suppressed, a separate, already-tracked gap
(`docs/dpg_evidence/06_non_pii_data_extraction.md`'s own action item 5 covers it, alongside
`/api/earth/stats`/`/api/country/stats`/`/api/continent/stats`).

## API field naming inconsistency to resolve (separate task, not fixed here)

`/api/country/stats/<id>` and `/api/continent/stats/<id>` return a field named `total_humans`
meaning "born here" (still birth-location-keyed, unchanged by this correction — see
`docs/dpg_evidence/06_non_pii_data_extraction.md`'s own note that these are the "older" routes).
`/api/location/stats/<level>/<id>` returns a field with the *same name*, `total_humans`, meaning
"lives here." Same name, two different populations depending which endpoint you call — a reviewer
querying both could reasonably expect the numbers to be comparable or additive, and they are
neither.

**Recommended fix**: rename `total_humans` to `born_humans` in `/api/country/stats` and
`/api/continent/stats` specifically (leave `/api/location/stats` as `total_humans`, since that one
is already correctly residence-based). Update `docs/dpg_evidence/API.md` to document both field
names and which population each means. Verify no frontend caller reads `total_humans` by name from
those two specific endpoints before renaming (checked once already during this task's Piece 2
research: no first-party frontend code in this repo calls either endpoint at all today — worth
re-confirming at fix time in case that's changed).

Not fixed now: the current deployment is verified and this isn't gating anything. It needs its own
code change, deploy, and doc update — a separate, small task.

## `/api/location/elements/<id>` requires `?type=<level>`

`location_type` comes from the `?type=` query parameter (`app.py`'s `api_location_elements()`),
defaulting to `"country"` when omitted — already documented in `docs/dpg_evidence/API.md`. Calling
`/api/location/elements/CS.DL.3.4.1A` without `?type=village` will default to `type=country`, find
no matching row for a village id, and return 404 "No data yet for this location." This is not a
bug — the correct call is `/api/location/elements/CS.DL.3.4.1A?type=village`.

## Known gap: live updates vs. scheduled backfill

Member counts are currently refreshed by scheduled backfill (`scripts/backfill_location_elements.py`),
not by live updates when a user's present location changes. This is adequate at current scale.
Live updates become worth building when member movement becomes common — roughly when the pilot
has 100+ members with regular moves.

**Option A (current)**: the backfill recomputes `location_elements` from scratch on demand/on
schedule. Counts are approximate between runs — accurate as of the last backfill, not live.

**Option B (later, not built)**: when a user's present location changes (the two approval-gated
paths in `app.py`/`social_core.py`), decrement the old location's count and increment the new
location's count, for every level, in the same transaction as the `present_location_json` update
— mirroring what `_move_location_element_counts()` already does for birth-location changes. Counts
would always be accurate, at the cost of more code and a second incremental path to keep in sync
with the recompute logic. Not exercised at current scale (1 real member, 0 movement) — deferred
until it is.
