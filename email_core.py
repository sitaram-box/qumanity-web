"""Admin email notifications (2026-10-18, Resend API since 2026-10-20) + AI Support ticket-reply
notifications (2026-10-28). The ORIGINAL email this module sent: a notification to the Admin when
a new member registers. It is deliberately notification-only -- it never puts a real, usable
Private ID in an email body. The codebase's own existing design already treats a Private ID
reveal as something rare, individually justified and logged (recovery_core.reveal_private_code,
"the one place the system will show someone ELSE's 9-digit Private ID... every reveal is
logged"); mailing every new member's real ID into an inbox outside this project's control would
be the opposite of that. The email shows a masked ID and links the Admin to the authenticated
admin export tool (api_admin_users_export in app.py), where the real lookup happens and is itself
logged (migrations/019_admin_export_log.py).

send_ticket_reply() (2026-10-28) is a SEPARATE function, not a generalization of
send_registration_notification() -- that one's destination is deliberately hardcoded to the
Admin's own inbox (QM_ADMIN_EMAIL) and was never meant to take an arbitrary `to_addr`; sending TO
an anonymous AI Support ticket's own guest_contact is a different trust boundary (an outbound
email to whatever address a visitor typed, not to the one address this deploy's operator
configured), so it gets its own function with its own `to_addr` parameter rather than widening the
existing one's contract.

Sent via SendGrid's HTTPS API (https://api.sendgrid.com/v3/mail/send) using the standard
library's urllib.request -- no new dependency. 2026-11-11: this is the third transport this
module has used. It started on Resend's HTTPS API, which Resend itself rejected from Railway's
egress IP with a 403 (an IP-level restriction on Resend's side). It then moved to Resend's SMTP
relay, which failed differently: a TimeoutError connecting to port 587, because Railway's own
network firewall blocks outbound SMTP entirely, regardless of provider. Both failures are real and
independent, which is why SendGrid's HTTPS API (port 443, the same port every other outbound call
this app makes already uses) was chosen over a third SMTP attempt. If SendGrid isn't configured
(no SENDGRID_API_KEY or no QM_ADMIN_EMAIL), send_registration_notification() is a silent no-op --
registration must never depend on email being set up. If it IS configured but the send fails (bad
key, SendGrid outage, timeout), this function raises normally; app.py's api_auth_register is
responsible for catching that and logging it without failing the registration request itself.
"""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request

REQUEST_TIMEOUT_SECONDS = 10
SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
LOGIN_URL = "https://qumanity.in/login"


def _email_config() -> dict | None:
    """None if SendGrid isn't configured (no SENDGRID_API_KEY or no QM_ADMIN_EMAIL) -- the caller
    should treat that as "notifications are off", not an error. QM_ADMIN_EMAIL is the existing env
    var (already in .env.example) for the destination address; reused here rather than inventing
    a new one -- it names who receives the notification, independent of which provider sends it.

    2026-11-01 (diagnostic hardening): logs WHICH variable is missing (name only, never a value)
    whenever this returns None, so a silent no-op is distinguishable in Railway logs from "sending
    was actually attempted and failed" -- see email_qmail_diagnostic_audit.md."""
    api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    if not api_key:
        print("[email_core] EMAIL_CONFIG_MISSING var=SENDGRID_API_KEY")
        return None
    to_addr = os.environ.get("QM_ADMIN_EMAIL", "").strip()
    if not to_addr:
        print("[email_core] EMAIL_CONFIG_MISSING var=QM_ADMIN_EMAIL")
        return None
    return {
        "api_key": api_key,
        "from_addr": os.environ.get("SENDGRID_FROM_EMAIL", "founder@qumanity.in").strip(),
        "to_addr": to_addr,
    }


def _mask_addr(addr: str) -> str:
    """'someone@example.com' -> 's***@example.com' -- enough to spot an obviously wrong recipient
    in a log line without printing a real address."""
    addr = addr or ""
    at = addr.find("@")
    if at <= 0:
        return "***"
    return addr[0] + "***" + addr[at:]


def _log_sendgrid_http_error(operation: str, e: "urllib.error.HTTPError") -> None:
    """Makes SendGrid's own JSON error body (e.g. {"errors":[{"message":"The provided
    authorization grant is invalid"}]}) visible in Railway logs -- the single most useful
    diagnostic fact (WHY SendGrid rejected the request) must not be discarded. Body is capped and
    never includes the Authorization header or API key."""
    try:
        raw = e.read().decode("utf-8", "replace")
    except Exception:
        raw = ""
    raw = raw[:2000]
    try:
        body = json.loads(raw)
        print(f"[email_core] EMAIL_SEND_HTTP_ERROR operation={operation} status={e.code} response={json.dumps(body)}")
    except json.JSONDecodeError:
        print(f"[email_core] EMAIL_SEND_HTTP_ERROR operation={operation} status={e.code} response_text={raw!r}")


def _send(to_addr: str, subject: str, html_body: str, operation: str = "unspecified") -> None:
    """The actual SendGrid HTTP call, shared by send_registration_notification() (to_addr always
    QM_ADMIN_EMAIL) and send_ticket_reply() (to_addr is whatever a visitor typed as their
    guest_contact). Raises on a genuine send failure -- every caller is responsible for deciding
    whether that should break its own request or just get logged, same as
    send_registration_notification() already documents for itself.

    2026-11-11: switched to SendGrid's HTTPS API (see module docstring for why). `operation` is
    still threaded through every log line so Railway logs can tell which call site failed. Return
    contract and exception behavior are UNCHANGED from the earlier transports -- it still raises
    exactly when it used to, after logging, so every existing caller's try/except keeps working as
    before."""
    api_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    from_addr = os.environ.get("SENDGRID_FROM_EMAIL", "founder@qumanity.in").strip()
    payload = json.dumps({
        "personalizations": [{"to": [{"email": to_addr}]}],
        "from": {"email": from_addr},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }).encode("utf-8")
    req = urllib.request.Request(
        SENDGRID_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    print(f"[email_core] EMAIL_SEND_ATTEMPT operation={operation} to={_mask_addr(to_addr)}")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            print(f"[email_core] EMAIL_SEND_SUCCESS operation={operation} status={resp.status} message_id={resp.headers.get('X-Message-Id')}")
    except urllib.error.HTTPError as e:
        _log_sendgrid_http_error(operation, e)
        raise
    except urllib.error.URLError as e:
        print(f"[email_core] EMAIL_SEND_NETWORK_ERROR operation={operation} error={e.reason!r}")
        raise
    except Exception as e:
        print(f"[email_core] EMAIL_SEND_UNEXPECTED_ERROR operation={operation} error_class={type(e).__name__} error={e}")
        raise


def is_email_like(value: str) -> bool:
    """A deliberately loose check -- just enough to decide whether a guest_contact string is
    "shaped like an email" (so a reply attempts to send one) versus a Private ID or anything else
    (so it doesn't try and silently fail against SendGrid instead). Never used to validate input at
    submission time -- admin_queries_core.create() stores guest_contact exactly as typed,
    unvalidated, same as every other free-text field in that table."""
    value = (value or "").strip()
    return "@" in value and "." in value.split("@")[-1] and " " not in value


def send_ticket_reply(to_addr: str, ticket_id: int, subject: str, reply_message: str) -> bool:
    """Sends an AI Support ticket's guest_contact the Admin's reply. Returns False (does nothing)
    if SendGrid isn't configured (SENDGRID_API_KEY unset) OR to_addr isn't email-shaped (a Private ID
    or blank guest_contact has nowhere to send to -- the visitor only ever sees that reply if they
    come back to the ticket lookup, which is the real "channel" for those, not email). Raises on a
    genuine send failure, same contract as send_registration_notification()."""
    if not os.environ.get("SENDGRID_API_KEY", "").strip():
        print("[email_core] EMAIL_SEND_SKIPPED operation=ticket_reply reason=SENDGRID_API_KEY_missing")
        return False
    if not is_email_like(to_addr):
        print(f"[email_core] EMAIL_SEND_SKIPPED operation=ticket_reply reason=guest_contact_not_email_shaped ticket_id={ticket_id}")
        return False
    safe_subject = html.escape(subject or "Your Qumanity Support ticket")
    safe_message = html.escape(reply_message or "")
    html_body = (
        f"<p>There's a reply to your Qumanity Support ticket <b>#{ticket_id}</b>:</p>"
        f"<blockquote>{safe_message}</blockquote>"
        "<p>This is a one-way notification — replying to this email won't reach us.</p>"
    )
    _send(to_addr, f"Qumanity Support — reply to ticket #{ticket_id}", html_body, operation="ticket_reply")
    return True


def mask_private_id(private_id_9digit: str) -> str:
    """'583294017' -> '•••4017'. Never shown with more than the last 4 digits -- this is a
    notification that someone registered, not a way to retrieve their real ID by email."""
    digits = (private_id_9digit or "").strip()
    if len(digits) < 4:
        return "•••" + digits
    return "•••" + digits[-4:]


def send_registration_notification(name: str, location_chain: str, private_id_9digit: str) -> bool:
    """Sends the Admin a notification that `name` registered, with their present-location chain
    (e.g. "Rohini Sector 24, Bawana, Delhi") and a masked Private ID -- never the real one. Returns
    False (does nothing) if SendGrid isn't configured. Raises on a genuine send failure; app.py's
    registration route catches that so a mail outage can never break registration itself."""
    config = _email_config()
    if config is None:
        return False

    masked = mask_private_id(private_id_9digit)
    safe_name = html.escape(name or "")
    safe_location = html.escape(location_chain or "(not given)")
    html_body = (
        "<p>A new member registered on Qumanity.</p>"
        f"<p><b>Name:</b> {safe_name}<br>"
        f"<b>Location:</b> {safe_location}<br>"
        f"<b>Private ID:</b> {masked} (masked — the full ID is never emailed)</p>"
        "<p>To look up their full details, sign in as Administrator and use the member export tool:<br>"
        f'<a href="{LOGIN_URL}">{LOGIN_URL}</a></p>'
    )
    # 2026-11-01: routed through the shared _send() (same Resend call this function always made --
    # from_addr/api_key/endpoint/headers unchanged) instead of its own duplicate urlopen block, so
    # this call site gets the same HTTP-error/network-error/success diagnostic logging as
    # send_ticket_reply() rather than a second, undiagnosed copy of the same request.
    _send(config["to_addr"], f"Qumanity: new member registered — {name}", html_body, operation="registration")
    return True
