# Qmail — design and operations reference (2026-10-18)

This is a design and operations reference, not a user manual. It describes what Qmail is, why it
is built the way it is, and the invariants that must hold if anyone extends it later.

## 1. What Qmail is

Qmail is internal messaging between Qumanity members, addressed in an email-like format. **It is
not inbound internet mail.** There is no Postfix, no Mailgun, no SES, nothing that receives real
mail from the public internet anywhere in this codebase. `@qumanity.in` is an addressing
convention a message stays inside — composing to `someone-ABC123@qumanity.in` delivers an
internal message to that member's account, the same way a chat message would, dressed in a
format members already understand from real email. Say this plainly wherever Qmail is introduced
in the product: nobody should expect mail sent from Gmail or anywhere else to arrive at a Qumanity
address, because none ever will, unless a later phase explicitly builds real inbound receiving
through a chosen mail provider — which this module neither does nor assumes.

## 2. The address model

An address is `[username]-[account_id]@qumanity.in`, e.g.
`rohit.delhi-KR3-EO-GMA2-ZAI-CS.DL.3.4.1A@qumanity.in`.

**The username lives on `users.qmail_username`, not inside `qmail_addresses`.** This is a
deliberate split, not an oversight: the username is chosen once, is globally unique, and must
stay unique *across every account_id a member ever has*. If the username were stored as a column
inside `qmail_addresses` (the per-account_id history table, see below), the very first time that
member's `account_id` changed, a second row would be inserted carrying the *same* username — and
a `UNIQUE(username)` constraint on that table would reject it, since the member's own first row
already holds it. Storing the username once, on `users`, with its own unique index, sidesteps
this entirely: uniqueness only ever has to hold once per person, never fighting the address
history's own need to keep multiple past rows around.

**`qmail_addresses` is history, not state.** One row per `account_id` epoch. Every time
`account_id` regenerates (see §5), a new row is inserted and the old one is marked
`is_current = 0`. This mirrors `account_ids`' own "keep every past Account ID forever" pattern —
with one deliberate difference, the forward window (§4).

## 3. The username rules

- 8–15 characters.
- Letters, numbers, `.`, `_`, `-` only. Narrower than the original "letters, numbers, special
  characters" brief, deliberately: most characters that are technically legal in an email
  local-part behave inconsistently across real mail clients, and this address needs to actually
  work everywhere it's shown, not just pass an RFC reading.
- Always stored lowercase, whatever the member typed (`qmail_core.validate_username`).
- Globally unique (`idx_users_qmail_username`, a real `UNIQUE INDEX` — not just an
  application-level check, the way `account_id` itself still isn't constrained at the DB level).
- Nullable. Activation is optional; most members may never set one.
- A length `CHECK` constraint is the DB-level backstop for the 8–15 rule
  (`migrations/020_qmail.py`). The character-set rule can't be expressed as a `CHECK` without a
  loaded regex extension, so that part is Python-only (`qmail_core.QMAIL_USERNAME_RE`).

## 4. The 30-day forward window

`qmail_addresses.forward_until` is set the moment a row stops being current — `now + 30 days` —
and is the one place Qmail's behavior genuinely diverges from `account_ids`, which never expires
anything.

Resolution rules (`qmail_core.resolve_address`):
- **Current address** (`is_current = 1`): always resolves.
- **Old address, inside the window** (`is_current = 0 AND forward_until > now`): still resolves,
  to the same member — composing to a just-stale address quietly reaches the right person.
- **Old address, past the window** (`forward_until <= now`, or no row at all): resolves to
  nothing. `/api/qmail/compose` returns 404, cleanly, not a silent failure.

Because this is internal delivery rather than real SMTP, there is no bounce mechanism to build —
resolution either finds the current owner or it doesn't, and the sender finds out immediately.

## 5. The `regenerate_account_id()` choke point — the important one

`social_core.regenerate_account_id()` is the **only** place `account_id` is ever regenerated —
both the dedicated "request a new Account ID" flow and the generic profile-change-request queue
funnel through it (this was itself a bug fix, see `tests/test_account_id_sync.py`'s own
docstring). Qmail's address-sync logic is appended to the end of that same function: if the
member has `qmail_username IS NOT NULL`, it marks their current `qmail_addresses` row
`is_current = 0` with `forward_until = now + 30 days`, then inserts the new current row.

**This must never grow a second path.** If a future change needs to touch `account_id` outside
`regenerate_account_id()`, Qmail's addressing will silently fall out of sync with it — the exact
class of bug that `account_id` itself had before the Path A/Path B fix this feature was built
right after. There is one function that changes `account_id`. It is also the one function that
changes a Qmail address. Keep it that way.

## 6. The route table

All nine routes are `@login_required`; none is public.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/qmail/activate` | `{"username"}` → validates, checks global uniqueness, writes `users.qmail_username`, mints the first `qmail_addresses` row. |
| POST | `/api/qmail/compose` | `{"to", "subject", "body"}` (JSON), or multipart with those three fields plus an optional `attachment` file — `to` is re-resolved server-side via `qmail_core.resolve_address`, never trusted from the client; see §11 for how a council address routes differently here, and §12 for the attachment. |
| GET | `/api/qmail/inbox` | This member's received messages, each with an `attachments` list (metadata only). |
| GET | `/api/qmail/sent` | This member's sent messages — member-to-member rows plus this member's own outgoing copy of anything they sent to a council address (§11). |
| POST | `/api/qmail/messages/<id>/read` | Marks one received message read (`qmail_messages.read_at`) — only the recipient may call this for their own message. |
| GET | `/api/qmail/attachments/<id>` | Streams one attachment's bytes, access-checked against the message it belongs to (§12) — never a bare, unguarded file URL. |
| GET | `/api/qmail/resolve-username` | `?q=<partial>` — the smart "To" field's autocomplete, scoped to `social_core.connected_user_ids()` (§7). |
| GET | `/api/qmail/resolve-public-id` | `?code=<12-digit>` — resolves via the existing `account_ids.search_code`, no connection required. Returns a clean `{"activated": false, ...}` for a member who hasn't activated — never a 404, never a fabricated address. |
| GET | `/api/qmail/status` | **Not one of the original six design-approved routes.** Added because the activation card and the address-change banner both need page-load state (am I activated, do I have a still-forwarding old address) and none of the other six provide it. Flagged explicitly when added rather than folded in silently. Read-only. |

## 7. The smart "To" field

`social_core.connected_user_ids(conn, user_id)` is the *entire* mechanism scoping username
suggestions to people the member actually knows — every Personal Group (any category, approved
membership, both directions) unioned with every private chat where the member's own side hasn't
been left. `/api/qmail/resolve-username` filters strictly to `id IN (connected_user_ids(...))`.

**There is no fallback path that widens this.** A disconnected user does not appear in username
suggestions under any circumstance — not as a lower-priority result, not if the query matches
exactly, not ever. The outside-network path exists, but it's a different route entirely
(`/api/qmail/resolve-public-id`, by 12-digit Public ID, which the sender has to already have),
not a wider mode of the same one.

## 8. Known limits — planned, not built

- No message threading.
- No external delivery of any kind (§1) — no inbound receiving, no outbound to real mail
  providers.
- No spam filtering (meaningless for an entirely internal system today, but worth naming
  explicitly as a gap the moment real external delivery is ever considered).
- Read receipts are now wired up (`POST /api/qmail/messages/<id>/read`, §6) but are a plain
  high-water mark, not a receipt the sender is told about — the sender never learns *when* a
  message was read, only the recipient's own inbox shows it.
- The mailbox UI (activation card, inbox/sent, compose with a markup toolbar and an optional
  attachment) is built — see §12. Still not built: real-time delivery (the inbox is poll-on-open,
  like every other feed in this app, not pushed) and a brand-new, council-*initiated* conversation
  that isn't a reply to something a member sent first (§11's closing note).

## 9. A cautionary note: the compose `.lower()` bug

The first version of `/api/qmail/compose` lowercased the entire incoming `to` string before
resolving it. `account_id` legitimately contains uppercase letters (e.g. `KR3-EO-GMA2-ZAI-...`),
so the lowercased query never matched the stored, correctly-mixed-case `full_address` — every
single compose call failed with "address not recognized," including to a brand-new, definitely-
current address. The fix: don't lowercase `to` at all. The field is always system-generated and
auto-filled by the smart "To" field (per the original design: the full address is "generated by
the system, never typed by the user") — so there was never a case-insensitivity need to serve in
the first place, and the blanket `.lower()` call only ever had a chance to do harm.

The lesson for anything touching address strings in this codebase: `qmail_username` is
normalized lowercase by design (§3) — `account_id` is not, and must never be treated as if it
were.

## 10. A second cautionary note: the migration-number collision

Qmail's first migration file was named `migrations/020_qmail.py` — the same number as
`migrations/020_admin_panel.py`, created independently in a different session working on the same
tree at roughly the same time. Neither session checked `ls migrations/` first. The fix was a
rename, `020_qmail.py` → `021_qmail.py` (the admin panel's file was left untouched — it had no
reason to move, and correcting the collision only required one side of it to change).

Because `tools/run_migrations.py` tracks applied migrations by filename
(`filename TEXT PRIMARY KEY`), the rename meant a database that had already applied
`020_qmail.py` would see `021_qmail.py` as new and run it again. This was **proven** idempotent
before pushing, not assumed: a throwaway DB was built with `020_qmail.py` already applied and
recorded, the rename was performed, and the migration tool was re-run against that same DB. Result:
no error, `021_qmail.py` recorded as a new row (the stale `020_qmail.py` row correctly left in
place — migrations are never deleted from the tracking table), and the schema itself — one
`qmail_username` column, two tables, five indexes — identical before and after, because the
migration's `run()` body is pure idempotent DDL (`ALTER TABLE ADD COLUMN` guarded by a `PRAGMA
table_info` check, `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) with zero
`INSERT`/`UPDATE`/`DELETE` statements anywhere in it.

The standing rule, now recorded in two places (see also `docs/ADMIN_PANEL.md` §7, where the
collision's other half happened): **run `ls migrations/` before naming a new migration file**,
every time. If a rename is ever unavoidable after the fact, prove idempotency empirically against
a DB that already has the old name applied — don't reason your way to "should be fine" and push.

## 11. Q-Punch council addresses

An extension of Qmail that addresses a **location**, not a member. Format:
`<level>-<location_id>@qumanity.in` — e.g. `village-CS.DL.3.4.1A@qumanity.in`. No `qpunch-`
prefix (an earlier round of this design used one; dropped once the address no longer needed to be
distinguished from a member address by its shape at all — see "the withdrawn username guard"
below). `location_id` is the location's own existing hierarchical id, used exactly as it already
appears everywhere else in this codebase (`location_elements`, the folder tree, URL params) —
never a generated slug, never lowercased.

**One permanent row per location, created once it crosses a threshold, never removed.** A
location's `qpunch_addresses` row is inserted the first time its real member count (`is_demo=0
AND is_removed=0`) reaches its level's threshold, and stays forever — if the count later drops
back below threshold, the address is not retired, deactivated, or hidden. A council mailbox that
disappears because two members left is a worse experience than one that keeps serving a shrunk
community; this holds at every level, not just village. There is deliberately no `status` column
and no reactivate/retire logic to maintain.

| Level | Threshold | Reachable today |
|---|---|---|
| village | 5 | Yes |
| tehsil | 10 | Yes |
| district | 100 | No — no real elected data above village (see below) |
| state | 1,000 | No |
| zone | 10,000 | No |
| country | 100,000 | No |
| continent | 1,000,000 | No — theoretical at this project's current scale |
| earth | 10,000,000 | No — theoretical at this project's current scale |

The threshold is "at least," i.e. `total_users >= threshold`: a village with exactly 5 real
members gets its address. Generation hooks into `elemental_core.recompute_location_elements()`
(`qmail_core.sync_qpunch_addresses`, called in the same transaction, so a dry run creates zero
addresses the same way it writes zero stats) — inheriting that function's existing staleness (only
the manual backfill script calls it; nothing in the scheduler does), a tradeoff already accepted
elsewhere in this project, not something this feature newly introduces.

**The village-only reachability gate is one constant, read by two consumers — not two
independently-maintained gates.** `qmail_core.QPUNCH_REACHABLE_LEVELS = {"village"}` is checked
by `resolve_address()` (delivery: a non-village council address resolves to `None`, same as an
unknown one) and by the board-line renderer (display: a non-village address still *shows*, labeled
"not yet reachable in this prototype"). An address at every level above village exists and is
visible the moment it's generated; only village can actually receive mail, because only village
has real elected data (`village_council` — the same documented gap as
`reports_core.is_holder_council()` / `announcements_core.is_council_member()`). Having one shared
constant, rather than a separate check hard-coded into each consumer, means the two can't drift
apart — if a future change widens reachability, there is exactly one line to touch.

**Delivery**: `resolve_address()` returns a tagged result, not a bare value — `{"kind": "member",
"user_ids": [id]}` or `{"kind": "council", "level", "location_id", "user_ids": [...]}` — because a
council message's *storage* differs from a member message's, not just its recipient count. A
council address's `user_ids` (both current heads, or the admin fallback if the seat is empty, via
the same precedent `reports_core.is_holder_council()` already established) is informational, used
for the board line and for who the panel attributes a reply to — the message itself is never
inserted into `qmail_messages`, because a council message has no fixed recipient set: the heads
change at every election, and a message addressed to the village must still be visible to whoever
holds the seat next. See `docs/ADMIN_PANEL.md`'s council-inbox section for where it actually lives
(`qpunch_queue_messages`, read through the Admin Panel, not through personal Qmail).

**The withdrawn username guard.** An earlier round of this design proposed rejecting any Qmail
username that started with a reserved level word (`village-`, `district-`, …), to prevent a
member's own address from being mistaken for a council one. The guard turned out to solve a
problem that doesn't exist: `resolve_address()` does a single exact-string lookup against the
stored `full_address` — no parsing, no hyphen-splitting, no inference from an address's shape at
all. A member's full address and a council address can only ever collide if they are the *exact
same string*, which `account_id`'s own generated shape (starting with a random prefix and
initials, never with a literal level word) makes impossible by construction. **Do not re-propose
this guard** — if a future change makes `resolve_address()` start parsing addresses instead of
doing an exact lookup, that is the point to reconsider it, not before.

**Compose-outward from a council address is reply-only in this pass.** A council head replying to
an existing `qpunch_queue_messages` thread is fully built (`docs/ADMIN_PANEL.md`). A
council-*initiated* new conversation — the council messaging a member who never wrote in first —
is a genuinely different feature: it needs a way to mark a `qmail_messages` row as sent *as* a
council rather than as the individual head who pressed send, so the recipient sees "Village
Council" while the database still honestly records who actually sent it. That needs two new
nullable columns (tentatively `sent_as_level` / `sent_as_location_id`) that **do not exist in this
codebase** — deferred to a later pass, not half-built. Composing *to* another village's council
address already works today with no new code (a council head who has personally activated Qmail
is just a member composing to a `village-...` address like anyone else).

## 12. The member mailbox: formatted text and attachments

**Stored format: plain text with a narrow whitelist markup — `**bold**`, `_italic_`,
`[text](url)` — never HTML, on either side.** There is no sanitizer library installed in this
project (`requirements.txt` has none) and no `|safe` anywhere in any Jinja template — **this is
deliberate, not an oversight.** The client (`static/js/qmail_format.js`'s `qmRenderFormattedText`)
parses a message body and builds `<b>`/`<i>`/`<a>` DOM nodes directly via
`createElement`/`textContent`, the same way every other piece of user text in this codebase has
always been rendered (`board.js`'s `el()` helper, used everywhere, sets `.textContent`, never
`.innerHTML`) — no HTML string is ever constructed from user input, so there is nothing to
sanitize and no class of injection bug to guard against. A future contributor who notices no
sanitizer is installed should not conclude it was forgotten; adding one, or adding `|safe`
anywhere, would be the first time this codebase ever did either, and is worth stopping to
reconsider rather than reaching for reflexively. A link's `url` is checked against `^https?://`
before becoming a real `<a href>` — anything else (most importantly a `javascript:` URL) renders
as its plain-text label, never a clickable element.

**The renderer was extracted into its own file at commit `e99eced` (2026-10-18), and rewritten,
not merely moved.** `qmRenderFormattedText` originally lived in `static/js/dashboard.js` and built
its `<b>`/`<i>` elements through that file's own local `apEl()` helper. Moving it into standalone
`static/js/qmail_format.js` — so every real consumer loads one shared definition instead of risking
a second copy drifting from the first, the same reasoning `social_core.regenerate_account_id()`
already established as this codebase's precedent — meant `apEl()` was no longer reachable (a
different file's closure-local helper). The function was rewritten to call
`document.createElement`/`.textContent` directly instead, producing identical output but **new
code, not the old bytes relocated**. A future reader diffing behavior against an old version of
`dashboard.js` should know the implementation changed at commit `e99eced`, not just its address.
Both `templates/dashboard.html` and `templates/qmail.html` load `qmail_format.js` before their own
consumer script (`dashboard.js`'s `apOpenCouncil`; `qmail.js`'s reading pane) — plain `<script>`
tags, no `defer`/`async`, so document order *is* execution order, deterministically; this is not a
"usually fine, rarely flaky" ordering concern, it's guaranteed by the browser's own parsing model
as long as none of those tags ever gains a `defer`/`async` attribute.

The set of real consumers changed again one commit later (`ab01267`, the `/qmail` page): the
member mailbox UI that used to live inline on the dashboard (in `dash_extras.js`, calling this
function) moved entirely to the standalone `/qmail` page, taking its only call site with it.
`dash_extras.js` today calls `window.qmRenderFormattedText` zero times — it keeps only the Qmail
*activation* card (username chooser, address display, the "Open Qmail →" link), which never
needed the renderer. The two real consumers are `dashboard.js` (Admin Panel council detail) and
`qmail.js` (the page's own reading pane).

**Images are attachment-only, never inline by URL.** This is a privacy decision, not a style one:
an `<img src="...">` pointing at an external URL leaks the viewer's IP and user-agent to that URL
the moment the message renders, before anyone clicks anything — unacceptable for a governance
mailbox where "who read this and when" shouldn't be observable by a third party. An attachment's
bytes live in this app's own database and are only ever served back through an authenticated,
access-checked route (`GET /api/qmail/attachments/<id>`, §6) — reading one never pings anyone
outside Qumanity.

**Attachments are stored as SQLite BLOBs (`qmail_attachments`, `migrations/023_qmail_attachments.py`)
— a prototype choice, not a permanent architecture.** The database already carries the
volume-persistence guarantee Railway requires a separate, deliberately-configured path for
(`docs/INSTALL.md`'s own warning about `QM_DB_PATH` and the ephemeral container filesystem shows
how easily that gets forgotten) — a BLOB inherits that guarantee for free, with no new env var and
no new "did I mount this right" failure mode. Migrating to real object storage later, if this ever
outgrows SQLite, is a separable decision this table doesn't make any harder. Capped at 2 MB per
attachment, **enforced twice, independently**: `app.config["MAX_CONTENT_LENGTH"]` (3 MB, an
app-wide first line of defense that rejects an oversized request before `request.files` is even
populated) and `qmail_core.save_attachment()`'s own explicit `len(data) > MAX_ATTACHMENT_BYTES`
check against the decoded bytes — a client that lies about size, or whose multipart overhead eats
into the wider global cap, is still caught by the second, precise check. `kind` + `message_id` is
a loose, polymorphic reference (`'member'` → `qmail_messages.id`, `'council'` →
`qpunch_queue_messages.id`) rather than a real foreign key, since it points at two different
tables depending on `kind` — every query filters on both columns together, never `message_id`
alone. Attachments are compose-time only; a reply never carries one in this pass.

**A known gap, stated plainly rather than silently left for someone to discover**: whether a
`<script>` tag actually renders as inert text, and whether a `javascript:`-scheme link actually
fails to become clickable, are properties of the client-side DOM renderer with no Python-testable
surface in this project's stack (no Selenium/Playwright/jsdom installed, and this pass deliberately
didn't add one). Both were verified directly in a live browser once, by hand, this session — not
by an automated regression test. `tests/test_qmail_attachments.py` covers everything about this
feature that a backend test *can* verify (size limits, access control, that the server never
mangles a message body); it does not and cannot re-check the renderer itself. A future change to
`qmRenderFormattedText` could reintroduce an XSS path and nothing in this test suite would catch
it. **This gap applies in full to the extracted-and-rewritten version of the function above** — the
extraction's own browser walkthrough (bold/italic rendered correctly in both the Admin Panel's
council detail view and the member mailbox, zero console errors) and `tests/
test_qmail_format_extraction.py` (which checks the script-tag wiring, not the rendering logic)
are both one-time or structural checks, not a regression test of the renderer's safety properties
either. There is still exactly one gap here, not two.

## 13. Drafts

Unsent compose-form state (`qmail_drafts`, `migrations/024_qmail_drafts.py`), one row per draft,
scoped by `user_id`. Text only — no attachment in a draft; autosaving a BLOB on every
compose-overlay close would multiply write volume for a feature that wasn't asked to extend.
`to_address` is whatever the compose form's To field currently holds, unresolved and unvalidated —
a draft is allowed to have a garbage or incomplete recipient while being edited; resolution only
happens at actual send time, same as it always has for compose itself.

**Scoping is the same 404-not-403 shape as the council queue's own invariants** (`docs/
ADMIN_PANEL.md` §8): `qmail_core.save_draft()` and `delete_draft()` both filter their `UPDATE`/
`DELETE` by `user_id` directly in the `WHERE` clause, not a fetch-then-check — a draft id
belonging to a different user and a draft id that doesn't exist at all produce the identical
zero-rows-affected result, which the routes turn into the same 404 either way.

**Send-clears-draft is atomic with the message itself — and the atomicity lives inside
`delete_draft()`, not where it looks like it should.** `api_qmail_compose` inserts the message
(and the attachment, if any) first, and only calls `qmail_core.delete_draft()` after both have
already succeeded — so a failure in between (the oversized-attachment check, specifically) rolls
back the message insert via `conn.rollback()` and returns *before* the draft-deletion code is ever
reached; the draft is never touched on a failed send. On a successful send, though, the commit
that makes the message, the attachment, and the draft-deletion durable together is **`delete_draft()`'s
own internal `conn.commit()`** (`qmail_core.py`), not `api_qmail_compose`'s trailing `conn.commit()`
line — that trailing commit is a no-op in the draft case (nothing left pending to commit) and only
does real work for an ordinary compose call with no `draft_id` at all. **This is non-obvious and
easy to break**: a future tidy-up of `delete_draft()` that removes its `conn.commit()` — on the
reasonable-looking grounds that "the caller already commits" — would silently split what is
currently one atomic transaction into two, reopening exactly the failure mode this design avoids
(a message sent but the draft not cleared, or worse, if the split landed differently). If
`delete_draft()`'s commit is ever removed, the atomicity has to move somewhere else
*deliberately*, not be dropped by accident.

**No cleanup job for abandoned drafts.** A draft nobody ever sends or deletes sits in
`qmail_drafts` forever — a stated, deliberate prototype limitation, not an oversight. Gmail has
the same behavior (an abandoned draft sits in the Drafts folder indefinitely), so this isn't a
regression against the product being mirrored. `POST /api/qmail/drafts/<id>/delete` exists
specifically so a member can clean up their own drafts manually; nothing automatic does it for
them.

## 14. The `/qmail` page

A standalone route (`@app.route("/qmail")`, `templates/qmail.html`), not a dashboard tab — it
gets its own scroll/focus context and a real, bookmarkable URL, the same tradeoff every other page
in this codebase already makes (no shared layout system exists here; every template is a
self-contained `<!doctype html>…</html>` file). `GET /qmail` redirects an unactivated member back
to `/dashboard`, where the activation UI (`#qm-qmail-card`) actually lives — this page assumes an
address already exists, it doesn't mint one.

**`static/css/qmail.css` is a separate file, not appended to `dashboard.css` — deliberately.**
`/qmail` does not load `dashboard.css` at all, matching `templates/elements.html`'s own precedent
(`style.css` + `register.css` + one page-specific stylesheet, no shared dashboard file). Appending
to `dashboard.css` would mean loading a large amount of unrelated dashboard-only CSS — the Admin
Panel's grid, `.pv-card`, every stats panel — on a page that needs none of it. Two small utility
classes, `.qm-dash-empty` and `.sg-btn`, only existed in `dashboard.css` before this page needed
them; they're redefined **verbatim** in `qmail.css` rather than pulling the whole file in for two
rules. **A future contributor who notices `.sg-btn` defined in two CSS files should find this
explanation, not "fix" it into one shared file** — that would mean `/qmail` loading
`dashboard.css`, which is exactly the bloat this split was chosen to avoid.

**The dashboard's own inline mailbox UI — the thing `/qmail` replaces — was deleted, not left to
no-op.** `templates/dashboard.html`'s `#qm-mail-card` (the inbox/sent/compose block built the pass
before this one) is gone; so is the legacy `#qm-messagebox-card` "Coming soon" placeholder it sat
near. `static/js/dash_extras.js` lost the ~124 lines of inbox/sent/compose logic that only
`#qm-mail-card` ever drove — once that element left the DOM, `$("qm-mail-card")` returns `null`
and the whole block was already dead (the `if (mailCard) { … }` guard made it a safe no-op, not a
crash), but a safe no-op left sitting in the file is still something a future reader has to read,
understand, and confirm is actually unreachable before trusting it's unreachable. Removing it
outright means the dashboard's own mailbox UI genuinely left, matching the feature's own framing,
not merely stopped running.

**Two bugs found by the live browser walkthrough, not by any static check — recorded here because
neither has a Python-testable surface, the same class of gap already named for the renderer's
safety properties.**

- **An unconditional `display: flex` on `.qmail-compose-overlay` overrode the browser's own
  `[hidden] { display: none }` default rule.** The overlay's `hidden` attribute was correctly set
  and correctly read by JS (`overlay.hidden === true`), but it rendered on screen anyway, because
  a same-specificity author rule beats the browser's own default stylesheet. No static-file test
  can see this — the DOM attribute was right, the JS was right, only the rendered pixels were
  wrong. The lesson for any future `hidden`-toggled element in this codebase: if its class also
  declares `display` unconditionally, add an explicit `.your-class[hidden] { display: none; }`
  rule, or the attribute does nothing.
- **A smart-To autocomplete's display string leaked into a stored field meant to hold the
  resolved value.** `closeCompose()`'s autosave originally read `toInput.value` directly — the
  input's own *display* text ("Page Target (pagetargetqm-…@qumanity.in)") — not the address the
  user actually selected. Every draft composed via the autocomplete (the common case, not an edge
  one) silently saved a `to_address` that `resolve_address()`'s exact-string match could never
  resolve; reopening and sending such a draft failed with "address not recognized" every time.
  Fixed by preferring the autocomplete's own stored `selectedAddress` variable over the input's
  display text. The general lesson: **any autocomplete field that writes a human-readable label
  into the same input it resolves an address from must save the resolved value, not the input's
  current text** — this pattern will recur anywhere else a "Name (address)" style autocomplete
  feeds a field that gets persisted and re-submitted later (a draft, a saved search, anything).
