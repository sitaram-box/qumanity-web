"""Verifies email_core.py's diagnostic logging (2026-11-01, see docs/production/
email_qmail_diagnostic_audit.md): every scenario in the audit's test table -- missing config,
HTTP success, 401/403/400/429/5xx, a network failure, and an unexpected exception -- produces the
right print() line AND preserves the function's original return/raise contract (nothing here
changed caller-facing behavior, only what gets logged on the way). Also confirms Resend's actual
JSON error body reaches the log (the one thing the old `except Exception as e: print(... {e} ...)`
could never show), and that a recipient address is only ever logged masked.

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
    """Stands in for the context-manager urlopen() returns on success."""
    def __init__(self, status: int, body: dict):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(status: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url=email_core.RESEND_URL, code=status, msg="error",
        hdrs=None, fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


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
print("Section 2: success -- EMAIL_SEND_ATTEMPT + EMAIL_SEND_SUCCESS, masked recipient")
print("=" * 70)

set_env()
with patch("email_core.urllib.request.urlopen", return_value=FakeResponse(200, {"id": "re_abc123"})):
    result, exc, lines = run_capturing_stdout(
        email_core.send_registration_notification, "Test User", "Rohini Sector 24", "123456789"
    )
check("configured + HTTP 200: send_registration_notification returns True", result is True and exc is None)
check("logs EMAIL_SEND_ATTEMPT operation=registration", any("EMAIL_SEND_ATTEMPT operation=registration" in l for l in lines))
check("logs EMAIL_SEND_SUCCESS with the Resend id", any("EMAIL_SEND_SUCCESS operation=registration status=200 resend_id=re_abc123" in l for l in lines))
check("the admin's real recipient address is never printed in full", not any("admin@example.com" in l for l in lines))
check("the recipient is logged masked instead", any("a***@example.com" in l for l in lines))

print()
print("=" * 70)
print("Section 3: Resend HTTP error responses -- exact JSON body reaches the log")
print("=" * 70)

HTTP_SCENARIOS = [
    (401, {"statusCode": 401, "message": "API key is invalid", "name": "validation_error"}),
    (403, {"statusCode": 403, "message": "Domain is not verified", "name": "validation_error"}),
    (400, {"statusCode": 400, "message": "Missing `from` field", "name": "validation_error"}),
    (429, {"statusCode": 429, "message": "Too many requests", "name": "rate_limit_exceeded"}),
    (500, {"statusCode": 500, "message": "Internal server error", "name": "application_error"}),
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
    for key, val in body.items():
        check(f"HTTP {status}: logged response body includes {key!r}: {val!r}", f'"{key}": {json.dumps(val)}' in log_line.replace(" ", "") or f'"{key}":{json.dumps(val).replace(" ", "")}' in log_line.replace(" ", ""))

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
with patch("email_core.urllib.request.urlopen", return_value=FakeResponse(200, {"id": "re_ticket1"})):
    result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply with valid config + email-shaped contact returns True", result is True and exc is None)
check("logs EMAIL_SEND_SUCCESS operation=ticket_reply", any("EMAIL_SEND_SUCCESS operation=ticket_reply" in l for l in lines))

set_env()
with patch("email_core.urllib.request.urlopen", side_effect=http_error(401, {"statusCode": 401, "message": "API key is invalid"})):
    result, exc, lines = run_capturing_stdout(email_core.send_ticket_reply, "visitor@example.com", 42, "Hi", "reply body")
check("send_ticket_reply HTTP 401 re-raised, not swallowed into a False return", isinstance(exc, urllib.error.HTTPError))
check("send_ticket_reply HTTP 401 logs the Resend body with operation=ticket_reply", any("EMAIL_SEND_HTTP_ERROR operation=ticket_reply status=401" in l for l in lines))

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
