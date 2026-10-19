"""Admin email notifications (2026-10-18, Resend API since 2026-10-20). The only email this
module sends today: a notification to the Admin when a new member registers. It is deliberately
notification-only -- it never puts a real, usable Private ID in an email body. The codebase's own
existing design already treats a Private ID reveal as something rare, individually justified and
logged (recovery_core.reveal_private_code, "the one place the system will show someone ELSE's
9-digit Private ID... every reveal is logged"); mailing every new member's real ID into an inbox
outside this project's control would be the opposite of that. The email shows a masked ID and
links the Admin to the authenticated admin export tool (api_admin_users_export in app.py), where
the real lookup happens and is itself logged (migrations/019_admin_export_log.py).

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
