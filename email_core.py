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

No new dependency: sent via Resend's HTTP API (https://api.resend.com/emails) using the standard
library's urllib.request, not smtplib -- Railway's outbound SMTP is unreliable/blocked on some
plans, Resend's API is plain HTTPS. If Resend isn't configured (no RESEND_API_KEY or no
QM_ADMIN_EMAIL), send_registration_notification() is a silent no-op -- registration must never
depend on email being set up. If it IS configured but the send fails (bad key, Resend outage,
timeout), this function raises normally; app.py's api_auth_register is responsible for catching
that and logging it without failing the registration request itself.
"""
from __future__ import annotations

import html
import json
import os
import urllib.error
import urllib.request

REQUEST_TIMEOUT_SECONDS = 10
RESEND_URL = "https://api.resend.com/emails"
LOGIN_URL = "https://qumanity.in/login"


def _resend_config() -> dict | None:
    """None if Resend isn't configured (no RESEND_API_KEY or no QM_ADMIN_EMAIL) -- the caller
    should treat that as "notifications are off", not an error. QM_ADMIN_EMAIL is the existing env
    var (already in .env.example) for the destination address; reused here rather than inventing
    a new one."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        return None
    to_addr = os.environ.get("QM_ADMIN_EMAIL", "").strip()
    if not to_addr:
        return None
    return {
        "api_key": api_key,
        "from_addr": os.environ.get("RESEND_FROM_EMAIL", "Qumanity <founder@qumanity.in>").strip(),
        "to_addr": to_addr,
    }


def _send(to_addr: str, subject: str, html_body: str) -> None:
    """The actual Resend HTTP call, shared by send_registration_notification() (to_addr always
    QM_ADMIN_EMAIL) and send_ticket_reply() (to_addr is whatever a visitor typed as their
    guest_contact). Raises on a genuine send failure -- every caller is responsible for deciding
    whether that should break its own request or just get logged, same as
    send_registration_notification() already documents for itself."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    from_addr = os.environ.get("RESEND_FROM_EMAIL", "Qumanity <founder@qumanity.in>").strip()
    payload = json.dumps({"from": from_addr, "to": [to_addr], "subject": subject, "html": html_body}).encode("utf-8")
    req = urllib.request.Request(
        RESEND_URL, data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        resp.read()


def is_email_like(value: str) -> bool:
    """A deliberately loose check -- just enough to decide whether a guest_contact string is
    "shaped like an email" (so a reply attempts to send one) versus a Private ID or anything else
    (so it doesn't try and silently fail against Resend instead). Never used to validate input at
    submission time -- admin_queries_core.create() stores guest_contact exactly as typed,
    unvalidated, same as every other free-text field in that table."""
    value = (value or "").strip()
    return "@" in value and "." in value.split("@")[-1] and " " not in value


def send_ticket_reply(to_addr: str, ticket_id: int, subject: str, reply_message: str) -> bool:
    """Sends an AI Support ticket's guest_contact the Admin's reply. Returns False (does nothing)
    if Resend isn't configured (RESEND_API_KEY unset) OR to_addr isn't email-shaped (a Private ID
    or blank guest_contact has nowhere to send to -- the visitor only ever sees that reply if they
    come back to the ticket lookup, which is the real "channel" for those, not email). Raises on a
    genuine send failure, same contract as send_registration_notification()."""
    if not os.environ.get("RESEND_API_KEY", "").strip() or not is_email_like(to_addr):
        return False
    safe_subject = html.escape(subject or "Your Qumanity Support ticket")
    safe_message = html.escape(reply_message or "")
    html_body = (
        f"<p>There's a reply to your Qumanity Support ticket <b>#{ticket_id}</b>:</p>"
        f"<blockquote>{safe_message}</blockquote>"
        "<p>This is a one-way notification — replying to this email won't reach us.</p>"
    )
    _send(to_addr, f"Qumanity Support — reply to ticket #{ticket_id}", html_body)
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
    False (does nothing) if Resend isn't configured. Raises on a genuine send failure; app.py's
    registration route catches that so a mail outage can never break registration itself."""
    config = _resend_config()
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
    payload = json.dumps({
        "from": config["from_addr"],
        "to": [config["to_addr"]],
        "subject": f"Qumanity: new member registered — {name}",
        "html": html_body,
    }).encode("utf-8")

    req = urllib.request.Request(
        RESEND_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        resp.read()
    return True
