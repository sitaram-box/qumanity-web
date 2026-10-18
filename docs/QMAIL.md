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

All seven routes are `@login_required`; none is public.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/qmail/activate` | `{"username"}` → validates, checks global uniqueness, writes `users.qmail_username`, mints the first `qmail_addresses` row. |
| POST | `/api/qmail/compose` | `{"to", "subject", "body"}` — `to` is re-resolved server-side via `qmail_core.resolve_address`, never trusted from the client. |
| GET | `/api/qmail/inbox` | This member's received messages. |
| GET | `/api/qmail/sent` | This member's sent messages. |
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

- No attachments.
- No message threading.
- No external delivery of any kind (§1) — no inbound receiving, no outbound to real mail
  providers.
- No spam filtering (meaningless for an entirely internal system today, but worth naming
  explicitly as a gap the moment real external delivery is ever considered).
- No read receipts beyond the plain `read_at` timestamp column already in `qmail_messages`
  (nothing currently sets it — marking a message read isn't wired up yet).
- No full mailbox UI (compose/inbox/sent screens) — only the activation card and the
  address-change banner shipped with the backend. The mailbox UI was explicitly deferred as its
  own, separate pass rather than folded into this one.

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
