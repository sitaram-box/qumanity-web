# Homepage Scoreboard + Tutorial redesign (2026-10-04)

Second slice of the 10-part platform request (see [[project-platform-roadmap-2026-10]]); first
slice was [[private-account-fixes-2026-10]]. Both pieces here are website + shared-backend; the
app got a lighter, proportionate content update for its own existing tour (see "App tour" below).

## Homepage India Scoreboard

- `elemental_core.india_scoreboard(conn, india_states_data, top_n=10)` — total India members, all
  Zones ranked by `total_users`, and the top `top_n` States ranked the same way. Reads straight from
  `location_elements` (already kept current by `update_location_stats()` on every registration, no
  new write path needed) joined against `static/data/india_states.json`'s zone/state names for
  display — a zone/state with 0 members is still listed, just last.
- `GET /api/scoreboard/india` (`app.py`) — the one route; shared by the website homepage and (when
  built) an app equivalent screen.
- `templates/home.html` (`#scoreboard` section, right after "Live from Qumanity") +
  `static/js/scoreboard.js` + `static/css/home.css` (`.hm-sb-*`) — big animated total-members count,
  two ranked lists (Zones, top 10 States) with progress bars, #1 highlighted gold.
- **Clickable rows**: each row links to `/elements?level=<zone|state>&id=<id>&name=<name>` — a real,
  working deep link, not a dead end. `static/js/elements-dashboard.js` was extended to read those
  query params, pre-select that level in the dropdown, and scroll+highlight the matching card
  (showing the friendly name passed in the URL instead of the card's default raw location-id text).
  There is no separate "Public page for an arbitrary location" in this codebase (the dashboard's own
  Public tab only ever shows the signed-in user's own location) — the public, unauthenticated
  Elemental Dashboard (`/elements`) is the closest real equivalent, so that's what rows link to.

## Website Tutorial — a real spotlight tour, not a slideshow

`static/js/tutorial.js` (+ `.qm-tour-*` CSS in `dashboard.css`) is a genuine guided-tour engine
that dims the live dashboard and cuts a highlighted hole around one REAL element per step — it
does not show illustrative slides. 12 steps, each with `{ tab, selector, title, body }`:

1. The 4 bottom tabs together (`.qm-dash-tabs`)
2. Global: Earth → Continent → Country (`#global-root-tabs`, switches to Global tab first)
3. Public: Zone → State → District → Tehsil → Village (`#public-root-tabs`, Public tab)
4. Personal Account (`#qm-dash-personal`, Personal tab)
5. Private Account (`#qm-dash-private .pv-hero`, Private tab)
6. Language switcher (`#ui-lang-btn`)
7. Time-box (`#timebox-btn`)
8. Village Council Voting / Q-Punch election card (`#qm-elections-card`)
9. Post to the Collective Board (`#bd-public-board .bd-compose`)
10. Q-Punch council (`#bd-public-board .bd-qp`)
11. Groups (`#bd-public-board .bd-groups`)
12. Statistics (`#qm-dp-stats-content`)

...followed by a separate, always-shown completion screen ("🎉 You're ready to use Qumanity!")
with a "Don't show this tutorial again" checkbox — kept structurally apart from the 12 numbered
steps specifically so it still appears even when several real steps get skipped (see below), rather
than the tour just silently ending on whichever step happened to be last.

**Steps gracefully skip, never block**: before each step, `isVisible()` checks the target is
actually on screen (not `hidden`, has real size) — a step whose element isn't there right now (the
election card outside the pilot village; the Post button when posting isn't open at that level) is
skipped automatically, moving straight to the next reachable one. Verified live: for a freshly
registered member, step 8 (Voting) is skipped because the Public tab defaults to Zone level, not
Village, so the election card isn't visible yet — exactly the intended behavior.

**Found and fixed during verification**: the popup's position was computed only from the target's
own rect, so a target below the fold on first load (nothing had scrolled yet) could place the popup
off-screen in both the "below" and the "flip above" fallback — neither fits when the target itself
isn't in the viewport. Fixed by `scrollIntoView({block:'center'})`-ing the target before measuring,
and by clamping the popup's position against the real rendered popup height instead of a guessed
constant.

**Hover tooltips**: native `title` attributes (already the established convention here — see the
header's pre-existing `title="Change language"` etc.) were added to the 4 tab buttons; the board's
`.bd-qp`/`.bd-groups` buttons already had them.

**Backend**: reuses `review_core.py`'s existing tour status (`GET /api/onboarding`,
`POST /api/onboarding/tour`) — already built for the app, now shared. Auto-starts once per member
on first dashboard load (`tour` is `null`); replayable any time via the Private tab's "🎓 Tutorial"
button (`templates/dashboard.html`), which bypasses the status check.

## App tour (lighter-touch update, not a spotlight rewrite)

Qumanity_App's `app/tour.tsx` is a separate, already-reasonably-built 7-slide swipeable
illustrated walkthrough (not real-element spotlighting — React Native's `measure()` + overlay-cutout
approach is a much bigger native-engineering lift than the website's DOM-based one, and wasn't
worth it for this pass given the existing tour is already solid). Content-aligned instead:

- Added a new "Global & Public, tier by tier" slide (Earth→Continent→Country,
  Zone→State→District→Tehsil→Village, "Public's tiers are exactly the present location you chose at
  registration") — the website's steps 2-3, which the app's tour didn't cover before.
- Added Language (Settings) and Time-box (`app/sky.tsx`) to the "Private stays private" slide's
  bullet points — confirmed both screens actually exist before referencing them.
- Added an Exit (×) button next to Skip, matching the website's Next/Skip/Exit — functionally
  identical to Skip (as it is on the website too), added for cross-platform consistency with the
  spec's own checklist.

Not done: a true element-measuring spotlight overlay for the app. If that's wanted later, it needs
`View.measureInWindow()` per target plus a `Modal`-based cutout overlay — a distinct, larger task.
