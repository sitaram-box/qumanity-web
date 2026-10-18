# Registration email

The only email Qumanity sends today: a notification to the Admin when a new member registers
(`email_core.py`, 2026-10-18). It is deliberately notification-only — the email never contains a
real, usable Private ID (see `email_core.py`'s own module docstring for why), and no outbound
email is ever sent to a member themselves. See [ENVIRONMENT.md](ENVIRONMENT.md) for every
variable's full row; this page explains the ones specific to this feature in more detail.

## Configuration

| Variable | Role |
|---|---|
| `SMTP_HOST` | Set this to turn the feature on at all. Empty/unset is a **deliberate no-op** — `email_core._smtp_config()` returns `None`, and `send_registration_notification()` does nothing and returns `False`. Registration itself never depends on this being set. |
| `SMTP_PORT` | Defaults to `587`. See "STARTTLS, not implicit SSL" below — this default matters, don't change it without also changing the code. |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP auth credentials. If `SMTP_USER` is empty, the code skips `server.login(...)` entirely (some providers/relays don't need it). |
| `SMTP_FROM_ADDR` | The `From:` address. Falls back to `SMTP_USER` if left empty. |
| `QM_ADMIN_EMAIL` | The **destination** — who receives the notification. Must be set *in addition to* `SMTP_HOST`; `_smtp_config()` returns `None` (no-op) if either one is missing, not just `SMTP_HOST` alone. |

## STARTTLS, not implicit SSL — a real failure mode to know about

`email_core.py` hardcodes `smtplib.SMTP(...)` followed by `server.starttls()` — it never uses
`smtplib.SMTP_SSL`. This matches `SMTP_PORT`'s default of `587` (the standard STARTTLS port).

**If the SMTP provider is configured for implicit SSL instead (typically port `465`), the send
will fail at the `starttls()` call.** This is not a hypothetical — some providers default their
own setup instructions to port 465. If registration notifications never arrive despite every
variable above being set, check this first.

## How a failure actually surfaces

- `SMTP_HOST` unset → **silent, by design**. No log line, no error — this is the intentional
  "notifications are off" state, not a failure.
- SMTP configured but the send fails for any reason (wrong port as above, auth failure, timeout,
  provider outage) → **caught and logged, not silent**. `app.py`'s registration route wraps the
  call in `try/except Exception` and prints:
  ```
  [email_core] registration notification failed for user_id=<id>: <exception message>
  ```
  This line lands in **Railway's deploy/runtime logs** — there is nothing about it in the Railway
  dashboard's own UI beyond the logs tab. A missing notification with no obvious cause means:
  check the logs for this exact prefix before assuming the variables are wrong.
- Either way, **registration itself never fails** because of this — the try/except exists
  specifically so a mail outage can never block a new member from signing up.
