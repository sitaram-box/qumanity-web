# Email + QMail Diagnostic Audit — Phase 1

**Date:** 2026-11-01
**Scope:** Diagnostic hardening only. No business logic, schema, or Railway/Resend configuration
was changed. See "Safety findings" at the end for the explicit zero-change confirmations this
phase requires.

---

## Email findings

### Functions inspected

`email_core.py` in full: `_resend_config()`, `_send()`, `is_email_like()`,
`send_ticket_reply()`, `mask_private_id()`, `send_registration_notification()`. Callers traced in
`app.py`: the registration route (`api_auth_register`, around line 4229) and the AI Support ticket
reply route (`api_admin_query_reply`, around line 2473).

### Environment-variable reads

| Variable | Where read | Behavior when missing |
|---|---|---|
| `RESEND_API_KEY` | `_resend_config()` (for registration email) AND independently in `send_ticket_reply()` and `_send()` | `_resend_config()` returns `None`; `send_ticket_reply()` returns `False`. Both are now logged (`EMAIL_CONFIG_MISSING` / `EMAIL_SEND_SKIPPED`) — **this was previously a fully silent no-op, no log line at all.** |
| `QM_ADMIN_EMAIL` | `_resend_config()` only | `_resend_config()` returns `None`. Now logged. Not read anywhere else — `send_ticket_reply()` doesn't need it, since its recipient is the ticket's own `guest_contact`. |
| `RESEND_FROM_EMAIL` | `_resend_config()` and (separately) `_send()`, each with the identical default `"Qumanity <founder@qumanity.in>"` | Never causes a skip — always has a usable default. Not independently diagnosed as "missing" since an absent value isn't an error here. |

All three are read **per call**, not once at startup — a value added to Railway and then
redeployed takes effect on the very next request, no caching involved.

### Resend endpoint and request construction

Confirmed against the expected integration:
- Endpoint: `https://api.resend.com/emails` (`RESEND_URL` constant) — correct.
- Method: `POST` — correct.
- Auth header: `Authorization: Bearer <RESEND_API_KEY>` — correct, built once per call.
- Content type: `application/json` — correct.
- Body: `{"from", "to": [...], "subject", "html"}` — all four required fields present on both
  send paths.
- Timeout: `REQUEST_TIMEOUT_SECONDS = 10`, passed to `urlopen()` — present (this was already
  correct before this pass).

### Every identified silent-return / silent-failure path (before this pass)

1. **`_resend_config()` returning `None`** — zero log output. A missing `RESEND_API_KEY` or
   `QM_ADMIN_EMAIL` and a fully successful send were indistinguishable in Railway logs; both
   produced nothing.
2. **`send_ticket_reply()`'s own early-return** — same: no log when skipped for either reason
   (missing key, or a `guest_contact` that isn't email-shaped).
3. **The caller's exception handler swallowing the real reason** — `app.py`'s
   `except Exception as e: print(f"[email_core] registration notification failed ... {e}")` only
   ever saw `HTTPError`'s generic `str()`, e.g. `"HTTP Error 401: Unauthorized"`. **The actual
   Resend JSON error body — the one fact that would say *why* (invalid key? unverified domain?
   bad payload? rate limited?) — was never read at all.** This is the single most important
   finding of this phase, and the primary reason the hypothesis in the work order ("the absence
   of the failure message may indicate the function silently returns") could not previously be
   distinguished from "the function ran, failed, and the real reason was discarded."
4. **No success logging existed at all.** Even a fully successful Resend acceptance produced no
   log line, so "nothing in the logs" was also consistent with total success — a third
   indistinguishable case.

### Diagnostic changes made

- `_resend_config()`: logs `EMAIL_CONFIG_MISSING var=<RESEND_API_KEY|QM_ADMIN_EMAIL>` (name only,
  never a value) on each missing-config path.
- `send_ticket_reply()`: logs `EMAIL_SEND_SKIPPED operation=ticket_reply
  reason=<RESEND_API_KEY_missing|guest_contact_not_email_shaped>` on its two skip paths.
- New `_send()` behavior, shared by both call sites (`send_registration_notification()` was
  refactored to call `_send()` instead of duplicating the same `urlopen()` block — same request,
  same headers, same timeout, now with the same logging):
  - `EMAIL_SEND_ATTEMPT operation=<registration|ticket_reply> to=<masked>` before the request.
  - `EMAIL_SEND_SUCCESS operation=... status=<code> resend_id=<id>` on a 2xx response.
  - `EMAIL_SEND_HTTP_ERROR operation=... status=<code> response=<exact Resend JSON body>` on any
    non-2xx (401, 403, 400, 429, 5xx all land here — this is the fix for finding #3 above).
  - `EMAIL_SEND_NETWORK_ERROR operation=... error=<reason>` on a connection/DNS/timeout failure
    with no HTTP response at all.
  - `EMAIL_SEND_UNEXPECTED_ERROR operation=... error_class=<name> error=<message>` as a catch-all
    for anything else.
  - Every exception is **re-raised after logging**, never swallowed — the return/raise contract
    both functions already documented is unchanged.
- A recipient address is logged masked (`_mask_addr`: `"a***@example.com"`), never in full.

### Test results

New `tests/test_email_core.py` (36 checks, all passing): missing `RESEND_API_KEY`, missing
`QM_ADMIN_EMAIL`, a successful send (verifies the masked recipient and the Resend id appear, and
the real address never does), HTTP 401/403/400/429/500 (verifies the exact Resend-style JSON body
reaches the log for each), a network error, an unexpected exception class, and both of
`send_ticket_reply()`'s skip paths plus its own success/HTTP-error path. All of Resend's HTTP
calls are mocked (`unittest.mock.patch` on `urllib.request.urlopen`) — **no real HTTP request was
made, and no real email was sent, by this test or by this phase's work.**

---

## QMail findings

### Activation route

`POST /api/qmail/activate` (`app.py`, decorated `@login_required @_board_error`) → calls
`qmail_core.activate(conn, user_id, username)` inside a `try/finally` that only closes the
connection. `@_board_error` converts `ValueError`/`PermissionError`/`LookupError` into a clean
4xx JSON response; **anything else falls through to Flask's default handler**, which returns an
HTML error page, not JSON.

**Confirmed frontend consequence of that gap**: `dash_extras.js`'s shared `api()` helper always
calls `r.json()`, even on a non-ok response (`fetch(url, opt).then(r => r.json().then(...))`). If
the server ever returns that HTML page instead of JSON, `r.json()` itself throws a `SyntaxError`
("Unexpected token '<' ... is not valid JSON"), which the activation UI then displays verbatim as
the error message — a real, reproducible failure mode where a database-level problem would show
up to a member as a cryptic parsing error rather than a clear message. This is now flagged in a
comment at the route; fixing it (e.g. a Flask-level JSON error handler, or hardening `_board_error`
to catch more exception types) is Phase 3 territory, not touched here.

### Activation function (`qmail_core.activate`)

Reviewed line by line. Sequence: already-activated check → username format validation
(`validate_username`) → cross-user username-uniqueness check → `account_id` lookup →
`full_address` generation → `UPDATE users SET qmail_username` → `INSERT INTO qmail_addresses` →
`commit()`. **The write/insert/commit block had no `try/except` at all before this pass** — any
database-level failure (a constraint violation, a locked database) would raise an unhandled
exception straight through `api_qmail_activate()`'s bare `try/finally`, hit none of
`@_board_error`'s three caught types, and surface as the HTML-error-page scenario above with zero
log trace of which stage failed.

### `qmail_addresses` schema (migrations/021_qmail.py)

- `UNIQUE INDEX idx_qmail_addresses_full ON qmail_addresses(full_address)` — the only uniqueness
  constraint that could reject an otherwise-valid insert; in practice unreachable through normal
  use since `full_address` is derived from `qmail_username` (already checked unique in Python
  first) plus `account_id`.
- `UNIQUE INDEX idx_users_qmail_username ON users(qmail_username)` plus a `CHECK` on length
  (8–15 chars) — a DB-level backstop behind the Python-level `validate_username()`/uniqueness
  check, not the primary gate.
- No foreign-key `NOT NULL` surprises, no trigger, no default that could silently produce an
  invalid row.

### Address-generation rules (`[username]-[account_id]@qumanity.in`)

`build_full_address()` matches the documented convention exactly. `username` comes from
`validate_username()` (lowercased, 8–15 chars, `[a-z0-9._-]` only) — code matches docs.
`account_id` is read fresh from `users.account_id` at activation time, so it's always current.
Account-ID-change synchronization (`social_core.regenerate_account_id()` minting a new
`qmail_addresses` row and marking the old one `is_current=0` with a 30-day `forward_until`) is a
**separate code path**, not touched or re-verified in this pass beyond confirming
`tests/test_qmail.py`'s existing Section 3 (compose resolution across current/inside-window/
past-window addresses) still passes unchanged.

### `/qmail` route (`qmail_page()`)

Simple and correct: not logged in → redirect to `/login`; logged in but
`users.qmail_username IS NULL` → redirect to `/dashboard` (where the activation UI lives);
otherwise renders `qmail.html`. **No log line existed for either redirect branch before this
pass** — a member who believed they'd activated (but whose write had silently failed) would land
back on the dashboard with zero trace of why, in the browser or in Railway logs.

### Diagnostic changes made

- `qmail_core.activate()`: one `print("[qmail] ...")` per stage —
  `QMAIL_ACTIVATION_FUNCTION_ENTERED`, the two `QMAIL_ACTIVATION_FAILED reason=...` branches
  (already-activated / username-taken), `QMAIL_ADDRESS_GENERATION_STARTED`/`_COMPLETED`,
  `QMAIL_ADDRESS_INSERT_ATTEMPT`, `QMAIL_DATABASE_COMMIT_SUCCESS`, `QMAIL_ACTIVATION_COMPLETED`.
  The write/insert/commit block is now wrapped in `try/except Exception`, which logs
  `QMAIL_DATABASE_INSERT_FAILED error_class=... error=...` and **re-raises the original exception
  unchanged** — no business logic altered, every existing raise/return path is identical to
  before.
- `app.py`'s `api_qmail_activate()`: logs `QMAIL_ACTIVATION_REQUEST_RECEIVED user_id=...` on
  entry, plus a comment documenting the `_board_error`/frontend-JSON-parsing gap found above.
- `app.py`'s `qmail_page()`: logs `QMAIL_PAGE_REDIRECT user_id=... reason=<no_such_user|
  not_activated> target=<login|dashboard>` on both redirect branches.
- Every log line uses the internal numeric `user_id` only — never a Private ID, PIN, or session
  token.

### Test results

- **All pre-existing QMail tests still pass unchanged**: `test_qmail.py` (23 checks),
  `test_qmail_attachments.py`, `test_qmail_drafts.py`, `test_qmail_format_extraction.py`,
  `test_qmail_page.py` — confirms none of this phase's logging changed any observable behavior.
- New `tests/test_qmail_activation_diagnostics.py` (two scenarios the existing suite didn't
  cover, plus a log-order check):
  - An **unauthenticated** activation POST is rejected with a redirect, not a 201 or a crash.
  - The **same user activating twice** is rejected (400, "already activated"), the original
    username from the first attempt is preserved, and no second `qmail_addresses` row is created.
  - A real, successful activation run produces all seven expected log events, in the documented
    order, each carrying the correct `user_id` — confirms the new logging is actually wired up,
    not just present in the source.
- **Not tested**: a forced `QMAIL_DATABASE_INSERT_FAILED` (e.g. artificially colliding on the
  `full_address` unique index). Verified by code review instead — the `try/except` wraps exactly
  the write+insert+commit block and re-raises unchanged, so this was judged not to need a second,
  more fragile grey-box test for a Phase-1 diagnostic pass. Worth adding in Phase 3 if evidence
  points at a database-level failure.

---

## Safety findings

**Files modified:** `email_core.py`, `app.py`, `qmail_core.py`, plus two new test files
(`tests/test_email_core.py`, `tests/test_qmail_activation_diagnostics.py`) and this report.

**Files NOT modified:** `qmail_core.py`'s address-generation rules, uniqueness logic, or return
contracts; `app.py`'s registration flow beyond the two `print()` additions already documented
above; any migration; `social_core.py`; `board_core.py`; any Jinja template; any JavaScript file.

- **Database changes: zero.** No migration was run as part of this phase beyond what was already
  pending before it started (see `tools/run_migrations.py` output in the new test runs — those
  are the project's own existing migrations replaying against each test's own throwaway tempfile
  database, not production).
- **Production configuration changes: zero.** No Railway environment variable was read, written,
  or even looked up outside of this local audit (`os.environ.get(...)` calls run against whatever
  environment executes the code — in all testing here, a local/test process).
- **Existing business-logic changes: zero.** Every `raise`, every `return`, every condition that
  previously decided whether an email sends or an activation succeeds is byte-for-byte unchanged.
  The only new control flow is the `try/except` added around `qmail_core.activate()`'s
  write/insert/commit block, which re-raises immediately after logging — functionally a no-op for
  every caller.
- **Test email sends: zero.** Every Resend HTTP call in the new tests is mocked
  (`unittest.mock.patch` on `urllib.request.urlopen`); nothing in this phase made a real network
  request to Resend or sent a real email to a real address.
- **Secrets in logs: zero.** `RESEND_API_KEY`, the `Authorization` header, PINs, Private IDs, and
  session tokens are never printed anywhere in this diff. Recipient addresses are masked
  (`a***@example.com`); only Resend's own response body (status codes and its error JSON) is
  logged verbatim, which is itself free of secrets by construction (Resend doesn't echo the
  request's Authorization header back in its response).

---

## Full diffs

See the repository's own `git diff -- email_core.py app.py qmail_core.py
tests/test_email_core.py tests/test_qmail_activation_diagnostics.py` for the complete, exact
changes (new files show as full adds). Summary: `email_core.py` +104/-33, `app.py` +13/-0,
`qmail_core.py` +33/-9.
