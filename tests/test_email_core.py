"""Verifies email_core.py's diagnostic logging (2026-11-01, see docs/production/
email_qmail_diagnostic_audit.md; updated 2026-11-10 when the send path moved from Resend's HTTPS
API to its SMTP relay -- see email_core.py's module docstring for why): every scenario in the
audit's test table -- missing config, SMTP success, several SMTP error responses, a network
failure, and an unexpected exception -- produces the right print() line AND preserves the
function's original return/raise contract (nothing here changed caller-facing behavior, only what
gets logged on the way, and now how the email is actually transported). Also confirms Resend's own
SMTP rejection reason reaches the log, and that a recipient address is only ever logged masked.

Mocks smtplib.SMTP -- this never makes a real network connection and never sends a real email.

Standalone script, no test framework (none installed in this project): PASS/FAIL printing,
exit 1 on failure, matching tests/test_qmail.py's own conventions.

Run with: python3 tests/test_email_core.py
"""
from __future__ import annotations

import io
import os
import smtplib
import sys
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import email_core  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


def run_capturing_stdout(fn, *a, **kw):
    """Runs fn(*a, **kw), returns (result, exception_or_None, captured_stdout_lines)."""
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        result = fn(*a, **kw)
        exc = None
    except Exception as e:  # noqa: BLE001 -- intentionally broad, this is a test harness
        result = None
        exc = e
    finally:
        sys.stdout = old_stdout
    return result, exc, buf.getvalue().splitlines()


def make_smtp_mock(connect_error=None, login_error=None, send_error=None):
    """Stands in for smtplib.SMTP(host, port, timeout=...), used as `with smtplib.SMTP(...) as
    server:`. `connect_error` is raised by the SMTP(...) call itself (a connection-level failure,
    before any command is sent); `login_error`/`send_error` are raised by server.login()/
    server.send_message() respectively, same as a real smtplib would for an SMTP-level rejection."""
    smtp_mock = MagicMock(name="smtplib.SMTP")
    if connect_error is not None:
        smtp_mock.side_effect = connect_error
        return smtp_mock
    server = smtp_mock.return_value.__enter__.return_value
    server.starttls.return_value = None
    if login_error is not None:
        server.login.side_effect = login_error
    else:
        server.login.return_value = None
    if send_error is not None:
        server.send_message.side_effect = send_error
    else:
        server.send_message.return_value = {}
    return smtp_mock


def set_env(api_key="re_test_key", from_email="Qumanity <founder@qumanity.in>", admin_email="admin@example.com"):
    for k, v in [("RESEND_API_KEY", api_key), ("RESEND_FROM_EMAIL", from_email), ("QM_ADMIN_EMAIL", admin_email)]:
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


print("=" * 70)
print("Section 1: missing configuration -- EMAIL_CONFIG_MISSING / EMAIL_SEND_SKIPPED")
print("=" * 70)

set_env(api_key=None)
result, exc, lines = run_capturing_stdout(
    email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
)
check("RESEND_API_KEY missing: send_registration_notification returns False (not an error)", result is False and exc is None)
check("RESEND_API_KEY missing: logs EMAIL_CONFIG_MISSING var=RESEND_API_KEY", any("EMAIL_CONFIG_MISSING var=RESEND_API_KEY" in l for l in lines))

set_env(api_key="re_test_key", admin_email=None)
result, exc, lines = run_capturing_stdout(
    email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
)
check("QM_ADMIN_EMAIL missing: send_registration_notification returns False", result is False and exc is None)
check("QM_ADMIN_EMAIL missing: logs EMAIL_CONFIG_MISSING var=QM_ADMIN_EMAIL", any("EMAIL_CONFIG_MISSING var=QM_ADMIN_EMAIL" in l for l in lines))

set_env(api_key=None)
result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply with no RESEND_API_KEY returns False", result is False and exc is None)
check("send_ticket_reply logs EMAIL_SEND_SKIPPED reason=RESEND_API_KEY_missing", any("EMAIL_SEND_SKIPPED operation=ticket_reply reason=RESEND_API_KEY_missing" in l for l in lines))

set_env()
result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "576013349", 42, "Hi", "reply body")
check("send_ticket_reply with a non-email guest_contact (a Private ID) returns False", result is False and exc is None)
check("send_ticket_reply logs EMAIL_SEND_SKIPPED reason=guest_contact_not_email_shaped", any("guest_contact_not_email_shaped" in l for l in lines))

print()
print("=" * 70)
print("Section 2: success -- EMAIL_SEND_ATTEMPT + EMAIL_SEND_SUCCESS, masked recipient, real SMTP shape")
print("=" * 70)

set_env()
smtp_mock = make_smtp_mock()
with patch("email_core.smtplib.SMTP", smtp_mock):
    result, exc, lines = run_capturing_stdout(
        email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
    )
check("configured + SMTP success: send_registration_notification returns True", result is True and exc is None)
check("logs EMAIL_SEND_ATTEMPT operation=registration", any("EMAIL_SEND_ATTEMPT operation=registration" in l for l in lines))
check("logs EMAIL_SEND_SUCCESS operation=registration", any("EMAIL_SEND_SUCCESS operation=registration" in l for l in lines))
check("the admin's real recipient address is never printed in full", not any("admin@example.com" in l for l in lines))
check("the recipient is logged masked instead", any("a***@example.com" in l for l in lines))
check("connects to smtp.resend.com:587", smtp_mock.call_args[0][:2] == (email_core.SMTP_HOST, email_core.SMTP_PORT))
server = smtp_mock.return_value.__enter__.return_value
check("calls starttls() before authenticating", server.starttls.called)
check("logs in with username 'resend' and RESEND_API_KEY as the password", server.login.call_args[0] == (email_core.SMTP_USERNAME, "re_test_key"))
check("sends the message via send_message()", server.send_message.called)
sent_msg = server.send_message.call_args[0][0]
check("the From header comes from RESEND_FROM_EMAIL", sent_msg["From"] == "Qumanity <founder@qumanity.in>")
check("the To header is the admin's address", sent_msg["To"] == "admin@example.com")

print()
print("=" * 70)
print("Section 3: Resend SMTP error responses -- the exact rejection reason reaches the log")
print("=" * 70)

SMTP_SCENARIOS = [
    (535, b"Invalid API Key"),
    (550, b"Domain is not verified"),
    (501, b"Missing 'from' field"),
    (421, b"Too many requests"),
    (451, b"Internal server error"),
]
for code, err in SMTP_SCENARIOS:
    set_env()
    smtp_mock = make_smtp_mock(login_error=smtplib.SMTPResponseException(code, err))
    with patch("email_core.smtplib.SMTP", smtp_mock):
        result, exc, lines = run_capturing_stdout(
            email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
        )
    check(f"SMTP {code}: the original SMTPResponseException is re-raised (not swallowed)", isinstance(exc, smtplib.SMTPResponseException) and exc.smtp_code == code)
    log_line = next((l for l in lines if "EMAIL_SEND_SMTP_ERROR" in l), "")
    check(f"SMTP {code}: logs EMAIL_SEND_SMTP_ERROR with status={code}", f"status={code}" in log_line)
    check(f"SMTP {code}: logged response includes the rejection reason {err!r}", repr(err.decode())[1:-1] in log_line or err.decode() in log_line)

print()
print("=" * 70)
print("Section 4: network and unexpected errors")
print("=" * 70)

set_env()
smtp_mock = make_smtp_mock(connect_error=OSError("Connection refused"))
with patch("email_core.smtplib.SMTP", smtp_mock):
    result, exc, lines = run_capturing_stdout(
        email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
    )
check("connection failure: OSError is re-raised", isinstance(exc, OSError))
check("connection failure: logs EMAIL_SEND_NETWORK_ERROR", any("EMAIL_SEND_NETWORK_ERROR operation=registration" in l for l in lines))

set_env()
smtp_mock = make_smtp_mock(send_error=RuntimeError("something unrelated broke"))
with patch("email_core.smtplib.SMTP", smtp_mock):
    result, exc, lines = run_capturing_stdout(
        email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
    )
check("unexpected exception type: re-raised unchanged", isinstance(exc, RuntimeError))
check("unexpected exception: logs EMAIL_SEND_UNEXPECTED_ERROR with the exception class", any("EMAIL_SEND_UNEXPECTED_ERROR operation=registration error_class=RuntimeError" in l for l in lines))

print()
print("=" * 70)
print("Section 5: send_ticket_reply uses the same _send() path (operation=ticket_reply)")
print("=" * 70)

set_env()
smtp_mock = make_smtp_mock()
with patch("email_core.smtplib.SMTP", smtp_mock):
    result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply with valid config + email-shaped contact returns True", result is True and exc is None)
check("logs EMAIL_SEND_SUCCESS operation=ticket_reply", any("EMAIL_SEND_SUCCESS operation=ticket_reply" in l for l in lines))

set_env()
smtp_mock = make_smtp_mock(login_error=smtplib.SMTPResponseException(535, b"Invalid API Key"))
with patch("email_core.smtplib.SMTP", smtp_mock):
    result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply SMTP 535 re-raised, not swallowed into a False return", isinstance(exc, smtplib.SMTPResponseException))
check("send_ticket_reply SMTP 535 logs the rejection with operation=ticket_reply", any("EMAIL_SEND_SMTP_ERROR operation=ticket_reply status=535" in l for l in lines))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
