"""Verifies email_core.py's diagnostic logging (2026-11-01, see docs/production/
email_qmail_diagnostic_audit.md; updated 2026-11-11 when the send path moved to SendGrid's HTTPS
API -- see email_core.py's module docstring for the full history of why Resend's HTTPS API and
then its SMTP relay were both abandoned): every scenario in the audit's test table -- missing
config, HTTP success, several HTTP error responses, a network failure, and an unexpected
exception -- produces the right print() line AND preserves the function's original return/raise
contract (nothing here changed caller-facing behavior, only what gets logged on the way, and now
which provider actually transports the email). Also confirms SendGrid's own JSON error body
reaches the log, and that a recipient address is only ever logged masked.

Mocks urllib.request.urlopen -- this never makes a real HTTP request and never sends a real email.

Standalone script, no test framework (none installed in this project): PASS/FAIL printing,
exit 1 on failure, matching tests/test_qmail.py's own conventions.

Run with: python3 tests/test_email_core.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
from unittest.mock import patch

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


class FakeResponse:
    """Stands in for the context-manager urlopen() returns on success. SendGrid's v3/mail/send
    returns 202 Accepted with an empty body and an X-Message-Id response header -- no JSON id in
    the body, unlike the old Resend HTTPS API."""
    def __init__(self, status: int, message_id: str = "sg_abc123"):
        self.status = status
        self.headers = {"X-Message-Id": message_id}

    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(status: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=email_core.SENDGRID_URL, code=status, msg="error",
        hdrs=None, fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


def set_env(api_key="sg_test_key", from_email="founder@qumanity.in", admin_email="admin@example.com"):
    for k, v in [("SENDGRID_API_KEY", api_key), ("SENDGRID_FROM_EMAIL", from_email), ("QM_ADMIN_EMAIL", admin_email)]:
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
check("SENDGRID_API_KEY missing: send_registration_notification returns False (not an error)", result is False and exc is None)
check("SENDGRID_API_KEY missing: logs EMAIL_CONFIG_MISSING var=SENDGRID_API_KEY", any("EMAIL_CONFIG_MISSING var=SENDGRID_API_KEY" in l for l in lines))

set_env(api_key="sg_test_key", admin_email=None)
result, exc, lines = run_capturing_stdout(
    email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
)
check("QM_ADMIN_EMAIL missing: send_registration_notification returns False", result is False and exc is None)
check("QM_ADMIN_EMAIL missing: logs EMAIL_CONFIG_MISSING var=QM_ADMIN_EMAIL", any("EMAIL_CONFIG_MISSING var=QM_ADMIN_EMAIL" in l for l in lines))

set_env(api_key=None)
result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply with no SENDGRID_API_KEY returns False", result is False and exc is None)
check("send_ticket_reply logs EMAIL_SEND_SKIPPED reason=SENDGRID_API_KEY_missing", any("EMAIL_SEND_SKIPPED operation=ticket_reply reason=SENDGRID_API_KEY_missing" in l for l in lines))

set_env()
result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "576013349", 42, "Hi", "reply body")
check("send_ticket_reply with a non-email guest_contact (a Private ID) returns False", result is False and exc is None)
check("send_ticket_reply logs EMAIL_SEND_SKIPPED reason=guest_contact_not_email_shaped", any("guest_contact_not_email_shaped" in l for l in lines))

print()
print("=" * 70)
print("Section 2: success -- EMAIL_SEND_ATTEMPT + EMAIL_SEND_SUCCESS, masked recipient, real request shape")
print("=" * 70)

set_env()
with patch("email_core.urllib.request.urlopen", return_value=FakeResponse(202, "sg_abc123")) as urlopen_mock:
    result, exc, lines = run_capturing_stdout(
        email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
    )
check("configured + HTTP 202: send_registration_notification returns True", result is True and exc is None)
check("logs EMAIL_SEND_ATTEMPT operation=registration", any("EMAIL_SEND_ATTEMPT operation=registration" in l for l in lines))
check("logs EMAIL_SEND_SUCCESS with status and message id", any("EMAIL_SEND_SUCCESS operation=registration status=202 message_id=sg_abc123" in l for l in lines))
check("the admin's real recipient address is never printed in full", not any("admin@example.com" in l for l in lines))
check("the recipient is logged masked instead", any("a***@example.com" in l for l in lines))
sent_req = urlopen_mock.call_args[0][0]
check("posts to SendGrid's v3/mail/send endpoint", sent_req.full_url == email_core.SENDGRID_URL)
check("sends Authorization: Bearer <SENDGRID_API_KEY>", sent_req.headers.get("Authorization") == "Bearer sg_test_key")
sent_body = json.loads(sent_req.data.decode("utf-8"))
check("body.personalizations[0].to[0].email is the admin's address", sent_body["personalizations"][0]["to"][0]["email"] == "admin@example.com")
check("body.from.email comes from SENDGRID_FROM_EMAIL", sent_body["from"]["email"] == "founder@qumanity.in")
check("body.content[0].type is text/html", sent_body["content"][0]["type"] == "text/html")

print()
print("=" * 70)
print("Section 3: SendGrid HTTP error responses -- exact JSON body reaches the log")
print("=" * 70)

HTTP_SCENARIOS = [
    (401, {"errors": [{"message": "The provided authorization grant is invalid", "field": None, "help": None}]}),
    (403, {"errors": [{"message": "Sender identity not verified", "field": "from", "help": None}]}),
    (400, {"errors": [{"message": "Missing required field", "field": "personalizations", "help": None}]}),
    (429, {"errors": [{"message": "Too many requests", "field": None, "help": None}]}),
    (500, {"errors": [{"message": "Internal server error", "field": None, "help": None}]}),
]
for status, body in HTTP_SCENARIOS:
    set_env()
    with patch("email_core.urllib.request.urlopen", side_effect=http_error(status, body)):
        result, exc, lines = run_capturing_stdout(
            email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
        )
    check(f"HTTP {status}: the original HTTPError is re-raised (not swallowed)", isinstance(exc, urllib.error.HTTPError) and exc.code == status)
    log_line = next((l for l in lines if "EMAIL_SEND_HTTP_ERROR" in l), "")
    check(f"HTTP {status}: logs EMAIL_SEND_HTTP_ERROR with status={status}", f"status={status}" in log_line)
    check(f"HTTP {status}: logged response body includes the error message", body["errors"][0]["message"] in log_line)

print()
print("=" * 70)
print("Section 4: network and unexpected errors")
print("=" * 70)

set_env()
with patch("email_core.urllib.request.urlopen", side_effect=urllib.error.URLError("timed out")):
    result, exc, lines = run_capturing_stdout(
        email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
    )
check("network failure: URLError is re-raised", isinstance(exc, urllib.error.URLError))
check("network failure: logs EMAIL_SEND_NETWORK_ERROR", any("EMAIL_SEND_NETWORK_ERROR operation=registration" in l for l in lines))

set_env()
with patch("email_core.urllib.request.urlopen", side_effect=RuntimeError("something unrelated broke")):
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
with patch("email_core.urllib.request.urlopen", return_value=FakeResponse(202, "sg_ticket1")):
    result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply with valid config + email-shaped contact returns True", result is True and exc is None)
check("logs EMAIL_SEND_SUCCESS operation=ticket_reply", any("EMAIL_SEND_SUCCESS operation=ticket_reply" in l for l in lines))

set_env()
with patch("email_core.urllib.request.urlopen", side_effect=http_error(401, {"errors": [{"message": "The provided authorization grant is invalid", "field": None, "help": None}]})):
    result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply HTTP 401 re-raised, not swallowed into a False return", isinstance(exc, urllib.error.HTTPError))
check("send_ticket_reply HTTP 401 logs the SendGrid body with operation=ticket_reply", any("EMAIL_SEND_HTTP_ERROR operation=ticket_reply status=401" in l for l in lines))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
