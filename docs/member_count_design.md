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
