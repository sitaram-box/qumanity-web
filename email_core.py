"""Admin email notifications (2026-10-18). The only email this module sends today: a
notification to the Admin when a new member registers. It is deliberately notification-only --
it never puts a real, usable Private ID in an email body. The codebase's own existing design
already treats a Private ID reveal as something rare, individually justified and logged
(recovery_core.reveal_private_code, "the one place the system will show someone ELSE's 9-digit
Private ID... every reveal is logged"); mailing every new member's real ID into an inbox outside
this project's control would be the opposite of that. The email shows a masked ID and links the
Admin to the authenticated admin export tool (api_admin_users_export in app.py), where the real
lookup happens and is itself logged (migrations/019_admin_export_log.py).

No new dependency: sent with the standard library's smtplib + email.message.EmailMessage. If
SMTP isn't configured (no SMTP_HOST), send_registration_notification() is a silent no-op --
registration must never depend on email being set up. If SMTP is configured but the send fails
(server down, auth failure, timeout), the caller (app.py's api_auth_register) is responsible for
catching that and logging it without failing the registration request; this module raises
normally so the caller's try/except can see exactly what went wrong.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

SMTP_TIMEOUT_SECONDS = 10
LOGIN_URL = "https://qumanity.in/login"


def _smtp_config() -> dict | None:
    """None if SMTP isn't configured (no SMTP_HOST) -- the caller should treat that as
    "notifications are off", not an error. QM_ADMIN_EMAIL is the existing env var (already in
    .env.example) for the destination address; it's reused here rather than inventing a new one."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None
    to_addr = os.environ.get("QM_ADMIN_EMAIL", "").strip()
    if not to_addr:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "587") or "587"),
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_addr": os.environ.get("SMTP_FROM_ADDR", "").strip() or os.environ.get("SMTP_USER", "").strip(),
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
    False (does nothing) if SMTP isn't configured. Raises on a genuine send failure; app.py's
    registration route catches that so a mail outage can never break registration itself."""
    config = _smtp_config()
    if config is None:
        return False

    masked = mask_private_id(private_id_9digit)
    msg = EmailMessage()
    msg["Subject"] = f"Qumanity: new member registered — {name}"
    msg["From"] = config["from_addr"]
    msg["To"] = config["to_addr"]
    msg.set_content(
        f"A new member registered on Qumanity.\n\n"
        f"Name: {name}\n"
        f"Location: {location_chain or '(not given)'}\n"
        f"Private ID: {masked} (masked — the full ID is never emailed)\n\n"
        f"To look up their full details, sign in as Administrator and use the member export tool:\n"
        f"{LOGIN_URL}\n"
    )

    with smtplib.SMTP(config["host"], config["port"], timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.starttls()
        if config["user"]:
            server.login(config["user"], config["password"])
        server.send_message(msg)
    return True
