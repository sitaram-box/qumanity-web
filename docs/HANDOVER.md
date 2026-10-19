# Qumanity — Project Handover

Written 17 October 2026, refreshed 18 October 2026 to cover Qmail, Q-Punch council addresses, the
Admin Panel's scope evolution, attachments, drafts, and the standalone `/qmail` mailbox page, and
refreshed again later on 18 October 2026 after the DPG evidence pack pass (§5), which led to two
code fixes and a README correction. This is a snapshot for whoever picks up the project next — it is not a replacement for the detailed
design docs already in this folder (linked throughout), and it will go stale as the code moves;
treat it as a map, not a source of truth for exact current state.

## 1. What Qumanity is

Qumanity (Quantum + Humanity) is a civic participation platform organised around eight nested
location levels — Village, Tehsil, District, State, Zone, Country, Continent, Earth. Each level
has a Collective Board where residents post and vote, and a council (one man, one woman — Nayak
and Nayika) elected through zodiac-sign cycles. Members get a verified identity (a 9-digit Private
ID + 5-character PIN, no email required), a Qoin wallet earned through civic service, and a Karma
score. The name is literal: a nested, transparent ledger of Space, Time and Consciousness, not a
quantum-computing claim — see the About page's "quantum qualities" section (§4.5) for how that
framing is actually justified in the UI.

One backend serves both the website (`qumanity-web`, this repo) and a React Native / Expo phone
app (`qumanity-app`) through the same `/api` routes — the app authenticates with a signed bearer
token, the website with a signed session cookie, and a valid token is treated exactly like a
session.

## 2. Architecture

- **Flask + SQLite**, modular business logic in `*_core.py` files at the repo root, each with its
  own `SCHEMA` / `ensure_tables(conn)`. `app.py` holds every page route, every `/api` route,
  startup wiring, and session/auth.
- **Migrations**: `migrations/NNN_description.{sql,py}`, applied by `tools/run_migrations.py`,
  tracked in a `migrations` table. `app.py`'s `ensure_database_ready()` runs the base schema, each
  module's own tables, and every migration on every boot — no manual step. Current range:
  001–003, 007–024 (004–006 unused). 024 is the most recent (Qmail drafts).
- **74 application tables on boot, 76 in a running database** — counted directly against a
  freshly-migrated throwaway database, not estimated from an older doc (75 on boot if you count
  SQLite's own `sqlite_sequence`). The other two are created on first use, not on boot:
  `chat_read_state` by `notify_core.py` and `election_cycle_config` by `election_core.py`. The
  legacy `election_history` table is no longer created. Full list with purposes in
  `docs/DATA_MODEL.md`.
- **Four in-process scheduler jobs** (APScheduler, `BackgroundScheduler`): daily folder sync
  (00:00), daily lunar-pipeline tick (00:00 IST), and the Post Testing cycle's monthly post job
  (1st, 02:00 IST) and weekly vote job (Monday, 02:00 IST). `QM_DISABLE_SCHEDULER` turns all of
  them off, used in tests.
- **No front-end framework.** Server-rendered Jinja templates, plain JavaScript in `static/js/`,
  no build step. The two third-party JS libraries in the whole project (Leaflet, three.js) are
  loaded via pinned-version CDN `<script>` tags, not npm — the precedent for how any future library
  would be added, should one genuinely be needed.
- **Astronomy is local** — pyswisseph's built-in Moshier ephemeris, no external service, no data
  files.
- Full architecture detail: `docs/ARCHITECTURE.md`. Every route (178 under `/api`):
  `docs/API.md`. Every table: `docs/DATA_MODEL.md`. All three were brought up to date at `065cecc`
  and match the DPG pack's own copies byte for byte.

## 3. Database schema — what's new since the last stable baseline

| Migration | What it added |
|---|---|
| 015 | `qoins` (one row per physical denominated Qoin a wallet holds), `recognition_stars` (permanent record of a positively-recognised board post, independent of the post's own lifecycle) |
| 016 | `users.is_demo`, `users.is_removed` — both default 0 |
| 017 | `board_posts.post_kind` (`member`/`test`/`council_update`), `.is_test`, `.is_demo_post`, `.test_reward_inr`; `board_votes.voted_at`; new table `testing_windows` |
| 018 | `location_elements.birth_users` |
| 019 | `admin_export_log` (the member-export tool's audit trail) |
| 020 | `admin_queries`, `admin_query_replies` (the Admin Panel's general-query ticket type) |
| 021 | `users.qmail_username`, `qmail_addresses`, `qmail_messages` — Qmail, internal member-to-member messaging (§4.7) |
| 022 | `qpunch_addresses`, `qpunch_queue_messages`, `qpunch_queue_actions` — Q-Punch council addresses and their shared queue (§4.8) |
| 023 | `qmail_attachments` — compose-time file attachments, stored as SQLite BLOBs (§4.10) |
| 024 | `qmail_drafts` — unsent compose-form state, autosaved on close (§4.7) |

**The invariant that matters most**: `board_posts.is_test = (post_kind == 'test')`, enforced by
writing all three fields (`post_kind`, `is_test`, `is_demo_post`) in a single `INSERT`, never a
follow-up `UPDATE`.

**The membership rule that matters most**: a user counts toward the total members of exactly one
location — their **present residence** (`users.present_location_json`), set only by an explicit,
user-initiated action, never GPS/IP/a scheduled job. `location_elements.total_users` is
present-location-keyed (`is_demo=0 AND is_removed=0`). `location_elements.birth_users` is
separate, metadata-only — never counted toward membership, voting or participation. Full rationale
in `docs/member_count_design.md`. **This rule is now also the input to Q-Punch address generation**
(§4.8) — a location's real member count is the single source both subsystems depend on.

## 4. Major subsystems

### 4.1 Qoin / wallet reward redesign

`qoin_core.rank_reward_inr(rank, n, level)` uses a **variable top-tier rule**, not a fixed top-5:
`top_tier_count(n)` is flat 1 for `n ≤ 10`, else `n // largest_power_of_ten_strictly_below_n`.
Reward fraction is `1 - position/remaining`, exact integer arithmetic. `board_core.py`'s `settle()`
branches on `post_kind`: a `test` post computes and stores `test_reward_inr` but never actually
credits anything; a `member` post does the real thing.

### 4.2 The Post Testing cycle (migration 017 + `test_cycle_scheduler.py`)

A one-year automated demo-user testing system. Monthly job posts one test post per demo voter;
weekly job runs a top-up voting round. `cast_vote()` rejects only `post_kind == 'council_update'`.
**Council Updates** are a third post kind: never voted on, never frozen/elevated/rewarded,
read-only except for Agree/Disagree reactions.

Demo users: `scripts/seed_demo_voters.py` (50 demo voters) and `scripts/mark_existing_demo_users.py`
(pre-existing users 25/26). Separate from the ~500 DB-only election-demo users already in Rohini
Sector 24 from the earlier election pilot.

### 4.3 Member count correction

Fixed in two layers: five live-query public-stats endpoints were missing `is_demo=0 AND
is_removed=0` filters; `location_elements` was birth-location-keyed, not present-location-keyed.
Fixed via `elemental_core.recompute_location_elements(conn, dry_run=False)`,
`scripts/backfill_location_elements.py`. Small-count suppression (`_suppress_small_count`):
counts 1–4 render as `"<5"`, 0 stays 0.

### 4.4 About page — the quantum qualities section

Maps six quantum-physics qualities to real features on `templates/about.html`. Explicitly honest
about which are live vs. built-not-active (Non-locality, the lunar pipeline). Now also describes
Qmail (as an example of Entanglement — the 30-day forward window linking old and new addresses)
and the Admin Panel (as an example of Coherence — a different kind, behind the sign-in wall).

### 4.5 Homepage redesign

Moved `templates/home.html` off a standalone dark theme onto the site's shared light palette, kept
a dark sticky nav/footer as the one deliberate dark anchor. Cut from 9 sections to 6. All four
must-stay elements (live stats + globe, Founder's Message teaser, inline sign-in, small-count
suppression display) preserved.

### 4.6 Dashboard onboarding tour — 12 steps to 5

`static/js/tutorial.js` is a live spotlight overlay over the real dashboard. Storage:
`review_core.py`'s `user_onboarding.tour_status`. Reduced to 5 steps: tabs, board feed, Citizen
Reports + My Reports, Qoins + Karma, closing CTA.

### 4.7 Qmail — internal member-to-member messaging

Full design: `docs/QMAIL.md`. An email-shaped internal messaging system — **not real inbound
internet mail**; `@qumanity.in` is an addressing convention a message never leaves. Address format
`[username]-[account_id]@qumanity.in`, e.g. `rohit.delhi-KR3-EO-GMA2-ZAI-CS.DL.3.4.1A@qumanity.in`.
`qmail_username` lives once on `users` (own unique index); `qmail_addresses` is history, one row
per `account_id` epoch, with a 30-day `forward_until` window so a just-changed address still
resolves for a month. `social_core.regenerate_account_id()` is the **single choke point** both
`account_id` itself and Qmail's address-sync run through — the one function that changes either,
by design, so they can never fall out of sync the way `account_id` itself once did (Path A/Path B,
fixed earlier in this project's history). The smart "To" field's autocomplete is scoped entirely
by `social_core.connected_user_ids()` (Personal Group membership unioned with active private
chats) — a disconnected member never appears, under any circumstance.

**The member mailbox UI lives on its own page, `/qmail`, not the dashboard's Private tab** — see
§4.11. The dashboard keeps only a small activation card (username chooser, address, an
"Open Qmail →" link). Message bodies are plain text with a narrow whitelist markup (`**bold**`,
`_italic_`, `[text](url)`) — never HTML, on either side. The client builds `<b>`/`<i>`/`<a>` DOM
nodes directly from the parsed text (`static/js/qmail_format.js`'s `qmRenderFormattedText`, shared
by the Admin Panel's council detail view and `/qmail`'s own reading pane); no HTML string is ever
constructed from user input, so there is no sanitizer installed and no `|safe` anywhere in this
codebase — **deliberately, not an oversight** (`docs/QMAIL.md` §12 says this explicitly, for
exactly the reason a future contributor might otherwise "fix" it). A link's URL is scheme-checked
(`http(s)://` only) before becoming clickable. Attachments are compose-time only, stored as SQLite
BLOBs (`qmail_attachments`, migration 023) — a prototype choice, not permanent architecture, chosen
because the database already carries the volume-persistence guarantee a disk path on Railway would
need a new, separately-configured path to earn. Capped at 2 MB, enforced twice independently
(Flask's app-wide `MAX_CONTENT_LENGTH` as a first line of defense, `qmail_core.save_attachment()`'s
own precise byte check against the decoded data). Images are attachment-only, never inline by
URL — a privacy decision (an inline `<img src>` to an external host leaks the viewer's IP at
render time), not a style one.

**Drafts** (`qmail_drafts`, migration 024): unsent compose-form state, autosaved silently when the
compose overlay closes with any field non-empty. Scoped by `user_id`, same 404-not-403 shape as
the council queue. Sending from a draft deletes it atomically with the send — the commit that does
this lives inside `qmail_core.delete_draft()` itself, not where it looks like it should (full
explanation in `docs/QMAIL.md` §13, worth reading before touching that function). **No cleanup job
for abandoned drafts** — a stated limitation, not an oversight (Gmail behaves the same way); the
delete route exists so a member can clean up their own drafts by hand.

### 4.8 Q-Punch council addresses

Full design: `docs/QMAIL.md` §11. An extension of Qmail that addresses a **location**, not a
member: `<level>-<location_id>@qumanity.in`, e.g. `village-CS.DL.3.4.1A@qumanity.in`. A location
gets one **permanent** row in `qpunch_addresses` the first time its real member count reaches its
level's threshold — never retired or reactivated afterward, at any level, even if the count later
drops:

| Level | Threshold | Reachable today |
|---|---|---|
| village | 5 | Yes |
| tehsil | 10 | Yes |
| district | 100 | No |
| state | 1,000 | No |
| zone | 10,000 | No |
| country | 100,000 | No |
| continent | 1,000,000 | No (theoretical at current scale) |
| earth | 10,000,000 | No (theoretical at current scale) |

Generation hooks into `elemental_core.recompute_location_elements()` (`qmail_core.
sync_qpunch_addresses`, same transaction, so a dry run creates nothing). **Village-only
reachability is one constant** (`qmail_core.QPUNCH_REACHABLE_LEVELS = {"village"}`), read by two
consumers — `resolve_address()` for delivery, the board-line renderer for display — not two
independently-maintained gates that could drift apart. The Collective Board's existing Q-Punch
popup (`/api/qpunch/<level>`, `board.js`'s `openQp()` — a pre-existing five-seat governance
display, not something this feature invented) now shows the address plus who currently receives
it: "Village Council — `<address>`" when a seat is filled, "Village Council (received by the
Founder until the first election) — `<address>`" when it's empty, "`<Level>` Council (not yet
reachable in this prototype) — `<address>`" above village.

**The council queue**: a council message is never delivered into `qmail_messages` — it has no
fixed recipient (the heads change at every election), so it goes into `qpunch_queue_messages`
instead, a shared, location-keyed inbox read through the Admin Panel (§4.9), never through an
individual's personal Qmail. A village head's own personal Qmail address and inbox are completely
untouched by any of this — two addresses, two surfaces, no crossover. Every touch on the queue
(view, reply, close) writes a `qpunch_queue_actions` row naming the real actor, the same
transparency posture `id_recovery_reveals` already established for this codebase.

**The resident reads the reply in Qmail.** Until `c09b91f` a member who wrote to their council, or
sent the Admin a query, was notified of a reply but no route returned the reply's text, and the
notification never cleared. Now `GET /api/qmail/sent/council/<id>` and `GET /api/queries/mine/<id>`
return the sender's original with each reply's text and time — never the action log, and never who
on the council or admin side replied — and opening either clears the notification through the
existing `chat_read_state` table (kinds `council` and `query`). Both are sender-only, with the same
404-not-403 shape as the queue. `tests/test_reply_read.py` covers them.

### 4.9 The Admin Panel's scope evolution

Full design: `docs/ADMIN_PANEL.md`. Built as a single **filterable list + detail pane** (not three
or four separate panes — an earlier design description called it "three-pane," which was wrong),
originally over three sources (Citizen Reports, ID recovery, member queries), gated by
`_is_admin_panel_user()`. That function now returns a **scope descriptor** instead of a bool —
`None`, `{"scope": "global"}` (the Founder, all four sources), or `{"scope": "location", "level":
"village", "location_id": ...}` (a currently-serving village head, their own council queue only,
nothing else) — read fresh from `village_council` on every request, no caching, so an expired term
drops a head out of scope on their very next request. The council queue slotted in as a **fourth
filter button** and one new detail renderer, not a new pane — confirming the original list+detail
shape was built generic enough to absorb it cheaply. Four scoping invariants (404-not-403 for an
out-of-scope message id, the location handler taking no request argument at all, the no-caching
re-check, no audit row on a rejected cross-location write) are recorded in full in
`docs/ADMIN_PANEL.md` §8, each proven by a named test, not just asserted.

### 4.10 The attachment system

Covered in §4.7 above (member mailbox) and §4.8 (council queue, which shares the same storage and
serve route). One thing worth restating here because it's easy to miss: `GET
/api/qmail/attachments/<id>` is the **only** way an attachment's bytes ever leave the server, and
it re-derives access on every request from the message the attachment belongs to — sender or
recipient for a member message, sender or panel scope (reusing `_qpunch_message_in_scope()`
directly) for a council one. There is no bare, unguarded file URL anywhere in this feature.

**Fixed at `f1edd55`: attachments used to be served inline** with the sender-declared content type
and no file-type allowlist, so an HTML or SVG attachment could run script on qumanity.in. They are
now always served as downloads with `X-Content-Type-Options: nosniff`, and uploads are limited to a
15-type allowlist (`qmail_core.AttachmentTypeError`, a `ValueError` subclass, so the compose route
returns 400 for a disallowed type, not the size limit's 413). A file whose browser declares a blank
or unknown type is rejected — deliberate strictness, and a limitation members may notice. The fix
changed the serve route, not stored data, so attachments already stored are covered without a
migration. `tests/test_qmail_attachments.py` section 6 covers it.

**A known, stated gap**: whether a `<script>` tag in a message body actually renders as inert text,
and whether a `javascript:`-scheme link actually fails to become clickable, are DOM-rendering
properties of `static/js/qmail_format.js`'s `qmRenderFormattedText()` (extracted out of
`dashboard.js` and **rewritten**, not merely relocated — see §4.11) with no Python-testable surface
in this stack (no Selenium/Playwright/jsdom installed). Both were verified directly in a live
browser once, by hand, this session — not by an automated regression test. `tests/
test_qmail_attachments.py` covers everything a backend test *can* verify about this feature
(size limits, access control, that the server never mangles a body); it cannot and does not
re-check the renderer. A future change to that function could reintroduce an XSS path and nothing
in this project's test suite would catch it — recorded here so the next person knows the renderer
is unguarded by automation, not assumed safe forever because it passed once.

### 4.11 The `/qmail` page

A standalone route (`@app.route("/qmail")`), not a dashboard tab — every page in this codebase is
already a self-contained template with no shared layout, so a dedicated route is the established
pattern here, not a departure; it gets a real URL, back-button correctness, and its own scroll
context with no risk of colliding with the dashboard's own overlay stack. `GET /qmail` redirects
an unactivated member to `/dashboard`, where the activation card lives — this page assumes an
address already exists.

**At commit `ab01267`, `#qm-qmail-card` on the dashboard stopped being a mailbox and became a
door.** It shows only activation (username chooser), the member's address, and an "Open Qmail →"
link — the inbox/sent/compose UI it used to hold moved to `/qmail` entirely. A future contributor
reading `templates/dashboard.html` and wondering why this card is just a link rather than a
mailbox should read this as the deliberate endpoint of that move, not a card someone forgot to
finish building.

**`static/css/qmail.css` is its own file, not appended to `dashboard.css`.** `/qmail` doesn't load
`dashboard.css` at all (same pattern `templates/elements.html` already used: `style.css` +
`register.css` + one page-specific stylesheet). Appending would mean loading the Admin Panel's
grid, `.pv-card`, and every stats-panel rule on a page that needs none of them. Two small utility
classes (`.qm-dash-empty`, `.sg-btn`) are redefined verbatim in `qmail.css` because they only
existed in `dashboard.css` before — **if `.sg-btn` ever looks like an accidental duplicate, it
isn't; see `docs/QMAIL.md` §14 before "fixing" it into one shared file.**

**The renderer was rewritten, not just moved, at commit `e99eced`.** `qmRenderFormattedText` used
to live in `dashboard.js` and build elements through that file's own local `apEl()` helper;
extracted into standalone `qmail_format.js`, it was rewritten to call
`document.createElement`/`.textContent` directly, since `apEl()` wasn't reachable from the new
file. Same output, different code — a future reader diffing against an old `dashboard.js` should
know the implementation changed at that commit, not just its address.

**Two bugs found only by a live browser walkthrough, neither with a static-test surface:**
- `.qmail-compose-overlay`'s unconditional `display: flex` overrode the browser's own `[hidden] {
  display: none }` default — the `hidden` attribute and the JS reading it were both correct, only
  the rendered pixels were wrong. Fixed with an explicit `.qmail-compose-overlay[hidden] { display:
  none; }`. Lesson for any future `hidden`-toggled element in this codebase: if its class also
  declares `display` unconditionally, it needs that same explicit override, or `hidden` does
  nothing.
- The smart-To autocomplete's close-to-save-draft path read the input's *display* text ("Page
  Target (pagetargetqm-…)") instead of the resolved address it had already captured in a separate
  variable. Every draft composed via the autocomplete — the common case, not an edge one — silently
  saved an unresolvable `to_address`; reopening and sending such a draft failed every time with
  "address not recognized." Fixed by preferring the stored resolved address over the input's
  display text. General lesson: **any autocomplete that writes a human-readable label into the
  same field it resolves a value from must persist the resolved value, not the input's current
  text** — this will recur wherever else a "Name (value)" autocomplete feeds something that gets
  saved and re-submitted later.

**Deleting the dashboard's old inline mailbox UI was a real removal, not a left-to-no-op.**
`#qm-mail-card` and the legacy `#qm-messagebox-card` placeholder are gone from
`templates/dashboard.html`; `static/js/dash_extras.js` lost the ~124 lines of inbox/sent/compose
logic that only `#qm-mail-card` ever drove. That block would have safely no-op'd once the element
left the DOM (`if (mailCard) { … }` already guarded it) — it was removed anyway, because a safe
no-op left in the file is still something a future reader has to read and confirm is unreachable
before trusting that it is.

**Known structural debt, named so nobody "fixes" it without knowing it grew that way
deliberately**: `static/js/dashboard.js` carries two unrelated jobs in one file — the dashboard's
own tab/profile logic, and the Admin Panel's list+detail rendering (`apEl`, `apLoadFeed`,
`apOpenReport`/`apOpenQuery`/`apOpenCouncil`, etc.). They ended up in the same file because the
Admin Panel was built as an extension of the existing dashboard page, not a separate one. Splitting
them into two files is a reasonable future cleanup, not something broken today.

**A known gap, not an oversight**: the member-profile popup (`static/js/dashboard.js:508-520`,
shown when clicking another member's card elsewhere in the app) still shows a disabled "✉️ Send
Message" button with a "Coming soon" note, even though Qmail fully exists now. Wiring it to
`/qmail`'s compose flow (or to a lighter in-place compose) is a reasonable future pass; it simply
hasn't been done yet.

### 4.12 The Family Tree (`family_core.py`, 2026-10-20)

**Two deliberately separate layers**, not one. `family_nodes` / `family_parent_links` /
`family_spouse_links` are the genealogical tree itself — a node is a person the tree knows about,
claimed (linked to a real `users.id`) or still empty (a typed name, possibly already marked
`is_deceased`, waiting to be claimed). `family_groups` / `family_group_members` /
`family_group_messages` / `family_group_nodes` are a shared, joinable container on top of it — a
chat plus a subset of nodes a specific set of real members can see drawn as one tree. A node can
belong to more than one group; a group's nodes are not its members (an empty node has no `user_id`
to be a chat member with). **Deliberately not built on `personal_groups`**: that table's
`category='family'` already carries privacy-sensitive meaning for `social_core.is_family_member()`
(which `hide_identity`'s exemption depends on) — reusing it here would have made "belongs to a
big searchable extended Family Group" quietly satisfy "is this person's close family," a real
privacy leak, not just a naming clash. The old Paternal/Maternal `personal_groups` still exist,
untouched, with their own small "Legacy Family Groups" bridge section restored in the same panel
(`static/js/family.js`'s `loadLegacyGroups()`) once their only UI entry point was replaced.

**Lineage vs. marital groups are structurally different, not just named differently.** A child has
two parents **and** a `family_groups.kind` of `'lineage'`; a married couple founds a separate
`'marital'` group for themselves and their children — `activate_timeline()` only ever handles
father/mother; `marry_timeline()` is a second, later-callable action for spouse/children, kept
deliberately apart so marital-group creation lives in exactly one place. The two group kinds use
**different naming algorithms**: lineage keeps a generation-rank-then-DOB pick (a parent always
outranks the activating user by generation, regardless of DOB — comparing raw DOB alone would make
the activating user "eldest" almost every time, since their own DOB is always known while a
freshly-typed parent's almost never is) and is deliberately deceased-blind, so a dead elder can
still lend the group his name; marital naming is alive-and-eldest between the spouse pair only.

**`family_group_members.is_admin` is derived at decision time, never stored as intent.** When a
join request is approved, admin status is granted only if the joiner has an *active*
`family_spouse_links` edge to a node whose claimed user is *already* an admin of that same group —
a spouse joining becomes co-admin; a child joining a parent's lineage group stays a plain member. A
spousal **join** (as opposed to create) links to the group's current real admin's own self-node,
never to the typed placeholder name the group's founder entered — claiming/merging two nodes that
turn out to be the same real person is a harder problem, deliberately deferred (see below), and
linking to the placeholder instead of the real admin would have silently half-solved it.

**The D3 visual tree (`static/js/family_tree.js`) renders `GET /api/family-groups/<id>/tree`'s flat
`nodes`/`parent_links`/`spouse_links` response (unchanged by Phase 2) via a composite-couple
merge**, not `d3-force` (non-deterministic, no concept of generation) and not `d3.tree()` on the
raw graph (a child's two parent edges violate `d3.hierarchy()`'s one-parent-per-node rule outright).
Every *active* spouse link is merged into one layout node before computing the hierarchy; a
**second merge pass** handles co-parents with no recorded spouse link at all — the normal case for
a lineage group's father and mother — by detecting composites that point at an identical child set
and merging those too, iterated to a fixed point. Skipping that second pass was a real bug caught
only by rendering an actual group, not by review: `d3.hierarchy()` silently visited the shared
child once per parent branch, duplicating the viewer's own node in the tree. Plain SVG rects/text
render each person, not `foreignObject` — simpler, and fully compatible with `d3-zoom`'s
transform-based panning.

**Node editing is two genuinely separate actions, not two paths to the same result.**
`POST /api/family/node/<id>/name` only ever changes an empty node's display label — it's refused
outright on an already-claimed node (whose visible name always comes live from `users.name`, so the
edit would silently do nothing) rather than allowed as a confusing no-op.
`POST /api/family/node/<id>/link` claims an empty node for a real user by id or Account ID, and
deliberately does **not** grant group membership or admin status — an admin identifying who a node
really is is not the same as that person requesting to join, and auto-adding them would reverse the
join-then-approve consent model used everywhere else in this project. In the UI, saving a name
never flips a dashed card to solid; only linking one does.

**Known, deliberately unsolved edge case**: if a Family Group's sole admin's own node is later
marked deceased (`mark_deceased()`), the group is simply left as-is — no succession, no automatic
promotion of another member. Not built speculatively; revisit once Report/Block and
account-deletion tools exist, or if a real user hits it.

## 5. DPG Evidence Pack — status at this handover

The master copy of the pack is a non-git directory on the owner's Mac, `~/Desktop/My Mac/DPG/`:
the 11 DPG Standard evidence docs plus its own `API.md`, `ARCHITECTURE.md` and `DATA_MODEL.md`.
The 18 October 2026 pass brought it up to date with Qmail, Q-Punch council addresses, the council
queue, the Admin Panel's scope, attachments, drafts, `/qmail`, the Admin member export and the
registration email. Statements the new features had made false were corrected in place, each with
a note saying what it used to say and when it changed. Its Forward Plan (Doc 10) is the tracked
list of open gaps; Doc 11 holds the application form answers (40 of 45 fields Ready).

**The pass found two real bugs, both by checking a pack claim against what the routes actually do,
not by reading the tests**, so it also served as a second review of the code. Both were fixed
before submission rather than only disclosed:
- `f1edd55` — Qmail attachments could run script on qumanity.in (§4.10).
- `c09b91f` — a member could not read a council's or the Admin's reply to their own message (§4.8).

**The README was also wrong, and was fixed at `065cecc`.** The front page still described a
deliberately disconnected prototype, pointing at `identity_core.py` and `global_core.py` on "the
real platform" (neither module exists in this repository), plus a manual `db/init_db.py` step the
app no longer needs, a 12-route API table (there are 178), two "known simplifications" that had
already been fixed, and nothing on Qmail, council addresses or the Admin Panel. Anyone reading that
commit's diff should know the old text was out of date, not that the project changed direction.

The pack's content is current as of `065cecc`; the pack itself was committed to `docs/dpg_evidence/`
at `7fda4cb`. As it says of itself, it will go stale as the code moves.

## 6. Gotchas and lessons learned worth not re-discovering

- `db.py`'s `DB_PATH` binds at import time — set `QM_DB_PATH` before any project import in any
  throwaway script.
- `cast_vote()`'s gate must reject by `post_kind == 'council_update'`, not `!= 'member'` — the
  latter silently also blocks voting on test posts, and a unit smoke test that never tries to vote
  won't catch it. Only an actual in-browser walkthrough did.
- SVG `<!-- comments -->` cannot contain a literal `--` even mid-sentence; breaks XML parsing.
- The registration wizard's `/api/auth/register` route only strictly requires
  `birth_location.country.id`; `present_location` needs `country.id` and `state.id` — the rest are
  UI conveniences, not backend requirements. Useful for scripting throwaway test accounts.
- A `data-i18n` attribute's English text is captured as the fallback at page-load time; rewriting
  the visible English copy on an element that keeps its `data-i18n` key means other languages show
  stale translated text until re-translated — an accepted trade-off, not a bug.
- This codebase accumulates real, harmless dead code when pages get trimmed down — worth an
  occasional audit rather than assuming unused-looking selectors are a mistake to "fix" reactively.
- **Run `ls migrations/` before naming a new migration file, every time.** Two sessions working on
  this tree at roughly the same time both independently named a file `020_*.py` — Qmail's and the
  Admin Panel's. Neither checked first. The fix was a rename (`020_qmail.py` → `021_qmail.py`),
  proven idempotent empirically against a DB that already had the old name applied before pushing,
  not assumed safe. The collision that actually happened is the argument for the rule.
- **A missing module-level import breaks `import app` itself, not just the one feature.**
  `admin_queries_core.py` was nearly left out of its own commit's file list — `app.py` imports it
  at module level, so shipping `app.py`'s changes without it would have taken down every route in
  the application on the next boot, not just the Admin Panel. Before composing any `git add` list,
  check what the changed files actually import at module level, and stage every one of those files
  together.
- **A commit state written into a document becomes false the moment the commit that carries the
  document lands.** Name the content's last commit and the document's own commit separately, or
  write the sentence so it stays true regardless of which commit last touched the file. This
  pass's own handover said "the pack is current at `065cecc`", which was true when written and
  false one commit later, once the pack itself was committed at `7fda4cb` (§5, §8).
- **A worktree checkout that still imports the original directory verifies nothing.** A test
  script's `sys.path.insert(0, ROOT)` with a hardcoded absolute path (a pre-existing pattern in
  `tests/test_qmail.py` and others) means running "from" a fresh worktree still imports this
  original directory's modules, not the worktree's own copy — false confidence, not real
  isolation. The honest substitute used in this project: `git diff HEAD` returning zero lines on
  every file a change touched proves the working tree and the committed tree are byte-identical,
  which is what running tests against the working copy is actually standing in for. State that
  explicitly rather than claim a worktree run proved something it didn't.
- **Re-read a diff for lifecycle ordering before running it — tests will not always have the data
  that triggers the bug.** A loop that fetches per-row data (e.g. attachments for each message)
  placed *after* `conn.close()` only fails once there's a row to iterate over; an empty-result test
  run passes silently. This was caught by re-reading the diff itself, not by any test failing.
- **The formatted-text DOM renderer is safe by construction but unguarded by automated tests.**
  See §4.10's closing note — verified live once, not regression-tested, because no browser
  automation framework exists in this project.
- **An unconditional `display` rule on a class beats the browser's own `[hidden] { display: none
  }` default.** `.qmail-compose-overlay { display: flex; }` with no `[hidden]` override meant the
  overlay rendered even while its `hidden` attribute was correctly `true` — the DOM was right, the
  JS was right, only the cascade was wrong. No static-file test can see this; only opening the page
  caught it (§4.11). Give any `hidden`-toggled element with its own `display` rule an explicit
  `.your-class[hidden] { display: none; }`.
- **A "Name (value)" autocomplete must persist the resolved value, not the input's display text,
  anywhere that value gets saved and reused later.** The `/qmail` compose overlay's draft autosave
  read the To field's own text instead of the address already captured in a separate variable —
  every autocomplete-composed draft silently saved something `resolve_address()` could never match,
  failing on every reopen-and-send. Found only by a live walkthrough (§4.11); will recur in any
  future autocomplete field feeding something persisted.

## 7. Standing operational rules for this project

- No access to Railway/production from an assistant session — always hand the user exact commands
  to run themselves.
- Never guess or use real member/admin credentials, even locally. Dev test accounts are created
  via the real `/api/auth/register` route with synthetic data, or via a documented dev fixture
  (`QM_TEST_PIN` in `.claude/launch.json`) — never by guessing.
- The local Admin's real Private ID has been rotated at least once after an earlier leak; the
  current one is never referenced in any file, commit or doc.
- Git: never force-push, never amend without being asked, stage named files only (never `git add
  -A`), one commit per approved task, `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
  trailer.
- The DPG pack directory is not a git repo — edits there are saved as plain files, never committed
  or pushed anywhere. `docs/dpg_evidence/` inside this repo is a copy of the pack and is changed
  only when the owner asks for it; the Mac master is the source (§5).
- Folder/master JSON rules, India location data, and the live user-account tree under `0_Earth`
  must never be restructured or deleted without being asked.

## 8. Current state

- Commits at this handover, all on `main` and pushed: `7fda4cb` (the DPG pack's 18 October 2026
  revision), `065cecc` (the README and `docs/API.md`, `ARCHITECTURE.md`, `DATA_MODEL.md`), and
  the two code fixes before them, `c09b91f` and `f1edd55` (§5). The commit that adds this file
  comes after them.
- Migration range: 001–003, 007–024 (024 is `qmail_drafts`). Tables: 74 on boot, 76 in a running
  database (§2).
- 11 test scripts in `tests/`, all passing at `c09b91f` (`065cecc` changed docs only). Each is a
  standalone script that prints PASS or FAIL; each hard-codes the owner's checkout path, so run
  them with `PYTHONPATH=.`, and four of them also read files through that path (§9).
- Docs current as of this handover: `README.md`, `docs/QMAIL.md`, `docs/ADMIN_PANEL.md`,
  `docs/EMAIL.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/DATA_MODEL.md`,
  `docs/HANDOVER.md` (this file).

## 9. Open items

Not exhaustive — the Forward Plan in the DPG pack (Doc 10, section 10.2) is the full tracked list,
and the row numbers below are its rows.

- **Members can't yet submit an Admin query, and replies need Qmail** (row 36).
  `admin_queries_core.create()` exists but no route calls it. The asker can already read replies
  (`GET /api/queries/mine/<id>`), but only on `/qmail`, which needs Qmail activated, so the
  submission work must also give a member without Qmail a way to open them.
- **Councils can only reply, not start a conversation** (row 37). Needs `sent_as_level` /
  `sent_as_location_id` columns that do not exist yet (`docs/QMAIL.md` §11,
  `docs/ADMIN_PANEL.md` §9).
- **Council addresses above village can't receive messages** (row 38). They are created and shown,
  but no elected councils exist above village yet (`QPUNCH_REACHABLE_LEVELS`, §4.8).
- **Council addresses can lag the member count** (row 39). They are created only when the
  member-count recompute runs, and only the manual backfill script runs it.
- **Attachments are SQLite BLOBs** (row 40), a prototype choice; move them to object storage if
  attachment volume outgrows SQLite (§4.7).
- **The test scripts hard-code the owner's checkout path** (row 41). Resolving the root from each
  script's own location fixes the import for all 11; the four that also read files through the
  path need those reads changed too.
- **`SMTP_*` environment variables are not yet set on Railway**, so the registration-notification
  email is built but does nothing in production until they are (`docs/EMAIL.md`).
- **DMCA ticket #4870732 is awaiting action on GitHub's side**; a cached `refs/pull/1/head` still
  serves the poem files in the meantime.

Also open, but not tracked in Doc 10:

- **Family Group admin succession is unsolved** (§4.12) if a group's sole admin's own node is
  later marked deceased.
- The member-profile popup's "Send Message" button (`static/js/dashboard.js:518`) is still disabled
  with a "Coming soon" note, even though Qmail exists (§4.11).
- Production verification at `https://qumanity.in` of the homepage, dashboard tour, Qmail, Q-Punch,
  Admin Panel and attachment changes; only local verification was done for them.
