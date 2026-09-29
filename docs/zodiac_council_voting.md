# Zodiac Council Voting (Village Council elections)

Piloted on **one village only** — `election_core.PILOT_VILLAGE_ID` (`CS.DL.3.4.1A`, Rohini Sector
24) — per the Founder's explicit scoping (2026-09-29): *"Build council voting for only 1 village...
it is testing phase. If it looks good then only we will move it to other pages later."* The
Tehsil → District → State/Zone → Country escalation hierarchy described in the original spec is
**deferred entirely** — nothing here builds it. Every function takes a `village_id` parameter
rather than assuming the constant, so lifting the restriction later is a matter of passing a
different id in, not restructuring the module.

## Cycle

One zodiac sign runs its own cycle at a time: `NOMINATION_DAYS = 7` then `VOTING_DAYS = 14`
(21 days total — the spec's "4-week cycle" language is approximated by this pre-existing, already
in-production window rather than replaced). `election_core.current_cycle_for_village()` gets-or-
creates the cycle row and live-recomputes its status (`nomination` / `voting` / `closed`) from
today's date, tallying results the moment a cycle is first seen as closed.

Electing **one Male "Nayak" and one Female "Nayika"** per sign (2 winners/cycle, 24 seats/year).

## Candidacy form (4 questions)

`election_candidates` columns `form_reason`, `form_why_vote`, `form_changes`, `form_past_work`
(migrated in via `election_core.ensure_council_columns()` — these 4 tables predate this codebase,
there is no `CREATE TABLE` for them anywhere, so every schema change here is an `ALTER TABLE`
migration, matching `app.py`'s own `_ensure_user_columns()` pattern):

- Why do you want to stand? (required)
- Why should members vote for you? (required)
- What changes will you bring? (required)
- Past work (optional)

`election_core.nominate(conn, user_row, reason, why_vote, changes, past_work="")` validates cycle
status + eligibility (`nomination_eligible()`: present-village match, age 25-60, born under the
cycle's sign, gender Male/Female only) before inserting. The old `manifest` column is kept populated
from `reason` for any legacy reader.

## Training → Leadership

`village_council` columns `training_start`, `training_end`, `leadership_start`, `leadership_end`
(same `ensure_council_columns()` migration), computed once in `_ensure_tallied()` when a cycle
closes:

- **Training** starts the day after voting closes and runs until leadership begins.
- **Leadership** is this same sign's *next annual occurrence* (`_sign_window()` run one year
  forward) — the elected pair leads for that ~1-month window, a year after being chosen.

`election_core.council_term_status(council_row, today=None)` derives `'training' | 'leadership' |
'completed'` live from those dates — nothing needs a background job to flip a status field.

## Karma on candidate cards

`candidates_for_cycle()` now returns each candidate's `karma` (`karma_core.individual_karma_score()`
— commercial/non-commercial/total) alongside their form answers, so voters can read a candidate's
Social Credit score before voting for them, per the Founder's explicit instruction. See
`docs/karma.md`.

## Routes (`app.py`)

- `GET /api/election/status` — cycle info + the caller's own eligibility.
- `GET /api/election/candidates` — `{male: [...], female: [...]}`, each with form answers + karma.
- `POST /api/election/nominate` — body `{reason, why_vote, changes, past_work}`.
- `POST /api/election/vote` — body `{candidate_user_id, gender}`.
- `GET /api/election/council` — the village's roster, including `term_status` and each head's karma.

## UI

Website: `templates/dashboard.html` (`#qm-elections-card`, Public tab) + `static/js/dashboard.js`.
Candidate reports render via safe DOM construction (`textContent`, not `innerHTML`) since form
answers are free user text.

## Not yet built

- App (React Native) equivalent — there is currently no Zodiac Council Voting screen in
  `Qumanity_App` at all (its existing `QPunchSheet.tsx` is a *different*, pre-existing 5-seat
  per-group moderation council — Founder/Male Leader/Female Leader/Managers/Agents & Volunteers —
  unrelated to this Nayak/Nayika zodiac system).
- Replicating past the pilot village.
