# Registration email

Two emails exist today, both sent via **Resend's HTTPS API** (`email_core.py`):

1. A notification to the Admin when a new member registers (2026-10-18). Deliberately
   notification-only — the email never contains a real, usable Private ID (see
   `email_core.py`'s own module docstring for why), and no outbound email is ever sent to a
   member themselves.
2. An AI Support ticket reply to the visitor's own `guest_contact` address (2026-10-28), a
   separate function (`send_ticket_reply()`) with its own trust boundary.

See [ENVIRONMENT.md](ENVIRONMENT.md) for every variable's full row; this page explains the ones
specific to this feature in more detail.

**2026-11-08 correction: this page previously described an SMTP-based implementation
(`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM_ADDR`). That was accurate before
2026-10-20, but the code was switched to Resend's HTTP API that day** (see `email_core.py`'s
module docstring: "Railway's outbound SMTP is unreliable/blocked on some plans, Resend's API is
plain HTTPS") **and this page was never updated to match — it was stale for nearly three weeks.
None of the `SMTP_*` variables are read anywhere in the current codebase** (confirmed by grep
across every `.py` file). If a deployment's environment was configured by following the old
version of this page, it would have `SMTP_HOST` etc. set and **`RESEND_API_KEY` unset** — which
is a silent no-op by design (see below), so registration would appear to work with no error
anywhere, and no admin notification email would ever be sent. **If registration emails have been
missing in production, checking Railway's Variables tab for `RESEND_API_KEY` specifically (not
any `SMTP_*` name) is the first thing to check.**

## Configuration

| Variable | Role |
|---|---|
| `RESEND_API_KEY` | Set this to turn the feature on at all. Empty/unset is a **deliberate no-op** — `email_core._resend_config()` returns `None`, and `send_registration_notification()` does nothing and returns `False`. Registration itself never depends on this being set. Also logs `[email_core] EMAIL_CONFIG_MISSING var=RESEND_API_KEY` (added 2026-11-01) when this happens. |
| `QM_ADMIN_EMAIL` | The **destination** — who receives the registration notification. Must be set *in addition to* `RESEND_API_KEY`; `_resend_config()` returns `None` (no-op) if either one is missing. Logs `[email_core] EMAIL_CONFIG_MISSING var=QM_ADMIN_EMAIL` when this one specifically is missing. |
| `RESEND_FROM_EMAIL` | The `From:` address. Optional — defaults to `"Qumanity <founder@qumanity.in>"` if left empty. The sending domain (`qumanity.in` by default) must be a **verified domain** in the Resend dashboard, or Resend will reject the send. |

## How a failure actually surfaces

Diagnostic logging was substantially expanded on 2026-11-01
(`docs/production/email_qmail_diagnostic_audit.md` has the full detail). Current behavior:

- `RESEND_API_KEY` or `QM_ADMIN_EMAIL` unset → **silent no-op by design**, but now logged:
  `[email_core] EMAIL_CONFIG_MISSING var=<name>`. This is the "notifications are off" state, not
  a failure — `send_registration_notification()` returns `False`, nothing raises, and the
  `[email_core] registration notification failed for user_id=<id>: ...` line below is **never**
  printed in this case (there's no exception to catch).
- Resend is configured and the send is attempted → `[email_core] EMAIL_SEND_ATTEMPT
  operation=registration to=<masked>` is logged before the request.
- Successful send → `[email_core] EMAIL_SEND_SUCCESS operation=registration status=<code>
  resend_id=<id>`.
- Resend rejects the request (bad key, unverified domain, bad payload, rate limit — HTTP 4xx/5xx)
  → `[email_core] EMAIL_SEND_HTTP_ERROR operation=registration status=<code>
  response=<Resend's own JSON error body>`, **then** the exception propagates up and `app.py`'s
  registration route also logs:
  ```
  [email_core] registration notification failed for user_id=<id>: <exception message>
  ```
  (This second line only ever carries a generic summary, e.g. `HTTP Error 401: Unauthorized` —
  the `EMAIL_SEND_HTTP_ERROR` line just above it is the one with the actual Resend error detail.)
- A network/DNS/timeout failure (no HTTP response at all) → `[email_core]
  EMAIL_SEND_NETWORK_ERROR operation=registration error=<reason>`, then the same
  `registration notification failed` line as above.
- Either way, **registration itself never fails** because of this — the try/except exists
  specifically so a mail outage can never block a new member from signing up.

All of these lines land in **Railway's deploy/runtime logs** — there is nothing about them in the
Railway dashboard's own UI beyond the logs tab.
