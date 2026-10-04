# Election History & Perception Calculator: display gating (2026-10-04)

The Founder asked to keep both features fully functional for saving a user's own input, but hide
the calculated/aggregated result from everyone until a specific later trigger. New module:
`visibility_core.py` (table `system_settings`, a generic key-value store — none existed before).

## What stayed exactly as-is

- Saving your own Election History party choice — `POST /api/election-history`
  (`app.py:api_election_history`) — untouched.
- Reading back your own saved choices + your own Q-Punch vote history on the private dashboard
  (`GET /api/election-history`) — untouched.
- Casting a Perception Pro/Anti vote — `POST /api/perception/country/<id>/vote`,
  `POST /api/perception/zone/<id>/vote` — untouched; `can_vote`/`my_vote`/`vote_reason` in the GET
  responses are untouched too, so the vote buttons keep working normally.

## What's now hidden

- `GET /api/election-sentiment/<level>/<location_id>` (Country/State aggregate %, previously shown
  in the Collective Board's country/state view via `board.js`'s `loadSentiment`) — now returns
  `{"visible": false, "reason": "..."}` instead of the real breakdown, unless open (see below).
  `board.js` shows the reason text in place of the bars.
- `GET /api/perception/country/<id>` / `.../zone/<id>` — `pro_count`/`anti_count` come back `null`
  and `results_visible: false` with a `results_reason` unless open. `dashboard.js`'s
  `renderPerception` hides the bar/count elements and shows the reason text instead; the vote
  button block is unaffected.

## When Election History opens automatically

Either, for exactly 1 year:
1. **2028-03-21** (this app's zodiac system uses fixed civil-calendar MM-DD boundaries everywhere —
   see `zodiac_core.ZODIAC_RANGES`'s Aries start "03-21" — there is no real ephemeris "Sun enters
   Aries" helper in this codebase, so this reuses that same existing convention rather than adding
   a new one), or
2. Earlier, from the day the count of India-resident (present-location) users with at least one
   saved Election History entry first reaches **50,00,000 (5,000,000)** — timed "to give survey
   reports only 1 year before [the] next national election of Lok Sabha in 2029." Once that day is
   reached it's frozen in `system_settings` (`election_history_threshold_crossed_at`) so the
   1-year window doesn't keep sliding as the count keeps climbing after that.

Both paths were verified directly: the window opens exactly on the trigger date, stays open for
365 days, and closes the day after — and crossing the (test-lowered) count threshold correctly
freezes the trigger date on first crossing only.

## Perception Calculator: no automatic trigger

Only a manual Admin override opens it — no date or count condition was specified for this one.

## Admin override (either gate, any time)

`GET /api/admin/visibility` (admin-only, `_is_admin()` — same env-var-gated pattern as every other
admin route in this app, e.g. `/api/admin/election-cycle`) returns a full snapshot: current
visibility + reason for both gates, the live India-saved-count vs. the 50,00,000 threshold, and
any override in effect.

`POST /api/admin/visibility/<key>` (`key` = `election_history` or `perception`), body
`{"enabled": true|false|null, "display_until": "YYYY-MM-DD"|null}`:
- `enabled: true` forces that gate open (optionally until `display_until`).
- `enabled: false` forces it shut, even inside what would otherwise be an open window.
- `enabled: null` clears the override — Election History falls back to its automatic schedule;
  Perception simply goes back to hidden, since it has no automatic schedule of its own.

**Note**: `_is_admin()` only recognizes Private IDs listed in the `QM_ADMIN_PRIVATE_IDS`
environment variable — this isn't set in local dev yet, so these two endpoints 403 (or redirect to
login, matching every other `@login_required` admin route) until that env var is set to the
Founder's own Private ID on whichever server actually runs this.

## Deliberately not done this pass

**State-level (Vidhan Sabha) data moving from a State page into its Zone page** — the Founder
asked for state results to eventually appear nested inside the zone view ("where user can check
their own state data separately"), not as their own page. Right now the only live surface for this
data is the Collective Board's country/state view (`board.js`), and it's fully hidden by this gate
regardless of level — there is no separate "State page" to move it off of yet. This is a `board.js`
navigation change to make *when the gate actually opens*, not something to build correctly while
it's invisible and unverifiable. Flagging here so it isn't forgotten.
