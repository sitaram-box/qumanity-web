# Qumanity: Family Tree Evidence

**Supplement to the DPG Standard Indicator 5 (Documentation) and Indicator 1 (SDG Relevance,
§5.3's table of what runs on the website) evidence.** Not itself a DPG Standard indicator — a
factual evidence section the main 01-09 pack did not previously cover.

> **DPG Evidence Refresh — 2026-11-01.** Internal correction pass, not a DPGA resubmission. This
> is a new addition, not a revision of a previously submitted claim.

> **Line-reference re-verification — 2026-11-02.** Every `family_core.py`/`app.py` line citation in
> this document was re-checked against the current repository (not re-stated from memory). Every
> citation from `_sync_family_membership()` onward had drifted +93 lines (the Option B backfill
> code, `family_core.py:1513-1607`, was inserted between this document's original citations and
> those functions after this document was first written) and has been corrected below. One cascade
> cross-reference (`family_core.py:1543`) was pointing at what is now the
> `GRANDPARENT_BACKFILL_MAX_GENERATIONS` constant, not `_cascade_relatives_after_link()` — corrected
> to `family_core.py:1608`. A handful of `app.py` family-route citations had drifted by a separate,
> unrelated 2 lines and were also corrected. No claim about behavior, schema, or test counts changed
> — only the line numbers pointing at where that behavior lives.

## What this covers

Qumanity's Family Tree subsystem: schema, relationship model, membership rules, the ambiguous-
unit-selection rule, the direct-roster cascade, and the Profile Card. Every claim below cites
source file:line evidence from the current repository and real test evidence, re-verified
2026-11-01 — distinguished explicitly from operational (production) evidence, which this pass does
not establish for any of it (all testing below ran against local throwaway SQLite databases,
never the production database).

## Schema

Built across two migrations (`migrations/026_family_tree.py`, `migrations/027_family_nuclear_nodes.py`),
schema owned by `family_core.ensure_tables()` (`family_core.py:161`):

- `family_nodes` (`family_core.py:72-86`) — a person reference: `claimed_user_id` (nullable,
  globally unique via `idx_family_nodes_claimed_user`, so one real Qumanity account can occupy
  exactly one node across the whole tree), `display_name`/`gender`/`dob_approx` (authoritative only
  while unclaimed — once claimed, `users.name`/`users.dob` win live, never a stale snapshot; see
  `_node_display_name()`/`_node_dob()`, `family_core.py:221-239`), `status` (`empty`|`claimed`),
  `is_deceased`, and `approximate_age` (added 2026-11-01 for the Unclaimed Profile Card editor —
  an integer year count, deliberately not a fabricated date of birth; only meaningful for an
  unclaimed node, since a claimed one's age always comes live from `users.dob`).
- `family_groups` (`family_core.py:114-126`) — a marriage/nuclear-family unit, not a generic
  container. `husband_node_id`/`wife_node_id` name its two founders (either may still be an empty,
  unclaimed placeholder); `husband_parent_group_id`/`wife_parent_group_id` each point at a
  founder's own birth unit when the tree already knows it — a unit can have 0, 1, or 2 known
  parent units. `marriage_status` (`active`|`separated`|`dissolved`) has no mutator route built yet
  (default `active` only). `kind` is a historical column (`lineage`|`marital` on old rows; always
  `unit` going forward under the current, 2026-10-20 Nuclear Family Node model).
- `family_group_nodes` (`family_core.py:148-154`) — a unit's unmarried child placeholders/claimed
  members (composite PK `group_id, node_id`). A married child is never tracked here — they get
  their OWN `family_groups` row instead, linked back via `husband_parent_group_id`/
  `wife_parent_group_id`.
- `family_group_members` (`family_core.py:129-137`) — a unit's own chat roster, computed live from
  the tree shape and marital status (`status`: `approved`|`left`|`pending`; `is_admin`), not a
  one-off grant frozen at creation time.
- `family_parent_links` (`family_core.py:88-98`) — raw parent/child genealogical facts, `UNIQUE
  (parent_node_id, child_node_id)`, independent of which unit currently organizes the tree.
- `family_spouse_links` (`family_core.py:102-112`) — **deprecated**; no new code writes to it
  (confirmed: `grep -n "family_spouse_links" family_core.py` finds only the `SCHEMA` definition
  and this module's own historical-data comment, no `INSERT`/`UPDATE` against it anywhere). A
  marriage today is the unit itself (`family_groups.husband_node_id`/`wife_node_id`);
  `tree_for_group()` synthesizes an equivalent spouse-link entry from a unit's own founder pair at
  read time, purely so the (unchanged) D3 frontend's spouse-connector still renders.
- `people_requests.target_node_id` (an additive column on `social_core.py`'s own table, lazily
  `ALTER`ed in by `ensure_tables()`, `family_core.py:207-209`) — records which empty founder slot a
  self-service join request means to claim, since `family_spouse_links` no longer exists as a
  source of truth to derive that intent from.

Source evidence: `family_core.py`'s own module docstring (lines 1-62) and `SCHEMA` constant (lines
71-155).

## Founder, spouse, and parent-group relationships

A unit's two founders are its `husband_node_id`/`wife_node_id`. Marrying into an existing unit's
empty founder slot is a declared mutual fact, not a third-party-approved join (`marry_timeline()`,
`family_core.py:1842`, calling `_claim_founder_slot()` directly — the 2026-10-26 founder's ruling,
documented in this module's own docstring, lines 50-61). Admin status is granted the moment a
founder slot is filled or claimed (`_grant_founder_admin_if_applicable`, `family_core.py:442`);
the unit's **creator** is also always separately granted `is_admin=1` at creation
(`create_group()`, `family_core.py:740-745`) — additive to, not a replacement for, founder admin,
and practically necessary the moment a unit is founded with one or both slots still unclaimed
placeholders (otherwise nobody could rename a typo'd placeholder or link it once that person signs
up). `my_family_groups()`'s `role` field (`family_core.py:2017`, `'founder'|'admin'|'member'`) is
the honest, user-facing distinction between a true founder and a plain creator-admin — `is_admin`
alone cannot tell them apart, which previously rendered a plain child as "Admin" in their own
parents' unit just because they happened to create it.

## Claimed vs. placeholder identities

`family_nodes.claimed_user_id` is globally unique — one real Qumanity account can occupy exactly
one node across the whole tree. An admin linking a placeholder to a real person who already has
their own node elsewhere re-points every reference onto that existing node rather than creating a
duplicate (`link_node_to_user()`, `family_core.py:520`, specifically lines 559-575's
already-has-a-self-node branch). This is a 2026-10-25 change: before it, such a link was refused
outright with "already has their own profile node elsewhere"; now `_swap_node_references()`
(`family_core.py:467`) repoints every table that could reference the old placeholder id onto the
real node instead.

## Group creation

`create_group()` (`family_core.py:708-762`) is the low-level mechanics: inserts the unit row,
grants `family_group_nodes` tree visibility to every founder/member node, and grants
`family_group_members` chat access (`is_admin=1` for the two founders) for whichever of them is
*currently* a real, claimed user — an unclaimed founder slot is granted admin automatically only
once `link_node_to_user()` later claims it. `_find_or_create_couple_group()`
(`family_core.py:765-796`) is the higher-level entry point `activate_timeline()`/`marry_timeline()`
both call: it finds an existing unit already founded by the exact pair, or by *either* side alone
(e.g. a sibling who activated first), or creates a new one. If both sides independently match two
*different* existing units, the husband's side wins — a documented, explicit tie-break for a
genuine data conflict ("a genuine data conflict that would need a human to resolve properly
anyway, not a silent guess dressed up as correct" — `family_core.py:771-773`), not a silently
invented resolution.

`activate_timeline()` (`family_core.py:1808-1934`, re-verified 2026-11-02 -- shifted +93 lines
since this document was first written, by the Option B backfill code added between it and the
membership-state-machine functions above) is the signed-in user's own onboarding wizard:
creates/links their own self-node, finds-or-creates their parents' unit (if named) and their own
future unit (if they have children), and calls `_sync_family_membership()` at the end.
`marry_timeline()` (`family_core.py:1935-2081`) is the marriage flow: finds-or-creates the couple's
own unit, attaches any declared children (`_attach_children_to_group()`, `family_core.py:1815`),
and — per the 2026-10-26 ruling above — claims either spouse's founder slot directly and
synchronously rather than queuing an approval request.

## Membership state machine

`family_group_members.status` is one of `approved`|`left`|`pending`, never a hard delete:

- **Self-service join** — `request_join_group()` (`family_core.py:857-914`) queues a
  `people_requests` row (`kind='family_group_join'`) for the unit's *founding creator* specifically
  to approve (a documented simplification, not every current co-admin). Made idempotent on
  2026-11-01 (see `docs/family_tree/PHASE_1_BACKEND_REPAIR_REPORT.md`): a repeat call returns the
  existing pending/approved state via its return value instead of raising, so a retried
  `activate_timeline()`/`marry_timeline()` call that incidentally re-hits an already-pending match
  doesn't abort the caller's entire, otherwise-unrelated operation. A user whose status is `left`
  cannot self-request back in (the 2026-10-26 rejoin rule) — only an admin-initiated
  `invite_to_group()` can bring them back.
- **Admin-initiated invite** — `invite_to_group()` (`family_core.py:917-962`) requires
  `_is_admin_of_group()`; queues a `people_requests` row (`kind='family_group_invite')`) the target
  must separately accept (`social_core.decide_request()`'s matching branch, confirmed by
  `tests/test_group_members.py`'s own docstring). A target who previously left/was removed has
  their row moved from `left` to `pending` at invite time (a visibility marker only —
  `add_member()`'s own accept-time upsert already overwrites any prior status with `approved`).
- **Accept** — `add_member()` (`family_core.py:815-854`) is the single approval point for both
  join and invite flows. When the acceptance is a founder-slot claim (`target_node_id` set), it
  calls `_claim_founder_slot()` and returns `_cascade_relatives_after_link()`'s own auditable dict
  (see below) instead of the plain-member `None`.
- **Leave** — `leave_group(conn, user_id, group_id)` (`family_core.py:1015-1060`) sets `status='left'`
  under three real-world exit rules, keyed off `_classify_membership()` (`family_core.py:1002-1012`,
  `'founder'|'birth'|'other'`): a **founder** can never leave (it's the unit their marriage
  literally founded); a **birth**-unit member is blocked only if their own parent or child is still
  an active member of that *same* unit (which is why an unmarried person can never leave their
  birth unit at all — their parents are definitionally active there); anything else (an in-laws
  unit, a grandparent unit) is always allowed, with no check — the explicit 2026-10-26 fix for a
  real bug where this check used to be unscoped and could trap a wife in her in-laws' unit just
  because her own child was later auto-joined there too.
- **Admin removal** — `remove_member()` (`family_core.py:1063-1084`) is the admin-initiated
  counterpart: any admin of the unit (not scoped to in-laws units only) may set a non-founder
  target's status to `left`; a founder can never be removed (removing one would be dissolving the
  marriage, out of scope here).

## Family Admin responsibilities and succession across parental lineages

`_is_admin_of_group()` (`family_core.py:302-329`) is the single authority check every mutating
route funnels through. A unit's admin is a living founder, or (the same check, generalized) any
approved `is_admin=1` membership row — covering the separate creator-admin grant above. Once a unit
goes **dormant** (`_group_is_dormant()`, `family_core.py:274-285` — neither founder slot is a
currently-filled, alive node), authority over the unit's own chat does not move (a founder's own
admin row is historical fact), but authority to act on the unit's **child units** (rename a node,
mark someone deceased, link a placeholder) passes up through **either** parent-group chain
recursively, with **no patrilineal/matrilineal default** — any reachable active ancestor on either
the husband's or the wife's side is an equally valid authority (`family_core.py:321-329`,
`_visited` guarding a pathological cycle). `_is_admin_of_node_group()`
(`family_core.py:332-338`) is the shared per-node variant `mark_deceased()`/`rename_node()`/
`link_node_to_user()` all use — a node can belong to more than one unit, and any one of them being
admin-accessible is sufficient.

## The actual distinction between family units and people/nodes

A `family_nodes` row is always one person — real (claimed) or a placeholder (empty). A
`family_groups` row is always one marriage/nuclear unit, never a generic multi-person container
and never itself a person. A person can appear as a founder of one unit, an unmarried member of
their birth unit, and (if the architecture permits — see below) a founder of a second unit, all at
once; a unit always has exactly the fields above (two founder slots, up to two parent-unit links),
never a variable-sized "family" grouping of unrelated people.

## Current behavior for multiple family units and ambiguous group selection

A single node/person **can** legitimately be a founder of more than one active unit at once — a
real, architecturally-permitted state discovered and documented directly in source while testing
this feature (`family_core.py:2460-2470`): `link_node_to_user()` can re-point an unrelated viewer's
own placeholder founder slot onto a real person without ever unifying it with that person's
pre-existing marital unit elsewhere (a "deliberately separate, harder decision," per that
function's own docstring, lines 544-549), so the same node can end up as `husband_node_id`/
`wife_node_id` of two different `family_groups` rows that were never reconciled into one marriage.

`add_child_to_node()` (`family_core.py:2546-2582`) is where this ambiguity surfaces concretely and
is handled explicitly, never guessed: if the target person founds exactly one active unit, the
optional `group_id` parameter may be omitted and the call still succeeds unambiguously. If they
found **more than one**, the caller (Phase 2's Profile Card, which always has a definite unit
already in view — the neighborhood the card was opened from) **must** pass `group_id` explicitly;
omitting it in that case raises `ValueError("This person has more than one family unit on record —
specify which one with group_id")` rather than silently picking one (e.g. "whichever was created
most recently"). The route layer threads this through directly: `POST /api/family/person/<node_id>
/child` accepts an optional `group_id` in its JSON body (`app.py:2114-2127`).

The same multi-unit reality is also why `_cascade_relatives_after_link()` (below) explicitly
*skips*, rather than guesses, the founder-side cascade when a linked person founds more than one
active unit — the two places in this codebase that must disambiguate a multi-unit person both
refuse to guess, by the same underlying design decision.

A user's own list of units they belong to (`my_family_groups()`, `family_core.py:2082-2112`,
surfaced via `GET /api/family/status`, `app.py:1887-1906`) is deliberately narrower than "every
unit this node appears in" — it excludes dormant units entirely (they still render in the D3 tree,
faded, as root ancestors, just not as a chat to open) and tags each row with `is_founder` and the
honest `role` label so the frontend can distinguish "My Family" (a unit the viewer founded) from
"Joined Family" (one they were approved into, e.g. their parents' unit).

## Direct-roster cascade (Option A, non-recursive)

When an admin links an empty placeholder to a real person who already has their own pre-existing
node, two helpers (added 2026-11, `family_core.py:1513` and `family_core.py:1608`) cascade that
person's own directly-represented family into active membership, instead of requiring each member
to be individually re-found:

- `_direct_roster_of_group(conn, group_id)` — the claimed user_ids directly represented in one
  `family_groups` row: its two founders and every `family_group_nodes` entry. No further
  traversal.
- `_cascade_relatives_after_link(conn, user_id)` — resolves up to two source groups for the linked
  person (the unit they found, if unambiguous; their birth unit, if known) and re-syncs every
  claimed member of each, via the pre-existing `_sync_family_membership()` (`family_core.py:1712`).
  Explicitly skips the founder-side cascade (never guesses) when the person founds more than one
  active marital unit at once — see the multi-unit section above.

**Option B (grandparent-group backfill) — implemented AND committed 2026-11-02** (commit `0a8ab5b`,
"feat: OSM proximity, grandparent backfill, and location tooling" — re-verified this pass via
`git status --short family_core.py tests/test_family_tree_cascade.py`, both clean/unmodified
relative to `HEAD`; this corrects this document's own prior claim that it remained uncommitted,
which was already stale by the time of that same-day commit). The owner approved it after the
privacy/consent review this section
previously said was pending; the review's own finding (recorded in
`_backfill_parent_group_links()`'s own docstring, `family_core.py`) is that backfilling a link
does not grant any new ad-hoc membership beyond the same bounded direct-roster rule every other
cascade call already uses — what it DOES change is `_is_admin_of_group()`'s own dormant-ancestor
succession reach, which should keep being watched as the tree grows deeper. Mechanics:
`_backfill_parent_group_links(conn, start_group_id, max_additional_hops, _visited)`
(`family_core.py`, added 2026-11-02) does a breadth-first walk, strictly capped at
`GRANDPARENT_BACKFILL_MAX_GENERATIONS = 2` hops above each of `_cascade_relatives_after_link()`'s
existing source groups — discovering and writing `husband_parent_group_id`/`wife_parent_group_id`
wherever currently `NULL` and a real link can be established via `_find_parents_group_for_node()`,
and cascading each newly-reached ancestor group's own direct roster (same Option A rule, just
applied one and two hops further up). A third hop (great-grandparent) is never attempted. Cycle-safe
via a shared `_visited` set; idempotent (re-running makes no further writes); still never recurses
into a linked child's own further-married *descendant* units — only the parent chain, and still
never touches `family_spouse_links`. Tests: 21 new checks in `tests/test_family_tree_cascade.py`
(now 115 total, up from 94), covering discovery, the 3rd-generation exclusion, direct-roster-only
cascading, idempotency, a manufactured cycle, and a missing-parent-group case.

## Profile Card and relationship functionality

`_relationship_label()` (`family_core.py:2141`) and `cascade_for_node()` (`family_core.py:2444`)
compute a viewer-relative relationship label (Father/Mother/Grandfather/Uncle/Cousin/Nephew, etc.)
and the Profile Card's neighborhood view, entirely read-only, derived from the graph — never
touched by the direct-roster cascade above. `neighborhood_for_group()`/`tree_for_group()`
(`family_core.py:2309`, `2364`) render one unit's own immediate surroundings at a time rather than
a single multi-generation hierarchy, since a married couple almost always has two separate,
unrelated ancestries meeting only at that one marriage — not representable as one `d3.tree()`.

## Relevant routes

Every `/api/family...` route is `@login_required`; `app.py:1887-2214`:

| Route | Core function |
|---|---|
| `GET /api/family/status` | `my_family_groups`, `linked_with_parents` |
| `GET /api/family/suggest` | `search_suggestions` |
| `POST /api/family/activate` | `activate_timeline` |
| `POST /api/family/marry` | `marry_timeline` |
| `POST /api/family/node/<id>/mark-deceased` | `mark_deceased` |
| `POST /api/family/node/<id>/name` | `rename_node` |
| `POST /api/family/node/<id>/details` | `update_node_details` (Phase 2, combined name/gender/age save) |
| `POST /api/family/node/<id>/link` | `link_node_to_user` (response carries the additive `cascade` field) |
| `POST /api/family/node/<group_id>/add-parents` | `add_parents_to_group` |
| `POST /api/family/node/<group_id>/add-child` | `add_child_to_group` |
| `GET /api/family-groups/<group_id>/tree` | `tree_for_group` |
| `GET /api/family/node/<group_id>/neighborhood` | `neighborhood_for_group` (route path says "node"; `group_id` here is a `family_groups.id`, not a `family_nodes.id`) |
| `POST /api/family-groups/<group_id>/join-request` | `request_join_group` |
| `GET /api/family/person/<node_id>/cascade` | `cascade_for_node` (Phase 2, person-centric) |
| `POST /api/family/person/<node_id>/sibling` | `add_sibling_to_node` |
| `POST /api/family/person/<node_id>/child` | `add_child_to_node` (optional `group_id` — see ambiguity section above) |
| `POST /api/family/person/<node_id>/spouse` | `add_spouse_to_node` |
| `POST /api/family-groups/<group_id>/leave` | `leave_group` |
| `GET /api/family-groups/<group_id>/members` | `group_members_for` |
| `POST /api/family-groups/<group_id>/invite` | `invite_to_group` |
| `GET,POST /api/family-groups/<group_id>/messages` | `family_messages`, `post_family_message` |
| `POST /api/family-groups/<group_id>/remove-member` | `remove_member` |

## Frontend entry points

- `static/js/family.js` (713 lines) — the onboarding/activation wizard: `GET /api/family/status`
  (line 88), `GET /api/family/suggest` (line 519, name search while filling the wizard),
  `POST /api/family/activate` (line 668), `POST /api/family/marry` (line 681).
- `static/js/family_tree.js` (894 lines) — the D3 tree view and its Profile Card: the unit
  neighborhood fetch (line 353), leave-group (line 385), unit chat read/send (lines 428, 463),
  link-to-user (line 672) immediately followed by a cascade refetch (line 674), the combined
  details-save (line 701), the generic sibling/child/spouse Profile Card actions (lines 761-764,
  dispatched through a shared `cfg.route` table), add-parents (line 816), and the Members
  modal/invite-by-Public-ID flow (lines 865, 882).
- Both are loaded from `templates/dashboard.html`.

## The actual authorization and validation rules

Every mutation checks `_is_admin_of_group()`/`_is_admin_of_node_group()`, never session identity
alone, and every lookup returns a scoped 404 (never a 403 that would confirm a group's existence
to a non-member) — e.g. `group_members_for()` returns `None` for a non-approved viewer, matched by
`api_family_group_members` returning `{"error": "Family Group not found"}, 404`. `rename_node()`
refuses outright on a *claimed* node (`family_core.py:362-363`) rather than silently no-op'ing,
since a claimed node's visible name always comes live from `users.name`. `invite_to_group()`
rejects inviting yourself, an already-approved member, or a duplicate pending invite
(`family_core.py:935-953`). `leave_group()`/`remove_member()` enforce the founder/birth-unit rules
above purely in Python against `_classify_membership()`'s result, never relying on a database
constraint to catch it.

## Relevant test suites

| Suite | What it verifies |
|---|---|
| `tests/test_family_tree.py` (211 checks, re-run 2026-11-01) | Core unit creation, activation/marriage flows, join/invite/accept, the three leave-group exit rules, founder-removal rejection, rejoin-after-removal going through `pending` not straight to `approved` |
| `tests/test_family_tree_cascade.py` (115 checks, re-run 2026-11-02) | The direct-roster cascade: 3-claimed-direct-member fixture, idempotency, the multi-unit founder-side skip; plus (new, 2026-11-02) Option B's grandparent-group backfill: 4-generation discovery, the 3rd-generation exclusion, a manufactured cycle, a missing-parent-group case |
| `tests/test_group_members.py` | Partially relevant: covers `family_core.invite_to_group()`/`group_members_for()`'s admin-only invite flow and `social_core.decide_request()`'s matching `family_group_invite` accept branch — alongside unrelated coverage of `social_core.py`'s own personal (Friends/Business/Custom) groups, which are a separate subsystem, not part of the Family Tree |

## Evidence summary

| | Status |
|---|---|
| Source evidence | `family_core.py` (2,540 lines), `migrations/026_family_tree.py`, `migrations/027_family_nuclear_nodes.py`, `app.py` (route block, lines 1885-2215), `static/js/family.js`, `static/js/family_tree.js` |
| Test evidence | 211 + 115 = 326 directly-dedicated checks (re-run 2026-11-02), plus partial coverage from `tests/test_group_members.py` |
| Operational evidence | None independently verified this pass — all testing above ran against local throwaway databases; production deployment behavior of this subsystem has not been checked |
| Remaining limitations | A married child's own further-married children are never swept into a cascade (Option B's own cap is strictly on the ancestor/parent chain, not descendants); a multi-unit founder always requires an explicit `group_id` from the caller for the one operation (`add_child_to_node`) that needs it today. Option B is implemented **and committed** (commit `0a8ab5b`, corrected this pass from this document's own prior stale claim — see `docs/MASTER_STATUS.md`) |
