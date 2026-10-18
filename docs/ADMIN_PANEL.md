# Admin Panel — design and operations reference (2026-10-18)

A design and operations reference, not a user manual. Built in commit `e4750e4`.

## 1. What it's for, and who can see it

A combined inbox, rendered as **one filterable list plus a detail pane** (`#ap-list` /
`#ap-detail` in `templates/dashboard.html`, driven by `static/js/dashboard.js`'s `apRenderList`/
`apOpenDetail`) — not three (or four) separate panes side by side. An earlier design round
described this as "three-pane"; that was wrong, and this doc says what the code actually does:
one list, filterable by source, with a detail view that dispatches on `item.source` to a
per-source renderer. Four sources feed that one list today: Citizen Reports, ID recovery
requests, general member queries ("my karma looks wrong," "I can't find my account" — things that
are inherently admin-only from the start, with no location and no council escalation ladder, so
they don't fit `reports_core.py`'s model at all; see §4), and, since 2026-10-18, the Q-Punch
council queue (§9) — added as a fourth filter button and one new detail renderer
(`apOpenCouncil`), not a new pane or a fifth tab. The shape absorbed a fourth source with almost
no new pattern, which is the point of building it generic in the first place.

**Today**: the Founder sees all four sources, globally. A village council head sees only their
own village's council queue (§8) — `_is_admin_panel_user()` is no longer identical to `_is_admin()`
for that second audience, now that village has real elected data to scope by. Every level past
village still has the same documented gap as `announcements_core.is_council_member()` /
`reports_core.is_holder_council()`, so a council head at any other level doesn't exist yet to
have access at all.

**Later**: when a real council role exists at another level, `_is_admin_panel_user()` (§2) is
still the one function that changes — but the panel's *global*, cross-location views (reports, ID
recovery, member queries) stay Admin-only forever. They are never extended to a scoped council
member the way the council queue already is.

## 2. `_is_admin_panel_user()` — the one swap point

Returns a scope descriptor, not a bool, as of 2026-10-18 — `None` (no access), `{"scope":
"global"}` (the Founder), or `{"scope": "location", "level": "village", "location_id": ...}` (a
currently-serving village council head, read fresh from `village_council` on every call, no
caching). The full shape, and the four invariants every route built on it must hold, are in §8 —
not repeated here to avoid the two copies drifting apart.

Additive to `_is_admin()`, never a replacement for it — every other existing admin check in this
codebase (the test-cycle panel, the member export tool, etc.) keeps calling `_is_admin()`
directly and keeps meaning exactly "the Founder." The Admin Panel's seven routes all gate on this
new, separate function instead, specifically so that the day a real council role is built, it's a
one-function change — not a find-and-replace across seven routes, and not a risk of missing one
of them.

## 3. Both halves of the gate

Neither half is sufficient alone; both are present:

- **DOM absence**: `templates/dashboard.html` wraps both the "🛡️ Admin" tab button *and* the
  entire `#qm-dash-admin` section in `{% if is_admin_panel_user %}`. For a non-admin viewer, the
  tab and its panel don't exist in the rendered page at all — not hidden by CSS, not present and
  disabled, genuinely absent from the HTML. `is_admin_panel_user` is passed into the template as
  its own variable, deliberately separate from the existing `is_admin` variable. A scope
  descriptor dict is truthy, `None` is falsy, so this `{% if %}` still works correctly for a
  location-scoped head without any template change — confirmed directly (`git status` showed no
  diff to any `.html` file when the scope-descriptor change landed), not assumed.
- **403 on direct fetch**: every one of the seven admin-panel routes
  (`/api/admin/panel/feed`, `/api/admin/queries/<id>`, `/api/admin/queries/<id>/reply`,
  `/api/admin/queries/<id>/close`, `/api/admin/panel/council/<id>`,
  `/api/admin/panel/council/<id>/reply`, `/api/admin/panel/council/<id>/close`, plus the four
  already covered by the member-export pass) checks `_is_admin_panel_user()` as its first
  statement and returns `403` if it fails — so hitting the API directly, bypassing the UI
  entirely, is refused the same way the DOM already hides it. (The three query routes additionally
  require `scope["scope"] == "global"` — see §8.)

A DOM-only gate would still leak data to anyone who called the route directly. A route-only gate
would still show a tab link to people who'd just get a 403 clicking it. Both are needed, and both
are present.

## 4. Why `admin_queries` is its own table, not folded into `reports_core`

A general query has no location and no council escalation ladder — the entire point of
`reports_core.py`'s model is a village-first escalation path with a 10-day SLA deadline per
level, and `reports.location_id` is `NOT NULL`. Forcing "my karma looks wrong" through that shape
would mean inventing a fake location for something that has none.

Instead, `admin_queries` / `admin_query_replies` deliberately mirror `reports_core.py`'s own
`reports` / `report_updates` shape — a ticket plus an append-only reply log — reusing the
*pattern* without reusing the *table*, since the underlying thing being modeled (where does this
belong, who escalates it) is genuinely different.

One thing worth knowing: `admin_queries_core.create()` exists and is fully built, but no
citizen-facing "submit a query" route is wired up yet (per the module's own docstring) — this
pass built the complete model and the admin-facing read/reply/close side, not the member-facing
submission entry point. That's a separate, later decision.

## 5. ID recovery reuse — one write path, unmodified

The Admin Panel's feed reads `recovery_core.list_requests()` to show open ID-recovery requests
alongside reports and queries. **Nothing about `recovery_core.reveal_private_code()` or the
`id_recovery_reveals` logging table changed in this commit** — confirmed directly (`git show
e4750e4` has zero hits for either name). The panel is a read-aggregation layer on top of the
existing recovery flow; deciding a request and revealing a Private ID still goes through exactly
the same single, logged write path it always did (`docs/QMAIL.md` §5 and this codebase's whole
posture on ID visibility rests on that path staying singular — see the `reveal_private_code`
docstring: "the one place the system will show someone ELSE's 9-digit Private ID... every reveal
is logged"). The Admin Panel adds visibility into *that* flow; it does not add a second way to
trigger it.

## 6. The notification mechanism — derived, not pushed

No new notification infrastructure. `notify_core.py`'s existing pattern — a read-state high-water
mark per `(user_id, kind, chat_id)`, "unread" meaning "newer message than the last mark" — gets a
third `kind` value, `'query'`, alongside the existing `'private'` and `'group'`. No migration was
needed for this: `chat_read_state.kind` is a plain `TEXT` column with no `CHECK` constraint
(verified directly against its schema), so adding a third accepted value is a pure application
change inside `notify_core.py` (`mark_read()`'s tuple check, `summary()`, `recent_items()`), not
a schema change.

This covers the **asker's** side — a member whose query got an admin reply sees the same unread
badge their private/group chats already use. It is unrelated to how the **admin** sees new
incoming items, which is the panel's own feed (`/api/admin/panel/feed`), fetched directly when
the Admin tab opens — not routed through `notify_core` at all.

## 7. The import-graph lesson

`admin_queries_core.py` was nearly left out of this commit's file list. `app.py` imports it **at
module level** (`import admin_queries_core`, alongside the other `*_core` imports) — had the
commit shipped `app.py`'s changes without that file, `import app` itself would fail on the very
next boot, taking down every route in the application, not just the Admin Panel. This is the same
failure mode flagged and specifically guarded against before staging Qmail's own commit (see
`docs/QMAIL.md`): **before composing any `git add` list, check what the changed files actually
import at module level, and stage every one of those files together.** A missing function-level
import only breaks the one feature that calls it; a missing module-level import breaks the whole
site.

### A related lesson, recorded here because this is where the collision happened

This commit's own migration, `migrations/020_admin_panel.py`, and Qmail's first migration file
were both independently named `020_*.py` — created in two sessions working on the same tree at
roughly the same time, neither checking what the other had already added. The fix was a rename
(Qmail's file became `021_qmail.py`; this file was left untouched, since it had no reason to
move). It was empirically proven idempotent before pushing — see `docs/QMAIL.md`'s own note on
the proof — but the real fix is upstream of needing a fix at all: **run `ls migrations/` before
naming a new migration file**, every time, especially when more than one line of work might be
touching the tree concurrently. The collision that actually happened here is the argument for the
rule, not a hypothetical one.

## 8. Scoping invariants (2026-10-18, Q-Punch council scope)

`_is_admin_panel_user()` now returns a scope descriptor (`None`, `{"scope": "global"}`, or
`{"scope": "location", "level": "village", "location_id": ...}`) rather than a bool, so the panel
can serve a village council head a feed scoped to their own location without ever letting them
see a report, an ID-recovery request, or a member query — see `docs/QMAIL.md`'s Q-Punch section
for the full feature. Four invariants hold for every route built on that scope, each one found or
decided deliberately while building the feed branch, each one easy to undo by accident if a future
change doesn't know why it's there:

- **An out-of-scope message id returns 404, never 403.** `_qpunch_message_in_scope()` treats "the
  message doesn't exist" and "the message exists but belongs to a different location" as the same
  outcome on purpose. A 403 would confirm to a village head that some OTHER village's message id
  is real; a 404 tells them nothing either way. Never special-case the 404 into a 403 "to be more
  informative" — that information is exactly what a location-scoped caller must not get.

- **The location handler takes no request argument.** `_admin_panel_feed_location(level,
  location_id)` is only ever called with the two values the scope descriptor computed
  server-side — never with anything read from `request.args`, `request.json`, or the URL. Scoping
  here is structural (the function physically cannot see a client-supplied location), not a check
  that could be forgotten or bypassed. If a future change adds a parameter to this function to let
  a caller "pick" a location, the structural guarantee is gone — don't add one.

- **The scope query re-runs on every call, with no caching.** `_is_admin_panel_user()` checks
  `village_council`'s current term fresh, every request, against today's date. A head whose
  `leadership_end` has passed falls out of location scope on their very next request, not at some
  later session refresh or cache expiry — proven, not assumed, by
  `tests/test_admin_panel_council_scope.py`'s Section 7 (an expired term turns a previously-200
  feed fetch into a 403 with no other state change in between). Don't introduce a session-level
  cache of the scope descriptor; it would reopen exactly this gap.

- **A rejected cross-location write leaves no audit row.** When `_qpunch_message_in_scope()`
  returns `None`, the route returns 404 *before* `_log_qpunch_action()` is ever called — a village
  head's attempt to reply to or close another village's message produces nothing in
  `qpunch_queue_actions`, not a logged-and-rejected attempt. `tests/test_admin_panel_council_scope.py`
  Section 2 asserts this directly (queries the other village's action log for the attempted reply
  text and asserts absence). Logging the attempt itself would mean the one table built to be an
  honest record of who touched what also ends up holding read access to information the writer
  was never shown.

## 9. The council queue — the fourth source

A village's Q-Punch council address (`docs/QMAIL.md` §11) delivers into `qpunch_queue_messages`,
not into any individual's personal Qmail — `GET /api/admin/panel/council/<id>` (view),
`POST .../reply`, `POST .../close` are its only read/write surface, all gated on
`_is_admin_panel_user()` and scoped through `_qpunch_message_in_scope()` (§8). Every touch —
**view, reply, and close alike** — writes a `qpunch_queue_actions` row naming the real
`actor_user_id`, matching `id_recovery_reveals`' posture: a shared, auditable queue where every
read and every write is attributable, not just the writes. A reply additionally moves the
message's `status` to `'answered'` and is read back by `notify_core`'s derived unread count (kind
`'council'`, `chat_id = qpunch_queue_messages.id`) — the asker sees the same unread badge their
private/group chats already use, with no new notification infrastructure, the same reasoning §6
already gives for the `'query'` kind.

Reading `message.attachments` (`qmail_core.attachments_for(conn, "council", message_id)`) is part
of this same detail response — an attachment on a council message is access-checked the identical
way the message itself is, through `/api/qmail/attachments/<id>` reusing
`_qpunch_message_in_scope()` directly, not a parallel check that could drift from it.

**Composing a brand-new, council-*initiated* message to a member — one who never wrote in first —
is deferred to a later pass, deliberately, not missing by oversight.** It needs a way to mark a
`qmail_messages` row as sent *as* a council rather than as the individual head who pressed send
(tentatively two nullable columns, `sent_as_level` / `sent_as_location_id`), so the recipient sees
"Village Council" while the database still honestly records who actually sent it. **These columns
do not exist anywhere in this codebase** — `qmail_messages`' schema has no `sent_as_level` column,
and neither `api_qmail_compose` nor `api_admin_panel_council_reply`'s own source references the
name, confirmed directly (`tests/test_qmail_attachments.py` Section 1), not assumed from the
absence of a migration. *Replying* within an existing thread needs none of this and is fully
built (above); composing *to* another village's council address already works today with no new
code either (see `docs/QMAIL.md` §11's closing note). Only the proactive, council-as-sender case
is the open piece.
