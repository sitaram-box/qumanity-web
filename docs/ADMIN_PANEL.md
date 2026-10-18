# Admin Panel — design and operations reference (2026-10-18)

A design and operations reference, not a user manual. Built in commit `e4750e4`.

## 1. What it's for, and who can see it

A combined inbox over three things an admin needs to review: Citizen Reports, ID recovery
requests, and general member queries ("my karma looks wrong," "I can't find my account" — things
that are inherently admin-only from the start, with no location and no council escalation
ladder, so they don't fit `reports_core.py`'s model at all; see §4).

**Today**: the Founder only — `_is_admin_panel_user()` is identical to `_is_admin()` right now,
because village is the only level with a real elected council (the same documented gap as
`announcements_core.is_council_member()` / `reports_core.is_holder_council()`).

**Later**: when a real Q-Punch council role exists at any level, that's the one function that
changes (§2) — but even then, the panel's *global*, cross-location views (e.g.
`reports_core.list_all_open()`) stay Admin-only forever. They are never extended to a scoped
council member the way a single location's own report inbox already is, through
`is_holder_council()`.

## 2. `_is_admin_panel_user()` — the one swap point

```python
def _is_admin_panel_user() -> bool:
    return _is_admin()
```

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
  its own variable, deliberately separate from the existing `is_admin` variable, even though
  they're identical today (same reasoning as §2).
- **403 on direct fetch**: every one of the seven admin-panel routes
  (`/api/admin/panel/feed`, `/api/admin/queries/<id>`, `/api/admin/queries/<id>/reply`,
  `/api/admin/queries/<id>/close`, plus the four already covered by the member-export pass)
  checks `_is_admin_panel_user()` as its first statement and returns `403` if it fails — so
  hitting the API directly, bypassing the UI entirely, is refused the same way the DOM already
  hides it.

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
