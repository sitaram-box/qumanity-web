# Qumanity Dashboard Redesign — Full Roadmap (Review & Submit + 3-Column Dashboard)

> This document is written to be handed to a fresh Claude Code session on the
> `/Users/macmudgal/Desktop/Qumanity_DPG` repo and executed phase by phase — it
> includes the concrete file paths, existing patterns, and data sources already
> verified in this codebase, not just a description of intent.

## Context

Qumanity_DPG is a Flask prototype (single `app.py`, SQLite, server-rendered
Jinja templates, vanilla JS — no build step, no framework). A Karma Qoins
wallet system and a pilot-village election system have already been built and
shipped (`wallet_core.py`, `election_core.py`, plus the corresponding
dashboard additions) — this roadmap is the next stage: a full dashboard UI
redesign, driven by two rounds of detailed specs from the project owner.

The **second** (most recent, more specific) spec message corrected and
sharpened the first one on one important point: the left-sidebar location
explorer is **not** a free-roam browser of the whole Earth — it's scoped to
**the user's own present-location lineage**, listing siblings at each level
(e.g. "all countries in *my* continent," "all states in *my* zone," "all
villages in *my* tehsil"). This is closer to, and mostly reuses, what the
dashboard's existing Global/Public sub-tabs already compute (they're already
keyed off `profile.present_location_struct`) — it just needs to become a
nested tree of **siblings**, not a single active path, and needs to move from
a horizontal tab bar into a left-sidebar explorer.

## Scope decisions (carried over + reconfirmed this round)

- **Collective Board** (posts w/ word limit + images, opinion polls,
  business-opportunity listings, comments) — real content is **Phase 2**, not
  this pass. Phase 1 shows an honest placeholder card, same pattern already
  used for the Personal tab's "Coming Soon."
- **Message Box** (inbox/compose) and **friend/family requests** — **Phase
  3**. The user's own message confirms this: *"We will work on message box
  features later."* The village-member profile popup (Phase 1) shows
  Send Message / Add Friend / Add Family as visibly present but disabled
  ("Coming soon") buttons, so the UI already communicates where those actions
  will live once Phase 3 ships.
- **Q-Punch (leadership council) & Commerce (marketplace)** — no backend
  exists for either. Phase 1 shows them as disabled "Coming soon" pills in
  the left sidebar. The spec's mention of "Quantum Punch Council Members...
  limited access to perform operations" describes a *write/edit* capability
  gated by council membership — that requires a general leadership/council
  system that doesn't exist yet (today only the pilot village has real
  elected council members, via `village_council`). This is **Phase 4**; Phase
  1's explorer is read-only for every logged-in user.
- **Right-sidebar "announcements"/"recent updates"** — no data model exists,
  and the spec's example numbers were illustrative mockup content, not real
  data. Phase 1 ships the right sidebar with **real** statistics only (already
  built). Whether announcements become real "pinned Collective Board posts"
  (Phase 2) or their own small table is a decision to make when Phase 2 is
  scoped, not now.
- **Member-list privacy** (from the prior round): visible to all residents of
  a village, but each entry/popup shows only **Name, Gender, Age Category** —
  never Private ID, Account ID, email, phone, or zodiac detail.

## Phase 1 (this build): Review redesign + 3-column dashboard shell

### 1a. Review & Submit redesign

Files: `templates/register.html` (step markup, `templates/register.html:244-282`),
`static/js/register.js` (`renderReview()`/`renderList()`, lines 745-810),
`static/css/register.css`.

- Keep `renderReview()`/`renderList()`'s logic exactly as-is (it already
  builds the right data from `state.form`/`state.zodiacPreview`/
  `state.birthLocation`/`state.presentLocation`) — just prefix each label
  string with an emoji, e.g. `["👤 Name", f.name]`, `["📅 Date & Time of
  Birth", ...]`, `["✨ Zodiac", ...]`, `["🗺️ Present Location", ...]`,
  `["🆔 User-ID", ...]`. This project has no icon font/SVG icon set anywhere
  (confirmed) — inline emoji is the existing, only convention (34 uses
  already in `register.html` alone), so this is consistent, not a new
  pattern.
- Add a `.qm-review-card` CSS class in `register.css`: same box family as the
  existing `.chart-summary` (`register.css:287-293` — `var(--qm-panel-bg)`
  background, gold border, radius) but with larger padding, larger `dt`/`dd`
  font-size, bolder `dd`, applied to the four review groups (Personal
  Details / Global Account / Public Account / Your IDs) in place of the bare
  `.chart-summary`.
- No JS logic changes, no backend changes — this is template + CSS only.

### 1b. Dashboard 3-column layout — Global and Public tabs only

The Private tab (own account/wallet) and Personal tab (already an honest
"Coming Soon" placeholder) have no location dimension, so they keep their
current single-column layout unchanged. The top Global/Public/Personal/Private
tab bar (`templates/dashboard.html:26-31`) is unchanged.

**Layout** (`templates/dashboard.html`, `static/css/dashboard.css`): a
`.qm-dash-3col` grid — `.qm-dash-left` (20%) / `.qm-dash-center` (60%) /
`.qm-dash-right` (20%), stacking to one column under a `~900px` breakpoint
(matching the existing `@media (max-width: 620px)` pattern already used in
`register.css`).

**Left column — location explorer** (replaces the current
`global-sub-tabs`/`public-sub-tabs` pill bars, `dashboard.html:123-132` and
`134-177`):

A nested, indented `<ul>` tree per tab, scoped to the user's own lineage —
siblings at each level, not a free-roam browser:

| Tab / level | Left column shows |
|---|---|
| Global → Earth | All 7 Continents; expanding one lists its Countries |
| Global → Continent | All Countries in *the user's own* continent |
| Global → Country (India only) | All Zones, and within each, its States |
| Public → Zone | All States in *the user's own* zone, each expandable to its Districts |
| Public → State | All Districts in the user's state, each expandable to its Tehsils |
| Public → District | All Tehsils in the user's district, each expandable to its Villages |
| Public → Tehsil | All Villages in the user's tehsil |
| Public → Village | All **registered members** of the user's village (name/gender/age only) |

Data sources — **all already exist**, no new "children" endpoints needed
except one (member list, below):
- Continents/countries: `/api/world-data` (already serves the whole
  `global_countries.json` tree, 32KB — filter client-side by the user's
  continent id, exactly like `register.js`'s location picker already
  consumes this same endpoint).
- Zones/states: `/api/india-states` (`india_states.json`, 9KB).
- Districts/tehsils: `/api/india-districts` (`india_districts_tehsils.json`,
  259KB, keyed by state id).
- Villages per tehsil: `/api/india-villages/<tehsil_id>` — **the one
  endpoint already scoped/indexed correctly** (queries the 621K-row
  `india_villages` table `WHERE tehsil_id = ?`); fetch on-demand when a
  tehsil node is expanded.
- Village members: **new** — see 1c below.

Do **not** read `/Users/macmudgal/Desktop/0_Earth/Qumanity_Master.json` (or
the on-disk folder tree) live for any of this — it's 106MB of pure location
metadata with no per-user data and no existing reader (confirmed via
`folder_connector.py`, which only *writes* user folders, never lists
children). The app's own static JSON + SQLite already cover exactly this need
faster.

Below the tree: three quick-link pills — **Elections** (only shown when a
Village node is selected; scrolls to the center column's Elections card),
**Q-Punch** and **Commerce** (both disabled, "Coming soon").

**Village member list + profile popup**: clicking a Village node fetches
`/api/location/members/village/<village_id>` (1c) and renders a simple
search box + scrollable name list. Clicking a member opens a small popup
showing **Name, Gender, Age Category** and three buttons — **Send Message**,
**Add Friend**, **Add Family** — all rendered but `disabled`, with a
"Coming soon (Phase 3)" tooltip/note, so the UI is honest about what works
today without hiding where those features will live.

**Center column**: a **Collective Board** placeholder card (same visual
pattern as the existing Personal-tab "Coming Soon" card) — *"Posts, opinion
polls, and local business listings are coming in a future update."* For
Public tab specifically, when the selected village is
`election_core.PILOT_VILLAGE_ID`, the existing (already working) Elections
card renders here too; for any other village, show a plain "Elections aren't
active in this village yet" note instead — elections are genuinely
pilot-scoped today, this isn't a bug to hide.

**Right column — statistics**: the existing `stat_block` macro output
(Total Humans, Gender/Age/Elements/Zodiac breakdown, Wallet balance —
already fully built and working), collapsed from the old one-block-per-level
approach into **one** reusable panel per tab (`qm-dg-stats` / `qm-dp-stats`)
that gets repopulated via the existing `loadStatsFor`/`loadWalletBalanceFor`
(`static/js/dashboard.js`) whenever the explorer selection changes, instead
of only reacting to the old fixed sub-tab buttons.

**`static/js/dashboard.js`** changes: replace `wireSubTabGroup` /
`loadLocationLevelStats` (the Global/Public-specific parts only — the
Edit-Profile, Wallet, and Elections JS already built are untouched) with:
- `renderExplorer(tab)` — builds the sibling tree from the cached static
  JSON responses above, fetching villages per-tehsil on demand.
- `selectLocation(tab, level, id, name)` — on node click: marks it active,
  retargets the right-column stat panel (reusing the existing loader
  functions, just pointed at the new generic panel ids), and — for Public +
  `village` level — calls `loadVillageMembers(id)` and toggles the Elections
  card per the pilot-village check.
- `loadVillageMembers(villageId)` — fetches 1c's endpoint, renders the list,
  wires the popup.

### 1c. New backend: village member list (privacy-scoped)

One new route in `app.py`, following the existing `_LOCATION_STATS_LEVELS` /
`/api/location/stats/<level>/<id>` pattern:

```
GET /api/location/members/village/<village_id>
```
→ `SELECT id, name, gender, dob FROM users WHERE
json_extract(present_location_json,'$.village.id') = ?`, mapping each `dob`
to an age-category label via the existing `id_generator.age_code` +
`_AGE_CATEGORY_NAMES` (already used by `/api/zodiac/preview`,
`app.py:620-644`). Returns only `{id, name, gender, age_category}` — no
private_id/account_id/email/phone/zodiac. Village-only (not generalized to
every level) — every other level already has real aggregate stats rather
than a raw member list, and only villages are small/bounded enough for a
browsable directory.

## Phase 2 (future pass): Collective Board

Real content behind the Phase 1 placeholder — posts (text with a word limit
+ optional image), opinion polls (Pro/Anti voting with live tallies),
business-opportunity listings, and comments on posts. Needs new tables
(`posts`, `post_votes` or `poll_votes`, `business_listings`, `comments`) and
roughly 10-15 new routes — comparable in size to the wallet+elections work
already shipped. Also the natural place to reconsider whether "pinned"
Collective Board posts should populate the right sidebar's
announcements/recent-updates section.

## Phase 3 (future pass): Message Box + friend/family requests

Inbox/compose/sent/drafts in the Private tab, plus friend-request and
family-request flows triggered from the Phase 1 village-member popup (which
already has the disabled buttons wired up, waiting for this). Needs a
`messages` table and a `connection_requests` table (friend vs. family
distinguished by a type column), plus the routes to send/accept/reject.

## Phase 4 (future pass): Q-Punch / leadership council + council-gated operations

A general leadership/council system across every location tier (today only
the pilot village has real elected members, via `village_council`). Once
that exists, the left-sidebar explorer's "Q-Punch" pill becomes real, and the
"perform operations in their locations" capability (edit/write access scoped
to council members) can be layered onto the read-only explorer built in
Phase 1.

## Verification (Phase 1)

- Start the app via the preview tool, log in as an existing user.
- **Review page**: register a new test account through all 4 steps; confirm
  the Review step shows icon-prefixed, larger-font cards, and that Submit
  still creates the account correctly (no change to submit logic).
- **Global tab**: Earth level lists all 7 continents, expanding one lists its
  countries; Continent level lists only the user's own continent's countries;
  selecting any country updates the right-column stats to that country.
- **Public tab**: Zone → State → District → Tehsil → Village tree expands
  correctly (villages fetched live per tehsil, scoped to the user's own
  zone/state/district/tehsil at each level); selecting the pilot village
  (`CS.DL.5.4.1E`) shows the real Elections card and a live member list with
  working name/gender/age popups (Send Message/Add Friend/Add Family visibly
  disabled); selecting any other village shows the "not active yet" note.
- Confirm Private and Personal tabs are visually unchanged.
- Check the browser console/preview logs for JS errors while navigating the
  new explorer.
