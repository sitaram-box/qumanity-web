# Qumanity — Project Handover

Written 17 October 2026, refreshed 18 October 2026 to cover Qmail, Q-Punch council addresses, the
Admin Panel's scope evolution and the member mailbox UI. This is a snapshot for whoever picks up
the project next — it is not a replacement for the detailed design docs already in this folder
(linked throughout), and it will go stale as the code moves; treat it as a map, not a source of
truth for exact current state.

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
  001–003, 007–023 (004–006 unused). 023 is the most recent (Qmail attachments).
- **73 application tables** (74 with SQLite's own `sqlite_sequence`) — counted directly against a
  freshly-migrated throwaway database, not estimated from an older doc. Full list with purposes in
  `docs/DATA_MODEL.md` (not refreshed in this pass — see §9).
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
- Full architecture detail: `docs/ARCHITECTURE.md`. Every route: `docs/API.md`. Every table:
  `docs/DATA_MODEL.md`. **Only `docs/API.md` was refreshed in this pass** (new Qmail/attachment/
  council routes added); `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` still reflect 17 October
  and do not yet list `qmail_attachments`, `qpunch_addresses`, `qpunch_queue_messages` or
  `qpunch_queue_actions` — flagged here rather than left for someone to discover by surprise.

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

**The member mailbox UI** (activation card, inbox, sent, compose with a markup toolbar) lives on
the dashboard's Private tab. Message bodies are plain text with a narrow whitelist markup
(`**bold**`, `_italic_`, `[text](url)`) — never HTML, on either side. The client builds `<b>`/`<i>`/
`<a>` DOM nodes directly from the parsed text; no HTML string is ever constructed from user input,
so there is no sanitizer installed and no `|safe` anywhere in this codebase — **deliberately, not
an oversight** (`docs/QMAIL.md` §12 says this explicitly, for exactly the reason a future
contributor might otherwise "fix" it). A link's URL is scheme-checked (`http(s)://` only) before
becoming clickable. Attachments are compose-time only, stored as SQLite BLOBs
(`qmail_attachments`, migration 023) — a prototype choice, not permanent architecture, chosen
because the database already carries the volume-persistence guarantee a disk path on Railway would
need a new, separately-configured path to earn. Capped at 2 MB, enforced twice independently
(Flask's app-wide `MAX_CONTENT_LENGTH` as a first line of defense, `qmail_core.save_attachment()`'s
own precise byte check against the decoded data). Images are attachment-only, never inline by
URL — a privacy decision (an inline `<img src>` to an external host leaks the viewer's IP at
render time), not a style one.

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

**A known, stated gap**: whether a `<script>` tag in a message body actually renders as inert text,
and whether a `javascript:`-scheme link actually fails to become clickable, are DOM-rendering
properties of `static/js/dashboard.js`'s `qmRenderFormattedText()` with no Python-testable surface
in this stack (no Selenium/Playwright/jsdom installed). Both were verified directly in a live
browser once, by hand, this session — not by an automated regression test. `tests/
test_qmail_attachments.py` covers everything a backend test *can* verify about this feature
(size limits, access control, that the server never mangles a body); it cannot and does not
re-check the renderer. A future change to that function could reintroduce an XSS path and nothing
in this project's test suite would catch it — recorded here so the next person knows the renderer
is unguarded by automation, not assumed safe forever because it passed once.

## 5. DPG Evidence Pack — status at this handover

A separate, non-git directory at `~/Desktop/My Mac/DPG/` holds the 11 DPG Standard evidence docs.
**A full re-audit is in progress, not complete.** Task 1 (read all 11 docs, summarize claims, flag
sections likely affected by recent changes) is done. Tasks 2–6 (section-by-section drift analysis,
proposed edits, Doc 11 status re-check, a new cover letter, applying + saving the edits) are **not
yet started**, and explicitly have not been touched by the Qmail/Q-Punch/Admin-Panel work in this
handover — that work was deliberately kept separate, not folded in. Whoever picks this up should
re-read the prior Task 1 output before continuing, not restart from scratch.

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
  or pushed anywhere. `docs/dpg_evidence/` inside this repo is likewise off-limits until the
  audit pass explicitly resumes (§5).
- Folder/master JSON rules, India location data, and the live user-account tree under `0_Earth`
  must never be restructured or deleted without being asked.

## 8. Current state

- Latest commit at this handover: `079313c` ("feat: add member mailbox and council inbox UI with
  attachment support"), on `main`, pushed.
- Migration range: 001–003, 007–023.
- Five test suites cover this handover's new work and all pass together against the working tree:
  `tests/test_qpunch.py`, `tests/test_qmail.py`, `tests/test_account_id_sync.py`,
  `tests/test_admin_panel_council_scope.py`, `tests/test_qmail_attachments.py`.
- Docs current as of this handover: `docs/QMAIL.md`, `docs/ADMIN_PANEL.md`, `docs/API.md`,
  `docs/HANDOVER.md` (this file). **Not refreshed in this pass**: `docs/ARCHITECTURE.md`,
  `docs/DATA_MODEL.md` (both still reflect 17 October — missing the three Q-Punch tables and
  `qmail_attachments`).

## 9. Open items

Not exhaustive — see `docs/DATA_MODEL.md`, `docs/ARCHITECTURE.md` and the Forward Plan in the DPG
pack for the full lists.

- DPG pack audit: Tasks 2–6 outstanding (§5).
- `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` need a pass to add the four new tables and the
  Q-Punch/attachment additions to `qmail_core.py`'s module-map entry.
- Council-*initiated* new conversations (a council proactively messaging a member who never wrote
  in first) deferred to v2 — needs `sent_as_level`/`sent_as_location_id` columns that do not exist
  yet (`docs/QMAIL.md` §11, `docs/ADMIN_PANEL.md` §9). Replying within an existing thread and
  composing *to* a council address both already work today.
- `SMTP_*` environment variables are not yet set on Railway — registration-notification email is
  built but silent-no-ops in production until that's configured (`docs/EMAIL.md`).
- A DMCA ticket (#4870732) is awaiting action on GitHub's side; a cached `refs/pull/1/head` is
  still serving the poem files in the meantime.
- `location_elements.total_users` suppression on `/api/location/elements/<id>` and
  `/api/global/elements` (only `birth_users` is suppressed there today).
- Production verification of the homepage, dashboard-tour, Qmail, Q-Punch, Admin Panel and
  attachment changes at `https://qumanity.in` (local verification only is complete for all of
  them).
